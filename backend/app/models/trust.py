"""Canonical Phase 2: exact, timestamped analytical evidence, never execution authority."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BeforeValidator, Field, StrictBool, StrictInt, field_validator, model_validator

from app.models.data import (
    DataMode,
    DataModel,
    EquityObservation,
    Nonnegative,
    Positive,
    financial,
    utc,
)

Exact = Annotated[Decimal, BeforeValidator(financial)]
State = Literal["NORMAL", "LIKELY_NOISE", "LIKELY_INFORMATION", "INSUFFICIENT_EVIDENCE"]
NewsState = Literal[
    "NO_RELEVANT_NEWS", "RELEVANT_NEWS", "CORROBORATING", "CONFLICTING", "PARTIAL", "UNAVAILABLE"
]


class TrustPolicy(DataModel):
    version: Literal["trust-engineering-v1"] = "trust-engineering-v1"
    provenance: Literal["ENGINEERING_POLICY"] = "ENGINEERING_POLICY"
    lookback_days: Literal[180] = 180
    min_baseline_episodes: Literal[30] = 30
    min_analogues: Literal[3] = 3
    top_k: Literal[3] = 3
    max_age_seconds: Literal[120] = 120
    max_skew_seconds: Literal[30] = 30
    episode_minutes: Literal[30] = 30
    max_observation_gap_seconds: Literal[120] = 120
    similarity_floor: Literal["0.8"] = "0.8"


class RegimeEvidence(DataModel):
    state: str
    baseline_bucket: str
    evaluated_at: datetime
    previous_regular_open: datetime
    previous_regular_close: datetime
    next_open: datetime
    early_close: StrictBool
    reopening: StrictBool
    multi_day_closure: StrictBool
    schedule_version: str
    earnings_window: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    scheduled_not_halt_status: Literal[True] = True


class ReferenceEvidence(DataModel):
    status: Literal["AVAILABLE", "UNAVAILABLE", "STALE", "CONFLICTING", "UNVERIFIED"]
    observation: EquityObservation | None = None
    reference_asof: datetime | None = None
    timestamp_skew_seconds: Nonnegative | None = None
    token_age_seconds: Nonnegative | None = None
    reference_age_seconds: Nonnegative | None = None
    reason_codes: list[str] = []


class LiquidityEvidence(DataModel):
    status: Literal["AVAILABLE", "UNAVAILABLE", "AMBIGUOUS", "STALE", "CONFLICTING"]
    source: str | None = None
    observed_at: datetime | None = None
    volume_24h_usd: Nonnegative | None = None
    liquidity_usd: Nonnegative | None = None
    trade_count_24h: StrictInt | None = Field(default=None, ge=0)
    buy_volume_24h_usd: Nonnegative | None = None
    sell_volume_24h_usd: Nonnegative | None = None
    buy_transactions_24h: StrictInt | None = Field(default=None, ge=0)
    sell_transactions_24h: StrictInt | None = Field(default=None, ge=0)
    estimated_slippage: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    excluded_inputs: tuple[str, ...] = ("TRADE_PRICE_UNITS", "CANDLE_VOLUME_UNITS")
    reason_codes: list[str] = []


class NewsEvidence(DataModel):
    state: NewsState
    directional_state: Literal["CORROBORATING", "CONFLICTING", "UNKNOWN"] = "UNKNOWN"
    coverage: Literal["COMPLETE_REQUESTED_WINDOW", "PARTIAL", "UNAVAILABLE"]
    window_start: datetime
    window_end: datetime
    article_ids: list[str] = []
    published_timestamps: list[datetime] = []
    first_seen_timestamps: list[datetime] = []
    directional_article_ids: list[str] = []
    method: Literal["DETERMINISTIC_HEADLINE_RULES_V1"] = "DETERMINISTIC_HEADLINE_RULES_V1"
    reason_codes: list[str] = []
    absence_proves_no_information: Literal[False] = False
    provider_llm_sentiment_used: Literal[False] = False


class TrustFeatures(DataModel):
    effective_price_per_share_usd: Positive
    comparable_token_value_usd: Positive
    deviation: Exact
    absolute_deviation: Nonnegative
    volume_24h_usd: Nonnegative
    liquidity_usd: Nonnegative
    persistence_seconds: Nonnegative
    time_to_open_seconds: Nonnegative
    starting_deviation: Exact
    ending_deviation: Exact  # Ending at feature time, NEVER the future episode outcome.
    news_state: NewsState
    asof: datetime
    available_at: datetime

    @field_validator("asof", "available_at")
    @classmethod
    def aware(cls, value):
        return utc(value)

    @model_validator(mode="after")
    def consistency(self):
        if self.available_at < self.asof:
            raise ValueError("Features cannot be available before observed")
        if (
            self.absolute_deviation != self.deviation.copy_abs()
            or self.ending_deviation != self.deviation
        ):
            raise ValueError("Conflicting feature economics")
        return self


class TrustSample(DataModel):
    sample_id: str
    data_mode: DataMode
    ticker: str
    issuer: str
    chain_id: str
    contract: str
    regime: str
    ratio: Positive
    reference_kind: Literal["CURRENT", "REGULAR_CLOSE"]
    features: TrustFeatures
    policy_version: Literal["trust-engineering-v1"] = "trust-engineering-v1"

    @property
    def scope(self):
        return (
            self.data_mode,
            self.ticker,
            self.issuer,
            self.chain_id,
            self.contract,
            self.regime,
            self.ratio,
            self.reference_kind,
            self.policy_version,
        )


class TrustEpisode(DataModel):
    episode_id: str
    sample: TrustSample  # Features at the middle of the completed 30-minute window.
    started_at: datetime
    ended_at: datetime
    outcome_available_at: datetime
    outcome_deviation: Exact
    outcome: Literal["REVERSED", "PERSISTED", "MIXED"]
    observation_count: StrictInt = Field(ge=2)
    evidence_kind: Literal["LOCAL_OBSERVATIONS", "SYNTHETIC_TEST"] = "LOCAL_OBSERVATIONS"

    @field_validator("started_at", "ended_at", "outcome_available_at")
    @classmethod
    def aware(cls, value):
        return utc(value)

    @model_validator(mode="after")
    def no_future_features(self):
        if not (
            self.started_at
            <= self.sample.features.asof
            < self.ended_at
            <= self.outcome_available_at
        ):
            raise ValueError("Invalid episode chronology")
        if self.sample.features.available_at >= self.ended_at:
            raise ValueError("Features must predate the outcome")
        if self.evidence_kind == "SYNTHETIC_TEST" and self.sample.data_mode != "DEMO":
            raise ValueError("Synthetic episodes cannot enter LIVE history")
        return self


class Distribution(DataModel):
    mean: Exact
    median: Exact
    mad: Nonnegative
    standard_deviation: Nonnegative
    quantiles: dict[str, Exact]


class BaselineEvidence(DataModel):
    status: Literal["SUFFICIENT", "INSUFFICIENT", "DEGENERATE", "TRUNCATED"]
    sample_count: StrictInt
    minimum_sample_count: Literal[30] = 30
    regime: str
    ticker: str
    lookback_start: datetime
    decision_at: datetime
    deviation: Distribution | None = None
    absolute_deviation: Distribution | None = None
    volume: Distribution | None = None
    liquidity: Distribution | None = None
    persistence: Distribution | None = None
    deviation_percentile: Nonnegative | None = None
    volume_percentile: Nonnegative | None = None
    z_score: Exact | None = None
    research_coefficients_used: Literal[False] = False


class AnalogueEvidence(DataModel):
    status: Literal["SUFFICIENT", "INSUFFICIENT"]
    eligible_sample_count: StrictInt
    retrieved_sample_count: StrictInt
    minimum_sample_count: Literal[3] = 3
    method: Literal["BASELINE_SCALED_L2_COSINE_TOP_3"] = "BASELINE_SCALED_L2_COSINE_TOP_3"
    matches: list[dict] = []
    guaranteed_prediction: Literal[False] = False


class RepresentationTrust(DataModel):
    ticker: str
    issuer: str
    chain_id: str
    contract: str
    symbol: str
    token_price_usd: Positive | None
    token_to_share_ratio: Positive
    token_timestamp: datetime | None
    ratio_observed_at: datetime
    ratio_source_timestamp: datetime | None
    reference: ReferenceEvidence
    liquidity: LiquidityEvidence
    news: NewsEvidence
    baseline: BaselineEvidence
    analogues: AnalogueEvidence
    economic_comparison: dict[str, Exact] | None
    features: TrustFeatures | None
    classification: State
    confidence: Literal["LOW", "MEDIUM", "HIGH"] | None
    evidence_quality: Literal["INSUFFICIENT", "SYNTHETIC_DEMO", "LOCAL_EMPIRICAL_RESULT"]
    reason_codes: list[str]
    missing_evidence: list[str]


class TrustAssessment(DataModel):
    assessment_id: UUID
    run_id: str
    request_id: str
    correlation_id: str
    data_mode: DataMode
    evaluated_at: datetime
    ticker: str | None
    status: Literal["ASSESSED", "UNAVAILABLE"]
    regime: RegimeEvidence | None
    representations: list[RepresentationTrust]
    policy: TrustPolicy = TrustPolicy()
    limitations: list[str]
    execution_mode: Literal["DRY_RUN"] = "DRY_RUN"
    approval_mode: Literal["PROPOSE_ONLY"] = "PROPOSE_ONLY"
    live_trading_enabled: Literal[False] = False
    require_simulation: Literal[True] = True
    execution_ready: Literal[False] = False
    transaction_broadcast: Literal[False] = False
    no_broadcast_statement: Literal["No real transaction was broadcast."] = (
        "No real transaction was broadcast."
    )
    llm_authoritative: Literal[False] = False
    trust_gate: Literal["BLOCKED"] = "BLOCKED"
