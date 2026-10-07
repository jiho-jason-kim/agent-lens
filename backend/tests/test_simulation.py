"""Verify recorded artifacts and reconstruct turns without executing an agent."""

import json
from dataclasses import asdict

import pytest
from pydantic import ValidationError

from app.agent.mock_agent import MockAgent
from app.environment.grid_world import GridWorld
from app.models.recording import AgentContext, AgentDecision
from app.simulation.runner import run_simulation
from app.storage.json_store import RunStore


def test_complete_run_and_reconstruct_every_turn(tmp_path):
    store = RunStore(tmp_path)
    run = run_simulation(MockAgent(), store=store)
    assert run.metadata.status == "goal_complete"
    assert run.metadata.turns <= 50
    assert len(run.states) == run.metadata.turns + 1
    loaded = store.load(run.metadata.run_id)
    assert loaded.model_dump(mode="json") == run.model_dump(mode="json")
    assert {p.name for p in (tmp_path / run.metadata.run_id).iterdir()} == {
        "metadata.json", "events.json", "states.json",
    }

    # Apply recorded changes to the initial snapshot, without calling world tools.
    reconstructed = asdict(loaded.states[0])
    for turn in range(1, loaded.metadata.turns + 1):
        events = [event for event in loaded.events if event.turn == turn]
        assert [event.type for event in events[:4]] == ["observation", "plan", "action", "environment_delta"]
        context = AgentContext.model_validate(events[0].payload["context"])
        before = loaded.states[turn - 1]
        assert context.observation.position == before.position
        assert context.inventory == before.inventory
        assert len(context.recent_history) == min(turn - 1, 5)
        if turn > 1:
            prior_plan = next(e.payload["plan"] for e in loaded.events if e.turn == turn - 1 and e.type == "plan")
            assert context.previous_plan == prior_plan
        for cell in context.observation.cells:
            assert abs(cell.position[0] - before.position[0]) + abs(cell.position[1] - before.position[1]) <= 2
            assert cell.resource == (cell.position in before.resources)
        delta = events[3].payload
        assert tuple(delta["position"]["before"]) == reconstructed["position"]
        assert delta["inventory"]["before"] == reconstructed["inventory"]
        reconstructed.update(turn=turn, position=tuple(delta["position"]["after"]),
                             inventory=delta["inventory"]["after"], goal_complete=delta["goal_complete"]["after"])
        removed = {tuple(p) for p in delta["removed_resources"]}
        reconstructed["resources"] = tuple(p for p in reconstructed["resources"] if p not in removed)
        assert reconstructed == asdict(loaded.states[turn])
    assert loaded.events[-1].type == "goal_complete"


def test_event_references_are_bidirectional_and_ordered(tmp_path):
    run = run_simulation(MockAgent(), store=RunStore(tmp_path))
    by_id = {event.event_id: event for event in run.events}
    assert len(by_id) == len(run.events)
    for index, event in enumerate(run.events):
        assert event.run_id == run.metadata.run_id
        assert event.timestamp.tzinfo is not None
        for reference in event.input_refs:
            parent = by_id[reference]
            assert event.event_id in parent.effect_refs
            assert parent in run.events[:index]
        for reference in event.effect_refs:
            assert event.event_id in by_id[reference].input_refs


def test_mock_is_deterministic(tmp_path):
    first = run_simulation(MockAgent(), store=RunStore(tmp_path))
    second = run_simulation(MockAgent(), store=RunStore(tmp_path))
    assert first.states == second.states
    assert [(e.type, e.payload) for e in first.events] == [(e.type, e.payload) for e in second.events]


def test_replay_does_not_execute_agent_or_environment(tmp_path, monkeypatch):
    store = RunStore(tmp_path)
    run = run_simulation(MockAgent(), store=store)

    def forbidden(*args, **kwargs):
        pytest.fail("Replay executed simulation code.")

    monkeypatch.setattr(MockAgent, "decide", forbidden)
    monkeypatch.setattr(GridWorld, "__init__", forbidden)
    monkeypatch.setattr(GridWorld, "move", forbidden)
    assert store.load(run.metadata.run_id).states == run.states


class WaitingAgent:
    def decide(self, context):
        return AgentDecision(plan="Wait at the current cell.", action={"type": "wait"})


def test_fifty_turn_limit(tmp_path):
    run = run_simulation(WaitingAgent(), store=RunStore(tmp_path))
    assert run.metadata.status == "turn_limit"
    assert run.metadata.turns == 50
    assert len(run.states) == 51
    assert len(run.events) == 200


@pytest.mark.parametrize("limit", [0, 51, True, 2.5])
def test_invalid_turn_limit(tmp_path, limit):
    with pytest.raises(ValueError):
        run_simulation(WaitingAgent(), max_turns=limit, store=RunStore(tmp_path))


@pytest.mark.parametrize("action", [
    {"type": "move", "direction": "up"}, {"type": "move"},
    {"type": "collect", "direction": "north"}, {"type": "teleport"},
    {"type": "wait", "position": [7, 7]},
])
def test_structured_action_validation(action):
    with pytest.raises(ValidationError):
        AgentDecision.model_validate({"plan": "Explore.", "action": action})


@pytest.mark.parametrize("plan", ["", "   ", 123, None])
def test_invalid_plan(plan):
    with pytest.raises(ValidationError):
        AgentDecision.model_validate({"plan": plan, "action": {"type": "wait"}})


def test_structured_json_and_extra_field_rejection():
    valid = {"plan": "Explore east.", "action": {"type": "move", "direction": "east"}}
    assert AgentDecision.model_validate_json(json.dumps(valid)).action.direction == "east"
    with pytest.raises(ValidationError):
        AgentDecision.model_validate({**valid, "hidden_reasoning": "Not an accepted artifact."})


def test_invalid_agent_output_stops_without_mutating_world(tmp_path):
    class InvalidAgent:
        def decide(self, context):
            return {"plan": "Move.", "action": {"type": "teleport"}}

    world = GridWorld()
    initial = world.snapshot()
    run = run_simulation(InvalidAgent(), world, store=RunStore(tmp_path))
    assert run.metadata.status == "error"
    assert run.metadata.turns == 0
    assert world.snapshot() == initial
    assert [e.type for e in run.events] == ["observation", "error"]


def test_provider_failure_is_recorded_without_exception_text(tmp_path):
    class FailingAgent:
        def decide(self, context):
            raise RuntimeError("secret-provider-token")

    run = run_simulation(FailingAgent(), store=RunStore(tmp_path))
    assert run.metadata.status == "error"
    assert "secret-provider-token" not in run.model_dump_json()


def test_rejected_environment_action_records_error_and_snapshot(tmp_path):
    class NorthAgent:
        def decide(self, context):
            return AgentDecision(plan="Move north.", action={"type": "move", "direction": "north"})

    run = run_simulation(NorthAgent(), max_turns=1, store=RunStore(tmp_path))
    assert run.states[1].position == run.states[0].position
    assert run.states[1].turn == 1
    assert run.events[3].payload["success"] is False
    assert run.events[3].payload["changed_cells"] == []
    assert run.events[4].type == "error"


def test_agent_context_contains_no_global_state(tmp_path):
    contexts = []

    class SpyAgent(WaitingAgent):
        def decide(self, context):
            contexts.append(context)
            return super().decide(context)

    run_simulation(SpyAgent(), GridWorld(resources=((7, 7),)), max_turns=1, store=RunStore(tmp_path))
    context = contexts[0]
    assert set(context.model_dump()) == {"goal", "observation", "inventory", "previous_plan", "recent_history"}
    assert not any(cell.resource for cell in context.observation.cells)
    assert not hasattr(context, "world")


def test_store_rejects_path_traversal_and_overwrite(tmp_path):
    store = RunStore(tmp_path)
    with pytest.raises(ValueError):
        store.load("../metadata")
    run = run_simulation(MockAgent(), store=store)
    with pytest.raises(FileExistsError):
        store.save(run)
