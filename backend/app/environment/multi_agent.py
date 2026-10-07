"""Shared grid engine for tutorial and multi-agent execution."""

from dataclasses import dataclass, replace

from app.environment.grid_world import ActionResult, Direction, OFFSETS, Position, RADIUS, SIZE, _validate_position


@dataclass(frozen=True)
class AgentConfig:
    agent_id: str
    goal: str
    home: Position
    start: Position
    target: int = 3
    return_home: bool = False
    rival_id: str | None = None
    target_position: Position | None = None


@dataclass(frozen=True)
class VisibleAgent:
    agent_id: str
    position: Position


@dataclass(frozen=True)
class LocalCell:
    position: Position
    resource: bool
    home: bool
    agents: tuple[str, ...]
    obstacle: bool = False
    target: bool = False


@dataclass(frozen=True)
class LocalObservation:
    position: Position
    inventory: int
    cells: tuple[LocalCell, ...]
    visible_agents: tuple[VisibleAgent, ...]


@dataclass(frozen=True)
class AgentState:
    agent_id: str
    position: Position
    inventory: int
    home: Position
    goal_complete: bool


@dataclass(frozen=True)
class Message:
    message_id: str
    sender_id: str
    recipient_id: str
    content: str
    sent_turn: int
    delivered_turn: int | None = None


@dataclass(frozen=True)
class MultiWorldState:
    turn: int
    agents: tuple[AgentState, ...]
    resources: tuple[Position, ...]
    messages: tuple[Message, ...] = ()
    obstacles: tuple[Position, ...] = ()
    targets: tuple[Position, ...] = ()


class GridEngine:
    """Own all physical state. Configured goals are evaluated only for global snapshots."""

    def __init__(self, agents: tuple[AgentConfig, ...], resources: tuple[Position, ...], *,
                 obstacles: tuple[Position, ...] = (), targets: tuple[Position, ...] = ()) -> None:
        if not agents or len({agent.agent_id for agent in agents}) != len(agents):
            raise ValueError('Agents must have unique identities.')
        for agent in agents:
            if not agent.agent_id or not agent.goal.strip() or type(agent.target) is not int or agent.target < 1:
                raise ValueError('Each agent needs an identity, goal, and positive target.')
            _validate_position(agent.home)
            _validate_position(agent.start)
            if agent.target_position is not None:
                _validate_position(agent.target_position)
            if agent.rival_id is not None and (agent.rival_id == agent.agent_id or agent.rival_id not in {a.agent_id for a in agents}):
                raise ValueError('Rival must identify a different configured agent.')
        checked = tuple(_validate_position(position) for position in resources)
        if len(set(checked)) != len(checked):
            raise ValueError('Resource positions must be unique.')
        self.configs = agents
        self._configs = {agent.agent_id: agent for agent in agents}
        self._positions = {agent.agent_id: agent.start for agent in agents}
        self._inventories = {agent.agent_id: 0 for agent in agents}
        self._resources = set(checked)
        self.obstacles = tuple(sorted({_validate_position(p) for p in obstacles}))
        self.targets = tuple(sorted({_validate_position(p) for p in targets}))
        if set(self.obstacles) & (set(checked) | set(self.targets) | {a.start for a in agents} | {a.home for a in agents}):
            raise ValueError('Obstacles cannot overlap resources, targets, starts, or homes.')
        self.turn = 0
        self._messages: list[Message] = []

    def _check_agent(self, agent_id: str) -> None:
        if agent_id not in self._configs:
            raise ValueError('Unknown agent identity.')

    def goal_complete(self, agent_id: str) -> bool:
        self._check_agent(agent_id)
        config = self._configs[agent_id]
        if config.target_position is not None:
            return self._positions[agent_id] == config.target_position
        inventory = self._inventories[agent_id]
        enough = inventory > self._inventories[config.rival_id] if config.rival_id else inventory >= config.target
        return enough and (not config.return_home or self._positions[agent_id] == config.home)

    def snapshot(self) -> MultiWorldState:
        return MultiWorldState(self.turn, tuple(AgentState(
            config.agent_id, self._positions[config.agent_id], self._inventories[config.agent_id],
            config.home, self.goal_complete(config.agent_id),
        ) for config in self.configs), tuple(sorted(self._resources)), tuple(self._messages), self.obstacles, self.targets)

    def observe(self, agent_id: str) -> LocalObservation:
        self._check_agent(agent_id)
        x, y = self._positions[agent_id]
        visible = {(cx, cy) for cy in range(SIZE) for cx in range(SIZE)
                   if abs(cx - x) + abs(cy - y) <= RADIUS}
        # Visibility filters identities before any information enters the observation.
        agents = tuple(VisibleAgent(other, position) for other, position in self._positions.items()
                       if other != agent_id and position in visible)
        cells = tuple(LocalCell((cx, cy), (cx, cy) in self._resources,
                                (cx, cy) == self._configs[agent_id].home,
                                tuple(other.agent_id for other in agents if other.position == (cx, cy)),
                                (cx, cy) in self.obstacles, (cx, cy) in self.targets)
                      for cx, cy in sorted(visible, key=lambda p: (p[1], p[0])))
        return LocalObservation((x, y), self._inventories[agent_id], cells, agents)

    def move(self, direction: Direction, agent_id: str) -> ActionResult:
        self._check_agent(agent_id)
        self.turn += 1
        if not isinstance(direction, str) or direction not in OFFSETS:
            return ActionResult(False, 'Invalid direction.')
        dx, dy = OFFSETS[direction]
        x, y = self._positions[agent_id]
        destination = (x + dx, y + dy)
        if not all(0 <= value < SIZE for value in destination):
            return ActionResult(False, 'Movement would leave the grid.')
        if destination in self.obstacles:
            return ActionResult(False, 'Movement is blocked by an obstacle.')
        # Agents can share a cell. Sequential collection resolves resource contention.
        self._positions[agent_id] = destination
        return ActionResult(True, 'Agent moved.')

    def collect(self, agent_id: str) -> ActionResult:
        self._check_agent(agent_id)
        self.turn += 1
        position = self._positions[agent_id]
        if position not in self._resources:
            return ActionResult(False, 'No resource at the current cell.')
        self._resources.remove(position)
        self._inventories[agent_id] += 1
        return ActionResult(True, 'Resource collected.')

    def wait(self, agent_id: str) -> ActionResult:
        self._check_agent(agent_id)
        self.turn += 1
        return ActionResult(True, 'Agent waited.')

    def send_message(self, sender_id: str, recipient_id: str, content: str) -> ActionResult:
        self._check_agent(sender_id)
        self.turn += 1
        if not isinstance(recipient_id, str) or recipient_id not in self._configs or recipient_id == sender_id:
            return ActionResult(False, 'Recipient must identify another configured agent.')
        if not isinstance(content, str) or not content.strip() or len(content) > 1000:
            return ActionResult(False, 'Message must contain 1 through 1000 characters and non-whitespace text.')
        self._messages.append(Message(f'm-{len(self._messages) + 1:04d}', sender_id, recipient_id, content, self.turn))
        return ActionResult(True, 'Message queued for recipient.')

    def receive_messages(self, agent_id: str) -> tuple[Message, ...]:
        self._check_agent(agent_id)
        received = []
        # Deliver only at the recipient's next scheduled decision, never at send time.
        for index, message in enumerate(self._messages):
            if message.recipient_id == agent_id and message.delivered_turn is None:
                delivered = replace(message, delivered_turn=self.turn + 1)
                self._messages[index] = delivered
                received.append(delivered)
        return tuple(received)
