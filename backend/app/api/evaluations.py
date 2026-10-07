"""Comparison endpoints read saved evidence and never execute agents."""
import json
from fastapi import APIRouter, HTTPException, Query, Request
from app.evaluation.compare import compare
from app.evaluation.run import ROOT
router = APIRouter(prefix='/evaluations', tags=['evaluations'])


@router.get('')
def list_evaluations():
    try:
        return sorted([json.loads(path.read_text()) for path in ROOT.glob('eval-*.json')],
                      key=lambda item: item['created_at'], reverse=True)
    except (OSError, ValueError):
        raise HTTPException(500, 'Evaluation reports could not be read.') from None


@router.get('/compare')
def compare_runs(request: Request, left: str = Query(pattern=r'^run-[a-zA-Z0-9-]+$'), right: str = Query(pattern=r'^run-[a-zA-Z0-9-]+$')):
    try:
        store = request.app.state.run_store
        return compare(store.load(left), store.load(right))
    except FileNotFoundError:
        raise HTTPException(404, 'Run not found.') from None
    except (OSError, ValueError):
        raise HTTPException(500, 'Comparison could not be read.') from None
