"""Schemas for observable artifacts, without hidden reasoning fields."""

from datetime import datetime
import json
from hashlib import sha256
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.environment.grid_world import Direction, Observation, WorldState


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Move(Model):
    type: Literal["move"]
    direction: Direction


class Collect(Model):
    type: Literal["collect"]


class Wait(Model):
    type: Literal["wait"]


Action = Annotated[Move | Collect | Wait, Field(discriminator="type")]


class AgentDecision(Model):
    plan: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    action: Action


class HistoryEntry(Model):
    turn: int
    action: Action
    success: bool
    message: str


class AgentContext(Model):
    goal: str
    observation: Observation
    inventory: int
    previous_plan: str | None
    recent_history: tuple[HistoryEntry, ...]


class ObservationPayload(Model):
    context: AgentContext
    sources: dict[str, str | tuple[str, ...]] = {}


class PlanPayload(Model):
    plan: str = Field(min_length=1, max_length=2000, pattern=r"\S")


class ActionPayload(Model):
    action: Action


class PositionChange(Model):
    before: tuple[int, int]
    after: tuple[int, int]


class InventoryChange(Model):
    before: int = Field(ge=0)
    after: int = Field(ge=0)


class GoalChange(Model):
    before: bool
    after: bool


class DeltaPayload(Model):
    success: bool
    message: str
    position: PositionChange
    inventory: InventoryChange
    removed_resources: tuple[tuple[int, int], ...]
    goal_complete: GoalChange
    changed_cells: tuple[tuple[int, int], ...]


class CompletionPayload(Model):
    inventory: int = Field(ge=3)
    position: tuple[int, int]


class ErrorPayload(Model):
    stage: Literal["decision", "environment"]
    message: str
    error_type: str | None = None


class ModelCallPayload(Model):
    model: str
    settings: dict[str, Any]
    system_instructions: str
    prompt_version: str
    prompt_sha256: str
    context_json: str
    validated_response: dict[str, Any] | None
    usage: dict[str, int] = {}
    duration_ms: float = Field(ge=0)
    error_category: str | None = None


PAYLOAD_MODELS = {"model_call": ModelCallPayload, "observation": ObservationPayload, "plan": PlanPayload, "action": ActionPayload,
                  "environment_delta": DeltaPayload, "goal_complete": CompletionPayload, "error": ErrorPayload}


class Event(Model):
    event_id: str
    run_id: str
    turn: int = Field(ge=1, le=50)
    agent_id: str = "agent-1"
    type: Literal["observation", "plan", "action", "environment_delta", "goal_complete", "error", "model_call"]
    timestamp: datetime
    payload: dict[str, Any]
    input_refs: tuple[str, ...] = ()
    effect_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_payload(self) -> "Event":
        # Reject malformed saved artifacts before the browser reads their fields.
        PAYLOAD_MODELS[self.type].model_validate(self.payload)
        return self


class Metadata(Model):
    agent_mode: Literal["mock", "llm", "langchain"] | None = None
    schema_version: Literal[1] = 1
    scenario_id: str = "tutorial"
    scenario_name: str = "Tutorial — Resource Collection"
    run_id: str
    created_at: datetime
    agent: str
    goal: str
    status: Literal["goal_complete", "turn_limit", "error"]
    turns: int = Field(ge=0, le=50)
    max_turns: int = Field(ge=1, le=50)


class RecordedRun(Model):
    metadata: Metadata
    events: tuple[Event, ...]
    states: tuple[WorldState, ...]

    @model_validator(mode="after")
    def validate_recording(self) -> "RecordedRun":
        if len(self.states) != self.metadata.turns + 1:
            raise ValueError("Snapshot count does not match completed turns.")
        if any(state.turn != index for index, state in enumerate(self.states)):
            raise ValueError("Snapshot turns are not consecutive.")
        by_id = {event.event_id: event for event in self.events}
        if len(by_id) != len(self.events):
            raise ValueError("Event IDs are not unique.")
        seen: set[str] = set()
        for event in self.events:
            if event.run_id != self.metadata.run_id:
                raise ValueError("Event belongs to another run.")
            for reference in event.input_refs:
                if reference not in seen or event.event_id not in by_id[reference].effect_refs:
                    raise ValueError("Input reference is missing, unordered, or inconsistent.")
            for reference in event.effect_refs:
                if reference not in by_id or event.event_id not in by_id[reference].input_refs:
                    raise ValueError("Effect reference is missing or inconsistent.")
            if event.type == "observation" and event.payload.get("sources") is not None:
                context, sources = event.payload["context"], event.payload["sources"]
                if set(context) != set(sources):
                    raise ValueError("Every context field needs a source or external-input label.")
                for source in sources.values():
                    if isinstance(source, str):
                        if not source.startswith(("snapshot:", "metadata:", "external:")):
                            raise ValueError("Unknown external input source.")
                    elif any(ref not in event.input_refs for ref in source):
                        raise ValueError("Context sources must appear in provenance references.")
                previous = [item for item in self.events if item.event_id in seen and item.agent_id == event.agent_id and item.type == "plan"]
                expected_plan = previous[-1:] if context["previous_plan"] is not None else []
                if tuple(sources["previous_plan"]) != tuple(item.event_id for item in expected_plan):
                    raise ValueError("Previous plan source is incorrect.")
                if expected_plan and expected_plan[0].payload["plan"] != context["previous_plan"]:
                    raise ValueError("Previous plan differs from its source.")
                history_refs = sources["recent_history"]
                if len(history_refs) != 2 * len(context["recent_history"]):
                    raise ValueError("History must link each action and result.")
                for index, entry in enumerate(context["recent_history"]):
                    action, result = (by_id[ref] for ref in history_refs[index*2:index*2+2])
                    if action.type != "action" or result.type != "environment_delta" or action.agent_id != event.agent_id or result.agent_id != event.agent_id or action.turn != entry["turn"] or action.payload["action"] != entry["action"] or result.payload["success"] != entry["success"] or result.payload["message"] != entry["message"]:
                        raise ValueError("Recorded history differs from its referenced artifacts.")
            if event.type == "model_call":
                calls = [by_id[ref] for ref in event.input_refs if by_id[ref].type == "observation"]
                if len(calls) != 1 or calls[0].agent_id != event.agent_id or calls[0].turn != event.turn or json.loads(event.payload["context_json"]) != calls[0].payload["context"]:
                    raise ValueError("Model request must match the recorded context.")
                response = event.payload["validated_response"]
                if response is not None:
                    decisions = [item for item in self.events if item.agent_id == event.agent_id and item.turn == event.turn]
                    plans = [item for item in decisions if item.type == "plan"]
                    actions = [item for item in decisions if item.type == "action"]
                    if len(plans) != 1 or len(actions) != 1 or response != {"plan": plans[0].payload["plan"], "action": actions[0].payload["action"]}:
                        raise ValueError("Model response does not match the executed decision.")
                if sha256(event.payload["system_instructions"].encode()).hexdigest() != event.payload["prompt_sha256"]:
                    raise ValueError("Prompt fingerprint mismatch.")
            seen.add(event.event_id)
        return self
