"""Analytical GET only; no writable history or execution endpoints."""

import re

from fastapi import APIRouter, HTTPException, Request

from app.models.trust import TrustAssessment

router = APIRouter(prefix="/api", tags=["read-only trust"])


@router.get("/assets/{ticker}/trust", response_model=TrustAssessment)
def trust(ticker: str, request: Request):
    if (
        not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,14}", ticker)
        or request.query_params
        or any(value in ticker for value in request.app.state.settings.redaction_values())
    ):
        raise HTTPException(422)
    return request.app.state.trust.assess(
        ticker,
        run_id=request.app.state.run_id,
        request_id=request.state.request_id,
        correlation_id=request.state.correlation_id,
    )
