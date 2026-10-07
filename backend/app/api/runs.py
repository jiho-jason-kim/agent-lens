"""Keep simulation execution confined to POST /runs."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from pydantic import Field

from app.agent.openai_provider import ProviderConfigurationError
from app.environment.grid_world import WorldState
from app.environment.multi_agent import MultiWorldState
from app.models.multi_recording import MultiEvent, MultiMetadata, MultiRecordedRun
from app.models.recording import Event, Metadata, Model, RecordedRun
from app.scenarios.run import run_scenario
from app.storage.json_store import RunStore

router = APIRouter(prefix="/runs", tags=["runs"])
RunId = Annotated[str, Path(pattern=r"^run-[a-zA-Z0-9-]+$")]


class CreateRunRequest(Model):
    scenario_id: Literal["handoff-race", "verified-handoff", "tutorial", "resource-race", "cooperation", "misinformation", "stale-memory", "hidden-information", "coordination"] = "tutorial"
    agent: Literal["mock", "llm", "langchain"] = "mock"
    max_turns: int = Field(default=50, ge=1, le=50, strict=True)


def get_store(request: Request) -> RunStore:
    return request.app.state.run_store


Store = Annotated[RunStore, Depends(get_store)]


def load_recording(run_id: str, store: Store) -> RecordedRun | MultiRecordedRun:
    try:
        return store.load(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Stored run could not be read.") from exc


@router.post("", response_model=MultiMetadata | Metadata, status_code=201)
def create_run(response: Response, store: Store, options: CreateRunRequest | None = None) -> Metadata | MultiMetadata:
    options = options or CreateRunRequest()
    try:
        run = run_scenario(options.scenario_id, agent_mode=options.agent, max_turns=options.max_turns, store=store)
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Run could not be saved.") from exc
    response.headers["Location"] = f"/runs/{run.metadata.run_id}"
    return run.metadata


@router.get("", response_model=list[MultiMetadata | Metadata])
def list_runs(store: Store, schema_version: Annotated[int, Query(ge=1, le=2)] = 1) -> list[Metadata | MultiMetadata]:
    try:
        # Keep the current tutorial UI on its supported schema until Phase E.
        return store.list_runs(schema_version=schema_version)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Stored runs could not be read.") from exc


@router.get("/{run_id}", response_model=MultiRecordedRun | RecordedRun)
def get_run(run_id: RunId, store: Store) -> RecordedRun | MultiRecordedRun:
    return load_recording(run_id, store)


@router.get("/{run_id}/events", response_model=tuple[MultiEvent | Event, ...])
def get_events(run_id: RunId, store: Store) -> tuple[Event | MultiEvent, ...]:
    return load_recording(run_id, store).events


@router.get("/{run_id}/states", response_model=tuple[MultiWorldState | WorldState, ...])
def get_states(run_id: RunId, store: Store) -> tuple[WorldState | MultiWorldState, ...]:
    return load_recording(run_id, store).states
