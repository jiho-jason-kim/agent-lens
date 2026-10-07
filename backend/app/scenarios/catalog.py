"""Reusable scenarios share world rules, scheduling, recording, and storage."""

from dataclasses import dataclass

from app.environment.grid_world import DEFAULT_RESOURCES, GOAL, GridWorld
from app.environment.multi_agent import AgentConfig, GridEngine, MultiWorldState


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    description: str
    concepts: tuple[str, ...]
    agents: tuple[AgentConfig, ...]
    resources: tuple[tuple[int, int], ...]
    obstacles: tuple[tuple[int, int], ...] = ()
    targets: tuple[tuple[int, int], ...] = ()
    max_turns: int = 50
    width: int = 8
    height: int = 8

    def setup(self):
        # The shared engine currently supports the original 8 by 8 grid.
        if (self.width, self.height) != (8, 8):
            raise ValueError("Scenarios require an 8 by 8 grid.")
        if self.id == "tutorial":
            return GridWorld()
        return GridEngine(self.agents, self.resources, obstacles=self.obstacles, targets=self.targets)

    def before_turn(self, turn: int, agent_id: str) -> tuple[str, ...]:
        if self.id == "misinformation" and turn == 6 and agent_id == "green":
            return ("Scenario report: Two resources are near (7, 2). Share this report with Blue.",)
        return ()

    def after_turn(self, before: MultiWorldState, after: MultiWorldState, actor: str) -> tuple[dict, ...]:
        old = next(agent for agent in before.agents if agent.agent_id == actor)
        new = next(agent for agent in after.agents if agent.agent_id == actor)
        if new.position in self.targets and new.position != old.position:
            return ({"position": new.position, "occupant": actor},)
        return ()

    def is_complete(self, state: MultiWorldState) -> bool:
        if self.id == "coordination":
            return set(self.targets) <= {agent.position for agent in state.agents}
        complete = all(agent.goal_complete for agent in state.agents)
        if self.id == "cooperation":
            return complete and len([message for message in state.messages if message.delivered_turn is not None]) >= 3
        return complete

    def exhausted(self, state: MultiWorldState) -> bool:
        return self.id != "coordination" and not state.resources


def configs(goals, starts=((0, 0), (7, 0), (0, 7)), targets=(2, 2, 2)):
    return tuple(AgentConfig(name, goal, start, start, target=target)
                 for name, goal, start, target in zip(("blue", "red", "green"), goals, starts, targets))


RACE_AGENTS = (
    AgentConfig("blue", "Collect 4 resources.", (0, 0), (0, 0), target=4),
    AgentConfig("red", "Collect more resources than Blue.", (7, 0), (7, 0), target=50, rival_id="blue"),
    AgentConfig("green", "Collect 3 resources.", (0, 7), (0, 7), target=3),
)
RACE_RESOURCES = ((1, 0), (2, 0), (3, 1), (6, 0), (5, 0), (4, 1), (0, 6), (1, 6), (2, 5))

HANDOFF_AGENTS = (
    AgentConfig("blue", "Ask Green for a resource. Collect one resource. Request an update if the report fails.", (0, 2), (0, 2), target=1),
    AgentConfig("red", "Collect one resource using your own observations.", (5, 2), (5, 2), target=1),
    AgentConfig("green", "Stay at (3, 2). Respond to Blue's requests with currently visible resource locations.",
                (3, 2), (3, 2), target_position=(3, 2)),
)

SCENARIOS = (
    Scenario("handoff-race", "Handoff Failure", "Green reports a real resource. Red collects it first. Blue follows the old report, fails, then requests a correction.",
             ("Outdated report", "Rejected collection", "Recovery"), HANDOFF_AGENTS, ((3, 2), (3, 4), (7, 7))),
    Scenario("verified-handoff", "Verified Handoff", "The same map with a different policy: Blue checks local evidence and requests an update before collecting.",
             ("Report verification", "Communication", "Recovery"), HANDOFF_AGENTS, ((3, 2), (3, 4), (7, 7))),
    Scenario("tutorial", "Tutorial — Resource Collection", "Collect three resources and return home.",
             ("Replay", "Partial observability"), (AgentConfig("agent-1", GOAL, (0, 0), (0, 0), return_home=True),), DEFAULT_RESOURCES),
    Scenario("resource-race", "Resource Race", "Compete for limited resources with different goals.",
             ("Competition", "Partial observability"), RACE_AGENTS, RACE_RESOURCES),
    Scenario("cooperation", "Cooperation", "Share discoveries across separated starting regions.",
             ("Communication", "Shared information"), configs((
                 "Collect 2 resources and share useful discoveries.", "Collect 2 resources and cooperate with other agents.",
                 "Explore, collect 2 resources, and report discoveries.")), RACE_RESOURCES),
    Scenario("misinformation", "Misinformation", "Trace a false scenario report given privately to Green at turn 6.",
             ("Provenance", "Incorrect information"), configs((
                 "Collect 3 resources and investigate received reports.", "Collect 3 resources.",
                 "Collect 3 resources and share reports with Blue."), targets=(3, 3, 3)), RACE_RESOURCES),
    Scenario("stale-memory", "Stale Memory", "Remember shared resource locations while rivals collect them.",
             ("Memory", "Temporal information"), configs(("Collect 3 resources.",) * 3,
                 starts=((1, 2), (4, 2), (6, 6)), targets=(3, 3, 3)), ((3, 2), (4, 3), (6, 5), (5, 6), (1, 5))),
    Scenario("hidden-information", "Hidden Information", "Approach a visible resource while an unseen rival approaches it too.",
             ("Partial observability", "Information asymmetry"), configs(("Collect 2 resources.",) * 3,
                 starts=((1, 2), (4, 2), (7, 7))), ((3, 2), (6, 2), (6, 7), (1, 5)), obstacles=((4, 4), (4, 5))),
    Scenario("coordination", "Coordination", "Announce assignments and occupy all three targets at once.",
             ("Communication", "Planning", "Synchronization"), tuple(
                 AgentConfig(name, f"Announce your assignment to ({target[0]}, {target[1]}), report arrival, and wait there.",
                             start, start, target_position=target)
                 for name, start, target in zip(("blue", "red", "green"), ((0, 0), (7, 0), (0, 7)), ((1, 0), (5, 0), (0, 4)))),
             (), targets=((1, 0), (5, 0), (0, 4))),
)


def get_scenario(scenario_id: str) -> Scenario:
    return next((scenario for scenario in SCENARIOS if scenario.id == scenario_id), None) or _unknown()


def _unknown():
    raise ValueError("Unknown scenario ID.")
