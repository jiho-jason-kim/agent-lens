"""Execute at most 50 turns and record explicit dependencies."""

from datetime import datetime, timezone
from uuid import uuid4

from app.agent.base import Agent
from app.environment.grid_world import GOAL, GridWorld
from app.environment.multi_agent import GridEngine
from app.models.multi_recording import MultiAgentContext, MultiAgentDecision, MultiEvent, MultiHistoryEntry, MultiMetadata, MultiRecordedRun
from app.models.recording import AgentContext, AgentDecision, Event, HistoryEntry, Metadata, RecordedRun
from app.storage.json_store import RunStore
from app.memory.store import PrivateMemory
from app.scenarios.catalog import Scenario


def run_simulation(agent: Agent, world: GridWorld | None = None, *,
                   max_turns: int = 50, store: RunStore | None = None) -> RecordedRun:
    return _run({"agent-1": agent}, world if world is not None else GridWorld(), max_turns=max_turns, store=store)


def run_multi_simulation(agents: dict[str, Agent], world: GridEngine, *,
                         max_turns: int = 50, store: RunStore | None = None, scenario: Scenario | None = None) -> MultiRecordedRun:
    if set(agents) != {config.agent_id for config in world.configs}:
        raise ValueError("Provide exactly one agent for each configured identity.")
    if len({id(agent) for agent in agents.values()}) != len(agents):
        raise ValueError("Each identity needs an independent agent instance.")
    return _run(agents, world, max_turns=max_turns, store=store, scenario=scenario)


def _run(agents: dict[str, Agent], world: GridWorld | GridEngine, *,
         max_turns: int, store: RunStore | None, scenario: Scenario | None = None) -> RecordedRun | MultiRecordedRun:
    multi = isinstance(world, GridEngine)
    schedule = tuple(config.agent_id for config in world.configs) if multi else ("agent-1",)
    goals = {config.agent_id: config.goal for config in world.configs} if multi else {"agent-1": GOAL}
    if type(max_turns) is not int or not 1 <= max_turns <= 50:
        raise ValueError("max_turns must be an integer from 1 through 50.")
    if world.snapshot().turn != 0:
        raise ValueError("Simulation requires a fresh environment.")
    run_id = f"run-{uuid4().hex}"
    created_at = datetime.now(timezone.utc)
    events: list[Event] = []
    states = [world.snapshot()]
    histories: dict[str, list[HistoryEntry]] = {identity: [] for identity in schedule}
    plans: dict[str, str | None] = {identity: None for identity in schedule}
    status = "turn_limit"
    send_refs: dict[str, str] = {}
    memory_stores = {identity: PrivateMemory(identity) for identity in schedule} if multi else {}
    memory_refs: dict[str, str] = {}

    def emit(kind: str, payload: dict, refs: tuple[str, ...] = ()) -> Event:
        event = (MultiEvent if multi else Event)(event_id=f"e-{len(events) + 1:04d}", run_id=run_id,
                      turn=turn, agent_id=actor, type=kind, timestamp=datetime.now(timezone.utc),
                      payload=payload, input_refs=refs)
        # Store both directions of each recorded dependency for the future UI.
        for index, parent in enumerate(events):
            if parent.event_id in refs:
                events[index] = parent.model_copy(update={"effect_refs": (*parent.effect_refs, event.event_id)})
        events.append(event)
        return event

    def write_memory(content: str, source_type: str, source_id: str, resource_position=None):
        memory = memory_stores[actor].write(content=content, source_type=source_type,
                                          source_event_id=source_id, turn=turn, resource_position=resource_position)
        written = emit("memory_write", {"memory": memory.model_dump(mode="json")}, (source_id,))
        memory_refs[memory.memory_id] = written.event_id

    for turn in range(1, max_turns + 1):
        actor = schedule[(turn - 1) % len(schedule)]
        agent = agents[actor]
        local = world.observe(actor) if multi else world.observe()
        # Local perception follows a saved world snapshot, not an inferred model belief.
        prior_effect = next((event for event in reversed(events) if event.type == "environment_delta"), None)
        local_event = emit("local_observation", {"observation": local.__dict__, "snapshot_turn": len(states)-1},
                           (prior_effect.event_id,) if prior_effect else ()) if multi else None
        instructions = scenario.before_turn(turn, actor) if scenario else ()
        instruction_refs = tuple(emit("scenario_instruction", {"content": content, "scenario_id": scenario.id,
            "inaccurate": scenario.id == "misinformation"}).event_id for content in instructions)
        incoming = world.receive_messages(actor) if multi else ()
        receipt_refs = tuple(emit("message_receive", {"message": message.__dict__}, (send_refs[message.message_id],)).event_id
                             for message in incoming)
        retrieved = ()
        context_refs = receipt_refs
        if multi:
            for content, reference in zip(instructions, instruction_refs):
                write_memory(content, "scenario_instruction", reference)
            for cell in local.cells:
                if cell.resource:
                    write_memory(f"Resource observed at ({cell.position[0]}, {cell.position[1]}).", "observation",
                                 local_event.event_id, cell.position)
            for message, reference in zip(incoming, receipt_refs):
                write_memory(f"{message.sender_id} reported: {message.content}", "message", reference)
            query = goals[actor] + " " + " ".join(
                f"resource {cell.position[0]} {cell.position[1]}" for cell in local.cells if cell.resource)
            retrieved, scores = memory_stores[actor].retrieve(query, turn)
            retrieval = emit("memory_retrieve", {"memory_ids": [memory.memory_id for memory in retrieved],
                "memories": [memory.model_dump(mode="json") for memory in retrieved], "scores": scores, "query": query},
                (local_event.event_id, *(memory_refs[memory.memory_id] for memory in retrieved)))
            context_refs = (local_event.event_id, *instruction_refs, *receipt_refs, retrieval.event_id)
        context_data = dict(goal=goals[actor], observation=local, inventory=local.inventory,
                            previous_plan=plans[actor], recent_history=tuple(histories[actor][-5:]))
        context = MultiAgentContext(agent_id=actor, turn=turn, scenario_instructions=instructions, recent_messages=incoming, retrieved_memories=retrieved, **context_data) if multi else AgentContext(**context_data)
        # Reference every prior plan and action result actually included in the context.
        prior = [event for event in events if event.agent_id == actor]
        previous_plan = [event.event_id for event in prior if event.type == "plan"][-1:]
        history = [event.event_id for event in prior if event.type in ("action", "environment_delta")][-10:]
        sources = {key: "external: runner configuration" for key in context.model_dump()}
        sources.update(goal="metadata: agent goal", observation=f"snapshot:{len(states)-1}",
                       inventory=f"snapshot:{len(states)-1}", previous_plan=tuple(previous_plan), recent_history=tuple(history))
        if multi:
            sources.update(observation=(local_event.event_id,), recent_messages=tuple(receipt_refs),
                           retrieved_memories=(retrieval.event_id,), scenario_instructions=instruction_refs)
        observation = emit("observation", {"context": context.model_dump(mode="json"), "sources": sources},
                           tuple(dict.fromkeys((*context_refs, *previous_plan, *history))))
        try:
            # Revalidate even custom agents before executing any environment action.
            raw = agent.decide(context)
            decision = (MultiAgentDecision if multi else AgentDecision).model_validate(raw.model_dump() if isinstance(raw, AgentDecision) else raw)
        except Exception as exc:
            # Do not save exception text, which could contain provider credentials.
            failed_call = emit("model_call", agent.last_call, (observation.event_id,)) if getattr(agent, "last_call", None) else None
            emit("error", {"stage": "decision", "error_type": type(exc).__name__,
                           "message": "Agent decision failed. No action was executed."},
                 (observation.event_id, failed_call.event_id) if failed_call else (observation.event_id,))
            status = "error"
            break
        call = emit("model_call", agent.last_call, (observation.event_id,)) if getattr(agent, "last_call", None) else None
        decision_refs = (observation.event_id, call.event_id) if call else (observation.event_id,)
        plan = emit("plan", {"plan": decision.plan}, decision_refs)
        action = emit("action", {"action": decision.action.model_dump()}, (observation.event_id, plan.event_id))
        before_all = world.snapshot()
        before = next(state for state in before_all.agents if state.agent_id == actor) if multi else before_all
        if decision.action.type == "move":
            result = world.move(decision.action.direction, actor) if multi else world.move(decision.action.direction)
        elif decision.action.type == "collect":
            result = world.collect(actor) if multi else world.collect()
        elif multi and decision.action.type == "send_message":
            result = world.send_message(actor, decision.action.recipient, decision.action.message)
        else:
            result = world.wait(actor) if multi else world.wait()
        after_all = world.snapshot()
        sent_messages = after_all.messages[len(before_all.messages):] if multi else ()
        for message in sent_messages:
            sent_event = emit("message_send", {"message": message.__dict__}, (action.event_id,))
            send_refs[message.message_id] = sent_event.event_id
        after = next(state for state in after_all.agents if state.agent_id == actor) if multi else after_all
        delta_payload = {
            "success": result.success, "message": result.message,
            "position": {"before": before.position, "after": after.position},
            "inventory": {"before": before.inventory, "after": after.inventory},
            "removed_resources": sorted(set(before_all.resources) - set(after_all.resources)),
            "goal_complete": {"before": before.goal_complete, "after": after.goal_complete},
            "changed_cells": sorted(({before.position, after.position} if before.position != after.position else set())
                                    | (set(before_all.resources) - set(after_all.resources))),
        }
        if multi:
            delta_payload["messages_sent"] = [message.message_id for message in sent_messages]
            delta_payload["messages_delivered"] = [message.message_id for message in incoming]
            # A collection can change a rival's goal status without changing its inventory.
            delta_payload["agent_goal_changes"] = [
                {"agent_id": old.agent_id, "before": old.goal_complete, "after": new.goal_complete}
                for old, new in zip(before_all.agents, after_all.agents)
                if old.goal_complete != new.goal_complete
            ]
        delta = emit("environment_delta", delta_payload, (action.event_id, *receipt_refs, *(send_refs[message.message_id] for message in sent_messages)))
        if multi:
            write_memory(f"{result.message} Position ({after.position[0]}, {after.position[1]}). Inventory {after.inventory}.",
                         "action_result", delta.event_id)
        states.append(after_all)
        histories[actor].append((MultiHistoryEntry if multi else HistoryEntry)(turn=turn, action=decision.action, success=result.success, message=result.message))
        plans[actor] = decision.plan
        if not result.success:
            emit("error", {"stage": "environment", "message": result.message}, (action.event_id, delta.event_id))
        if scenario:
            for payload in scenario.after_turn(before_all, after_all, actor):
                emit("target_occupied", payload, (delta.event_id,))
        completed = all(state.goal_complete for state in after_all.agents) if multi else after.goal_complete
        if scenario:
            completed = scenario.is_complete(after_all)
        if completed:
            payload = {"completed_agents": schedule} if multi else {"inventory": after.inventory, "position": after.position}
            emit("goal_complete", payload, (delta.event_id,))
            if scenario:
                emit("scenario_complete", payload, (delta.event_id,))
            status = "goal_complete"
            break
        if multi and (scenario.exhausted(after_all) if scenario else not after_all.resources):
            status = "resources_exhausted"
            break

    # Persist the execution mode so replay never labels model decisions as mock behavior.
    modes = {getattr(agent, "recording_mode", None) for agent in agents.values()}
    metadata_data = dict(agent_mode=next(iter(modes)) if len(modes) == 1 else None, run_id=run_id, created_at=created_at,
                         agent="MultiAgent" if multi else type(agents["agent-1"]).__name__,
                         goal=scenario.name if scenario else ("Resource Race" if multi else GOAL),
                         status=status, turns=len(states) - 1, max_turns=max_turns)
    if scenario:
        metadata_data.update(scenario_id=scenario.id, scenario_name=scenario.name)
    metadata = MultiMetadata(agents=world.configs, schedule=schedule, **metadata_data) if multi else Metadata(**metadata_data)
    run = (MultiRecordedRun if multi else RecordedRun)(metadata=metadata, events=tuple(events), states=tuple(states))
    (store if store is not None else RunStore()).save(run)
    return run


if __name__ == "__main__":
    from app.agent.mock_agent import MockAgent

    recording = run_simulation(MockAgent())
    print(f"{recording.metadata.run_id}: {recording.metadata.status}, {recording.metadata.turns} turns")
