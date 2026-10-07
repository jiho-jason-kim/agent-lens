"""Small common interface for mock and future LLM agents."""

from typing import Protocol

from app.models.recording import AgentContext, AgentDecision


class Agent(Protocol):
    def decide(self, context: AgentContext) -> AgentDecision:
        """Select an action from observable context."""
        ...
