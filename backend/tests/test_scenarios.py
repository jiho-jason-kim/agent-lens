"""Verify scenario behavior and recorded evidence without provider requests."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.memory.store import Memory, possibly_stale
from app.scenarios.catalog import SCENARIOS, get_scenario
from app.scenarios.run import run_scenario
from app.storage.json_store import RunStore


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.id)
def test_scenario_roundtrip_and_determinism(scenario, tmp_path):
    store = RunStore(tmp_path)
    first = run_scenario(scenario.id, store=store)
    second = run_scenario(scenario.id, store=store)
    assert first.metadata.status != "error"
    assert first.states == second.states
    assert [(e.type, e.payload) for e in first.events] == [(e.type, e.payload) for e in second.events]
    assert store.load(first.metadata.run_id).model_dump(mode="json") == first.model_dump(mode="json")
    assert first.metadata.scenario_id == scenario.id
    assert 1 <= first.metadata.turns <= 50


def test_misinformation_is_private_and_traceable(tmp_path):
    run = run_scenario("misinformation", store=RunStore(tmp_path))
    source = next(e for e in run.events if e.type == "scenario_instruction")
    assert (source.turn, source.agent_id) == (6, "green")
    assert source.payload["inaccurate"]
    assert all((7, 2) not in state.resources for state in run.states)
    write = next(e for e in run.events if e.type == "memory_write" and source.event_id in e.input_refs)
    assert write.payload["memory"]["content"] == source.payload["content"]
    sent = next(e for e in run.events if e.type == "message_send" and e.turn == 6)
    assert sent.payload["message"]["recipient_id"] == "blue"
    receipt = next(e for e in run.events if e.type == "message_receive" and sent.event_id in e.input_refs)
    assert receipt.agent_id == "blue"
    for event in run.events:
        if event.type == "observation":
            context = event.payload["context"]
            assert bool(context["scenario_instructions"]) == (event.turn == 6)
            assert "inaccurate" not in context
            assert "resources" not in context
    assert any(e.type == "plan" and e.agent_id == "blue" and "received resource report" in e.payload["plan"] for e in run.events)


def test_stale_memory_occurs_after_another_agent_collects(tmp_path):
    run = run_scenario("stale-memory", store=RunStore(tmp_path))
    found = False
    for event in run.events:
        if event.type != "memory_retrieve":
            continue
        for raw in event.payload["memories"]:
            memory = Memory.model_validate(raw)
            if not possibly_stale(memory, run.states[event.turn - 1].resources):
                continue
            found |= any(delta.type == "environment_delta" and delta.agent_id != memory.agent_id
                         and memory.created_turn < delta.turn < event.turn
                         and memory.resource_position in map(tuple, delta.payload["removed_resources"])
                         for delta in run.events)
    assert found


def test_hidden_rival_and_obstacle():
    world = get_scenario("hidden-information").setup()
    local = world.observe("blue")
    assert any(cell.resource and cell.position == (3, 2) for cell in local.cells)
    assert "red" not in [agent.agent_id for agent in local.visible_agents]
    assert len(world.snapshot().agents) == 3
    world.move("south", "red")
    result = world.move("south", "red")
    assert not result.success
    assert world.observe("red").position == (4, 3)


def test_coordination_requires_simultaneous_occupancy(tmp_path):
    scenario = get_scenario("coordination")
    state = scenario.setup().snapshot()
    assert not scenario.is_complete(state)
    occupied = replace(state, agents=tuple(replace(agent, position=target) for agent, target in zip(state.agents, scenario.targets)))
    assert scenario.is_complete(occupied)
    departed = replace(occupied, agents=(replace(occupied.agents[0], position=(2, 0)), *occupied.agents[1:]))
    assert not scenario.is_complete(departed)
    run = run_scenario(scenario.id, store=RunStore(tmp_path))
    assert run.metadata.status == "goal_complete"
    assert scenario.is_complete(run.states[-1])
    assert sum(e.type == "target_occupied" for e in run.events) == 3
    assert {e.agent_id for e in run.events if e.type == "message_send"} == {"blue", "red", "green"}
    assert run.events[-1].type == "scenario_complete"


def test_cooperation_has_delivered_reports(tmp_path):
    run = run_scenario("cooperation", store=RunStore(tmp_path))
    assert run.metadata.status == "goal_complete"
    assert len([m for m in run.states[-1].messages if m.delivered_turn]) >= 3


def test_scenario_api(tmp_path):
    client = TestClient(create_app(RunStore(tmp_path)))
    assert len(client.get("/scenarios").json()) == len(SCENARIOS)
    for scenario in SCENARIOS:
        response = client.post("/runs", json={"scenario_id": scenario.id})
        assert response.status_code == 201
        assert response.json()["scenario_id"] == scenario.id
        assert client.get(response.headers["Location"]).status_code == 200
    assert client.post("/runs", json={"scenario_id": "unknown"}).status_code == 422


def test_handoff_has_real_failure_correction_and_recovery(tmp_path):
    run = run_scenario("handoff-race", store=RunStore(tmp_path))
    assert run.metadata.status == "goal_complete"
    failures = [e for e in run.events if e.type == "environment_delta" and not e.payload["success"]]
    assert len(failures) == 1
    assert failures[0].agent_id == "blue"
    assert failures[0].payload["message"] == "No resource at the current cell."
    assert any(e.agent_id == "red" and e.turn < failures[0].turn and e.type == "environment_delta"
               and (3, 2) in map(tuple, e.payload["removed_resources"]) for e in run.events)
    reports = [e for e in run.events if e.type == "message_send" and e.payload["message"]["content"].startswith("RESOURCE")]
    assert len(reports) == 2
    assert "(3, 2)" in reports[0].payload["message"]["content"]
    assert "(3, 4)" in reports[1].payload["message"]["content"]
    assert reports[1].turn > failures[0].turn
    assert run.states[-1].agents[0].inventory == 1
    # Every report must describe a resource in the scout's actual local observation.
    for report in reports:
        observation = next(e for e in run.events if e.turn == report.turn and e.type == "observation")
        cells = observation.payload["context"]["observation"]["cells"]
        assert any(cell["resource"] and str(tuple(cell["position"])) in report.payload["message"]["content"] for cell in cells)


def test_verified_policy_avoids_rejection_on_identical_initial_state(tmp_path):
    naive = run_scenario("handoff-race", store=RunStore(tmp_path))
    checked = run_scenario("verified-handoff", store=RunStore(tmp_path))
    assert naive.states[0] == checked.states[0]
    assert checked.metadata.status == "goal_complete"
    assert checked.metadata.turns < naive.metadata.turns
    assert not any(e.type == "environment_delta" and not e.payload["success"] for e in checked.events)
    correction = next(e for e in checked.events if e.type == "message_send" and "visibly empty" in e.payload["message"]["content"])
    observation = next(e for e in checked.events if e.turn == correction.turn and e.type == "observation")
    assert any(tuple(cell["position"]) == (3, 2) and not cell["resource"] for cell in observation.payload["context"]["observation"]["cells"])


def test_handoff_collector_cannot_locate_resources_without_reports(tmp_path):
    from app.agent.handoff_mock import HandoffAgent
    from app.models.multi_recording import MultiAgentDecision
    from app.simulation.runner import run_multi_simulation

    class SilentScout:
        def decide(self, context):
            return MultiAgentDecision(plan="Wait without sending reports.", action={"type": "wait"})

    scenario = get_scenario("handoff-race")
    run = run_multi_simulation({"blue": HandoffAgent("blue", False), "red": HandoffAgent("red", False),
                                "green": SilentScout()}, scenario.setup(), scenario=scenario, store=RunStore(tmp_path))
    assert run.metadata.status == "turn_limit"
    assert run.states[-1].agents[0].position == (0, 2)
    assert run.states[-1].agents[0].inventory == 0
