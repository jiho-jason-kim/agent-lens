"""Check evidence coverage and comparison metrics before drawing experimental conclusions."""
import json
import httpx
import pytest
from pydantic import ValidationError
from app.agent.llm_agent import LLMAgent
from app.agent.openai_provider import OpenAIProvider
from app.evaluation.compare import compare
from app.evaluation.run import run_evaluation
from app.models.multi_recording import MultiRecordedRun
from app.scenarios.run import run_scenario
from app.simulation.runner import run_simulation
from app.storage.json_store import RunStore


def test_context_sources_cover_history_and_reject_missing_links(tmp_path):
    run = run_scenario('handoff-race', max_turns=7, store=RunStore(tmp_path))
    event = next(e for e in run.events if e.type == 'observation' and e.turn == 7)
    assert set(event.payload['sources']) == set(event.payload['context'])
    assert len(event.payload['sources']['previous_plan']) == 1
    assert len(event.payload['sources']['recent_history']) == 4
    broken = run.model_dump(mode='json')
    target = next(e for e in broken['events'] if e['event_id'] == event.event_id)
    target['payload']['sources']['recent_history'] = []
    with pytest.raises(ValidationError):
        MultiRecordedRun.model_validate(broken)


def test_comparison_and_resumable_evaluation(tmp_path, monkeypatch):
    store = RunStore(tmp_path / 'runs')
    report = run_evaluation(repetitions=2, store=store, root=tmp_path / 'reports')
    assert len(report['pairs']) == 2
    for pair in report['pairs']:
        assert pair['same_initial_state'] and pair['same_turn_limit']
        assert pair['left']['rejected_actions'] == 1 and pair['right']['rejected_actions'] == 0
        assert pair['left']['turns'] == 31 and pair['right']['turns'] == 28
        assert not pair['left']['usage_complete']
    def must_not_execute(*args, **kwargs):
        raise AssertionError('Repeated paid work during resume')
    monkeypatch.setattr('app.evaluation.run.run_scenario', must_not_execute)
    resumed = run_evaluation(repetitions=2, store=store, root=tmp_path / 'reports', resume=report['evaluation_id'])
    assert resumed['run_ids'] == report['run_ids']
    assert compare(store.load(report['run_ids'][0]), store.load(report['run_ids'][1])) == report['pairs'][0]


def test_safe_error_categories_and_complete_request(tmp_path):
    def fail(request):
        return httpx.Response(401, json={'error': {'message': 'test-secret'}})
    agent = LLMAgent(OpenAIProvider(api_key='test-secret', model='test-model', transport=httpx.MockTransport(fail)))
    run = run_simulation(agent, max_turns=1, store=RunStore(tmp_path))
    call = next(e for e in run.events if e.type == 'model_call')
    assert call.payload['error_category'] == 'authentication'
    assert call.payload['model'] == 'test-model'
    assert call.payload['duration_ms'] >= 0
    assert call.payload['validated_response'] is None
    assert 'test-secret' not in run.model_dump_json()
    observation = next(e for e in run.events if e.type == 'observation')
    assert json.loads(call.payload['context_json']) == observation.payload['context']


def test_distinct_live_policies_have_common_roles():
    from app.agent.handoff_policy import handoff_policy
    assert handoff_policy('blue', False) != handoff_policy('blue', True)
    assert handoff_policy('red', False) == handoff_policy('red', True)
    assert handoff_policy('green', False) == handoff_policy('green', True)
