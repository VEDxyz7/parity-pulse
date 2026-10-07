"""Analytical POSTs only, conditionally registered in RUNTIME_MODE=DEMO."""

from fastapi import APIRouter, HTTPException, Request

from app.models.demo_opportunity import (
    DemoOpportunityResult,
    DemoRiskResult,
    OpportunityRequest,
    RiskRequest,
)

router = APIRouter(prefix="/api/demo", tags=["synthetic opportunity analysis"])


def flow(request):
    if request.app.state.settings.runtime_mode != "DEMO" or request.query_params:
        raise HTTPException(404)
    return request.app.state.demo_opportunity


@router.post("/opportunity", response_model=DemoOpportunityResult)
def opportunity(body: OpportunityRequest, request: Request):
    try:
        return flow(request).opportunity(body.trust_assessment_id)
    except LookupError:
        raise HTTPException(410) from None


@router.post("/risk", response_model=DemoRiskResult)
def risk(body: RiskRequest, request: Request):
    try:
        return flow(request).risk(body.opportunity_id)
    except LookupError:
        raise HTTPException(410) from None
