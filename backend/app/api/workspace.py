"""Bounded Phase 15 inspection, with no provider refresh or wallet-worker invocation."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from app.models.agent_api import PortfolioState, PositionView, project_portfolio
from app.models.data import DataModel
from app.models.demo_sandbox import DemoProductionGates
from app.services.audit import safe_record


class WalletAvailability(DataModel):
    status: Literal["WALLET_UNAVAILABLE", "UNKNOWN"]
    connection: Literal["UNKNOWN"] = "UNKNOWN"
    address: None = None
    balance: None = None
    source: Literal["PUBLIC_RUNTIME_CAPABILITY"] = "PUBLIC_RUNTIME_CAPABILITY"
    reasons: tuple[str, ...]
    execution_ready: Literal[False] = False


class WorkspaceState(DataModel):
    schema_version: Literal["workspace-1"] = "workspace-1"
    data_mode: Literal["DEMO", "LIVE_READ_ONLY"]
    generated_at: datetime
    run_id: str
    request_id: str
    correlation_id: str
    portfolio: PortfolioState
    positions: tuple[PositionView, ...] = Field(max_length=100)
    position_history_complete: bool
    wallet: WalletAvailability
    production_gates: DemoProductionGates = DemoProductionGates()
    routing_status: Literal["PRODUCTION_CAPABLE_PROVIDER_PARTIAL"] = (
        "PRODUCTION_CAPABLE_PROVIDER_PARTIAL"
    )
    approval_status: Literal["PUBLIC_APPROVAL_UNAVAILABLE"] = "PUBLIC_APPROVAL_UNAVAILABLE"
    simulation_status: Literal["EXACT_LIVE_EQUIVALENCE_UNVERIFIED"] = (
        "EXACT_LIVE_EQUIVALENCE_UNVERIFIED"
    )
    execution_mode: Literal["DRY_RUN"] = "DRY_RUN"
    approval_mode: Literal["PROPOSE_ONLY"] = "PROPOSE_ONLY"
    execution_ready: Literal[False] = False
    broadcast: Literal[False] = False
    live_trading_enabled: Literal[False] = False
    require_simulation: Literal[True] = True
    source: Literal["EXISTING_PORTFOLIO_POSITION_AND_HOST_CAPABILITIES"] = (
        "EXISTING_PORTFOLIO_POSITION_AND_HOST_CAPABILITIES"
    )


router = APIRouter(prefix="/api/workspace", tags=["non-executable workspace inspection"])


@router.get("", response_model=WorkspaceState)
def workspace(request: Request):
    if request.query_params:
        raise HTTPException(422)
    state = request.app.state
    try:
        # The public backend intentionally has no authenticated CLI worker. Do not probe one.
        adapter = getattr(state.safety_execution.gateway, "adapter", None)
        client = adapter.client if adapter is not None else None
        result = WorkspaceState(
            data_mode=state.settings.data_mode,
            generated_at=datetime.now(UTC),
            run_id=state.run_id,
            request_id=request.state.request_id,
            correlation_id=request.state.correlation_id,
            portfolio=project_portfolio(state.portfolio.state()),
            positions=tuple(
                PositionView(**{k: getattr(p, k) for k in PositionView.model_fields})
                for p in state.positions.store.list(mode=state.positions.mode, limit=100)
            ),
            position_history_complete=state.positions.store.count(mode=state.positions.mode) <= 100,
            wallet=WalletAvailability(
                status="WALLET_UNAVAILABLE" if client is None else "UNKNOWN",
                reasons=("WORKER_UNAVAILABLE",)
                if client is None
                else ("HOST_WORKER_NOT_EXPOSED_BY_PUBLIC_API",),
            ),
        )
        safe_record(result, state.settings.redaction_values())
        return result
    except (ValueError, LookupError, ArithmeticError, OSError, TypeError):
        raise HTTPException(503, "Workspace inspection unavailable; no substitution") from None
