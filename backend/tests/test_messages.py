"""Private delivery, validation, event references, and replay without agent calls."""

from dataclasses import asdict

import pytest
import httpx
import json
from pydantic import ValidationError

from app.models.multi_recording import MultiAgentDecision, MultiRecordedRun
from app.agent.llm_agent import LLMAgent
from app.agent.openai_provider import OpenAIProvider
from app.simulation.resource_race import resource_race
from app.simulation.runner import run_multi_simulation
from app.storage.json_store import RunStore


class Scripted:
    def __init__(self, recipient=None):
        self.recipient = recipient
        self.contexts = []

    def decide(self, context):
        self.contexts.append(context)
        if len(self.contexts) == 1 and self.recipient:
            return MultiAgentDecision(plan="Send a private greeting.", action={
                "type": "send_message", "recipient": self.recipient, "message": "Private greeting.",
            })
        return MultiAgentDecision(plan="Wait for the next turn.", action={"type": "wait"})


def test_real_adapter_supports_multi_agent_message_decisions_offline(tmp_path):
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert "send_message" in json.dumps(body["text"]["format"]["schema"])
        assert "collect at least 3 resources" not in body["instructions"]
        return httpx.Response(200, json={"status": "completed", "output": [{
            "type": "message", "role": "assistant", "status": "completed", "content": [{
                "type": "output_text", "text": json.dumps({"plan": "Send a report.", "action": {
                    "type": "send_message", "recipient": "red", "message": "Hello Red.",
                }}),
            }],
        }]})

    world, _ = resource_race()
    blue = LLMAgent(OpenAIProvider(api_key="fake", model="fake", transport=httpx.MockTransport(respond)))
    red = Scripted()
    run_multi_simulation({"blue": blue, "red": red, "green": Scripted()}, world, max_turns=2, store=RunStore(tmp_path))
    assert len(requests) == 1
    assert red.contexts[0].recent_messages[0].content == "Hello Red."


def test_private_next_turn_delivery_and_replay(tmp_path, monkeypatch):
    world, _ = resource_race()
    agents = {"blue": Scripted("green"), "red": Scripted(), "green": Scripted("blue")}
    store = RunStore(tmp_path)
    run = run_multi_simulation(agents, world, max_turns=7, store=store)
    assert all(not context.recent_messages for context in agents["red"].contexts)
    assert not agents["blue"].contexts[0].recent_messages
    green_message = agents["green"].contexts[0].recent_messages[0]
    assert green_message.sender_id == "blue" and green_message.delivered_turn == 3
    assert agents["blue"].contexts[1].recent_messages[0].delivered_turn == 4
    assert not agents["blue"].contexts[2].recent_messages
    assert not agents["green"].contexts[1].recent_messages
    assert agents["blue"].contexts[1].recent_history[0].action.type == "send_message"
    sends = [event for event in run.events if event.type == "message_send"]
    receives = [event for event in run.events if event.type == "message_receive"]
    assert len(sends) == len(receives) == 2
    assert receives[0].input_refs == (sends[0].event_id,)
    assert receives[0].event_id in sends[0].effect_refs
    assert run.states[1].messages[0].delivered_turn is None
    assert run.states[3].messages[0].delivered_turn == 3
    assert all(state.agents[0].position == (0, 0) for state in run.states)

    def forbidden(*args):
        pytest.fail("Replay called an agent.")

    monkeypatch.setattr(Scripted, "decide", forbidden)
    loaded = store.load(run.metadata.run_id)
    assert loaded.model_dump(mode="json") == run.model_dump(mode="json")
    # Reconstruct each snapshot's message archive using send and receive events only.
    messages = {}
    for turn, state in enumerate(loaded.states):
        for event in loaded.events:
            if event.turn == turn and event.type in ("message_send", "message_receive"):
                message = event.payload["message"]
                messages[message["message_id"]] = message
        assert list(messages.values()) == [asdict(message) for message in state.messages]


@pytest.mark.parametrize("recipient,content", [("missing", "Hello"), ("blue", "Hello"), ("red", " "), ("red", "x" * 1001)])
def test_environment_rejects_invalid_messages(recipient, content):
    world, _ = resource_race()
    before = world.snapshot()
    assert not world.send_message("blue", recipient, content).success
    after = world.snapshot()
    assert after.turn == 1 and after.messages == ()
    assert before.agents == after.agents and before.resources == after.resources


@pytest.mark.parametrize("action", [
    {"type": "send_message", "recipient": "red", "message": ""},
    {"type": "send_message", "recipient": "red", "message": " "},
    {"type": "send_message", "recipient": "red", "message": "x" * 1001},
    {"type": "send_message", "recipient": "red"},
    {"type": "send_message", "recipient": "red", "message": "Hello", "sender": "green"},
])
def test_structured_messages_reject_invalid_output(action):
    with pytest.raises(ValidationError):
        MultiAgentDecision(plan="Send.", action=action)


def test_pending_delivery_at_end_of_run(tmp_path):
    world, _ = resource_race()
    run = run_multi_simulation({"blue": Scripted("green"), "red": Scripted(), "green": Scripted()}, world,
                               max_turns=1, store=RunStore(tmp_path))
    assert run.states[-1].messages[0].delivered_turn is None
    assert not any(event.type == "message_receive" for event in run.events)


def test_inbox_delivers_multiple_messages_once_in_send_order():
    world, _ = resource_race()
    world.send_message("blue", "green", "First report.")
    world.send_message("red", "green", "Second report.")
    assert world.receive_messages("red") == ()
    received = world.receive_messages("green")
    assert [message.content for message in received] == ["First report.", "Second report."]
    assert all(message.delivered_turn == 3 for message in received)
    assert world.receive_messages("green") == ()


def test_invalid_recipient_records_failed_action_without_send(tmp_path):
    world, _ = resource_race()
    run = run_multi_simulation({"blue": Scripted("unknown"), "red": Scripted(), "green": Scripted()}, world,
                               max_turns=1, store=RunStore(tmp_path))
    assert not any(event.type == "message_send" for event in run.events)
    assert run.events[-1].type == "error"
    assert run.states[-1].messages == ()


def test_tampered_receipts_and_context_are_rejected(tmp_path):
    world, _ = resource_race()
    run = run_multi_simulation({"blue": Scripted("red"), "red": Scripted(), "green": Scripted()}, world,
                               max_turns=3, store=RunStore(tmp_path))
    data = run.model_dump(mode="json")
    receipt = next(event for event in data["events"] if event["type"] == "message_receive")
    receipt["payload"]["message"]["content"] = "Fabricated message."
    with pytest.raises(ValidationError):
        MultiRecordedRun.model_validate(data)
    data = run.model_dump(mode="json")
    observation = next(event for event in data["events"] if event["type"] == "observation" and event["agent_id"] == "green")
    observation["payload"]["context"]["recent_messages"] = [asdict(run.states[2].messages[0])]
    with pytest.raises(ValidationError):
        MultiRecordedRun.model_validate(data)
