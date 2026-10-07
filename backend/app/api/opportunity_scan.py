"""Analytical opportunity scans only. Production navigation and execution gates are unchanged."""

import asyncio
import re

from fastapi import APIRouter, HTTPException, Request

from app.models.opportunity_scan import OpportunityRequest, OpportunityScan

router = APIRouter(prefix="/api/opportunities", tags=["non-executable opportunity analysis"])


@router.post("/scan", response_model=OpportunityScan)
async def scan(body: OpportunityRequest, request: Request):
    if request.query_params or any(
        secret in body.model_dump_json() for secret in request.app.state.settings.redaction_values()
    ):
        raise HTTPException(422)
    state = request.app.state
    if body.demo_scenario is not None and state.settings.runtime_mode != "DEMO":
        raise HTTPException(422)
    if state.opportunity_scan_lock.locked():
        raise HTTPException(409)
    async with state.opportunity_scan_lock:
        snapshot = await asyncio.to_thread(
            state.opportunity_source.capture, body, state.opportunity_scan.policy
        )
        return await state.opportunity_scan.scan(body, snapshot)


@router.get("/{run_id}", response_model=OpportunityScan)
def retrieve(run_id: str, request: Request):
    if request.query_params or not re.fullmatch(r"[a-f0-9]{64}", run_id):
        raise HTTPException(422)
    mode = "DEMO" if request.app.state.settings.data_mode == "DEMO" else "LIVE_READ_ONLY"
    try:
        return request.app.state.opportunity_scan_store.get(run_id, mode=mode)
    except LookupError:
        raise HTTPException(404) from None
