"""Create independent agents and execute scenarios through the shared runner."""

import argparse
import re

from app.agent.mock_agent import MockAgent
from app.agent.communicating_mock import CommunicatingMockAgent
from app.models.multi_recording import MultiAgentDecision
from app.scenarios.catalog import SCENARIOS, get_scenario
from app.simulation.runner import run_multi_simulation, run_simulation
from app.storage.json_store import RunStore


class ScenarioMockAgent(CommunicatingMockAgent):
    def __init__(self, config, recipient, scenario_id):
        super().__init__(recipient=recipient, target=config.target, return_home=config.return_home)
        self.scenario_id = scenario_id
        self.destination = config.target_position
        self.recipient = recipient
        self.announced = False
        self.arrived = False
        self.report_target = None
        self.inspected = set()

    def send(self, content):
        return MultiAgentDecision(plan="Share information with my assigned recipient.",
                                  action={"type": "send_message", "recipient": self.recipient, "message": content})

    def decide(self, context):
        if self.destination is not None:
            if not self.announced:
                self.announced = True
                return self.send(f"My assigned target is {self.destination}.")
            if context.observation.position != self.destination:
                return self._toward(context.observation.position, self.destination, "Move toward my assigned target.")
            if not self.arrived:
                self.arrived = True
                return self.send(f"I reached {self.destination}. I will wait here.")
            return MultiAgentDecision(plan="Wait at my target for the other agents.", action={"type": "wait"})
        # Reports remain claims. Only local observation can confirm a resource.
        if context.scenario_instructions:
            return self.send(context.scenario_instructions[0])
        if self.scenario_id == "misinformation" and context.agent_id == "blue":
            for message in context.recent_messages:
                match = re.search(r"\((\d), (\d)\)", message.content)
                if match:
                    target = tuple(map(int, match.groups()))
                    if target not in self.inspected:
                        self.report_target = target
            if self.report_target is not None:
                if context.observation.position == self.report_target:
                    self.inspected.add(self.report_target)
                    self.report_target = None
                else:
                    return self._toward(context.observation.position, self.report_target, "Investigate the received resource report.")
        return super().decide(context)


def run_scenario(scenario_id, *, agent_mode="mock", max_turns=None, store=None):
    scenario = get_scenario(scenario_id)
    if agent_mode not in ("mock", "llm", "langchain"):
        raise ValueError("Unknown agent mode.")
    def create(config, index):
        if agent_mode in ("llm", "langchain"):
            from app.agent.llm_agent import LLMAgent
            from app.agent.handoff_policy import handoff_policy
            policy = handoff_policy(config.agent_id, scenario_id == "verified-handoff") if scenario_id in ("handoff-race", "verified-handoff") else ""
            from app.agent.openai_provider import OpenAIProvider
            if agent_mode == "langchain":
                from app.agent.langchain_provider import LangChainProvider
                agent = LLMAgent(LangChainProvider.from_environment(), policy=policy)
                agent.recording_mode = "langchain"
                return agent
            return LLMAgent(OpenAIProvider.from_environment(), policy=policy)
        if scenario_id in ("handoff-race", "verified-handoff"):
            from app.agent.handoff_mock import HandoffAgent
            return HandoffAgent(config.agent_id, verify=scenario_id == "verified-handoff")
        if scenario_id in ("cooperation", "misinformation", "coordination"):
            recipient = scenario.agents[(index + 1) % len(scenario.agents)].agent_id
            return ScenarioMockAgent(config, recipient, scenario_id)
        return MockAgent(target=config.target, return_home=config.return_home)
    agents = {config.agent_id: create(config, index) for index, config in enumerate(scenario.agents)}
    limit = scenario.max_turns if max_turns is None else max_turns
    if scenario_id == "tutorial":
        return run_simulation(agents["agent-1"], scenario.setup(), max_turns=limit, store=store)
    return run_multi_simulation(agents, scenario.setup(), max_turns=limit, store=store, scenario=scenario)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", nargs="?", default="tutorial", choices=[item.id for item in SCENARIOS])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--agent", choices=("mock", "llm", "langchain"), default="mock")
    parser.add_argument("--max-turns", type=int, default=None)
    args = parser.parse_args()
    store = RunStore()
    for item in SCENARIOS if args.all else (get_scenario(args.scenario),):
        run = run_scenario(item.id, store=store, agent_mode=args.agent, max_turns=args.max_turns)
        assert store.load(run.metadata.run_id).model_dump(mode="json") == run.model_dump(mode="json")
        print(f"{item.id}: {run.metadata.status}, {run.metadata.turns} turns, {len(run.events)} events, {run.metadata.run_id}")
