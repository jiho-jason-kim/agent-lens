"""Phase A: independent agents, local contexts, deterministic scheduling, and replay."""

from dataclasses import FrozenInstanceError, replace

import pytest
from fastapi.testclient import TestClient

from app.agent.mock_agent import MockAgent
from app.environment.multi_agent import AgentConfig, GridEngine
from app.main import create_app
from app.models.recording import AgentDecision, RecordedRun
from app.models.multi_recording import MultiAgentContext, MultiRecordedRun
from app.simulation.resource_race import resource_race
from app.simulation.runner import run_multi_simulation, run_simulation
from app.storage.json_store import RunStore


class SpyAgent:
    def __init__(self, name, action=None):
        self.name = name
        self.action = action or {"type": "wait"}
        self.contexts = []

    def decide(self, context):
        self.contexts.append(context)
        return AgentDecision(plan=f"{self.name} private plan", action=self.action)


def test_context_contains_only_legitimately_available_information(tmp_path):
    world, _ = resource_race()
    agents = {config.agent_id: SpyAgent(config.agent_id) for config in world.configs}
    run = run_multi_simulation(agents, world, max_turns=9, store=RunStore(tmp_path))
    for config in world.configs:
        contexts = agents[config.agent_id].contexts
        assert len(contexts) == 3
        for index, context in enumerate(contexts):
            assert isinstance(context, MultiAgentContext)
            assert set(context.model_dump()) == {"agent_id", "turn", "goal", "observation", "inventory", "previous_plan", "recent_history", "recent_messages", "retrieved_memories", "scenario_instructions"}
            assert context.agent_id == config.agent_id
            assert context.goal == config.goal
            assert context.previous_plan == (f"{config.agent_id} private plan" if index else None)
            assert len(context.recent_history) == index
            assert [entry.turn for entry in context.recent_history] == [earlier.turn for earlier in contexts[:index]]
            for other in world.configs:
                if other.agent_id != config.agent_id:
                    assert other.goal not in context.model_dump_json()
                    assert f"{other.agent_id} private plan" not in context.model_dump_json()
            observation = context.observation
            x, y = observation.position
            assert all(abs(cell.position[0] - x) + abs(cell.position[1] - y) <= 2 for cell in observation.cells)
            assert observation.visible_agents == ()
            assert all(not cell.agents for cell in observation.cells)
            assert not hasattr(observation, "goal_complete")  # Rival progress must not leak through goal evaluation.
    assert [event.agent_id for event in run.events if event.type == "action"] == ["blue", "red", "green"] * 3


def test_hidden_global_changes_cannot_change_an_observation():
    world, _ = resource_race()
    before = world.observe("blue")
    world.collect("red")
    world.move("west", "red")
    world.collect("red")
    assert world.observe("blue") == before
    configs = tuple(replace(config, goal="Secret changed goal") if config.agent_id == "red" else config for config in world.configs)
    alternate = GridEngine(configs, ((1, 0), (7, 7)))
    original = GridEngine(world.configs, ((1, 0), (6, 6)))
    assert alternate.observe("blue") == original.observe("blue")


def test_visible_agents_reveal_position_and_identity_only():
    configs = (AgentConfig("blue", "Blue goal", (0, 0), (0, 0)),
               AgentConfig("red", "Secret red goal", (7, 7), (2, 0)))
    world = GridEngine(configs, ((2, 0),))
    world.collect("red")
    observation = world.observe("blue")
    assert observation.visible_agents[0].agent_id == "red"
    assert observation.visible_agents[0].position == (2, 0)
    assert not hasattr(observation.visible_agents[0], "inventory")
    assert not hasattr(observation.visible_agents[0], "goal")
    assert next(cell for cell in observation.cells if cell.position == (2, 0)).agents == ("red",)


def test_collection_contention_and_independent_inventory():
    configs = tuple(AgentConfig(name, "Collect.", (0, 0), (0, 0)) for name in ("blue", "red", "green"))
    world = GridEngine(configs, ((0, 0),))
    snapshot = world.snapshot()
    observation = world.observe("blue")
    assert world.collect("blue").success
    assert not world.collect("red").success
    assert [agent.inventory for agent in world.snapshot().agents] == [1, 0, 0]
    assert world.snapshot().turn == 2
    assert snapshot.resources == ((0, 0),)
    assert observation.cells[0].resource
    with pytest.raises(FrozenInstanceError):
        snapshot.agents[0].inventory = 99


def test_movement_changes_only_the_actor_and_rejects_invalid_identity():
    world, _ = resource_race()
    before = world.snapshot()
    assert world.move("east", "blue").success
    assert world.snapshot().agents[1:] == before.agents[1:]
    assert not world.move("north", "red").success
    current = world.snapshot()
    with pytest.raises(ValueError):
        world.move("east", "unknown")
    assert world.snapshot() == current


def test_goal_rules_use_configuration():
    configs = (AgentConfig("blue", "Collect one and return home.", (0, 0), (1, 0), target=1, return_home=True),
               AgentConfig("red", "Collect more than Blue.", (7, 0), (6, 0), rival_id="blue"))
    world = GridEngine(configs, ((1, 0), (6, 0)))
    world.collect("red")
    assert world.goal_complete("red")
    world.collect("blue")
    assert not world.goal_complete("blue")
    assert not world.goal_complete("red")
    world.move("west", "blue")
    assert world.goal_complete("blue")


def test_race_round_trip_determinism_and_delta_reconstruction(tmp_path, monkeypatch):
    store = RunStore(tmp_path)
    world, agents = resource_race()
    run = run_multi_simulation(agents, world, store=store)
    other_world, other_agents = resource_race()
    second = run_multi_simulation(other_agents, other_world, store=store)
    assert run.states == second.states
    assert [(event.type, event.agent_id, event.payload) for event in run.events] == [
        (event.type, event.agent_id, event.payload) for event in second.events]
    assert run.metadata.schema_version == 2
    assert run.metadata.status == "resources_exhausted"
    assert [agent.inventory for agent in run.states[-1].agents] == [3, 3, 3]
    assert [agent.goal_complete for agent in run.states[-1].agents] == [False, False, True]

    def forbidden(*args, **kwargs):
        pytest.fail("Replay executed an agent or world action.")

    monkeypatch.setattr(MockAgent, "decide", forbidden)
    monkeypatch.setattr(GridEngine, "move", forbidden)
    loaded = store.load(run.metadata.run_id)
    assert loaded.model_dump(mode="json") == run.model_dump(mode="json")
    data = loaded.model_dump(mode="json")
    rebuilt = data["states"][0]
    by_id = {event["event_id"]: event for event in data["events"]}
    for event in data["events"]:
        for reference in event["input_refs"]:
            assert event["event_id"] in by_id[reference]["effect_refs"]
        if event["type"] != "environment_delta":
            continue
        delta = event["payload"]
        rebuilt["turn"] = event["turn"]
        actor = next(agent for agent in rebuilt["agents"] if agent["agent_id"] == event["agent_id"])
        actor["position"] = delta["position"]["after"]
        actor["inventory"] = delta["inventory"]["after"]
        rebuilt["resources"] = [p for p in rebuilt["resources"] if p not in delta["removed_resources"]]
        for change in delta["agent_goal_changes"]:
            next(agent for agent in rebuilt["agents"] if agent["agent_id"] == change["agent_id"])["goal_complete"] = change["after"]
        assert rebuilt == data["states"][event["turn"]]


def test_stop_at_individual_turn_limit_and_save_failed_actor(tmp_path):
    world, _ = resource_race()
    agents = {config.agent_id: SpyAgent(config.agent_id) for config in world.configs}
    run = run_multi_simulation(agents, world, max_turns=4, store=RunStore(tmp_path))
    assert run.metadata.status == "turn_limit"
    assert len(run.states) == 5
    assert len(agents["blue"].contexts) == 2
    world, agents = resource_race()

    class Broken:
        def decide(self, context):
            raise RuntimeError("private error")

    agents["red"] = Broken()
    failed = run_multi_simulation(agents, world, store=RunStore(tmp_path))
    assert failed.metadata.status == "error"
    assert failed.metadata.turns == 1
    assert failed.events[-1].agent_id == "red"
    assert failed.events[-1].turn == 2
    assert "private error" not in failed.model_dump_json()


def test_all_agent_goals_complete(tmp_path):
    configs = tuple(AgentConfig(name, "Collect one.", position, position, target=1)
                    for name, position in zip(("blue", "red", "green"), ((0, 0), (7, 0), (0, 7))))
    world = GridEngine(configs, tuple(config.start for config in configs))
    agents = {config.agent_id: SpyAgent(config.agent_id, {"type": "collect"}) for config in configs}
    run = run_multi_simulation(agents, world, store=RunStore(tmp_path))
    assert run.metadata.status == "goal_complete"
    assert run.metadata.turns == 3
    assert run.events[-1].type == "goal_complete"


def test_rejects_shared_agent_instances_and_mismatched_ids(tmp_path):
    world, _ = resource_race()
    shared = SpyAgent("shared")
    with pytest.raises(ValueError):
        run_multi_simulation({name: shared for name in ("blue", "red", "green")}, world, store=RunStore(tmp_path))
    with pytest.raises(ValueError):
        run_multi_simulation({"blue": shared}, world, store=RunStore(tmp_path))


def test_old_tutorial_and_v2_api_data_coexist(tmp_path):
    store = RunStore(tmp_path)
    tutorial = run_simulation(MockAgent(), store=store)
    world, agents = resource_race()
    race = run_multi_simulation(agents, world, store=store)
    assert isinstance(store.load(tutorial.metadata.run_id), RecordedRun)
    assert isinstance(store.load(race.metadata.run_id), MultiRecordedRun)
    with TestClient(create_app(store)) as client:
        assert [run["run_id"] for run in client.get("/runs").json()] == [tutorial.metadata.run_id]
        assert client.get("/runs?schema_version=2").json()[0]["run_id"] == race.metadata.run_id
        detail = client.get(f"/runs/{race.metadata.run_id}")
        assert detail.status_code == 200
        assert detail.json() == race.model_dump(mode="json")
        assert client.get(f"/runs/{race.metadata.run_id}/events").json() == detail.json()["events"]
        assert client.get(f"/runs/{race.metadata.run_id}/states").json() == detail.json()["states"]
