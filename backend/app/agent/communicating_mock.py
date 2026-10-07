"""Deterministic communication policy for offline demonstrations."""

from app.agent.mock_agent import MockAgent
from app.models.multi_recording import MultiAgentContext, MultiAgentDecision


class CommunicatingMockAgent(MockAgent):
    def __init__(self, recipient: str, target: int = 3, return_home: bool = False) -> None:
        super().__init__(target, return_home)
        self._recipient = recipient
        self._reported = False

    def decide(self, context: MultiAgentContext):
        resource = next((cell for cell in context.observation.cells if cell.resource), None)
        if not self._reported and resource:
            self._reported = True
            x, y = resource.position
            # Report a current observation, without consulting the global resource map.
            return MultiAgentDecision(plan="Share the resource I can currently observe.", action={
                "type": "send_message", "recipient": self._recipient,
                "message": f"I observed a resource at ({x}, {y}).",
            })
        return super().decide(context)
