"""Version-two recordings preserve independent contexts and complete shared snapshots."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.environment.multi_agent import AgentConfig, LocalObservation, Message, MultiWorldState
from app.memory.store import Memory, MemoryRetrievalPayload, MemoryWritePayload, retrieval_score
from app.models.recording import AgentContext, AgentDecision, Collect, DeltaPayload, Event, HistoryEntry, Metadata, Model, Move, PAYLOAD_MODELS, RecordedRun, Wait


class SendMessage(Model):
    type: Literal["send_message"]
    recipient: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=1000, pattern=r"\S")


MultiAction = Annotated[Move | Collect | Wait | SendMessage, Field(discriminator="type")]


class MultiAgentDecision(AgentDecision):
    action: MultiAction


class MultiHistoryEntry(HistoryEntry):
    action: MultiAction


class MultiAgentContext(AgentContext):
    agent_id: str
    turn: int = Field(ge=1, le=50)
    observation: LocalObservation
    scenario_instructions: tuple[str, ...] = ()
    recent_messages: tuple[Message, ...] = ()
    retrieved_memories: tuple[Memory, ...] = ()
    recent_history: tuple[MultiHistoryEntry, ...]


class MultiObservationPayload(Model):
    context: MultiAgentContext
    sources: dict[str, str | tuple[str, ...]] = {}


class MultiCompletionPayload(Model):
    completed_agents: tuple[str, ...]


class AgentGoalChange(Model):
    agent_id: str
    before: bool
    after: bool


class MultiDeltaPayload(DeltaPayload):
    agent_goal_changes: tuple[AgentGoalChange, ...]
    messages_sent: tuple[str, ...] = ()
    messages_delivered: tuple[str, ...] = ()


class MultiActionPayload(Model):
    action: MultiAction


class MessagePayload(Model):
    message: Message


class LocalObservationPayload(Model):
    observation: LocalObservation
    snapshot_turn: int | None = Field(default=None, ge=0)


class ScenarioInstruction(Model):
    content: str
    scenario_id: str
    inaccurate: bool


class TargetOccupied(Model):
    position: tuple[int, int]
    occupant: str


class MultiEvent(Event):
    type: Literal["observation", "plan", "action", "environment_delta", "goal_complete", "error", "message_send", "message_receive", "local_observation", "memory_write", "memory_retrieve", "scenario_instruction", "target_occupied", "scenario_complete", "model_call"]

    @model_validator(mode="after")
    def validate_payload(self) -> "MultiEvent":
        payload_type = {**PAYLOAD_MODELS, "observation": MultiObservationPayload, "goal_complete": MultiCompletionPayload,
                        "environment_delta": MultiDeltaPayload, "action": MultiActionPayload,
                        "message_send": MessagePayload, "message_receive": MessagePayload,
                        "local_observation": LocalObservationPayload, "memory_write": MemoryWritePayload,
                        "memory_retrieve": MemoryRetrievalPayload, "scenario_instruction": ScenarioInstruction,
                        "target_occupied": TargetOccupied, "scenario_complete": MultiCompletionPayload}[self.type]
        payload_type.model_validate(self.payload)
        if self.type == "observation":
            context = MultiAgentContext.model_validate(self.payload["context"])
            if context.agent_id != self.agent_id or context.turn != self.turn:
                raise ValueError("Observation context does not match the event actor and turn.")
        return self


class MultiMetadata(Metadata):
    schema_version: Literal[2] = 2
    scenario_id: str = "resource-race"
    scenario_name: str = "Resource Race"
    agents: tuple[AgentConfig, ...]
    schedule: tuple[str, ...]
    status: Literal["goal_complete", "resources_exhausted", "turn_limit", "error"]


class MultiRecordedRun(RecordedRun):
    metadata: MultiMetadata
    events: tuple[MultiEvent, ...]
    states: tuple[MultiWorldState, ...]

    @model_validator(mode="after")
    def validate_agents(self) -> "MultiRecordedRun":
        identities = tuple(agent.agent_id for agent in self.metadata.agents)
        if not identities or len(set(identities)) != len(identities) or set(identities) != set(self.metadata.schedule):
            raise ValueError("Agent identities and schedule must match.")
        if len(self.metadata.schedule) != len(identities):
            raise ValueError("Each agent must occur once in the schedule.")
        if any(tuple(agent.agent_id for agent in state.agents) != identities for state in self.states):
            raise ValueError("Each snapshot must contain all configured agents in order.")
        for event in self.events:
            expected = self.metadata.schedule[(event.turn - 1) % len(identities)]
            if event.agent_id != expected:
                raise ValueError("Event actor does not match the recorded schedule.")
        sent = {}
        received = set()
        receipts = {}
        by_id = {event.event_id: event for event in self.events}
        for event in self.events:
            if event.type == "message_send":
                message = MessagePayload.model_validate(event.payload).message
                if message.message_id in sent or message.sender_id != event.agent_id or message.sent_turn != event.turn:
                    raise ValueError("Invalid message sender, ID, or sent turn.")
                if message.recipient_id not in identities or message.sender_id == message.recipient_id or message.delivered_turn is not None:
                    raise ValueError("Invalid message recipient or premature delivery.")
                actions = [by_id[reference] for reference in event.input_refs if by_id[reference].type == "action"]
                if len(actions) != 1:
                    raise ValueError("Message send needs one action reference.")
                action = MultiActionPayload.model_validate(actions[0].payload).action
                if (actions[0].agent_id != message.sender_id or actions[0].turn != event.turn
                    or action.type != "send_message" or action.recipient != message.recipient_id or action.message != message.content):
                    raise ValueError("Message does not match its recorded action.")
                sent[message.message_id] = (event.event_id, message)
            elif event.type == "message_receive":
                message = MessagePayload.model_validate(event.payload).message
                source = sent.get(message.message_id)
                if not source or source[0] not in event.input_refs or message.message_id in received:
                    raise ValueError("Message receipt needs one matching send reference.")
                if (message.sender_id, message.recipient_id, message.content, message.sent_turn) != (
                    source[1].sender_id, source[1].recipient_id, source[1].content, source[1].sent_turn):
                    raise ValueError("Delivered message differs from the sent message.")
                if message.recipient_id != event.agent_id or message.delivered_turn != event.turn or event.turn <= message.sent_turn:
                    raise ValueError("Message delivered to the wrong agent or turn.")
                received.add(message.message_id)
                receipts.setdefault(event.turn, []).append((event.event_id, message))
            elif event.type == "observation":
                context = MultiAgentContext.model_validate(event.payload["context"])
                instructions = [item for item in self.events if item.turn == event.turn and item.type == "scenario_instruction"]
                if context.scenario_instructions != tuple(item.payload["content"] for item in instructions):
                    raise ValueError("Context instructions do not match scenario events.")
                if any(item.event_id not in event.input_refs for item in instructions):
                    raise ValueError("Context must reference scenario instructions.")
                available = receipts.get(event.turn, [])
                if context.recent_messages != tuple(message for _, message in available):
                    raise ValueError("Context messages do not match recorded deliveries.")
                if any(reference not in event.input_refs for reference, _ in available):
                    raise ValueError("Context must reference its message deliveries.")
        archive = {}
        for state in self.states:
            for event in self.events:
                if event.turn == state.turn and event.type in ("message_send", "message_receive"):
                    message = MessagePayload.model_validate(event.payload).message
                    archive[message.message_id] = message
            if state.messages != tuple(archive.values()):
                raise ValueError("Snapshot messages do not match recorded sends and receipts.")
        # Validate private memory provenance without executing retrieval or agents again.
        memories = {}
        writes = {}
        retrievals = {}
        for event in self.events:
            if event.type == "memory_write":
                memory = MemoryWritePayload.model_validate(event.payload).memory
                source = by_id.get(memory.source_event_id)
                expected_type = {"observation": "local_observation", "message": "message_receive", "action_result": "environment_delta", "scenario_instruction": "scenario_instruction"}[memory.source_type]
                if (memory.memory_id in memories or memory.agent_id != event.agent_id or memory.created_turn != event.turn
                    or not source or source.agent_id != event.agent_id or source.type != expected_type
                    or source.event_id not in event.input_refs or memory.access_count != 0 or memory.last_accessed_turn is not None):
                    raise ValueError("Invalid memory ownership or source reference.")
                if memory.source_type == "observation":
                    observed = LocalObservationPayload.model_validate(source.payload).observation
                    if not any(cell.resource and cell.position == memory.resource_position for cell in observed.cells):
                        raise ValueError("Memory resource was not in the source observation.")
                    x, y = memory.resource_position
                    content = f"Resource observed at ({x}, {y})."
                elif memory.source_type == "scenario_instruction":
                    content = source.payload["content"]
                elif memory.source_type == "message":
                    message = MessagePayload.model_validate(source.payload).message
                    content = f"{message.sender_id} reported: {message.content}"
                else:
                    result = MultiDeltaPayload.model_validate(source.payload)
                    x, y = result.position.after
                    content = f"{result.message} Position ({x}, {y}). Inventory {result.inventory.after}."
                if memory.content != content or (memory.source_type != "observation" and memory.resource_position is not None):
                    raise ValueError("Memory content does not match its source artifact.")
                memories[memory.memory_id] = memory
                writes[memory.memory_id] = event.event_id
            elif event.type == "memory_retrieve":
                payload = MemoryRetrievalPayload.model_validate(event.payload)
                if (len(payload.memories) > 4 or len(set(payload.memory_ids)) != len(payload.memory_ids)
                    or payload.memory_ids != tuple(memory.memory_id for memory in payload.memories)
                    or len(payload.scores) != len(payload.memories)):
                    raise ValueError("Invalid retrieval memory IDs or count.")
                ranked = sorted((memory for memory in memories.values() if memory.agent_id == event.agent_id),
                                key=lambda memory: (-retrieval_score(memory, payload.query, event.turn), memory.memory_id))[:4]
                if (payload.memory_ids != tuple(memory.memory_id for memory in ranked)
                    or payload.scores != tuple(retrieval_score(memory, payload.query, event.turn) for memory in ranked)):
                    raise ValueError("Retrieval does not match the recorded deterministic scoring policy.")
                for memory in payload.memories:
                    prior = memories.get(memory.memory_id)
                    if (not prior or prior.agent_id != event.agent_id or writes[memory.memory_id] not in event.input_refs
                        or memory != prior.model_copy(update={"access_count": prior.access_count + 1, "last_accessed_turn": event.turn})):
                        raise ValueError("Retrieved memory is unavailable or its content changed.")
                    memories[memory.memory_id] = memory
                retrievals[event.turn] = (event.event_id, payload.memories)
            elif event.type == "observation":
                context = MultiAgentContext.model_validate(event.payload["context"])
                retrieval = retrievals.get(event.turn)
                if context.retrieved_memories != (retrieval[1] if retrieval else ()):
                    raise ValueError("Context contains unrecorded retrieved memories.")
                if retrieval and retrieval[0] not in event.input_refs:
                    raise ValueError("Context must reference its retrieval event.")
        return self
