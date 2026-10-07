"""Deterministic local policy. No world object or resource map is available."""

from app.environment.grid_world import SIZE, TARGET, Position
from app.models.recording import AgentContext, AgentDecision


class MockAgent:
    recording_mode = "mock"

    def __init__(self, target: int = TARGET, return_home: bool = True) -> None:
        # Remember only cells previously visited and home when it becomes visible.
        self._visits: dict[Position, int] = {}
        self._home: Position | None = None
        self._target = target
        self._return_home = return_home

    def decide(self, context: AgentContext) -> AgentDecision:
        observation = context.observation
        position = observation.position
        self._visits[position] = self._visits.get(position, 0) + 1
        for cell in observation.cells:
            if cell.home:
                self._home = cell.position

        if observation.inventory >= self._target:
            if self._return_home and self._home is not None:
                return self._toward(position, self._home, "Return to the previously observed home.")
            if not self._return_home:
                return AgentDecision(plan="Wait after reaching my collection target.", action={"type": "wait"})

        resources = [cell.position for cell in observation.cells if cell.resource]
        if position in resources:
            return AgentDecision(plan="Collect the resource at the current cell.", action={"type": "collect"})
        if resources:
            target = min(resources, key=lambda p: (abs(p[0] - position[0]) + abs(p[1] - position[1]), p))
            return self._toward(position, target, "Move toward the nearest visible resource.")

        x, y = position
        neighbors = [(x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)]
        valid = [p for p in neighbors if all(0 <= value < SIZE for value in p)]
        target = min(valid, key=lambda p: self._visits.get(p, 0))
        return self._toward(position, target, "Explore the least visited adjacent cell.")

    @staticmethod
    def _toward(position: Position, target: Position, plan: str) -> AgentDecision:
        x, y = position
        tx, ty = target
        if position == target:
            return AgentDecision(plan=plan, action={"type": "wait"})
        direction = ("east" if tx > x else "west") if tx != x else ("south" if ty > y else "north")
        return AgentDecision(plan=plan, action={"type": "move", "direction": direction})
