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


@router.get("/rfq/captures")
def rfq_captures(request: Request):
    return runtime(request).journal.rfq_captures(50)


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


IN_FLIGHT = {"PREPARING", "QUOTED", "APPROVING", "SIGNED", "SUBMITTED"}


@router.post("/plans/{plan_id}/retire")
def retire(plan_id: str, request: Request):
    """Release a pending plan after a terminal non-success leg (e.g. an expired RFQ order).

    Refused while any leg could still settle; those must reconcile first (rerun execute).
    """
    live = runtime(request)
    legs = live.journal.for_plan(plan_id)
    if any(leg["status"] in IN_FLIGHT for leg in legs):
        raise HTTPException(409, "LEG_IN_FLIGHT_RECONCILE_FIRST")
    portfolio = request.app.state.portfolio
    try:
        plan = portfolio.retire(plan_id)
    except LookupError:
        raise HTTPException(404) from None
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    return {"plan_id": plan_id, "plan_status": plan.status, "legs": legs}
