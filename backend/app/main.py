"""FastAPI entry point. Importing the app does not start a simulation."""

from fastapi import FastAPI

from app.api.evaluations import router as evaluation_router
from app.api.runs import router
from app.api.workflows import router as workflow_router
from app.storage.workflow_store import WorkflowStore
from app.storage.json_store import RunStore
from app.scenarios.catalog import SCENARIOS


def create_app(store: RunStore | None = None, workflow_store: WorkflowStore | None = None) -> FastAPI:
    app = FastAPI(title="AI Agent Replay Debugger", version="0.1.0")
    # Tests can use temporary storage without changing production recordings.
    app.state.run_store = store if store is not None else RunStore()
    app.include_router(router)
    app.include_router(evaluation_router)
    app.state.workflow_store = workflow_store if workflow_store is not None else WorkflowStore()
    app.include_router(workflow_router)

    @app.get("/scenarios")
    def list_scenarios():
        return [dict(id=item.id, name=item.name, description=item.description, concepts=item.concepts,
                     agent_count=len(item.agents), max_turns=item.max_turns, width=item.width, height=item.height)
                for item in SCENARIOS]

    return app


app = create_app()
