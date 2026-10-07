"""Create the bounded example or read saved workflow evidence."""
from typing import Annotated, Literal
from fastapi import APIRouter, HTTPException, Path, Request
from app.agent.openai_provider import ProviderConfigurationError
from app.models.recording import Model
from app.models.workflow import WorkflowMetadata, WorkflowRecording

router = APIRouter(prefix='/workflows', tags=['workflows'])
WorkflowId = Annotated[str, Path(pattern=r'^workflow-[a-zA-Z0-9-]+$')]


class DemoRequest(Model):
    mode: Literal['demo', 'live'] = 'demo'


@router.get('', response_model=list[WorkflowMetadata])
def list_workflows(request: Request):
    try:
        return request.app.state.workflow_store.list_runs()
    except (OSError, ValueError):
        raise HTTPException(500, 'Workflow recordings could not be read.') from None


@router.post('/demo', response_model=WorkflowRecording, status_code=201)
def create_demo(request: Request, options: DemoRequest):
    try:
        from app.workflows.reservation import run_reservation
        return run_reservation(mode=options.mode, store=request.app.state.workflow_store)
    except ImportError:
        raise HTTPException(503, 'Install backend/requirements-langchain.txt to record workflows.') from None
    except ProviderConfigurationError as exc:
        raise HTTPException(503, str(exc)) from None
    except Exception:
        raise HTTPException(500, 'The workflow could not be recorded.') from None


@router.get('/{run_id}', response_model=WorkflowRecording)
def get_workflow(run_id: WorkflowId, request: Request):
    try:
        return request.app.state.workflow_store.load(run_id)
    except FileNotFoundError:
        raise HTTPException(404, 'Workflow recording not found.') from None
    except (OSError, ValueError):
        raise HTTPException(500, 'Workflow recording could not be read.') from None
