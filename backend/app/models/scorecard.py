"""Evaluation records, not authorization. Missing labels/costs remain unknown."""

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.models.data import DataModel, Nonnegative, utc
from app.models.demo_paper import PaperPnL
from app.models.execution import Mode
from app.models.portfolio import Signed
from app.models.terminal import ExecutionAnalyticsRow, TerminalContext, TerminalPage

Kind = Literal["OPPORTUNITY", "DIRECT_EXPOSURE", "AUTOPILOT"]
Quality = Literal[
    "CORRECT_ACTION", "INCORRECT_ACTION", "CORRECT_ABSTENTION", "INCORRECT_ABSTENTION", "UNSCORABLE"
]
Scalar = str | bool | int | None


class ScorecardQuery(DataModel):
    decision_id: str | None = Field(default=None, min_length=1, max_length=160)
    ticker: str | None = Field(default=None, pattern=r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")
    data_mode: Mode | None = None
    scorecard_type: Kind | None = None
    outcome: str | None = Field(default=None, pattern=r"^[A-Z_]{1,40}$")
    execution_status: str | None = Field(default=None, pattern=r"^[A-Z_]{1,40}$")
    after: datetime | None = None
    before: datetime | None = None
    as_of: datetime | None = None
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)

    _utc = field_validator("after", "before", "as_of")(lambda v: utc(v) if v else None)


class PredictionEvaluation(DataModel):
    predicted_return: Signed | None = None
    actual_opening_return: Signed | None = None
    predicted_direction: Literal["UP", "DOWN", "FLAT"] | None = None
    actual_direction: Literal["UP", "DOWN", "FLAT"] | None = None
    direction_correct: bool | None = None
    absolute_magnitude_error: Nonnegative | None = None
    classification_correct: None = None
    correctly_ignored_noise: None = None
    noise_suppressed: bool = False
    label_status: Literal["INDEPENDENT_TRUST_LABEL_UNAVAILABLE"] = (
        "INDEPENDENT_TRUST_LABEL_UNAVAILABLE"
    )


class RouteEvaluation(DataModel):
    route_id: str | None = None
    selected_issuer: str | None = None
    basis: str = "UNAVAILABLE"
    token_price_usd: Nonnegative | None = None
    shares_per_token: Nonnegative | None = None
    effective_cost_per_share_usd: Nonnegative | None = None
    liquidity_state: str = "UNAVAILABLE"
    liquidity_usd: Nonnegative | None = None
    liquidity_source: str | None = None
    trust_state: str | None = None
    tradability: str | None = None
    selected_cost_per_share_usd: Nonnegative | None = None
    minimum_eligible_cost_per_share_usd: Nonnegative | None = None
    excess_cost_per_share_usd: Nonnegative | None = None
    minimum_cost_selected: bool | None = None
    alternative_costs_per_share_usd: dict[str, Nonnegative | None] = Field(
        default_factory=dict, max_length=500
    )
    estimated_costs_usd: Nonnegative | None = None
    estimated_fees_usd: Nonnegative | None = None
    estimated_gas_usd: Nonnegative | None = None
    estimated_slippage_bps: Nonnegative | None = None
    actual_fees_native_base_units: str | None = None
    actual_average_execution_price: Nonnegative | None = None
    actual_slippage_bps: None = None
    actual_total_cost_usd: None = None
    simulated_cost_usd: None = None
    provider: str | None = None
    provider_quote_id: str | None = None
    execution_mode: str | None = None
    reasons: tuple[str, ...] = ()


class Scorecard(DataModel):
    schema_version: Literal["scorecard-1"] = "scorecard-1"
    evaluation_id: str
    scorecard_type: Kind
    data_mode: Mode
    origin: str
    origin_id: str
    decision_id: str
    run_id: str | None = None
    episode_id: str | None = None
    correlation_id: str | None = None
    ticker: str | None = None
    selected_issuer: str | None = None
    decision_at: datetime
    recorded_at: datetime
    evidence_asof: datetime
    input_digest: str
    source_digest: str
    synthetic: bool
    action: str
    outcome: str
    control_quality: Quality
    control_quality_basis: Literal["EXISTING_POLICY_CONSISTENCY_NOT_PROFITABILITY"] = (
        "EXISTING_POLICY_CONSISTENCY_NOT_PROFITABILITY"
    )
    abstained: bool
    abstention_scope: Literal["DECISION", "EXECUTION", "NOT_APPLICABLE"] = "DECISION"
    abstention_reasons: tuple[str, ...] = ()
    confidence: str | None = None
    trust_classification: str | None = None
    score: None = None
    score_reason: Literal["NO_COMPOSITE_SCORE_FORMULA_DEFINED"] = (
        "NO_COMPOSITE_SCORE_FORMULA_DEFINED"
    )
    requested_exposure_usd: Nonnegative | None = None
    estimated_share_exposure: Nonnegative | None = None
    expected_net_edge_usd: Signed | None = None
    prediction: PredictionEvaluation = PredictionEvaluation()
    route: RouteEvaluation = RouteEvaluation()
    executions: tuple[ExecutionAnalyticsRow, ...] = Field(default=(), max_length=100)
    allocations: tuple[dict[str, Scalar], ...] = Field(default=(), max_length=25)
    proposed_actions: tuple[dict[str, Scalar], ...] = Field(default=(), max_length=100)
    paper_pnl: PaperPnL | None = None
    reasons: tuple[str, ...] = ()
    event_ids: tuple[str, ...] = Field(default=(), max_length=2000)
    execution_ready: Literal[False] = False
    broadcast: Literal[False] = False

    _utc = field_validator("decision_at", "recorded_at", "evidence_asof")(utc)


class AuditEvent(DataModel):
    event_id: str
    data_mode: Mode
    decision_id: str
    run_id: str | None = None
    episode_id: str | None = None
    execution_id: str | None = None
    correlation_id: str | None = None
    ticker: str | None = None
    timestamp: datetime
    recorded_at: datetime
    event_type: str
    actor: Literal["DETERMINISTIC_BACKEND", "STRUCTURED_AGENT", "EVALUATOR"]
    source: str
    source_digest: str
    capture_kind: Literal["PERSISTED_SOURCE_PROJECTION", "OBSERVED_TOOL_INVOCATION"] = (
        "PERSISTED_SOURCE_PROJECTION"
    )
    status: str
    input_summary: dict[str, Scalar] = Field(default_factory=dict, max_length=30)
    output_summary: dict[str, Scalar] = Field(default_factory=dict, max_length=30)
    reasons: tuple[str, ...] = Field(default=(), max_length=100)

    _utc = field_validator("timestamp", "recorded_at")(utc)


class TraceStage(DataModel):
    stage: str
    status: Literal["RECORDED", "UNAVAILABLE_OR_NOT_APPLICABLE"]
    event_ids: tuple[str, ...]


class DecisionTrace(TerminalContext):
    decision_id: str
    stages: tuple[TraceStage, ...]
    events: tuple[AuditEvent, ...]
    scorecards: tuple[Scorecard, ...]
    complete_for_recorded_scope: bool
    limitations: tuple[str, ...] = (
        "SOURCE_PROJECTIONS_ARE_NOT_NEW_PROVIDER_OR_EXECUTION_OPERATIONS",
        "UNRECORDED_STAGES_ARE_NEVER_INFERRED_SUCCESSFUL",
    )


class EvaluationMetrics(DataModel):
    decision_count: int
    directional_samples: int
    directional_accuracy: Nonnegative | None
    high_confidence_samples: int
    high_confidence_accuracy: Nonnegative | None
    control_quality_counts: dict[str, int]
    classification_accuracy: None = None
    abstention_outcome_accuracy: None = None
    statistical_validation: Literal["NOT_CLAIMED"] = "NOT_CLAIMED"


class ScorecardPage(TerminalContext):
    page: TerminalPage[Scorecard]
    metrics: EvaluationMetrics
    limitations: tuple[str, ...] = (
        "POLICY_CONSISTENCY_IS_NOT_PROFITABILITY",
        "INDEPENDENT_CLASSIFICATION_LABELS_AND_COMPOSITE_SCORE_UNAVAILABLE",
        "LATEST_VALIDATED_EXECUTION_SNAPSHOT_ONLY_EARLIER_STATE_NOT_RECONSTRUCTED",
        "DESCRIPTIVE_EVALUATIONS_NOT_INDEPENDENT_MARKET_SAMPLE_ESTIMATES",
    )


class AuditPage(TerminalContext):
    page: TerminalPage[AuditEvent]
    limitations: tuple[str, ...] = (
        "SOURCE_PROJECTIONS_ARE_NOT_NEW_PROVIDER_OR_EXECUTION_OPERATIONS",
        "UNRECORDED_STAGES_ARE_NEVER_INFERRED_SUCCESSFUL",
    )
