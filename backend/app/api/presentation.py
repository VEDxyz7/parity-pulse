"""Offline scenario-only calculations. No execution, provider ingestion or production writes."""

from fastapi import APIRouter, HTTPException, Request

from app.models.presentation import (
    PresentationAnalysis,
    PresentationScan,
    PresentationWorkspace,
    ScanRequest,
    ScenarioRequest,
)
from app.models.routing import RouteDecision

router = APIRouter(prefix="/api/presentation", tags=["isolated presentation scenarios"])


@router.get("/workspace", response_model=PresentationWorkspace)
def workspace(request: Request):
    return request.app.state.presentation.workspace()


@router.post("/research", response_model=PresentationAnalysis)
def research(body: ScenarioRequest, request: Request):
    service = request.app.state.presentation
    return service.save(service.analyze(body))


@router.get("/research/{identifier}", response_model=PresentationAnalysis)
def inspect(identifier: str, request: Request):
    try:
        return request.app.state.presentation.inspect(identifier)
    except LookupError:
        raise HTTPException(404, "Run the scenario again to restore this saved study.") from None


@router.post("/scan", response_model=PresentationScan)
def scan(body: ScanRequest, request: Request):
    return request.app.state.presentation.scan(body)


@router.post("/exposure", response_model=RouteDecision)
def exposure(body: ScenarioRequest, request: Request):
    return request.app.state.presentation.exposure(body.ticker, body.budget)
