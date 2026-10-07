"""Record observable LangChain callbacks with explicit invocation relationships."""
import re
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from app.config import provider_settings
from app.models.workflow import WorkflowEvent, WorkflowMetadata, WorkflowRecording
from app.storage.workflow_store import WorkflowStore


class AgentLensRecorder(BaseCallbackHandler):
    raise_error = True
    run_inline = True

    def __init__(self, name='LangChain workflow', *, mode='external', redact_values=()):
        self.run_id = f'workflow-{uuid4().hex}'
        self.name, self.mode = name, mode
        self.created_at = datetime.now(timezone.utc)
        self._events, self._starts, self._closed = [], {}, set()
        self._lock = RLock()
        self._saved = False
        key = provider_settings()['OPENAI_API_KEY']
        self._secrets = tuple(value for value in (key, *redact_values) if value)

    def _text(self, text):
        for secret in self._secrets:
            text = text.replace(secret, '[REDACTED]')
        text = re.sub(r'\bsk-[A-Za-z0-9_-]{10,}', '[REDACTED]', text)
        text = re.sub(r'(?i)Bearer\s+\S+', 'Bearer [REDACTED]', text)
        return text if len(text) <= 12000 else text[:12000] + '\n[TRUNCATED: text limit]'

    def _value(self, value, depth=0):
        # Unknown objects are not stringified: repr() can expose credentials or SDK internals.
        if depth > 8:
            return '[TRUNCATED: nesting limit]'
        if isinstance(value, BaseMessage):
            content = value.content
            if isinstance(content, list):
                content = [block for block in content if isinstance(block, str) or
                           isinstance(block, dict) and block.get('type') in ('text', 'output_text')]
            return self._value({'role': value.type, 'content': content,
                'tool_calls': getattr(value, 'tool_calls', []),
                'tool_call_id': getattr(value, 'tool_call_id', None)}, depth + 1)
        if isinstance(value, Document):
            return self._value({'page_content': value.page_content, 'metadata': value.metadata}, depth + 1)
        if value is None or isinstance(value, (bool, int)):
            return value
        if isinstance(value, float):
            return value if value == value and abs(value) != float('inf') else '[non-finite number]'
        if isinstance(value, str):
            return self._text(value)
        if isinstance(value, dict):
            result = {}
            for key, item in list(value.items())[:100]:
                key = str(key)
                sensitive = re.search(r'(?i)(api.?key|authorization|password|secret|access.?token|refresh.?token)', key)
                result[self._text(key)] = '[REDACTED]' if sensitive else self._value(item, depth + 1)
            if len(value) > 100:
                result['__truncated__'] = 'Object entry limit'
            return result
        if isinstance(value, (tuple, list)):
            result = [self._value(item, depth + 1) for item in value[:100]]
            return result + ['[TRUNCATED: item limit]'] if len(value) > 100 else result
        return f'[Unsupported value: {type(value).__name__}]'

    def _append(self, span_id, parent, category, phase, name, payload):
        if self._saved:
            raise RuntimeError('This recorder is already saved. Create a recorder per workflow execution.')
        sequence = len(self._events) + 1
        event = WorkflowEvent(event_id=f'w-{sequence:04d}', sequence=sequence,
            timestamp=datetime.now(timezone.utc), span_id=str(span_id), parent_span_id=str(parent) if parent else None,
            category=category, phase=phase, name=self._text(name), payload=self._value(payload))
        self._events.append(event)
        return event

    def _start(self, category, serialized, inputs, run_id, parent_run_id=None, **kwargs):
        with self._lock:
            name = kwargs.get('name') or (serialized or {}).get('name') or category
            event = self._append(run_id, parent_run_id, category, 'start', name, {'input': inputs})
            self._starts[str(run_id)] = event

    def _finish(self, run_id, output=None, error=None):
        with self._lock:
            start = self._starts[str(run_id)]
            # Exception messages can include request bodies. Record only their class.
            payload = {'error_type': type(error).__name__, 'message': 'Operation failed. Inspect the recorded input and recovery steps.'} if error else {'output': output}
            self._append(run_id, start.parent_span_id, start.category, 'error' if error else 'end', start.name, payload)
            self._closed.add(str(run_id))

    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, **kwargs):
        self._start('chain', serialized, inputs, run_id, parent_run_id, **kwargs)

    def on_chat_model_start(self, serialized, messages, *, run_id, parent_run_id=None, **kwargs):
        self._start('model', serialized, messages, run_id, parent_run_id, **kwargs)

    def on_llm_start(self, serialized, prompts, *, run_id, parent_run_id=None, **kwargs):
        self._start('model', serialized, prompts, run_id, parent_run_id, **kwargs)

    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, inputs=None, **kwargs):
        self._start('tool', serialized, inputs if inputs is not None else input_str, run_id, parent_run_id, **kwargs)

    def on_retriever_start(self, serialized, query, *, run_id, parent_run_id=None, **kwargs):
        self._start('retriever', serialized, query, run_id, parent_run_id, **kwargs)

    def on_chain_end(self, outputs, *, run_id, **kwargs):
        self._finish(run_id, outputs)

    def on_llm_end(self, response, *, run_id, **kwargs):
        self._finish(run_id, [[getattr(generation, 'message', generation.text) for generation in group]
                              for group in response.generations])

    def on_tool_end(self, output, *, run_id, **kwargs):
        self._finish(run_id, output)

    def on_retriever_end(self, documents, *, run_id, **kwargs):
        self._finish(run_id, documents)

    def on_chain_error(self, error, *, run_id, **kwargs):
        self._finish(run_id, error=error)

    on_llm_error = on_chain_error
    on_tool_error = on_chain_error
    on_retriever_error = on_chain_error

    def on_custom_event(self, name, data, *, run_id, **kwargs):
        with self._lock:
            start = self._starts[str(run_id)]
            self._append(run_id, start.parent_span_id, 'custom', 'custom', name, data)

    def recording(self):
        with self._lock:
            status = ('incomplete' if not self._starts or len(self._starts) != len(self._closed) else
                      'error' if any(e.phase == 'error' and e.parent_span_id is None for e in self._events) else
                      'recovered' if any(e.phase == 'error' for e in self._events) else 'completed')
            return WorkflowRecording(metadata=WorkflowMetadata(run_id=self.run_id, name=self._text(self.name),
                created_at=self.created_at, mode=self.mode, status=status, event_count=len(self._events),
                span_count=len(self._starts)), events=tuple(self._events))

    def save(self, store=None):
        with self._lock:
            recording = self.recording()
            (store or WorkflowStore()).save(recording)
            self._saved = True
            return recording
