"""Allowlisted status views and authenticated local-worker boundaries; gates stay blocked."""

import hmac
import ipaddress
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.models.live import ExecutePlanRequest, PublicFill
from app.services.execution_gates import LIVE_GATES, LiveExecutionError

router = APIRouter(prefix="/api/live", tags=["gated execution worker"])


def failure(code, status=409):
    return JSONResponse({"error": {"code": code}}, status_code=status)


def authorized(request):
    """Reuse single-user loopback/Host/Origin policy, plus a dedicated worker credential.

    No browser receives this credential. Forwarded identities are never trusted.
    """
    token = request.app.state.settings.execution_worker_token
    try:
        origin = urlsplit(request.headers.get("origin", ""))
        local = (
            request.client is not None
            and ipaddress.ip_address(request.client.host).is_loopback
            and request.url.hostname in {"localhost", "127.0.0.1", "::1"}
            and not any(
                k in request.headers for k in ("forwarded", "x-forwarded-for", "x-forwarded-host")
            )
            and (
                "origin" not in request.headers
                or (
                    origin.scheme == request.url.scheme
                    and origin.netloc == request.url.netloc
                    and not origin.path
                    and not origin.query
                    and not origin.fragment
                )
            )
            and not request.query_params
        )
    except ValueError:
        local = False
    supplied = request.headers.get("x-execution-worker-token", "")
    return bool(local and token and hmac.compare_digest(token.get_secret_value(), supplied))


@router.get("/status")
def status(request: Request):
    return request.app.state.live.status()


@router.get("/fills", response_model=list[PublicFill])
def fills(request: Request):
    return [PublicFill.from_record(r) for r in request.app.state.live.journal.recent(100)]


@router.get("/plans/{plan_id}/fills", response_model=list[PublicFill])
def plan_fills(plan_id: str, request: Request):
    return [PublicFill.from_record(r) for r in request.app.state.live.journal.for_plan(plan_id)]


@router.get("/rfq/captures")
def captures(request: Request):
    # Authenticated diagnostics expose metadata/integrity only; never raw signing payloads.
    if not authorized(request):
        return failure("EXECUTION_WORKER_ACCESS_DENIED", 403)
    return request.app.state.live.journal.rfq_captures(50)


@router.post("/plans/{plan_id}/execute")
def execute(plan_id: str, body: ExecutePlanRequest, request: Request):
    if not authorized(request):
        return failure("EXECUTION_WORKER_ACCESS_DENIED", 403)
    runtime = request.app.state.live
    prepared = runtime.prepared.get(plan_id)
    if not prepared:
        return failure("SERVER_PREPARED_PAYLOAD_REQUIRED")
    try:
        for leg in prepared:
            LIVE_GATES.require(leg.route.quote.route.executionMode, wallet=True)
        if runtime.executor is None:
            return failure("VERIFIED_EXECUTION_WORKER_UNAVAILABLE")
        for consent in body.confirmations:
            runtime.journal.confirm(consent, now=runtime.executor.clock())
        results = runtime.executor.execute(
            plan_id, prepared=prepared, confirmations=body.confirmations
        )
        return {"plan_id": plan_id, "legs": [PublicFill.from_record(r) for r in results]}
    except LiveExecutionError as error:
        return failure(error.code)
    except (ValueError, LookupError):
        return failure("INVALID_OR_STALE_EXECUTION_CONFIRMATION")


@router.post("/actions/{action_id}/reconcile")
def reconcile(action_id: str, request: Request):
    if not authorized(request):
        return failure("EXECUTION_WORKER_ACCESS_DENIED", 403)
    worker = request.app.state.live.executor
    if worker is None:
        return failure("READ_ONLY_RECONCILIATION_WORKER_UNAVAILABLE")
    try:
        return PublicFill.from_record(worker.reconcile(action_id))
    except LookupError:
        return failure("EXECUTION_UNAVAILABLE", 404)


@router.post("/plans/{plan_id}/retire")
def retire(plan_id: str, request: Request):
    if not authorized(request):
        return failure("EXECUTION_WORKER_ACCESS_DENIED", 403)
    if request.app.state.live.journal.unresolved(plan_id):
        return failure("LEG_UNRESOLVED_RECONCILE_FIRST")
    try:
        plan = request.app.state.portfolio.retire(plan_id)
        return {"plan_id": str(plan.plan_id), "plan_status": plan.status}
    except (ValueError, LookupError):
        return failure("PLAN_RETIREMENT_REJECTED")
