"""A controlled handoff experiment driven only by local context and received reports."""

import re

from app.agent.mock_agent import MockAgent
from app.models.multi_recording import MultiAgentDecision


class HandoffAgent(MockAgent):
    def __init__(self, role: str, verify: bool):
        super().__init__(target=1, return_home=False)
        self.role = role
        self.verify = verify
        self.requested = False
        self.destination = None
        self.acknowledge = False
        self.failed = False
        self.reported = set()

    @staticmethod
    def message(recipient, content, plan):
        return MultiAgentDecision(plan=plan, action={"type": "send_message", "recipient": recipient, "message": content})

    def decide(self, context):
        if self.role == "red":
            return super().decide(context)
        if self.role == "green":
            if any(message.content.startswith(("REQUEST:", "UPDATE:")) for message in context.recent_messages):
                # Scout reports are current observations, never a hidden resource map.
                choices = [cell.position for cell in context.observation.cells if cell.resource and cell.position not in self.reported]
                if choices:
                    destination = min(choices)
                    self.reported.add(destination)
                    return self.message("blue", f"RESOURCE {destination}: I can see it now. Please collect it.",
                                        "Report a visible resource in response to Blue's request.")
            return MultiAgentDecision(plan="Wait for Blue to request a resource update.", action={"type": "wait"})
        if context.inventory >= 1:
            return MultiAgentDecision(plan="My resource goal is complete.", action={"type": "wait"})
        for message in context.recent_messages:
            match = re.search(r"RESOURCE \((\d), (\d)\)", message.content)
            if match:
                self.destination = tuple(map(int, match.groups()))
                self.acknowledge = True
        if not self.requested:
            self.requested = True
            return self.message("green", "REQUEST: Please locate a resource for me.", "Ask the scout for a resource outside my view.")
        if self.acknowledge:
            self.acknowledge = False
            return self.message("green", f"ACK {self.destination}: I will collect your reported resource.", "Acknowledge Green's report before travelling.")
        if self.failed:
            self.failed = False
            self.destination = None
            return self.message("green", "UPDATE: Collection failed. Please report another resource.", "Report the rejected collection and request a new location.")
        if self.destination is not None:
            visible = next((cell for cell in context.observation.cells if cell.position == self.destination), None)
            if self.verify and visible is not None and not visible.resource:
                self.destination = None
                return self.message("green", "UPDATE: Your reported cell is visibly empty. Please report another resource.",
                                    "Local observation contradicts the report. Request an update before collecting.")
            if context.observation.position != self.destination:
                return self._toward(context.observation.position, self.destination,
                                    "Follow Green's received resource report." if self.verify else "Follow Green's received report without checking whether it is still current.")
            # The naive policy deliberately demonstrates a trust bug. The engine decides the actual result.
            self.failed = True
            return MultiAgentDecision(plan="Collect at the reported location.", action={"type": "collect"})
        return MultiAgentDecision(plan="Wait for the scout's reply.", action={"type": "wait"})
