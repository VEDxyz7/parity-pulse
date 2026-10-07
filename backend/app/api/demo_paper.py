"""Synthetic paper fills only; this router is absent from the ordinary runtime."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from app.models.demo_paper import (
    PaperExitRequest,
    PaperFillRequest,
    PaperLifecycle,
    PaperMonitorRequest,
    PaperScorecard,
)

router = APIRouter(prefix="/api/demo/paper", tags=["synthetic paper ledger"])


def ledger(request):
    if request.app.state.settings.runtime_mode != "DEMO" or request.query_params:
        raise HTTPException(404)
    return request.app.state.demo_paper


def invoke(request, method, *args):
    try:
        return getattr(ledger(request), method)(*args)
    except LookupError:
        raise HTTPException(410) from None
    except ValueError:
        raise HTTPException(409) from None


@router.post("/fills", response_model=PaperLifecycle)
def fill(body: PaperFillRequest, request: Request):
    return invoke(request, "fill", body.transaction_id, body.simulation_id)


@router.get("/positions/{position_id}", response_model=PaperLifecycle)
def position(position_id: UUID, request: Request):
    return invoke(request, "get", position_id)


@router.post("/positions/{position_id}/monitor", response_model=PaperLifecycle)
def monitor(position_id: UUID, request: Request, body: PaperMonitorRequest | None = None):
    return invoke(request, "monitor", position_id)


@router.post("/positions/{position_id}/exit", response_model=PaperLifecycle)
def exit(position_id: UUID, body: PaperExitRequest, request: Request):
    return invoke(request, "exit", position_id, body.observation_id)


@router.get("/positions/{position_id}/scorecard", response_model=PaperScorecard)
def scorecard(position_id: UUID, request: Request):
    return invoke(request, "scorecard", position_id)
