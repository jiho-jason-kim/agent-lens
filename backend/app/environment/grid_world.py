"""Deterministic world rules. Only observe() supplies agent-visible data."""

from dataclasses import dataclass
from typing import Literal

Position = tuple[int, int]
Direction = Literal["north", "south", "east", "west"]
SIZE = 8
RADIUS = 2
TARGET = 3
GOAL = "Collect 3 resources and return home."
DEFAULT_RESOURCES: tuple[Position, ...] = ((2, 0), (2, 2), (0, 2), (6, 6))
OFFSETS: dict[str, Position] = {
    "north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0),
}


@dataclass(frozen=True)
class Cell:
    position: Position
    resource: bool
    home: bool


@dataclass(frozen=True)
class Observation:
    position: Position
    inventory: int
    cells: tuple[Cell, ...]
    goal_complete: bool


@dataclass(frozen=True)
class WorldState:
    """Complete state for the debugger. Never use this as agent context."""

    turn: int
    position: Position
    inventory: int
    resources: tuple[Position, ...]
    home: Position
    goal_complete: bool


@dataclass(frozen=True)
class ActionResult:
    success: bool
    message: str


def _validate_position(position: Position) -> Position:
    if not isinstance(position, tuple) or len(position) != 2:
        raise ValueError("Positions must be (x, y) tuples.")
    if any(type(value) is not int or not 0 <= value < SIZE for value in position):
        raise ValueError("Coordinates must be integers from 0 through 7.")
    return position


class GridWorld:
    """Own all mutable state and validate each requested action."""

    def __init__(
        self,
        resources: tuple[Position, ...] = DEFAULT_RESOURCES,
        home: Position = (0, 0),
        start: Position | None = None,
    ) -> None:
        # Import lazily to keep the legacy dataclasses available to the shared engine.
        from app.environment.multi_agent import AgentConfig, GridEngine

        self._engine = GridEngine((AgentConfig("agent-1", GOAL, home,
                                  start if start is not None else home, TARGET, True),), resources)

    @property
    def goal_complete(self) -> bool:
        return self._engine.goal_complete("agent-1")

    def snapshot(self) -> WorldState:
        state = self._engine.snapshot()
        agent = state.agents[0]
        return WorldState(state.turn, agent.position, agent.inventory, state.resources, agent.home, agent.goal_complete)

    def observe(self) -> Observation:
        local = self._engine.observe("agent-1")
        return Observation(local.position, local.inventory,
                           tuple(Cell(cell.position, cell.resource, cell.home) for cell in local.cells),
                           self.goal_complete)

    def move(self, direction: Direction) -> ActionResult:
        return self._engine.move(direction, "agent-1")

    def collect(self) -> ActionResult:
        return self._engine.collect("agent-1")

    def wait(self) -> ActionResult:
        return self._engine.wait("agent-1")
