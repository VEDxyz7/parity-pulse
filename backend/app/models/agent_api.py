"""Phase 14 bounded client contracts; existing models remain the financial authorities."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BeforeValidator, Field, StrictInt, StrictStr, model_validator

from app.agents.schemas import Candidate, DecisionOutput, EvidenceRef, Ticker
from app.models.data import DataModel
from app.models.demo_sandbox import DemoProductionGates
from app.models.execution import FundingState
from app.models.exposure import ExposureProposal
from app.models.opportunity_scan import CandidateAudit, ScanPolicy, UniverseFilters
from app.models.portfolio import (
    DriftRow,
    PortfolioConfig,
    PreparationRecord,
    RebalanceAction,
)
from app.models.position import PositionInstrument, PositionState
from app.models.routing import RouteDecision
from app.models.terminal import IssuerRow, TerminalPage
from app.models.trust import TrustAssessment

ToolName = Literal[
    "buy_stock_exposure",
    "find_opportunity",
    "compare_stock_tokens",
    "get_stock_trust",
    "get_route",
    "get_portfolio",
    "get_autopilot_status",
]
Mode = Literal["DEMO", "LIVE_READ_ONLY"]


def money(value):
    import re

    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,18}(?:\.[0-9]{1,18})?", value):
        raise ValueError("Bounded decimal string required")
    return Decimal(value)


Money = Annotated[
    Decimal,
    BeforeValidator(
        money,
        json_schema_input_type=Annotated[
            str, Field(pattern=r"^[0-9]{1,18}(?:\.[0-9]{1,18})?$", max_length=37)
        ],
    ),
    Field(gt=0, le=Decimal("1000000000")),
]


class ReadInput(DataModel):
    data_mode: Mode | None = None


class StockInput(ReadInput):
    ticker: Ticker


class CompareInput(StockInput):
    limit: StrictInt = Field(default=25, ge=1, le=100)
    offset: StrictInt = Field(default=0, ge=0, le=10000)


class RouteInput(StockInput):
    amount_usd: Money


class ProposalInput(ReadInput):
    idempotency_key: UUID
    mode: Literal["PROPOSE_ONLY", "DRY_RUN", "LIVE"] = "PROPOSE_ONLY"


class BuyInput(ProposalInput):
    ticker: Ticker
    amount_usd: Money
    risk_budget_usd: Money


class FindInput(ProposalInput):
    budget_usd: Money
    risk_budget_usd: Money
    time_window: Literal["PRE_OPEN", "BEFORE_MONDAY"]
    universe: UniverseFilters = UniverseFilters()
    demo_scenario: Literal["steady", "thin-move", "supported-move"] | None = None


class PositionView(DataModel):
    position_id: UUID
    data_mode: Mode
    state: PositionState
    instrument: PositionInstrument
    filled_quantity_base_units: str
    remaining_quantity_base_units: str
    normalized_share_exposure: Decimal
    effective_cost_per_share_usd: Decimal | None
    gross_pnl_usd: Decimal | None
    net_pnl_usd: Decimal | None
    reasons: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


class PlanView(DataModel):
    plan_id: str
    data_mode: Mode
    config: PortfolioConfig
    total_value_usd: Decimal | None
    rows: tuple[DriftRow, ...]
    actions: tuple[RebalanceAction, ...]
    route_decisions: tuple[RouteDecision, ...]
    preparations: tuple[PreparationRecord, ...]
    status: str
    reasons: tuple[str, ...]
    request_id: UUID
    correlation_id: UUID
    created_at: datetime
    updated_at: datetime
    funding: FundingState | None
    captured_at: datetime


class PortfolioState(DataModel):
    """Typed shape of PortfolioService.state(), without recomputing allocations."""

    data_mode: Mode
    execution_mode: Literal["DRY_RUN"]
    config: PortfolioConfig | None
    pending_plan: PlanView | None
    latest_decision: PlanView | None
    active_positions: tuple[PositionView, ...] = Field(max_length=100)
    position_coverage_complete: bool
    recovery_complete: bool
    live_trading_enabled: Literal[False]
    inspection_only: Literal[True] = True


class PublicScan(DataModel):
    """Existing scan facts only; no private agent responses or interpretation summaries."""

    run_id: str
    decision_id: str
    correlation_id: str
    timestamp: datetime
    data_mode: Mode
    policy: ScanPolicy
    universe_count: int
    eligible_count: int
    rejected_count: int
    candidates: tuple[CandidateAudit, ...] = Field(max_length=500)
    top_k: tuple[Candidate, ...] = Field(max_length=5)
    selected_candidate: Candidate | None
    final_action: Literal["BUY", "DEFER", "NO_QUALIFYING_OPPORTUNITY"]
    risk_validation: Literal["PASS", "FAIL", "UNAVAILABLE"]
    blockers: tuple[str, ...]
    rejection_counts: dict[str, int]
    provenance: tuple[EvidenceRef, ...]
    agent_decision: DecisionOutput | None
    llm_calls: int
    opportunity_gate: Literal["BLOCKED_BY_TRUST"]


class ToolError(DataModel):
    code: str
    category: Literal["CALLER", "DATA_PROVIDER", "PRODUCT", "SAFETY", "EXECUTION_CAPABILITY"]
    message: Literal["Request unavailable or blocked; no execution was performed."] = (
        "Request unavailable or blocked; no execution was performed."
    )
    retry_policy: Literal["DO_NOT_RESUBMIT_WITH_NEW_KEY", "CORRECT_INPUT", "READ_ONLY_RETRY"]


class ToolResult(DataModel):
    schema_version: Literal["agent-api-1"] = "agent-api-1"
    tool: ToolName
    status: Literal["PROPOSAL", "DEFERRED", "REJECTED", "AVAILABLE", "UNAVAILABLE", "BLOCKED"]
    request_id: UUID
    correlation_id: UUID
    origin_request_id: UUID | None = None
    origin_correlation_id: UUID | None = None
    run_id: str
    decision_id: str | None = None
    invocation_id: UUID
    generated_at: datetime
    as_of: datetime
    data_mode: Literal["DEMO", "LIVE_READ_ONLY", "UNKNOWN"]
    data_quality: str
    source: StrictStr
    reason_codes: tuple[str, ...] = Field(default=(), max_length=100)
    error: ToolError | None = None
    proposal: ExposureProposal | None = None
    trust: TrustAssessment | None = None
    comparison: TerminalPage[IssuerRow] | None = None
    route: RouteDecision | None = None
    opportunity: PublicScan | None = None
    portfolio: PortfolioState | None = None
    requested_risk_budget_usd: Decimal | None = None
    provider_execution_mode: None = None
    provider_quote_id: None = None
    simulation_status: Literal["UNAVAILABLE", "NOT_APPLICABLE"] = "NOT_APPLICABLE"
    replayed: bool = False
    gates: DemoProductionGates = DemoProductionGates()
    execution_mode: Literal["DRY_RUN"] = "DRY_RUN"
    approval_mode: Literal["PROPOSE_ONLY"] = "PROPOSE_ONLY"
    execution_ready: Literal[False] = False
    live_trading_enabled: Literal[False] = False
    require_simulation: Literal[True] = True
    transaction_broadcast: Literal[False] = False
    no_broadcast_statement: Literal["No real transaction was broadcast."] = (
        "No real transaction was broadcast."
    )

    @model_validator(mode="after")
    def isolation(self):
        if self.data_mode == "UNKNOWN" and (
            self.source != "MCP_TRANSPORT"
            or self.error is None
            or any(
                v is not None
                for v in (
                    self.proposal,
                    self.trust,
                    self.comparison,
                    self.route,
                    self.opportunity,
                    self.portfolio,
                )
            )
        ):
            raise ValueError("Unknown mode is reserved for empty transport failures")
        mode = "DEMO" if self.data_mode == "DEMO" else "LIVE"
        if any(
            v is not None and v.data_mode != mode for v in (self.proposal, self.trust, self.route)
        ):
            raise ValueError("Cross-mode tool data refused")
        if self.opportunity and self.opportunity.data_mode != self.data_mode:
            raise ValueError("Cross-mode scan refused")
        if self.portfolio and self.portfolio.data_mode != self.data_mode:
            raise ValueError("Cross-mode portfolio refused")
        return self


INPUTS = {
    "buy_stock_exposure": BuyInput,
    "find_opportunity": FindInput,
    "compare_stock_tokens": CompareInput,
    "get_stock_trust": StockInput,
    "get_route": RouteInput,
    "get_portfolio": ReadInput,
    "get_autopilot_status": ReadInput,
}
PROPOSALS = frozenset({"buy_stock_exposure", "find_opportunity"})


def project_portfolio(raw):
    """Shared read projection only; existing service owns all financial values."""
    raw = dict(raw)
    for key in ("pending_plan", "latest_decision"):
        plan = raw[key]
        raw[key] = (
            PlanView(
                **{
                    k: getattr(plan, k)
                    for k in PlanView.model_fields
                    if k not in {"funding", "captured_at"}
                },
                funding=plan.snapshot.inputs.funding,
                captured_at=plan.snapshot.captured_at,
            )
            if plan
            else None
        )
    raw["active_positions"] = tuple(
        PositionView(**{k: getattr(p, k) for k in PositionView.model_fields})
        for p in raw["active_positions"]
    )
    return PortfolioState.model_validate(raw)
