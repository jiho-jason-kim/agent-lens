"""Exercise the real adapter with an in-memory HTTP transport, without API calls."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agent.llm_agent import INSTRUCTIONS, LLMAgent
from app.agent.openai_provider import OpenAIProvider, ProviderConfigurationError, ProviderError, decision_schema
from app.environment.grid_world import GOAL, GridWorld
from app.main import create_app
from app.models.recording import AgentContext
from app.simulation.runner import run_simulation
from app.storage.json_store import RunStore

DECISION = {"plan": "Wait at home.", "action": {"type": "wait"}}


def response_body(decision=DECISION):
    return {"status": "completed", "output": [
        {"type": "reasoning", "summary": [{"text": "Must never be recorded."}]},
        {"type": "message", "role": "assistant", "status": "completed",
         "content": [{"type": "output_text", "text": json.dumps(decision)}]},
    ]}


def provider(handler):
    return OpenAIProvider(api_key="test-secret", model="test-model", transport=httpx.MockTransport(handler))


def context():
    return AgentContext(goal=GOAL, observation=GridWorld(resources=((7, 7),)).observe(),
                        inventory=0, previous_plan=None, recent_history=())


def test_exact_local_context_and_structured_request():
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json=response_body())

    decision = LLMAgent(provider(handler)).decide(context())
    assert decision.action.type == "wait"
    request = captured[0]
    assert str(request.url) == "https://api.openai.com/v1/responses"
    assert request.headers["authorization"] == "Bearer test-secret"
    body = json.loads(request.content)
    assert body["model"] == "test-model"
    assert body["instructions"] == INSTRUCTIONS
    assert body["store"] is False
    assert body["text"]["format"]["strict"] is True
    assert body["text"]["format"]["schema"] == decision_schema()
    assert json.loads(body["input"][0]["content"]) == context().model_dump(mode="json")
    sent_context = json.loads(body["input"][0]["content"])
    assert "resources" not in sent_context["observation"]
    assert all(cell["position"] != [7, 7] for cell in sent_context["observation"]["cells"])
    assert "previous_response_id" not in body
    assert "tools" not in body


@pytest.mark.parametrize("decision", [
    {"plan": "Move.", "action": {"type": "move", "direction": "east"}},
    {"plan": "Collect.", "action": {"type": "collect"}}, DECISION,
])
def test_valid_decisions(decision):
    agent = LLMAgent(provider(lambda request: httpx.Response(200, json=response_body(decision))))
    assert agent.decide(context()).model_dump() == decision


@pytest.mark.parametrize("decision", [
    {"plan": "Move.", "action": {"type": "move", "direction": "up"}},
    {"plan": "", "action": {"type": "wait"}},
    {"plan": "Wait.", "action": {"type": "wait"}, "reasoning": "Not accepted."},
])
def test_invalid_decisions_rejected_by_pydantic(decision):
    agent = LLMAgent(provider(lambda request: httpx.Response(200, json=response_body(decision))))
    with pytest.raises(ValidationError):
        agent.decide(context())


@pytest.mark.parametrize("body", [
    {"status": "incomplete", "output": []},
    {"status": "completed", "output": []},
    {"status": "completed", "output": [{"type": "message", "role": "assistant", "status": "completed",
                                         "content": [{"type": "refusal", "refusal": "No."}]}]},
    {"status": "completed", "output": None}, [],
])
def test_incomplete_refused_and_malformed_responses(body):
    with pytest.raises(ProviderError):
        provider(lambda request: httpx.Response(200, json=body)).generate(instructions=INSTRUCTIONS, context_json="{}")


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_failures_hide_response_body(status):
    with pytest.raises(ProviderError) as error:
        provider(lambda request: httpx.Response(status, text="test-secret")).generate(instructions=INSTRUCTIONS, context_json="{}")
    assert "test-secret" not in str(error.value)


def test_timeout_stops_and_records_error_without_executing_action(tmp_path):
    def timeout(request):
        raise httpx.ReadTimeout("test-secret", request=request)

    run = run_simulation(LLMAgent(provider(timeout)), store=RunStore(tmp_path))
    assert run.metadata.status == "error"
    assert run.metadata.turns == 0
    assert [event.type for event in run.events] == ["observation", "model_call", "error"]
    assert "test-secret" not in run.model_dump_json()


def test_llm_recording_and_replay_without_provider(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=response_body())

    store = RunStore(tmp_path)
    run = run_simulation(LLMAgent(provider(handler)), max_turns=2, store=store)
    loaded = store.load(run.metadata.run_id)
    assert loaded.metadata.agent == "LLMAgent"
    assert loaded.metadata.turns == 2
    assert len(requests) == 2
    assert "Must never be recorded" not in loaded.model_dump_json()
    assert "test-secret" not in loaded.model_dump_json()
    second_context = json.loads(json.loads(requests[1].content)["input"][0]["content"])
    assert second_context["previous_plan"] == DECISION["plan"]
    assert second_context["recent_history"][0]["action"] == {"type": "wait"}


def test_missing_configuration_and_mock_independence(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.ENV_FILE", tmp_path / "missing.env")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with pytest.raises(ProviderConfigurationError):
        OpenAIProvider.from_environment()
    with TestClient(create_app(RunStore(tmp_path))) as client:
        assert client.post("/runs", json={"agent": "llm"}).status_code == 503
        assert client.get("/runs").json() == []
        assert client.post("/runs").json()["status"] == "goal_complete"


def test_llm_api_uses_configured_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(OpenAIProvider, "from_environment", lambda: provider(lambda request: httpx.Response(200, json=response_body())))
    with TestClient(create_app(RunStore(tmp_path))) as client:
        created = client.post("/runs", json={"agent": "llm", "max_turns": 1})
        assert created.status_code == 201
        assert created.json()["agent"] == "LLMAgent"
        assert created.json()["turns"] == 1
        assert next(e for e in client.get(created.headers["location"]).json()["events"] if e["type"] == "plan")["payload"]["plan"] == DECISION["plan"]
