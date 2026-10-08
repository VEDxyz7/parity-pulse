"""Single-user configuration and non-executable deterministic planning only."""

from fastapi import APIRouter, HTTPException, Request

from app.models.portfolio import ConfigRequest, PlanRequest, PortfolioConfig, RebalancePlan

autopilot_router = APIRouter(
    prefix="/api/autopilot", tags=["non-executable autopilot configuration"]
)
router = APIRouter(prefix="/api/portfolio", tags=["non-executable portfolio planning"])


def checked(request, body=None):
    if request.query_params or (
        body
        and any(
            value in body.model_dump_json()
            for value in request.app.state.settings.redaction_values()
        )
    ):
        raise HTTPException(422)
    return request.app.state.portfolio


@autopilot_router.get("")
@router.get("")
def state(request: Request):
    return checked(request).state()


@autopilot_router.post("", response_model=PortfolioConfig)
@router.put("/config", response_model=PortfolioConfig)
def configure(body: ConfigRequest, request: Request):
    try:
        return checked(request, body).configure(
            body,
            expected_version=body.expected_version,
            request_id=request.state.request_id,
            correlation_id=request.state.correlation_id,
        )
    except ValueError:
        raise HTTPException(409) from None


@router.post("/drift", response_model=RebalancePlan)
@router.post("/plans", response_model=RebalancePlan)
def plan(body: PlanRequest, request: Request):
    # Both endpoints persist the same audited, idempotent decision; neither prepares an order.
    try:
        return checked(request, body).evaluate(
            idempotency_key=body.idempotency_key,
            request_id=request.state.request_id,
            correlation_id=request.state.correlation_id,
        )
    except (ValueError, LookupError):
        raise HTTPException(409) from None


@router.get("/pending")
def pending(request: Request):
    service = checked(request)
    plan = service.store.pending(mode=service.mode)
    return {
        "plan": plan,
        "actions": plan.actions if plan else [],
        "execution_mode": "DRY_RUN",
        "broadcast": False,
    }


@router.get("/audit")
def audit(request: Request):
    service = checked(request)
    return service.store.audit(mode=service.mode)


@router.get("/plans/{plan_id}", response_model=RebalancePlan)
def retrieve(plan_id: str, request: Request):
    try:
        return checked(request).store.get(plan_id, mode=request.app.state.portfolio.mode)
    except LookupError:
        raise HTTPException(404) from None
