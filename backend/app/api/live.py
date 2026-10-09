"""Live wallet-inventory rebalance: status, fills journal and explicit plan execution."""

from fastapi import APIRouter, HTTPException, Request

from app.services.live_execution import LiveExecutionError

router = APIRouter(prefix="/api/live", tags=["live wallet rebalance"])


def runtime(request):
    if request.query_params:
        raise HTTPException(422)
    live = getattr(request.app.state, "live", None)
    if live is None:
        raise HTTPException(404, "Wallet inventory is not configured")
    return live


@router.get("/status")
def status(request: Request):
    return runtime(request).status()


@router.get("/parity/{ticker}")
def parity(ticker: str, request: Request):
    from app.clients.common import ProviderError
    from app.services.live_wiring import parity as compute

    if not ticker.isalnum() or len(ticker) > 15:
        raise HTTPException(422)
    try:
        return compute(runtime(request), ticker)
    except ProviderError as error:
        raise HTTPException(503, error.kind) from None


@router.get("/fills")
def fills(request: Request):
    return runtime(request).journal.recent(100)


@router.get("/plans/{plan_id}/fills")
def plan_fills(plan_id: str, request: Request):
    return runtime(request).journal.for_plan(plan_id)


@router.post("/plans/{plan_id}/execute")
def execute(plan_id: str, request: Request):
    live = runtime(request)
    if live.executor is None:
        raise HTTPException(409, "LIVE execution is not enabled")
    try:
        legs = live.executor.execute(plan_id)
    except LookupError:
        raise HTTPException(404) from None
    except LiveExecutionError as error:
        raise HTTPException(409, error.code) from None
    plan = request.app.state.portfolio.store.get(plan_id, mode=request.app.state.portfolio.mode)
    return {"plan_id": plan_id, "plan_status": plan.status, "legs": legs}
