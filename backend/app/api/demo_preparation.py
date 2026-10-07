"""DEMO-only analytical quote/prepare/simulate APIs. No order or wallet operation."""

from fastapi import APIRouter, HTTPException, Request

from app.models.demo_execution import (
    DemoPreparationResult,
    DemoQuoteResult,
    DemoSimulationResult,
    PreparationRequest,
    QuoteRequest,
    SimulationRequest,
)

router = APIRouter(prefix="/api/demo", tags=["synthetic quote and local simulation"])


def flow(request):
    if request.app.state.settings.runtime_mode != "DEMO" or request.query_params:
        raise HTTPException(404)
    return request.app.state.demo_preparation


@router.post("/quote", response_model=DemoQuoteResult)
def quote(body: QuoteRequest, request: Request):
    try:
        return flow(request).quote(body.risk_id)
    except LookupError:
        raise HTTPException(410) from None


@router.post("/prepare", response_model=DemoPreparationResult)
def prepare(body: PreparationRequest, request: Request):
    try:
        return flow(request).prepare(body.quote_id)
    except LookupError:
        raise HTTPException(410) from None


@router.post("/simulate", response_model=DemoSimulationResult)
def simulate(body: SimulationRequest, request: Request):
    try:
        return flow(request).simulate(body.transaction_id)
    except LookupError:
        raise HTTPException(410) from None
