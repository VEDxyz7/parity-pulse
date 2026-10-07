"""Phase 7 structured full-universe audit; no execution authority or raw external text."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from app.agents.schemas import (
    Action,
    AgentRun,
    Candidate,
    Code,
    Codes,
    EvidenceRef,
    Identifier,
    Mandate,
    Mode,
    ResearchInput,
    Ticker,
)
from app.models.data import DataModel, NewsEvent, TokenMetadata, TrackedAsset, utc
from app.models.opportunity import Amount, OpportunityInputs, Price
from app.models.risk import OpportunityRiskContext, RiskInputs, RiskPolicy
from app.models.routing import RouteDecision, RouteInput
from app.models.trust import TrustAssessment


class UniverseFilters(DataModel):
    tickers: Annotated[tuple[Ticker, ...], Field(max_length=100)] = ()
    issuers: Annotated[tuple[Identifier, ...], Field(max_length=100)] = ()
    chains: Annotated[tuple[Identifier, ...], Field(max_length=20)] = ()

    @field_validator("tickers", "issuers", "chains")
    @classmethod
    def ordered(cls, values):
        return tuple(sorted(set(values)))

    def reasons(self, token):
        return tuple(
            code
            for values, value, code in (
                (self.tickers, token.ticker, "UNIVERSE_TICKER_EXCLUDED"),
                (self.issuers, token.platform_id, "UNIVERSE_ISSUER_EXCLUDED"),
                (self.chains, token.chain_id, "UNIVERSE_CHAIN_EXCLUDED"),
            )
            if values and value not in values
        )


class OpportunityRequest(DataModel):
    budget_usd: Price
    risk_budget_usd: Price
    time_window: Literal["PRE_OPEN", "BEFORE_MONDAY"]
    universe: UniverseFilters = UniverseFilters()
    correlation_id: Identifier | None = None
    demo_scenario: Literal["steady", "thin-move", "supported-move"] | None = None

    def mandate(self):
        return Mandate(
            mode="OPPORTUNITY",
            budget_usd=self.budget_usd,
            risk_budget_usd=self.risk_budget_usd,
            time_window=self.time_window,
        )


class ScanPolicy(DataModel):
    version: Literal["opportunity-scan-1"] = "opportunity-scan-1"
    top_k: StrictInt = Field(default=5, ge=1, le=5)
    max_representations: StrictInt = Field(default=500, ge=1, le=500)
    max_stocks: StrictInt = Field(default=100, ge=1, le=100)
    min_liquidity_usd: Price = Decimal("1000")
    max_slippage_bps: Amount = Field(default=Decimal("50"), le=10000)
    min_net_edge_usd: Price = Decimal("0.25")
    max_age_seconds: Literal[120] = 120
    max_alignment_seconds: Literal[30] = 30
    min_baseline: Literal[30] = 30
    min_model_samples: Literal[30] = 30
    min_analogues: Literal[3] = 3
    ranking: Literal["CONFIDENCE_EDGE_EVIDENCE_LIQUIDITY_COST_ID"] = (
        "CONFIDENCE_EDGE_EVIDENCE_LIQUIDITY_COST_ID"
    )
    # No policy switch can unblock real Opportunity or execution in this milestone.
    opportunity_gate: Literal["BLOCKED_BY_TRUST"] = "BLOCKED_BY_TRUST"


class ScanCosts(DataModel):
    observed_at: datetime
    available_at: datetime
    data_mode: Mode
    source: Identifier
    quoted_notional_usd: Price
    slippage_bps: Amount = Field(le=10000)
    fees_usd: Amount
    gas_usd: Amount
    execution_buffer_usd: Amount
    route_available: StrictBool
    _utc = field_validator("observed_at", "available_at")(utc)


class CatalogRejection(DataModel):
    row: StrictInt = Field(ge=0)
    reason: Literal["PAYLOAD_SCHEMA_INVALID"] = "PAYLOAD_SCHEMA_INVALID"


class ScanSnapshot(DataModel):
    """Host-controlled capture. Inputs are not accepted from the public API client."""

    data_mode: Mode
    captured_at: datetime
    assets: Annotated[tuple[TrackedAsset, ...], Field(max_length=100)] = ()
    tokens: Annotated[tuple[TokenMetadata, ...], Field(max_length=500)] = ()
    catalog_rejections: Annotated[tuple[CatalogRejection, ...], Field(max_length=500)] = ()
    assessments: Annotated[tuple[TrustAssessment, ...], Field(max_length=100)] = ()
    articles: Annotated[tuple[NewsEvent, ...], Field(max_length=1000)] = ()
    research: Annotated[tuple[ResearchInput, ...], Field(max_length=500)] = ()
    costs: dict[Identifier, ScanCosts] = Field(default_factory=dict, max_length=500)
    routes: dict[Identifier, RouteInput] = Field(default_factory=dict, max_length=500)
    # Current Risk Engine's downstream DEMO contracts remain synthetic-only.
    demo_economics: OpportunityInputs | None = None
    demo_risk_inputs: RiskInputs | None = None
    demo_risk_policy: RiskPolicy | None = None
    risk_context: OpportunityRiskContext | None = None
    blockers: Codes = ()
    discovery_source: Code
    discovery_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    _utc = field_validator("captured_at")(utc)

    @model_validator(mode="after")
    def isolated(self):
        mode = "DEMO" if self.data_mode == "DEMO" else "LIVE"
        records = (*self.assets, *self.tokens, *self.articles)
        if (
            any(r.data_mode != mode for r in records)
            or any(a.data_mode != mode for a in self.assessments)
            or any(r.current.data_mode != mode for r in self.research)
        ):
            raise ValueError("Mixed scan evidence forbidden")
        if any(c.data_mode != self.data_mode for c in self.costs.values()) or any(
            r.data_mode != mode for r in self.routes.values()
        ):
            raise ValueError("Mixed route/cost evidence forbidden")
        if mode != "DEMO" and any(
            v is not None
            for v in (self.demo_economics, self.demo_risk_inputs, self.demo_risk_policy)
        ):
            raise ValueError("Synthetic constraints cannot enter production")
        if self.risk_context and self.risk_context.data_mode != self.data_mode:
            raise ValueError("Mixed system risk constraints forbidden")
        if any(e.decision.data_mode != mode for r in self.research for e in r.episodes):
            raise ValueError("Mixed research history forbidden")
        return self


class CandidateAudit(DataModel):
    candidate: Candidate
    inclusion: Literal["INCLUDED", "EXCLUDED"]
    rejection_reasons: Codes
    rank: StrictInt | None = Field(default=None, ge=1)
    agent_selected: StrictBool = False
    route: RouteDecision | None = None

    @model_validator(mode="after")
    def coherent(self):
        if (not self.rejection_reasons) != (self.candidate.eligibility == "ELIGIBLE") or (
            self.rejection_reasons != self.candidate.rejection_reasons
            or self.candidate.risk_flags != self.rejection_reasons
            or self.inclusion == "EXCLUDED"
            and self.candidate.eligibility == "ELIGIBLE"
            or self.rank is not None
            and self.candidate.eligibility != "ELIGIBLE"
        ):
            raise ValueError("Candidate audit must agree with deterministic eligibility")
        return self


class OpportunityScan(DataModel):
    schema_version: Literal["opportunity-scan-1"] = "opportunity-scan-1"
    run_id: Identifier
    decision_id: Identifier
    correlation_id: Identifier
    timestamp: datetime
    data_mode: Mode
    mandate: Mandate
    policy: ScanPolicy
    universe_count: StrictInt = Field(ge=0)
    eligible_count: StrictInt = Field(ge=0)
    rejected_count: StrictInt = Field(ge=0)
    candidates: Annotated[tuple[CandidateAudit, ...], Field(max_length=500)]
    catalog_rejections: Annotated[tuple[CatalogRejection, ...], Field(max_length=500)] = ()
    top_k: Annotated[tuple[Candidate, ...], Field(max_length=5)]
    selected_candidate: Candidate | None = None
    final_action: Action
    blockers: Codes
    rejection_counts: dict[Code, StrictInt]
    provenance: Annotated[tuple[EvidenceRef, ...], Field(max_length=501)]
    agent_run: AgentRun | None = None
    risk_validation: Literal["PASS", "FAIL", "UNAVAILABLE"] = "UNAVAILABLE"
    opportunity_gate: Literal["BLOCKED_BY_TRUST"] = "BLOCKED_BY_TRUST"
    execution_mode: Literal["DRY_RUN"] = "DRY_RUN"
    approval_mode: Literal["PROPOSE_ONLY"] = "PROPOSE_ONLY"
    require_simulation: Literal[True] = True
    live_trading_enabled: Literal[False] = False
    execution_ready: Literal[False] = False
    transaction_broadcast: Literal[False] = False
    no_broadcast_statement: Literal["No real transaction was broadcast."] = (
        "No real transaction was broadcast."
    )
    risk_budget_semantics: Literal["EX_ANTE_NOT_A_GUARANTEED_MAXIMUM_REALIZED_LOSS"] = (
        "EX_ANTE_NOT_A_GUARANTEED_MAXIMUM_REALIZED_LOSS"
    )
    _utc = field_validator("timestamp")(utc)

    @model_validator(mode="after")
    def coherent(self):
        ids = {c.candidate.candidate_id for c in self.candidates}
        eligible = [c for c in self.candidates if c.candidate.eligibility == "ELIGIBLE"]
        if len(ids) != len(self.candidates) or (
            self.universe_count != len(self.candidates) + len(self.catalog_rejections)
            or self.eligible_count != len(eligible)
            or self.rejected_count != self.universe_count - self.eligible_count
            or len(self.top_k) > self.policy.top_k
            or any(c not in [a.candidate for a in eligible] for c in self.top_k)
            or any(c.data_mode != self.data_mode for c in self.top_k)
        ):
            raise ValueError("Inconsistent scan audit")
        if self.final_action == "BUY" and (
            self.data_mode != "DEMO"
            or self.risk_validation != "PASS"
            or self.selected_candidate is None
            or self.selected_candidate not in self.top_k
            or self.agent_run is None
            or self.agent_run.decision.decision != "BUY"
        ):
            raise ValueError("BUY needs bound DEMO agents and deterministic Risk")
        ranked = sorted(eligible, key=lambda c: c.rank or 0)
        if any(c.rank != i for i, c in enumerate(ranked, 1)) or (
            tuple(c.candidate for c in ranked[: len(self.top_k)]) != self.top_k
            or any(c.agent_selected != (c.candidate in self.top_k) for c in self.candidates)
            or any(c.candidate.data_mode != self.data_mode for c in self.candidates)
            or any(p.data_mode != self.data_mode for p in self.provenance)
            or self.agent_run
            and self.agent_run.candidate_table != self.top_k
            or self.agent_run
            and self.agent_run.data_mode != self.data_mode
            or self.selected_candidate is not None
            and self.selected_candidate not in self.top_k
            or self.final_action == "BUY"
            and (
                self.agent_run.decision.candidate_id != self.selected_candidate.candidate_id
                or self.agent_run.responses[0].output.mandate != self.mandate
            )
        ):
            raise ValueError("Scan decision must match deterministic top-K and mandate")
        return self
