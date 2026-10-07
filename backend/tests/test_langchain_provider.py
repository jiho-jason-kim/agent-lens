"""Exercise real LangChain serialization using an in-memory HTTP transport."""
import json
import httpx
import pytest
from fastapi.testclient import TestClient
ChatOpenAI = pytest.importorskip("langchain_openai").ChatOpenAI
from app.agent.langchain_provider import LangChainProvider
from app.main import create_app
from app.scenarios.run import run_scenario
from app.storage.json_store import RunStore


def provider(handler):
    return LangChainProvider(ChatOpenAI(api_key="test-secret", model="test-model", max_retries=0,
        store=False, http_client=httpx.Client(transport=httpx.MockTransport(handler))))


def completion(decision):
    return httpx.Response(200, json={"id": "chatcmpl-test", "object": "chat.completion", "created": 0,
        "model": "test-model", "choices": [{"index": 0, "finish_reason": "stop", "message": {
            "role": "assistant", "content": json.dumps(decision)}}]})


def test_private_context_delivery_and_replay(tmp_path, monkeypatch):
    requests = []
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        context = json.loads(body["messages"][1]["content"])
        action = {"type": "send_message", "recipient": "green", "message": "Please report a resource."} if context["agent_id"] == "blue" else {"type": "wait"}
        return completion({"plan": "Request information or wait.", "action": action})
    monkeypatch.setattr(LangChainProvider, "from_environment", classmethod(lambda cls: provider(handler)))
    store = RunStore(tmp_path)
    run = run_scenario("handoff-race", agent_mode="langchain", max_turns=3, store=store)
    assert run.metadata.agent_mode == "langchain"
    contexts = [event.payload["context"] for event in run.events if event.type == "observation"]
    assert [json.loads(body["messages"][1]["content"]) for body in requests] == contexts
    assert all(body["store"] is False for body in requests)
    assert all(body["response_format"]["json_schema"]["strict"] for body in requests)
    assert all("tools" not in body for body in requests)
    assert contexts[0]["recent_messages"] == []
    assert contexts[2]["recent_messages"][0]["sender_id"] == "blue"
    assert all(cell["position"] != [7, 7] for cell in contexts[0]["observation"]["cells"])
    assert store.load(run.metadata.run_id).model_dump(mode="json") == run.model_dump(mode="json")
    assert len(requests) == 3  # Replay must never invoke a model.
    assert "test-secret" not in run.model_dump_json()


@pytest.mark.parametrize("failure", ["network", "invalid"])
def test_failure_does_not_execute_or_expose_credentials(tmp_path, monkeypatch, failure):
    def handler(request):
        if failure == "network":
            raise RuntimeError("test-secret in provider error")
        return completion({"plan": "Invalid action", "action": {"type": "teleport"}})
    monkeypatch.setattr(LangChainProvider, "from_environment", classmethod(lambda cls: provider(handler)))
    run = run_scenario("tutorial", agent_mode="langchain", max_turns=1, store=RunStore(tmp_path))
    assert run.metadata.status == "error"
    assert run.metadata.turns == 0
    assert "test-secret" not in run.model_dump_json()


def test_missing_configuration_returns_503(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.ENV_FILE", tmp_path / "missing.env")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    client = TestClient(create_app(RunStore(tmp_path)))
    response = client.post("/runs", json={"scenario_id": "handoff-race", "agent": "langchain", "max_turns": 1})
    assert response.status_code == 503
    assert "OPENAI_MODEL" in response.json()["detail"]
