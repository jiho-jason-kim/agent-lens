"""Private stores, deterministic retrieval, source integrity, and recorded availability."""

import pytest
from pydantic import ValidationError

from app.memory.store import PrivateMemory, possibly_stale
from app.models.multi_recording import MultiRecordedRun
from app.agent.communicating_mock import CommunicatingMockAgent
from app.simulation.resource_race import resource_race
from app.simulation.runner import run_multi_simulation
from app.storage.json_store import RunStore
from app.environment.multi_agent import AgentConfig, GridEngine
from app.models.multi_recording import MultiAgentDecision


def test_retrieval_is_private_bounded_deterministic_and_immutable():
    blue = PrivateMemory("blue")
    red = PrivateMemory("red")
    first = blue.write(content="Resource observed at (1, 0).", source_type="observation",
                       source_event_id="e-1", turn=1, resource_position=(1, 0))
    for index in range(8):
        blue.write(content=f"Report {index}", source_type="message", source_event_id=f"e-{index + 2}", turn=index + 2)
    red.write(content="Red private content", source_type="message", source_event_id="secret", turn=1)
    memories, scores = blue.retrieve("Resource", 12)
    again, again_scores = blue.retrieve("Resource", 12)
    assert len(memories) == 4
    assert scores == again_scores
    assert [memory.memory_id for memory in memories] == [memory.memory_id for memory in again]
    assert all(memory.agent_id == "blue" and "Red private" not in memory.content for memory in memories)
    assert all(memory.access_count == 1 for memory in memories)
    assert all(memory.access_count == 2 and memory.last_accessed_turn == 12 for memory in again)
    assert first.access_count == 0
    with pytest.raises(ValidationError):
        memories[0].content = "Modified"


def test_staleness_uses_global_truth_only_in_debugger_helper():
    store = PrivateMemory("blue")
    memory = store.write(content="Resource observed at (2, 0).", source_type="observation",
                         source_event_id="obs", turn=1, resource_position=(2, 0))
    assert not possibly_stale(memory, ((2, 0),))
    assert possibly_stale(memory, ())
    memories, _ = store.retrieve("Resource", 20)
    assert memories[0].content == memory.content
    assert "stale" not in memories[0].model_dump()


def test_resource_memory_can_remain_after_another_agent_collects(tmp_path):
    class FixedAgent:
        def __init__(self, action):
            self.action = action
            self.contexts = []

        def decide(self, context):
            self.contexts.append(context)
            return MultiAgentDecision(plan="Execute the test action.", action={"type": self.action})

    configs = (AgentConfig("blue", "Collect resources.", (0, 0), (0, 0)),
               AgentConfig("red", "Collect resources.", (1, 0), (1, 0)),
               AgentConfig("green", "Explore.", (7, 7), (7, 7)))
    world = GridEngine(configs, ((1, 0), (7, 7)))
    agents = {"blue": FixedAgent("wait"), "red": FixedAgent("collect"), "green": FixedAgent("wait")}
    run = run_multi_simulation(agents, world, max_turns=4, store=RunStore(tmp_path))
    context = agents["blue"].contexts[1]
    memory = next(memory for memory in context.retrieved_memories if memory.resource_position == (1, 0))
    assert memory.created_turn == 1 and memory.last_accessed_turn == 4
    assert not any(cell.resource for cell in context.observation.cells)
    assert possibly_stale(memory, run.states[-1].resources)
    assert "stale" not in memory.model_dump()


def recorded_run(tmp_path):
    world, _ = resource_race()
    recipients = {"blue": "red", "red": "green", "green": "blue"}
    agents = {config.agent_id: CommunicatingMockAgent(recipients[config.agent_id], config.target) for config in world.configs}
    return run_multi_simulation(agents, world, max_turns=9, store=RunStore(tmp_path))


def test_message_memory_retrieval_context_plan_action_chain(tmp_path):
    run = recorded_run(tmp_path)
    events = run.events
    by_id = {event.event_id: event for event in events}
    writes = [event for event in events if event.type == "memory_write"]
    assert {event.payload["memory"]["source_type"] for event in writes} == {"observation", "message", "action_result"}
    for write in writes:
        memory = write.payload["memory"]
        source = by_id[memory["source_event_id"]]
        assert source.agent_id == write.agent_id == memory["agent_id"]
        assert source.event_id in write.input_refs
    message_memory = next(event for event in writes if event.payload["memory"]["source_type"] == "message")
    retrieval = next(event for event in events if event.type == "memory_retrieve" and message_memory.event_id in event.input_refs)
    context = next(event for event in events if event.type == "observation" and retrieval.event_id in event.input_refs)
    plan = next(event for event in events if event.type == "plan" and context.event_id in event.input_refs)
    action = next(event for event in events if event.type == "action" and plan.event_id in event.input_refs)
    assert action.agent_id == message_memory.agent_id
    assert context.payload["context"]["retrieved_memories"] == retrieval.payload["memories"]
    for event in events:
        if event.type == "observation":
            assert all(memory["agent_id"] == event.agent_id for memory in event.payload["context"]["retrieved_memories"])
    loaded = RunStore(tmp_path).load(run.metadata.run_id)
    assert loaded.model_dump(mode="json") == run.model_dump(mode="json")


@pytest.mark.parametrize("damage", ["owner", "source", "content", "retrieval", "context", "score"])
def test_fabricated_memory_artifacts_are_rejected(tmp_path, damage):
    data = recorded_run(tmp_path).model_dump(mode="json")
    write = next(event for event in data["events"] if event["type"] == "memory_write")
    retrieval = next(event for event in data["events"] if event["type"] == "memory_retrieve" and event["payload"]["memories"])
    context = next(event for event in data["events"] if event["type"] == "observation")
    if damage == "owner":
        write["payload"]["memory"]["agent_id"] = "red"
    elif damage == "source":
        write["payload"]["memory"]["source_event_id"] = "missing"
    elif damage == "content":
        write["payload"]["memory"]["content"] = "Fabricated resource."
    elif damage == "retrieval":
        retrieval["payload"]["memory_ids"] = ["missing"]
    elif damage == "score":
        retrieval["payload"]["scores"][0] = 9999
    else:
        context["payload"]["context"]["retrieved_memories"] = []
    with pytest.raises(ValidationError):
        MultiRecordedRun.model_validate(data)
