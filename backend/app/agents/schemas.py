"""Strict, mode-scoped Phase 6 contracts. All financial values remain backend evidence."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BeforeValidator,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from app.models.data import DataModel, NewsEvent, TrackedAsset, financial, utc
from app.models.demo_sandbox import DemoProductionGates
from app.models.opportunity import Amount, OpportunityDecision, Price
from app.models.research import ResearchDecision, ResearchEpisode
from app.models.risk import RiskDecision
from app.models.routing import RouteDecision
from app.models.trust import State, TrustAssessment

Mode = Literal["DEMO", "LIVE_READ_ONLY"]
AgentName = Literal["INTENT", "MARKET", "NEWS", "RESEARCH", "OPPORTUNITY", "DECISION"]
Status = Literal["OK", "ABSTAIN", "INSUFFICIENT_EVIDENCE", "UNAVAILABLE", "CONFLICT"]
Action = Literal["BUY", "DEFER", "NO_QUALIFYING_OPPORTUNITY"]
Direction = Literal["UP", "DOWN", "FLAT", "UNKNOWN"]
Pattern = Literal["CONTINUATION", "REVERSAL", "MIXED", "INSUFFICIENT"]
Code = Annotated[StrictStr, Field(pattern=r"^[A-Z][A-Z0-9_]{0,95}$")]
Identifier = Annotated[StrictStr, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]
Ticker = Annotated[StrictStr, Field(pattern=r"^[A-Z0-9][A-Z0-9.-]{0,14}$")]
Codes = Annotated[tuple[Code, ...], Field(max_length=32)]
Refs = Annotated[tuple[Identifier, ...], Field(max_length=64)]
Count = Annotated[StrictInt, Field(ge=0, le=20000)]


def derived(value):
    value = financial(value)
    if len(value.as_tuple().digits) > 256 or abs(value.adjusted()) > 72:
        raise ValueError("Bounded derived evidence required")
    return value


Derived = Annotated[Decimal, BeforeValidator(derived)]


class AgentPolicy(DataModel):
    version: Literal["agents-1"] = "agents-1"
    max_calls: StrictInt = Field(default=12, ge=6, le=24)
    max_calls_per_agent: StrictInt = Field(default=2, ge=1, le=3)
    max_llm_calls: StrictInt = Field(default=5, ge=0, le=5)
    timeout_seconds: StrictInt = Field(default=5, ge=1, le=30)
    retries: StrictInt = Field(default=1, ge=0, le=2)
    top_k: StrictInt = Field(default=5, ge=1, le=5)
    max_tool_calls: StrictInt = Field(default=24, ge=6, le=48)
    max_tools_per_agent: StrictInt = Field(default=6, ge=1, le=12)
    max_depth: StrictInt = Field(default=1, ge=0, le=1)
    memory_k: StrictInt = Field(default=4, ge=1, le=10)
    max_age_seconds: Literal[120] = 120
    news_window_seconds: Literal[3600] = 3600
    confidence_cap: Literal["LOW"] = "LOW"
    ranking: Literal["CONFIDENCE_EDGE_EVIDENCE_LIQUIDITY_COST_ID"] = (
        "CONFIDENCE_EDGE_EVIDENCE_LIQUIDITY_COST_ID"
    )


class EvidenceRef(DataModel):
    evidence_id: Identifier
    data_mode: Mode
    source: Code
    digest: Annotated[StrictStr, Field(pattern=r"^[a-f0-9]{64}$")]
    observed_at: datetime
    available_at: datetime
    synthetic: StrictBool

    _utc = field_validator("observed_at", "available_at")(utc)

    @model_validator(mode="after")
    def scope(self):
        if self.synthetic != (self.data_mode == "DEMO") or self.available_at < self.observed_at:
            raise ValueError("Invalid evidence mode/chronology")
        return self


class ConfidenceFactors(DataModel):
    data_quality: Literal["AVAILABLE", "INSUFFICIENT", "STALE", "CONFLICTING"]
    baseline_samples: Count = 0
    analogue_count: Count = 0
    model_samples: Count = 0
    feature_agreement: StrictBool = False
    news_corroboration: StrictBool = False
    persistence_supported: StrictBool = False
    regime_certain: StrictBool = False
    agent_disagreement: StrictBool = False


class AgentConfidence(DataModel):
    tier: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    evidence_status: Literal["SUPPORTED", "INSUFFICIENT", "CONFLICTING"]
    factors: ConfidenceFactors
    cap: Literal["LOW"] = "LOW"
    calibrated: Literal[False] = False
    reasons: Codes

    @model_validator(mode="after")
    def cap_confidence(self):
        if self.tier != self.cap:
            raise ValueError("Existing uncalibrated Trust confidence cap cannot be upgraded")
        return self


class Mandate(DataModel):
    mode: Literal["DIRECT_EXPOSURE", "OPPORTUNITY", "AUTOPILOT"]
    ticker: Ticker | None = None
    budget_usd: Price | None = None
    risk_budget_usd: Price | None = None
    time_window: Literal["PRE_OPEN", "BEFORE_MONDAY"] | None = None
    strategy: Literal["TOKENIZED_AI_AND_CASH"] | None = None
    allocation_stock_percent: Annotated[Amount, Field(le=100)] | None = None
    allocation_cash_percent: Annotated[Amount, Field(le=100)] | None = None
    approval_mode: Literal["PROPOSE_ONLY", "AUTONOMOUS"] = "PROPOSE_ONLY"

    @model_validator(mode="after")
    def safe(self):
        if self.approval_mode != "PROPOSE_ONLY":
            raise ValueError("Autonomous mandates are blocked")
        if self.mode == "DIRECT_EXPOSURE" and (self.ticker is None or self.budget_usd is None):
            raise ValueError("Explicit resolved stock and budget required")
        if self.mode == "OPPORTUNITY" and (
            self.budget_usd is None or self.risk_budget_usd is None or self.time_window is None
        ):
            raise ValueError("Explicit investment/risk budget and window required")
        if self.mode == "AUTOPILOT" and (
            self.strategy is None
            or self.allocation_stock_percent is None
            or self.allocation_cash_percent is None
            or self.allocation_stock_percent + self.allocation_cash_percent != 100
        ):
            raise ValueError("Explicit complete allocation required")
        return self


class IntentOutput(DataModel):
    mandate: Mandate | None = None
    needs_clarification: StrictBool = False


class MarketView(DataModel):
    candidate_id: Identifier
    classification: State
    direction: Direction
    risk_flags: Codes = ()


class MarketOutput(DataModel):
    views: Annotated[tuple[MarketView, ...], Field(max_length=5)] = ()


class NewsView(DataModel):
    candidate_id: Identifier
    relevance: Literal["CORROBORATING", "CONFLICTING", "RELEVANT", "NONE", "UNAVAILABLE"]
    direction: Direction
    event_type: Literal["HEADLINE_EVIDENCE", "UNAVAILABLE"]
    article_ids: Refs = ()
    publication_times: Annotated[tuple[datetime, ...], Field(max_length=10)] = ()
    causal_claim: Literal[False] = False


class NewsOutput(DataModel):
    views: Annotated[tuple[NewsView, ...], Field(max_length=5)] = ()


class ResearchPrior(DataModel):
    prior_id: Identifier
    source_reference: Identifier
    tag: Literal["RESEARCH_PRIOR"] = "RESEARCH_PRIOR"
    claim: Literal["OFF_HOURS_INFORMATION_POSSIBLE", "SHORT_HORIZON_REVERSAL_POSSIBLE"]
    coefficient_used: Literal[False] = False


class ResearchView(DataModel):
    candidate_id: Identifier
    similar_episodes: Refs = ()
    historical_pattern: Pattern = "INSUFFICIENT"
    opening_direction: Direction = "UNKNOWN"
    prediction_status: Literal["READY", "INSUFFICIENT_DATA", "NOT_READY"] = "NOT_READY"
    prediction_samples: Count = 0
    priors: Annotated[tuple[ResearchPrior, ...], Field(max_length=4)] = ()
    memory_ids: Refs = ()


class ResearchOutput(DataModel):
    retrieval_status: Literal["SUFFICIENT", "INSUFFICIENT_DATA", "NOT_READY"] = "NOT_READY"
    model_status: Literal["READY", "INSUFFICIENT_DATA", "NOT_READY"] = "NOT_READY"
    model_samples: Count = 0
    retrieved_analogues: Count = 0
    views: Annotated[tuple[ResearchView, ...], Field(max_length=5)] = ()


class OpportunityOutput(DataModel):
    action: Action = "DEFER"
    candidate_id: Identifier | None = None
    eligible_ids: Refs = ()
    rejected_ids: Refs = ()
    strengths: Codes = ()
    weaknesses: Codes = ()


class DecisionOutput(DataModel):
    decision: Action = "DEFER"
    candidate_id: Identifier | None = None
    ticker: Ticker | None = None
    issuer: Identifier | None = None
    reasons: Codes = ()
    risk_preview_status: Literal["PASS", "FAIL", "UNAVAILABLE"] = "UNAVAILABLE"
    execution_authorized: Literal[False] = False


class AgentResponse[T](DataModel):
    run_id: Identifier
    decision_id: Identifier
    correlation_id: Identifier
    agent: AgentName
    version: Literal["agents-1"] = "agents-1"
    data_mode: Mode
    timestamp: datetime
    evidence_refs: Refs
    status: Status
    output: T
    confidence: AgentConfidence
    limitations: Codes = ()
    conflicts: Codes = ()
    provider: Identifier = "DETERMINISTIC"
    model: Identifier = "deterministic-agents-1"

    _utc = field_validator("timestamp")(utc)


class IntentResponse(AgentResponse[IntentOutput]):
    agent: Literal["INTENT"] = "INTENT"


class MarketResponse(AgentResponse[MarketOutput]):
    agent: Literal["MARKET"] = "MARKET"


class NewsResponse(AgentResponse[NewsOutput]):
    agent: Literal["NEWS"] = "NEWS"


class ResearchResponse(AgentResponse[ResearchOutput]):
    agent: Literal["RESEARCH"] = "RESEARCH"


class OpportunityResponse(AgentResponse[OpportunityOutput]):
    agent: Literal["OPPORTUNITY"] = "OPPORTUNITY"


class DecisionResponse(AgentResponse[DecisionOutput]):
    agent: Literal["DECISION"] = "DECISION"


class Candidate(DataModel):
    """Backend-supplied table, not raw provider text or agent-produced economics."""

    candidate_id: Identifier
    ticker: Ticker
    issuer: Identifier
    chain_id: Identifier
    contract: Identifier
    data_mode: Mode
    observed_at: datetime
    available_at: datetime
    trust: State
    confidence: Literal["LOW", "MEDIUM", "HIGH"] | None = None
    deviation: Derived | None = None
    volume_percentile: Annotated[Derived, Field(ge=0, le=1)] | None = None
    effective_cost: Annotated[Derived, Field(gt=0)] | None = None
    liquidity_usd: Amount | None = None
    slippage_bps: Annotated[Amount, Field(le=10000)] | None = None
    net_edge_usd: Derived | None = None
    predicted_open_return: Derived | None = None
    prediction_samples: Count = 0
    baseline_samples: Count = 0
    analogue_count: Count = 0
    eligibility: Literal["ELIGIBLE", "REJECTED", "UNAVAILABLE"]
    tradable: StrictBool | None = None
    risk_flags: Codes = ()
    evidence_refs: Refs
    # Phase 7 supplies these facts before top-K interpretation. Optional for captured Phase 6 runs.
    company: Annotated[StrictStr, Field(max_length=160)] | None = None
    token: Identifier | None = None
    token_to_share_ratio: Price | None = None
    token_price_usd: Price | None = None
    independent_equity_price_usd: Price | None = None
    independent_equity_source: Annotated[StrictStr, Field(max_length=128)] | None = None
    regime: Code | None = None
    volume_usd: Amount | None = None
    persistence_seconds: Amount | None = None
    news_state: Code | None = None
    historical_pattern: Code | None = None
    prediction_interval_low: Derived | None = None
    prediction_interval_high: Derived | None = None
    prediction_status: Literal["READY", "INSUFFICIENT_DATA", "NOT_READY"] = "NOT_READY"
    economics_basis: Literal["OPENING_MODEL", "SYNTHETIC_SCENARIO", "UNAVAILABLE"] = "UNAVAILABLE"
    proposed_notional_usd: Amount | None = None
    stress_adverse_move_fraction: Annotated[Amount, Field(gt=0, le=1)] | None = None
    stress_loss_usd: Amount | None = None
    estimated_slippage_usd: Amount | None = None
    fees_usd: Amount | None = None
    gas_usd: Amount | None = None
    execution_buffer_usd: Amount | None = None
    gross_expected_edge_usd: Derived | None = None
    rejection_reasons: Codes = ()
    liquidity_state: Code | None = None
    source_timestamps: dict[Code, datetime | None] = Field(default_factory=dict, max_length=16)

    _utc = field_validator("observed_at", "available_at")(utc)


class ResearchInput(DataModel):
    current: ResearchDecision
    episodes: Annotated[tuple[ResearchEpisode, ...], Field(max_length=500)] = ()
    priors: Annotated[tuple[ResearchPrior, ...], Field(max_length=4)] = ()


class DownstreamEvidence(DataModel):
    candidate_id: Identifier
    opportunity: OpportunityDecision
    route: RouteDecision
    risk: RiskDecision


class EvidenceBundle(DataModel):
    data_mode: Mode
    decision_at: datetime
    assessment: TrustAssessment
    assets: Annotated[tuple[TrackedAsset, ...], Field(max_length=100)] = ()
    articles: Annotated[tuple[NewsEvent, ...], Field(max_length=50)] = ()
    candidates: Annotated[tuple[Candidate, ...], Field(max_length=5)] = ()
    references: Annotated[tuple[EvidenceRef, ...], Field(max_length=64)]
    research: Annotated[tuple[ResearchInput, ...], Field(max_length=5)] = ()
    downstream: Annotated[tuple[DownstreamEvidence, ...], Field(max_length=5)] = ()

    _utc = field_validator("decision_at")(utc)

    @model_validator(mode="after")
    def isolated(self):
        mode = "DEMO" if self.data_mode == "DEMO" else "LIVE"
        at = self.decision_at
        if self.assessment.data_mode != mode or self.assessment.evaluated_at != at:
            raise ValueError("Trust evidence mode/decision time mismatch")
        if len(self.assessment.representations) > 5:
            raise ValueError("Provide a bounded candidate context, not the raw universe")
        if any(a.data_mode != mode for a in (*self.assets, *self.articles)):
            raise ValueError("Mixed provider modes forbidden")
        if any(a.ingestion_timestamp > at for a in self.assets):
            raise ValueError("Future resolver evidence")
        for rep in self.assessment.representations:
            points = [
                rep.token_timestamp,
                rep.ratio_observed_at,
                rep.ratio_source_timestamp,
                rep.liquidity.observed_at,
            ]
            if rep.features:
                points.extend((rep.features.asof, rep.features.available_at))
            points.extend(rep.news.published_timestamps)
            points.extend(rep.news.first_seen_timestamps)
            if rep.reference.observation:
                equity = rep.reference.observation
                if equity.data_mode != mode or equity.source.startswith("BINANCE"):
                    raise ValueError("Independent reference mode/source mismatch")
                points.extend((equity.source_timestamp, equity.ingestion_timestamp))
            if any(t is not None and (t.tzinfo is None or t > at) for t in points):
                raise ValueError("Future or naive Trust evidence")
        ids = {r.evidence_id for r in self.references}
        if len(ids) != len(self.references) or any(
            r.data_mode != self.data_mode or r.available_at > at or r.observed_at > at
            for r in self.references
        ):
            raise ValueError("Unavailable or mixed provenance")
        candidates = {c.candidate_id: c for c in self.candidates}
        if len(candidates) != len(self.candidates):
            raise ValueError("Duplicate candidate identity")
        for c in self.candidates:
            if (
                c.data_mode != self.data_mode
                or c.observed_at > at
                or c.available_at > at
                or not c.evidence_refs
                or not set(c.evidence_refs) <= ids
                or not any(
                    (t.ticker, t.issuer, t.chain_id, t.contract)
                    == (c.ticker, c.issuer, c.chain_id, c.contract)
                    for t in self.assessment.representations
                )
            ):
                raise ValueError("Unbound candidate evidence")
        for r in self.research:
            if (
                r.current.data_mode != mode
                or r.current.decision_at != at
                or r.current.ticker
                not in ({self.assessment.ticker} | {c.ticker for c in self.candidates})
            ):
                raise ValueError("Research mode/time mismatch")
            if any(e.decision.data_mode != mode for e in r.episodes):
                raise ValueError("Mixed research history")
        for d in self.downstream:
            if self.data_mode != "DEMO" or d.candidate_id not in candidates:
                raise ValueError("Synthetic risk cannot become production authority")
            c = candidates[d.candidate_id]
            o, route, risk = d.opportunity, d.route, d.risk
            if (
                o.trust_assessment_id != self.assessment.assessment_id
                or (o.ticker, o.issuer, o.chain_id, o.contract)
                != (c.ticker, c.issuer, c.chain_id, c.contract)
                or risk.opportunity_id != o.opportunity_id
                or route.underlying != c.ticker
                or o.evaluated_at != at
                or risk.evaluated_at != at
                or route.timestamp != at
            ):
                raise ValueError("Downstream evidence binding mismatch")
        return self


class MemoryFeatures(DataModel):
    deviation: Derived | None = None
    volume_percentile: Annotated[Derived, Field(ge=0, le=1)] | None = None
    persistence_seconds: Amount | None = None
    effective_cost: Annotated[Derived, Field(gt=0)] | None = None
    asof: datetime | None = None

    _utc = field_validator("asof")(lambda v: utc(v) if v else None)


class MemoryEpisode(DataModel):
    memory_id: Identifier
    data_mode: Mode
    timestamp: datetime
    available_at: datetime
    stock: Ticker
    regime: Code
    feature_quality: Literal["COMPLETE", "INSUFFICIENT", "STALE"]
    feature_summary: MemoryFeatures = MemoryFeatures()
    evidence_refs: Refs = ()
    trust_state: State
    confidence: Literal["LOW"]
    conclusions: Annotated[tuple[Code, ...], Field(max_length=6)]
    action: Action
    eventual_outcome: Literal["POSITIVE", "NEGATIVE", "FLAT", "UNAVAILABLE"] = "UNAVAILABLE"
    outcome_available_at: datetime | None = None
    scorecard_reference: Identifier | None = None
    scorecard_available_at: datetime | None = None

    _utc = field_validator(
        "timestamp", "available_at", "outcome_available_at", "scorecard_available_at"
    )(lambda v: utc(v) if v else None)

    @model_validator(mode="after")
    def chronology(self):
        if self.available_at < self.timestamp:
            raise ValueError("Memory availability precedes decision")
        if self.feature_summary.asof and self.feature_summary.asof > self.timestamp:
            raise ValueError("Future memory feature")
        if self.eventual_outcome != "UNAVAILABLE" and (
            self.outcome_available_at is None or self.outcome_available_at < self.timestamp
        ):
            raise ValueError("Outcome availability required")
        if self.scorecard_reference is not None and (
            self.scorecard_available_at is None or self.scorecard_available_at < self.timestamp
        ):
            raise ValueError("Scorecard availability required")
        return self


class CallRecord(DataModel):
    agent: AgentName
    attempt: StrictInt = Field(ge=1, le=3)
    status: Literal["OK", "INVALID", "TIMEOUT", "UNAVAILABLE", "BUDGET_EXHAUSTED"]


class AgentRun(DataModel):
    run_id: Identifier
    decision_id: Identifier
    correlation_id: Identifier
    data_mode: Mode
    timestamp: datetime
    policy: AgentPolicy
    evidence: Annotated[tuple[EvidenceRef, ...], Field(max_length=64)]
    candidate_table: Annotated[tuple[Candidate, ...], Field(max_length=5)]
    responses: Annotated[
        tuple[
            Annotated[
                IntentResponse
                | MarketResponse
                | NewsResponse
                | ResearchResponse
                | OpportunityResponse
                | DecisionResponse,
                Field(discriminator="agent"),
            ],
            ...,
        ],
        Field(max_length=6),
    ]
    calls: Annotated[tuple[CallRecord, ...], Field(max_length=24)]
    tool_calls: StrictInt = Field(ge=0, le=48)
    llm_calls: StrictInt = Field(ge=0, le=5)
    decision: DecisionOutput
    status: Literal["COMPLETED", "DEFERRED"]
    production_gates: DemoProductionGates = DemoProductionGates()
    execution_mode: Literal["DRY_RUN"] = "DRY_RUN"
    approval_mode: Literal["PROPOSE_ONLY"] = "PROPOSE_ONLY"
    execution_authorized: Literal[False] = False
    transaction_broadcast: Literal[False] = False
    no_broadcast_statement: Literal["No real transaction was broadcast."] = (
        "No real transaction was broadcast."
    )

    _utc = field_validator("timestamp")(utc)

    @model_validator(mode="after")
    def validated_workflow(self):
        if tuple(r.agent for r in self.responses) != (
            "INTENT",
            "MARKET",
            "NEWS",
            "RESEARCH",
            "OPPORTUNITY",
            "DECISION",
        ):
            raise ValueError("Complete ordered agent trace required")
        if any(
            (r.run_id, r.decision_id, r.correlation_id, r.data_mode, r.timestamp)
            != (self.run_id, self.decision_id, self.correlation_id, self.data_mode, self.timestamp)
            for r in self.responses
        ):
            raise ValueError("Unbound workflow response")
        refs = {r.evidence_id for r in self.evidence}
        if (
            len(refs) != len(self.evidence)
            or any(
                r.data_mode != self.data_mode
                or r.available_at > self.timestamp
                or r.observed_at > self.timestamp
                for r in self.evidence
            )
            or any(not set(r.evidence_refs) <= refs for r in self.responses)
        ):
            raise ValueError("Unbound workflow provenance")
        if any(
            c.data_mode != self.data_mode or not set(c.evidence_refs) <= refs
            for c in self.candidate_table
        ):
            raise ValueError("Unbound persisted candidate")
        if self.decision != self.responses[-1].output:
            raise ValueError("Decision must equal the validated final response")
        if (
            len(self.calls) > self.policy.max_calls
            or self.llm_calls > self.policy.max_llm_calls
            or self.tool_calls > self.policy.max_tool_calls
        ):
            raise ValueError("Workflow policy budget exceeded")
        if self.decision.decision == "BUY" and (
            self.data_mode != "DEMO"
            or self.responses[-1].status != "OK"
            or self.decision.risk_preview_status != "PASS"
            or any(r.status != "OK" or r.conflicts for r in self.responses)
        ):
            raise ValueError("BUY cannot bypass required evidence or risk")
        return self
