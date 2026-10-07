"""Phase 5 point-in-time research contracts; no execution authority or synthetic promotion."""

from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from typing import Annotated, Literal

from pydantic import Field, StrictInt, field_validator, model_validator

from app.models.data import (
    DataMode,
    DataModel,
    EquityObservation,
    NewsEvent,
    Nonnegative,
    Positive,
    Provenance,
    TokenMetadata,
    TokenObservation,
    utc,
)
from app.models.trust import Exact, RepresentationTrust, TrustEpisode, TrustSample
from app.services.normalization import bounded_decimal

OPENING_MINUTES = 5
REGIMES = ("PREMARKET", "POSTMARKET", "WEEKDAY_OVERNIGHT", "WEEKEND_PREOPEN", "MULTI_DAY_REOPEN")
NEWS = (
    "NO_RELEVANT_NEWS",
    "RELEVANT_NEWS",
    "CORROBORATING",
    "CONFLICTING",
    "PARTIAL",
    "UNAVAILABLE",
)
ModelFeature = Literal[
    "deviation",
    "absolute_deviation",
    "volume_percentile",
    "persistence",
    "time_to_open",
    "starting_deviation",
    "ending_deviation",
    "news_flag",
    "off_hours_return",
]


class RawTokenBar(Provenance):
    """Legacy diagnostic candles lack economic ratio proof; preserve that null explicitly."""

    ticker: str
    issuer: str
    chain_id: str
    contract: str
    interval: Literal["1m", "1h", "1d"]
    kind: Literal["CANDLE"] = "CANDLE"
    token_to_share_ratio: None = None
    token_price: Positive
    volume: Nonnegative
    volume_unit: Literal["UNKNOWN"] = "UNKNOWN"
    historical_liquidity: None = None
    point_in_time_availability_verified: Literal[False] = False


class ResearchPolicy(DataModel):
    version: Literal["research-v1"] = "research-v1"
    target_version: Literal["previous-close-to-first-completed-regular-bar-v1"] = (
        "previous-close-to-first-completed-regular-bar-v1"
    )
    opening_minutes: Literal[5] = OPENING_MINUTES
    lookback_days: Literal[180] = 180
    min_model_samples: Literal[30] = 30
    min_analogues: Literal[3] = 3
    top_k: StrictInt = Field(default=3, ge=3, le=20)
    rolling_window: StrictInt = Field(default=120, ge=30, le=500)
    similarity_floor: Annotated[Exact, Field(ge=-1, le=1)] = Decimal("0.8")
    model_features: tuple[ModelFeature, ...] = ("deviation", "volume_percentile", "persistence")
    prediction_interval_multiplier: Positive = Decimal("1.96")
    rank_tolerance: Annotated[Positive, Field(ge=Decimal("1e-80"), le=Decimal("1e-12"))] = Decimal(
        "1e-40"
    )
    # Explicit engineering scales, not data-derived coefficients or research priors.
    deviation_scale: Positive = Decimal("0.01")
    persistence_scale: Positive = Decimal(900)
    time_scale: Positive = Decimal(86400)

    @model_validator(mode="after")
    def features_unique(self):
        if not self.model_features or len(set(self.model_features)) != len(self.model_features):
            raise ValueError("A nonempty unique feature list is required")
        for value in (
            self.prediction_interval_multiplier,
            self.deviation_scale,
            self.persistence_scale,
            self.time_scale,
        ):
            bounded_decimal(value)
        return self


class AvailableRecord(DataModel):
    """Proof binds an exact payload, not an unbound assertion about an entire provider."""

    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_at: datetime
    available_at: datetime
    revision_verified: Literal[True]
    source: str = Field(min_length=1)

    @field_validator("effective_at", "available_at")
    @classmethod
    def aware(cls, value):
        return utc(value)

    @model_validator(mode="after")
    def chronology(self):
        if self.available_at < self.effective_at:
            raise ValueError("Availability cannot precede effective time")
        return self


class ResearchFrame(DataModel):
    """Read-only historical snapshot. Proofs absent in legacy captures stay absent."""

    decision_at: datetime
    ticker: str
    issuer: str
    chain_id: str
    contract: str
    data_mode: DataMode
    metadata: tuple[TokenMetadata, ...] = ()
    tokens: tuple[TokenObservation | RawTokenBar, ...] = ()
    equities: tuple[EquityObservation, ...] = ()
    news: tuple[NewsEvent, ...] = ()
    samples: tuple[TrustSample, ...] = ()
    baseline_episodes: tuple[TrustEpisode, ...] = ()
    proofs: tuple[AvailableRecord, ...] = ()
    news_coverage_available_at: datetime | None = None
    news_prefix_start: datetime | None = None

    @field_validator("decision_at", "news_coverage_available_at", "news_prefix_start")
    @classmethod
    def aware(cls, value):
        return utc(value) if value else None

    @model_validator(mode="after")
    def isolation(self):
        records = (*self.metadata, *self.tokens, *self.equities, *self.news)
        if any(r.data_mode != self.data_mode for r in records):
            raise ValueError("Mixed data modes are forbidden")
        if any(s.data_mode != self.data_mode for s in self.samples) or any(
            e.sample.data_mode != self.data_mode for e in self.baseline_episodes
        ):
            raise ValueError("Mixed historical modes are forbidden")
        return self


class ResearchDecision(DataModel):
    decision_id: str
    decision_at: datetime
    data_mode: DataMode
    ticker: str
    issuer: str
    chain_id: str
    contract: str
    regime: str
    opening_at: datetime
    previous_close_at: datetime
    token: TokenObservation | RawTokenBar | None = None
    independent_equity: EquityObservation | None = None
    trust: RepresentationTrust | None = None
    sample: TrustSample | None = None
    volume_percentile: Annotated[Exact, Field(ge=0, le=1)] | None = None
    off_hours_return: Exact | None = None
    closure_token: TokenObservation | None = None
    data_quality: Literal["ELIGIBLE", "REJECTED"]
    reasons: tuple[str, ...]
    provenance: tuple[AvailableRecord, ...] = ()
    policy: ResearchPolicy = ResearchPolicy()
    execution_ready: Literal[False] = False
    transaction_broadcast: Literal[False] = False

    @field_validator("decision_at", "opening_at", "previous_close_at")
    @classmethod
    def aware(cls, value):
        return utc(value)

    @model_validator(mode="after")
    def no_future(self):
        for record in (self.token, self.independent_equity, self.closure_token):
            if record is not None and (
                record.data_mode != self.data_mode
                or record.ticker != self.ticker
                or record.source_timestamp is None
                or record.source_timestamp > self.decision_at
                or record.ingestion_timestamp > self.decision_at
            ):
                raise ValueError("Future or conflicting observation in decision")
        if self.off_hours_return is not None and (
            self.closure_token is None
            or self.closure_token.source_timestamp > self.previous_close_at
        ):
            raise ValueError("Off-hours return requires an observed closure anchor")
        if any(
            p.effective_at > self.decision_at or p.available_at > self.decision_at
            for p in self.provenance
        ):
            raise ValueError("Future provenance cannot enter decision features")
        if self.sample is not None and (
            self.sample.features.asof != self.decision_at
            or self.sample.features.available_at > self.decision_at
            or self.sample.data_mode != self.data_mode
        ):
            raise ValueError("Conflicting decision features")
        if self.sample is not None and (
            (
                self.sample.ticker,
                self.sample.issuer,
                self.sample.chain_id,
                self.sample.contract,
                self.sample.regime,
            )
            != (self.ticker, self.issuer, self.chain_id, self.contract, self.regime)
        ):
            raise ValueError("Conflicting feature scope")
        if self.data_quality == "ELIGIBLE" and (
            self.reasons
            or self.sample is None
            or self.volume_percentile is None
            or self.trust is None
            or self.trust.baseline.status != "SUFFICIENT"
            or self.regime not in REGIMES
            or not self.previous_close_at < self.decision_at
            or not self.decision_at < self.opening_at
        ):
            raise ValueError("Incomplete eligible decision")
        if self.data_quality == "ELIGIBLE" and (
            self.token is None
            or self.independent_equity is None
            or self.trust.reference.status != "AVAILABLE"
            or self.trust.liquidity.status != "AVAILABLE"
            or self.trust.news.coverage != "COMPLETE_REQUESTED_WINDOW"
            or self.trust.baseline.sample_count < 30
            or self.volume_percentile != self.trust.baseline.volume_percentile
            or not self.provenance
        ):
            raise ValueError("Unverified eligible evidence")
        if self.trust is not None:
            timestamps = (
                *self.trust.news.published_timestamps,
                *self.trust.news.first_seen_timestamps,
            )
            if any(t > self.decision_at for t in timestamps) or (
                self.trust.liquidity.observed_at is not None
                and self.trust.liquidity.observed_at > self.decision_at
            ):
                raise ValueError("Future news/liquidity in decision evidence")
        return self

    @property
    def scope(self):
        return (
            (*self.sample.scope, self.policy.version, self.policy.target_version)
            if (self.sample is not None)
            else None
        )


class OpeningTarget(DataModel):
    status: Literal["AVAILABLE", "POSTHOC_ONLY", "UNSCORABLE"]
    opening_at: datetime
    completed_at: datetime
    available_at: datetime | None = None
    previous_close: Positive | None = None
    first_bar_close: Positive | None = None
    opening_return: Exact | None = None
    reasons: tuple[str, ...] = ()
    provenance: tuple[AvailableRecord, ...] = ()
    target_version: str = ResearchPolicy().target_version

    @field_validator("opening_at", "completed_at", "available_at")
    @classmethod
    def aware(cls, value):
        return utc(value) if value else None

    @model_validator(mode="after")
    def chronology(self):
        if self.completed_at != self.opening_at + timedelta(minutes=OPENING_MINUTES) or (
            self.available_at is not None and self.available_at < self.completed_at
        ):
            raise ValueError("Opening outcome availability must follow completion")
        if self.status == "AVAILABLE" and (
            self.opening_return is None
            or self.previous_close is None
            or self.first_bar_close is None
            or self.available_at is None
            or not self.provenance
        ):
            raise ValueError("Incomplete opening outcome")
        if self.opening_return is not None:
            if self.previous_close is None or self.first_bar_close is None:
                raise ValueError("Opening return requires exact prices")
            with localcontext() as context:
                context.prec = 256
                expected = (self.first_bar_close - self.previous_close) / self.previous_close
            if self.opening_return != expected:
                raise ValueError("Conflicting opening return")
        if self.available_at is not None and any(
            p.available_at > self.available_at for p in self.provenance
        ):
            raise ValueError("Outcome cannot precede revision availability")
        return self


class ResearchEpisode(DataModel):
    episode_id: str
    decision: ResearchDecision
    target: OpeningTarget
    evidence_kind: Literal["LOCAL_OBSERVATIONS", "SYNTHETIC_TEST"]

    @model_validator(mode="after")
    def isolated(self):
        if self.evidence_kind == "SYNTHETIC_TEST" and self.decision.data_mode != "DEMO":
            raise ValueError("Synthetic research cannot enter LIVE history")
        if self.target.opening_at != self.decision.opening_at:
            raise ValueError("Outcome belongs to another opening")
        return self


class AnalogueMatch(DataModel):
    episode_id: str
    similarity: Exact
    opening_return: Exact
    pattern: Literal["UP", "DOWN", "FLAT"]
    outcome_available_at: datetime
    feature_at: datetime
    feature_available_at: datetime
    provenance: tuple[AvailableRecord, ...]
    evidence_kind: Literal["LOCAL_OBSERVATIONS", "SYNTHETIC_TEST"]


class RetrievalResult(DataModel):
    status: Literal["SUFFICIENT", "INSUFFICIENT_DATA", "NOT_READY"]
    eligible_count: int
    retrieved_count: int
    matches: tuple[AnalogueMatch, ...] = ()
    rejected: dict[str, tuple[str, ...]] = {}
    historical_pattern: str = "INSUFFICIENT_DATA"
    vector_version: Literal["explicit-scales-onehot-l2-v1"] = "explicit-scales-onehot-l2-v1"
    guaranteed_prediction: Literal[False] = False


class OpeningPrediction(DataModel):
    status: Literal["READY", "INSUFFICIENT_DATA", "NOT_READY"]
    reason: str
    eligible_count: int
    sample_count: int
    training_ids: tuple[str, ...] = ()
    model_id: str | None = None
    coefficients: dict[str, Exact] = {}
    predicted_return: Exact | None = None
    interval_low: Exact | None = None
    interval_high: Exact | None = None
    interval_method: Literal["APPROXIMATE_NORMAL_UNCALIBRATED"] = "APPROXIMATE_NORMAL_UNCALIBRATED"
    direction: Literal["UP", "DOWN", "FLAT"] | None = None
    confidence: Literal["UNCALIBRATED", "INSUFFICIENT_DATA"] = "INSUFFICIENT_DATA"
    historical_directional_accuracy: Annotated[Exact, Field(ge=0, le=1)] | None = None
    accuracy_sample_count: int = 0
    evidence_kind: Literal["LOCAL_EMPIRICAL_RESULT", "SYNTHETIC_TEST"]


class ReplayCosts(DataModel):
    """Optional observed costs. Missing costs cannot be silently zero-filled."""

    observed_at: datetime
    available_at: datetime
    requested_notional: Positive
    slippage_bps: Annotated[Nonnegative, Field(le=10000)]
    fees: Nonnegative
    gas: Nonnegative
    execution_buffer: Nonnegative
    source: str = Field(min_length=1)

    @field_validator("observed_at", "available_at")
    @classmethod
    def aware(cls, value):
        return utc(value)

    @model_validator(mode="after")
    def chronology(self):
        if self.available_at < self.observed_at:
            raise ValueError("Cost availability cannot precede observation")
        for value in (
            self.requested_notional,
            self.slippage_bps,
            self.fees,
            self.gas,
            self.execution_buffer,
        ):
            bounded_decimal(value)
        return self


class ReplayRow(DataModel):
    episode_id: str
    decision_id: str
    decision_at: datetime
    eligibility: Literal["ELIGIBLE", "REJECTED"]
    trust_state: str
    retrieval: RetrievalResult
    prediction: OpeningPrediction
    expected_adjustment_per_share: Exact | None = None
    cost_adjusted_edge_usd: Exact | None = None
    hypothetical_decision: Literal["DEFER", "PROPOSE_RESEARCH_ONLY"] = "DEFER"
    hypothetical_risk: Literal["NOT_READY", "REJECTED_PRODUCTION_GATES"] = "NOT_READY"
    hypothetical_outcome: dict[str, str | None] = {}
    reasons: tuple[str, ...]
    execution_ready: Literal[False] = False
    transaction_broadcast: Literal[False] = False


class ReplayRun(DataModel):
    run_id: str
    dataset_digest: str
    implementation_digest: str
    policy: ResearchPolicy
    data_mode: DataMode
    episode_count: int
    eligible_episode_count: int
    prediction_count: int
    accuracy_sample_count: int
    directional_accuracy: Exact | None
    rows: tuple[ReplayRow, ...]
    episodes: tuple[ResearchEpisode, ...]
    costs: dict[str, ReplayCosts]
    provenance: tuple[str, ...]
    production_writes: Literal[0] = 0
    execution_calls: Literal[0] = 0
    trust_gate: Literal["BLOCKED"] = "BLOCKED"
    opportunity_gate: Literal["BLOCKED_BY_TRUST"] = "BLOCKED_BY_TRUST"

    @model_validator(mode="after")
    def dataset_isolated(self):
        if any(e.decision.data_mode != self.data_mode for e in self.episodes):
            raise ValueError("Mixed persisted replay dataset")
        identifiers = {e.episode_id for e in self.episodes}
        if (
            len(identifiers) != self.episode_count
            or len(self.rows) != self.episode_count
            or {r.episode_id for r in self.rows} != identifiers
            or set(self.costs) - identifiers
        ):
            raise ValueError("Incomplete persisted replay dataset")
        return self
