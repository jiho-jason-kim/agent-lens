"""Print an actual message-to-action dependency chain from a saved run."""

from app.agent.communicating_mock import CommunicatingMockAgent
from app.simulation.resource_race import resource_race
from app.simulation.runner import run_multi_simulation
from app.storage.json_store import RunStore


if __name__ == "__main__":
    world, _ = resource_race()
    recipients = {"blue": "red", "red": "green", "green": "blue"}
    agents = {config.agent_id: CommunicatingMockAgent(recipients[config.agent_id], config.target)
              for config in world.configs}
    run = run_multi_simulation(agents, world, max_turns=9)
    loaded = RunStore().load(run.metadata.run_id)
    writes = [event for event in loaded.events if event.type == "memory_write"]
    write = next(event for event in writes if event.payload["memory"]["source_type"] == "message")
    retrieval = next(event for event in loaded.events if event.type == "memory_retrieve" and write.event_id in event.input_refs)
    context = next(event for event in loaded.events if event.type == "observation" and retrieval.event_id in event.input_refs)
    plan = next(event for event in loaded.events if event.type == "plan" and context.event_id in event.input_refs)
    action = next(event for event in loaded.events if event.type == "action" and plan.event_id in event.input_refs)
    print(f"{loaded.metadata.run_id}: {len(writes)} memories written")
    print(f"{write.payload['memory']['source_event_id']} --stored_as--> {write.payload['memory']['memory_id']} ({write.event_id})")
    print(f"{write.event_id} --retrieved_for--> {retrieval.event_id} --available_to--> {context.event_id}")
    print(f"{context.event_id} --available_to--> {plan.event_id} --followed_by--> {action.event_id}")
    print("Verified every displayed edge against saved event references. No causal claim is made.")
