"""Run a short private-message demonstration without an LLM API."""

from app.agent.communicating_mock import CommunicatingMockAgent
from app.simulation.resource_race import resource_race
from app.simulation.runner import run_multi_simulation
from app.storage.json_store import RunStore


if __name__ == "__main__":
    world, _ = resource_race()
    recipients = {"blue": "red", "red": "green", "green": "blue"}
    agents = {config.agent_id: CommunicatingMockAgent(recipients[config.agent_id], config.target)
              for config in world.configs}
    run = run_multi_simulation(agents, world, max_turns=6)
    loaded = RunStore().load(run.metadata.run_id)
    print(f"{loaded.metadata.run_id}: {loaded.metadata.turns} individual turns")
    for event in loaded.events:
        if event.type in ("message_send", "message_receive"):
            message = event.payload["message"]
            print(f"Turn {event.turn}: {event.type} {message['message_id']} "
                  f"{message['sender_id']} -> {message['recipient_id']}: {message['content']}")
    assert len([event for event in loaded.events if event.type == "message_receive"]) == 3
    print("Verified three private deliveries from the saved recording.")
