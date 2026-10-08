"""Read-only analytical projections. No transaction payloads or authorization surfaces."""

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.agents.schemas import (
    DecisionOutput,
    EvidenceRef,
    IntentOutput,
    MarketOutput,
    MemoryEpisode,
    NewsOutput,
    OpportunityOutput,
    ResearchOutput,
)
from app.models.data import DataModel, Nonnegative, Positive, utc
from app.models.demo_sandbox import DemoProductionGates
from app.models.execution import Mode
from app.models.research import OpeningPrediction, OpeningTarget, RetrievalResult
from app.models.trust import Exact, LiquidityEvidence, ReferenceEvidence, RepresentationTrust, State


class TerminalQuery(DataModel):
    ticker: str | None = Field(default=None, pattern=r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)


class EpisodeQuery(TerminalQuery):
    as_of: datetime | None = None

    _utc = field_validator("as_of")(lambda t: utc(t) if t else None)


class ObservationRef(DataModel):
    digest: str
    source: str
    provider_identifier: str
    observed_at: datetime | None
    available_at: datetime
    data_quality: str


class TrustMonitorRow(DataModel):
    ticker: str
    issuer: str | None = None
    contract: str | None = None
    assessment_id: str | None = None
    assessed_at: datetime | None = None
    age_seconds: Nonnegative | None = None
    freshness: Literal["FRESH", "STALE", "UNAVAILABLE"]
    classification: State = "INSUFFICIENT_EVIDENCE"
    confidence: Literal["LOW", "MEDIUM", "HIGH"] | None = None
    regime: str | None = None
    stored_evidence: RepresentationTrust | None = None
    reasons: tuple[str, ...]


class IssuerRow(DataModel):
    ticker: str
    company: str
    issuer: str
    token: str
    contract: str
    chain_id: str
    token_price_usd: Positive | None
    token_to_share_ratio: Positive
    ratio_observed_at: datetime
    ratio_source_timestamp: datetime | None
    effective_price_per_share_usd: Positive | None
    independent_equity_price_usd: Positive | None
    comparable_token_value_usd: Positive | None
    deviation: Exact | None
    absolute_deviation: Nonnegative | None
    deviation_percent: Exact | None
    spread_usd_per_share: Exact | None
    reference: ReferenceEvidence
    liquidity: LiquidityEvidence
    trust: TrustMonitorRow
    eligibility: Literal["ANALYTICAL_ONLY", "INSUFFICIENT_EVIDENCE"]
    freshness: Literal["FRESH", "STALE", "UNAVAILABLE", "CONFLICTING"]
    tradable: bool | None
    market_state: str
    regime: str
    reasons: tuple[str, ...]
    observations: tuple[ObservationRef, ...]
    calculation_version: Literal["existing-normalization-v1"] = "existing-normalization-v1"
    provider_route_id: None = None
    route_status: Literal["NOT_QUOTED"] = "NOT_QUOTED"


class AgentView(DataModel):
    agent: str
    status: str
    confidence: str
    provider: str
    model: str
    timestamp: datetime
    evidence_refs: tuple[str, ...]
    reasons: tuple[str, ...]
    conflicts: tuple[str, ...]
    output: (
        IntentOutput
        | MarketOutput
        | NewsOutput
        | ResearchOutput
        | OpportunityOutput
        | DecisionOutput
    )


class AgentEvidenceRow(DataModel):
    run_id: str
    decision_id: str
    correlation_id: str
    timestamp: datetime
    agents: tuple[AgentView, ...] = Field(max_length=6)
    evidence: tuple[EvidenceRef, ...] = Field(max_length=64)
    decision: DecisionOutput
    status: str
    memory: tuple[MemoryEpisode, ...] = Field(max_length=20)


class ExecutionAnalyticsRow(DataModel):
    execution_id: str
    decision_id: str
    correlation_id: str
    source: str
    synthetic: bool
    lifecycle_state: str
    category: Literal[
        "PROPOSED",
        "DRY_RUN",
        "SIMULATED",
        "SUBMITTED",
        "CONFIRMED",
        "FAILED",
        "UNKNOWN",
        "RECONCILIATION_REQUIRED",
        "BLOCKED",
    ]
    actual_completed_trade: bool
    created_at: datetime
    updated_at: datetime
    settled_at: datetime | None
    provider: str | None
    execution_mode: str | None
    quote_id: str | None
    quoted_at: datetime | None
    quote_expires_at: datetime | None
    fingerprint: str | None
    simulation_status: str | None
    simulation_at: datetime | None
    risk_status: str | None
    funding_status: str | None
    requested_base_units: str | None
    quoted_output_base_units: str | None
    filled_base_units: str | None
    average_execution_price: Positive | None
    network_fee_estimate_usd: Nonnegative | None
    estimated_gas_provider_units: str | None
    actual_fees_native_base_units: str | None
    quote_latency_seconds: Nonnegative | None
    position_id: str | None
    position_state: str | None
    remaining_base_units: str | None
    realized_gross_pnl_usd: Exact | None
    realized_net_pnl_usd: Exact | None
    reasons: tuple[str, ...]


class EpisodeRow(DataModel):
    run_id: str
    dataset_digest: str
    implementation_digest: str
    episode_id: str
    ticker: str
    issuer: str
    contract: str
    decision_at: datetime
    query_as_of: datetime
    regime: str
    evidence_kind: str
    eligibility: str
    trust_state: str
    deviation: Exact | None
    volume_usd: Nonnegative | None
    liquidity_usd: Nonnegative | None
    feature_available_at: datetime | None
    prediction: OpeningPrediction
    retrieval: RetrievalResult
    opening_outcome: OpeningTarget | None
    outcome_state: Literal["AVAILABLE", "NOT_YET_AVAILABLE", "UNSCORABLE", "POSTHOC_ONLY"]
    reasons: tuple[str, ...]
    provenance: tuple[ObservationRef, ...]


class TerminalPage[T](DataModel):
    items: tuple[T, ...]
    limit: int
    offset: int
    has_more: bool
    reasons: tuple[str, ...] = ()


class TerminalContext(DataModel):
    schema_version: Literal["terminal-1"] = "terminal-1"
    generated_at: datetime
    data_mode: Mode
    run_id: str
    request_id: str
    correlation_id: str
    source_scope: Literal["MODE_SCOPED_PERSISTED_RECORDS"] = "MODE_SCOPED_PERSISTED_RECORDS"
    production_gates: DemoProductionGates = DemoProductionGates()
    execution_mode: Literal["DRY_RUN"] = "DRY_RUN"
    approval_mode: Literal["PROPOSE_ONLY"] = "PROPOSE_ONLY"
    execution_ready: Literal[False] = False
    broadcast: Literal[False] = False


class TerminalSection[T](TerminalContext):
    page: TerminalPage[T]


class PortfolioMonitor(DataModel):
    config_version: int | None
    pending_plan_id: str | None
    status: str
    reasons: tuple[str, ...]


class TerminalOverview(TerminalContext):
    issuers: TerminalPage[IssuerRow]
    trust: TerminalPage[TrustMonitorRow]
    agents: TerminalPage[AgentEvidenceRow]
    executions: TerminalPage[ExecutionAnalyticsRow]
    episodes: TerminalPage[EpisodeRow]
    portfolio: PortfolioMonitor
    limitations: tuple[str, ...] = (
        "READ_ONLY_NO_TRADE_ACTIONS",
        "CACHE_AND_PERSISTED_HISTORY_NOT_A_LIVE_PROVIDER_REFRESH",
        "PRODUCTION_PROVIDER_VERIFICATION_REMAINS_PARTIAL",
    )
