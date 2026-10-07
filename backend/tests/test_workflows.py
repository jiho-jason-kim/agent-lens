"""Verify callback nesting, real tool failures, privacy boundaries, and saved replay."""
import asyncio
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
pytest.importorskip('langchain_core')
from langchain_core.callbacks.manager import dispatch_custom_event
from langchain_core.documents import Document
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.runnables import RunnableLambda, RunnableParallel
from app.integrations.langchain_recorder import AgentLensRecorder
from app.main import create_app
from app.models.workflow import WorkflowRecording
from app.storage.json_store import RunStore
from app.storage.workflow_store import WorkflowStore
from app.workflows.reservation import run_reservation


def test_demo_failure_and_state_change(tmp_path):
    store = WorkflowStore(tmp_path)
    run = run_reservation(store=store)
    assert run.metadata.status == 'recovered'
    errors = [e for e in run.events if e.phase == 'error']
    assert len(errors) == 1 and errors[0].payload['error_type'] == 'StockUnavailable'
    before = next(e.payload['state'] for e in run.events if e.name == 'inventory_before')
    after = next(e.payload['state'] for e in run.events if e.name == 'inventory_after')
    assert before['camera'] == after['camera'] == 0
    assert before['camera-alternative'] == 2 and after['camera-alternative'] == 1
    assert any(e.category == 'model' and e.phase == 'end' for e in run.events)
    assert store.load(run.metadata.run_id).model_dump(mode='json') == run.model_dump(mode='json')
    with pytest.raises(FileExistsError):
        store.save(run)


def test_async_parallel_nesting(tmp_path):
    async def add(value):
        await asyncio.sleep(0)
        return value + 1
    chain = RunnableParallel(left=RunnableLambda(add), right=RunnableLambda(add))
    recorder = AgentLensRecorder()
    assert asyncio.run(chain.ainvoke(4, config={'callbacks': [recorder]})) == {'left': 5, 'right': 5}
    run = recorder.save(WorkflowStore(tmp_path))
    assert run.metadata.status == 'completed'
    starts = [e for e in run.events if e.phase == 'start']
    assert len(starts) == len({e.span_id for e in starts}) == 3
    root = next(e for e in starts if e.parent_span_id is None)
    assert all(e.parent_span_id == root.span_id for e in starts if e != root)


def test_custom_handoff():
    def handoff(value, config):
        dispatch_custom_event('handoff', {'sender': 'researcher', 'recipient': 'reviewer', 'content': value}, config=config)
        return value
    recorder = AgentLensRecorder()
    RunnableLambda(handoff).invoke('Check this report', config={'callbacks': [recorder]})
    event = next(e for e in recorder.recording().events if e.phase == 'custom')
    assert event.payload['recipient'] == 'reviewer'
    assert event.span_id == recorder.recording().events[0].span_id


def test_secrets_and_reasoning_are_excluded(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-private-key')
    recorder = AgentLensRecorder(redact_values=('private-document-id',))
    span = uuid4()
    recorder.on_chat_model_start({'api_key': 'serialized-secret'}, [[AIMessage(content='test-private-key private-document-id')]], run_id=span)
    message = AIMessage(content=[{'type': 'reasoning', 'text': 'hidden reasoning'}, {'type': 'text', 'text': 'visible answer'}], additional_kwargs={'secret': 'sdk-secret'})
    recorder.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]), run_id=span)
    text = recorder.recording().model_dump_json()
    assert all(secret not in text for secret in ['test-private-key', 'private-document-id', 'serialized-secret', 'sdk-secret', 'hidden reasoning'])
    assert 'visible answer' in text
    recorder = AgentLensRecorder()
    recorder.on_chain_start({}, {'api_key': 'never-record-me'}, run_id=span)
    recorder.on_chain_error(ValueError('sensitive-provider-response'), run_id=span)
    text = recorder.recording().model_dump_json()
    assert 'never-record-me' not in text and 'sensitive-provider-response' not in text
    assert recorder.recording().metadata.status == 'error'


def test_retrieval_truncation():
    recorder = AgentLensRecorder()
    span = uuid4()
    recorder.on_retriever_start({'name': 'search'}, 'query', run_id=span)
    recorder.on_retriever_end([Document(page_content='x' * 13000, metadata={'authorization': 'secret'})], run_id=span)
    output = recorder.recording().events[-1].payload['output'][0]
    assert '[TRUNCATED' in output['page_content']
    assert output['metadata']['authorization'] == '[REDACTED]'


def test_incomplete_and_invalid_parent(tmp_path):
    recorder = AgentLensRecorder()
    recorder.on_chain_start({}, {'request': 'unfinished'}, run_id=uuid4())
    run = recorder.save(WorkflowStore(tmp_path))
    assert run.metadata.status == 'incomplete'
    broken = run.model_dump(mode='json')
    broken['events'][0]['parent_span_id'] = 'unknown'
    with pytest.raises(ValidationError):
        WorkflowRecording.model_validate(broken)


def test_api_replay_never_executes(tmp_path, monkeypatch):
    client = TestClient(create_app(RunStore(tmp_path / 'grid'), WorkflowStore(tmp_path / 'workflows')))
    response = client.post('/workflows/demo', json={'mode': 'demo'})
    assert response.status_code == 201
    recording = response.json()
    run_id = recording['metadata']['run_id']
    def cannot_run(*args, **kwargs):
        raise AssertionError('Replay attempted execution')
    monkeypatch.setattr('app.workflows.reservation.run_reservation', cannot_run)
    assert client.get(f'/workflows/{run_id}').json() == recording
    assert client.get('/workflows').json()[0]['run_id'] == run_id
    assert client.get('/runs').json() == []
    assert client.get('/workflows/workflow-missing').status_code == 404
    assert client.get('/workflows/invalid').status_code == 422
