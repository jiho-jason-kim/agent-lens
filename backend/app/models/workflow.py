"""Framework-neutral workflow events, separate from grid turns and snapshots."""
from datetime import datetime
from typing import Literal
from pydantic import Field, JsonValue, model_validator
from app.models.recording import Model


class WorkflowEvent(Model):
    event_id: str
    sequence: int = Field(ge=1)
    timestamp: datetime
    span_id: str
    parent_span_id: str | None = None
    category: Literal['chain', 'model', 'tool', 'retriever', 'custom']
    phase: Literal['start', 'end', 'error', 'custom']
    name: str
    payload: JsonValue


class WorkflowMetadata(Model):
    schema_version: Literal[1] = 1
    recording_type: Literal['workflow'] = 'workflow'
    run_id: str = Field(pattern=r'^workflow-[a-zA-Z0-9-]+$')
    name: str
    created_at: datetime
    source: Literal['langchain'] = 'langchain'
    mode: Literal['demo', 'live', 'external'] = 'external'
    status: Literal['completed', 'recovered', 'error', 'incomplete']
    event_count: int = Field(ge=0)
    span_count: int = Field(ge=0)


class WorkflowRecording(Model):
    metadata: WorkflowMetadata
    events: tuple[WorkflowEvent, ...]

    @model_validator(mode='after')
    def validate_lifecycle(self):
        starts, closed, ids = {}, set(), set()
        for index, event in enumerate(self.events, 1):
            if event.sequence != index or event.event_id in ids:
                raise ValueError('Invalid workflow event sequence or duplicate ID.')
            ids.add(event.event_id)
            if event.phase == 'start':
                if event.span_id in starts or event.category == 'custom':
                    raise ValueError('Duplicate or invalid span start.')
                if event.parent_span_id is not None and event.parent_span_id not in starts:
                    raise ValueError('Parent span must already exist.')
                starts[event.span_id] = event
            else:
                start = starts.get(event.span_id)
                if not start or event.span_id in closed or event.parent_span_id != start.parent_span_id:
                    raise ValueError('Event must belong to an open span.')
                if event.phase == 'custom':
                    if event.category != 'custom':
                        raise ValueError('Custom event category must match its phase.')
                else:
                    if (event.category, event.name) != (start.category, start.name):
                        raise ValueError('Span result must match its start.')
                    closed.add(event.span_id)
        root_errors = any(e.phase == 'error' and e.parent_span_id is None for e in self.events)
        # A handled child error differs from a failed workflow. Open spans remain incomplete.
        status = ('incomplete' if not starts or len(closed) != len(starts) else
                  'error' if root_errors else 'recovered' if any(e.phase == 'error' for e in self.events) else 'completed')
        if self.metadata.status != status or self.metadata.event_count != len(self.events) or self.metadata.span_count != len(starts):
            raise ValueError('Workflow summary does not match its events.')
        return self
