"""Registered only in the explicit synthetic sandbox runtime; analytical GETs only."""

from fastapi import APIRouter, HTTPException, Request

from app.models.demo_sandbox import DemoCatalog, DemoTrustResult, ScenarioId

router = APIRouter(prefix="/api/demo/trust", tags=["synthetic demo sandbox"])


def sandbox(request):
    if request.app.state.settings.runtime_mode != "DEMO" or request.query_params:
        raise HTTPException(404)
    return request.app.state.demo_sandbox


@router.get("/scenarios", response_model=DemoCatalog)
def catalog(request: Request):
    return sandbox(request).catalog()


@router.get("/scenarios/{identifier}", response_model=DemoTrustResult)
def assess(identifier: ScenarioId, request: Request):
    return sandbox(request).assess(
        identifier,
        run_id=request.state.run_id,
        request_id=request.state.request_id,
        correlation_id=request.state.correlation_id,
    )
