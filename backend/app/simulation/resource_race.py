"""Compatibility fixture for the shared Resource Race scenario."""

from app.agent.mock_agent import MockAgent
from app.environment.multi_agent import GridEngine
from app.scenarios.catalog import get_scenario
from app.simulation.runner import run_multi_simulation
from app.storage.json_store import RunStore


def resource_race() -> tuple[GridEngine, dict[str, MockAgent]]:
    scenario = get_scenario("resource-race")
    configs = scenario.agents
    world = scenario.setup()
    agents = {config.agent_id: MockAgent(config.target, config.return_home) for config in configs}
    return world, agents


if __name__ == "__main__":
    world, agents = resource_race()
    run = run_multi_simulation(agents, world)
    # Load only recorded artifacts. The verification does not execute the agents again.
    loaded = RunStore().load(run.metadata.run_id)
    assert loaded.model_dump(mode="json") == run.model_dump(mode="json")
    print(f"{loaded.metadata.run_id}: schema v2, {loaded.metadata.status}, {loaded.metadata.turns} individual turns")
    for agent in loaded.states[-1].agents:
        print(f"{agent.agent_id}: inventory={agent.inventory}, position={agent.position}, goal_complete={agent.goal_complete}")
    print(f"Verified {len(loaded.states)} snapshots and {len(loaded.events)} recorded events.")
