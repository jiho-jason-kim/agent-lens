"""One private store per agent. No provider or global state is used during retrieval."""

import re
from typing import Literal

from pydantic import Field

from app.models.recording import Model


class Memory(Model):
    memory_id: str
    agent_id: str
    content: str = Field(min_length=1)
    source_type: Literal["observation", "message", "action_result", "scenario_instruction"]
    source_event_id: str
    created_turn: int = Field(ge=1)
    last_accessed_turn: int | None = None
    access_count: int = Field(default=0, ge=0)
    resource_position: tuple[int, int] | None = None


class MemoryWritePayload(Model):
    memory: Memory


class MemoryRetrievalPayload(Model):
    memory_ids: tuple[str, ...]
    memories: tuple[Memory, ...]
    scores: tuple[int, ...]
    query: str


def retrieval_score(memory: Memory, query: str, turn: int) -> int:
    tokens = lambda text: set(re.findall(r"[a-z0-9]+", text.lower()))
    overlap = len(tokens(memory.content) & tokens(query))
    recency = max(0, 20 - (turn - memory.created_turn))
    source_weight = {"scenario_instruction": 8, "message": 8, "observation": 4, "action_result": 1}[memory.source_type]
    return recency + source_weight + 4 * overlap


def possibly_stale(memory: Memory, resources: tuple[tuple[int, int], ...]) -> bool:
    """Debugger-only check. Never feed this global assessment into agent context."""
    return memory.resource_position is not None and memory.resource_position not in resources


class PrivateMemory:
    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self._memories: dict[str, Memory] = {}

    def write(self, *, content: str, source_type: str, source_event_id: str, turn: int,
              resource_position: tuple[int, int] | None = None) -> Memory:
        memory = Memory(memory_id=f"M-{self.agent_id}-{len(self._memories) + 1:04d}", agent_id=self.agent_id,
                        content=content, source_type=source_type, source_event_id=source_event_id,
                        created_turn=turn, resource_position=resource_position)
        self._memories[memory.memory_id] = memory
        return memory

    def retrieve(self, query: str, turn: int) -> tuple[tuple[Memory, ...], tuple[int, ...]]:
        # Stable IDs break score ties. Retrieval never consults other agents or global truth.
        ranked = sorted(self._memories.values(),
                        key=lambda memory: (-retrieval_score(memory, query, turn), memory.memory_id))[:4]
        retrieved = tuple(memory.model_copy(update={"access_count": memory.access_count + 1,
                                                    "last_accessed_turn": turn}) for memory in ranked)
        for memory in retrieved:
            self._memories[memory.memory_id] = memory
        return retrieved, tuple(retrieval_score(memory, query, turn) for memory in retrieved)
