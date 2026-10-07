"""Non-executable Opportunity contracts. This stage supports synthetic analysis only."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BeforeValidator, Field, field_validator, model_validator

from app.models.data import utc
from app.models.demo_sandbox import DemoMarker
from app.models.trust import State
from app.services.normalization import bounded_decimal, financial


def bounded(value):
    value = financial(value)
    bounded_decimal(value)
    return value


Money = Annotated[Decimal, BeforeValidator(bounded)]
Amount = Annotated[Money, Field(ge=0)]
Price = Annotated[Money, Field(gt=0)]
Fraction = Annotated[Money, Field(gt=0, le=1)]


class AnalyticalSafety(DemoMarker):
    data_mode: Literal["DEMO"] = "DEMO"
    execution_mode: Literal["DRY_RUN"] = "DRY_RUN"
    approval_mode: Literal["PROPOSE_ONLY"] = "PROPOSE_ONLY"
    live_trading_enabled: Literal[False] = False
    require_simulation: Literal[True] = True
    execution_ready: Literal[False] = False
    transaction_broadcast: Literal[False] = False
    no_broadcast_statement: Literal["No real transaction was broadcast."] = (
        "No real transaction was broadcast."
    )
    quote_status: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    preparation_status: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    simulation_status: Literal["UNAVAILABLE"] = "UNAVAILABLE"


class OpportunityInputs(DemoMarker):
    version: Literal["demo-economics-1"]
    ticker: str
    issuer: str
    chain_id: Literal["DEMO"]
    contract: str = Field(pattern=r"^demo:")
    observed_at: datetime
    target_basis: Literal["HYPOTHETICAL_SCENARIO_ASSUMPTION"]
    target_share_price_usd: Price
    requested_notional_usd: Price
    fees_usd: Amount
    gas_usd: Amount
    slippage_bps: Annotated[Amount, Field(le=10000)]
    execution_buffer_usd: Amount
    minimum_net_edge_usd: Price
    validity_seconds: int = Field(strict=True, ge=1, le=120)

    @field_validator("observed_at")
    @classmethod
    def aware(cls, value):
        return utc(value)


class OpportunityEconomics(DemoMarker):
    token_price_usd: Price
    token_to_share_ratio: Price
    independent_share_price_usd: Price
    effective_price_per_share_usd: Price
    reference_deviation: Money
    hypothetical_target_share_price_usd: Price
    hypothetical_adjustment_per_share_usd: Money
    hypothetical_return_fraction: Money
    requested_notional_usd: Price
    gross_hypothetical_edge_usd: Money
    estimated_slippage_usd: Amount
    fees_usd: Amount
    gas_usd: Amount
    execution_buffer_usd: Amount
    net_hypothetical_edge_usd: Money
    metric_basis: Literal["HYPOTHETICAL_SCENARIO_ASSUMPTION"] = "HYPOTHETICAL_SCENARIO_ASSUMPTION"
    calibrated_prediction: Literal[False] = False


class OpportunityDecision(AnalyticalSafety):
    opportunity_id: UUID
    trust_assessment_id: UUID
    evaluated_at: datetime
    valid_until: datetime
    ticker: str
    issuer: str
    chain_id: Literal["DEMO"]
    contract: str = Field(pattern=r"^demo:")
    symbol: str
    source_trust_classification: State
    confidence: Literal["LOW", "MEDIUM", "HIGH"] | None
    evidence_quality: Literal["SYNTHETIC_DEMO", "INSUFFICIENT"]
    status: Literal["NO_OPPORTUNITY", "REJECTED_BY_TRUST", "REJECTED", "ACTIONABLE"]
    action: Literal["BUY", "NONE"]
    reason_codes: list[str]
    inputs: OpportunityInputs
    economics: OpportunityEconomics | None
    token_observed_at: datetime | None
    equity_observed_at: datetime | None
    liquidity_observed_at: datetime | None
    liquidity_usd: Amount | None
    liquidity_p50_usd: Amount | None
    decimals: int | None = Field(ge=0, le=255)
    limitations: tuple[str, ...] = (
        "SYNTHETIC_ANALYSIS_ONLY_NOT_EXECUTION_AUTHORITY",
        "HYPOTHETICAL_TARGET_AND_COSTS_NOT_PROVIDER_QUOTE_OR_CALIBRATED_FORECAST",
        "SINGLE_REPRESENTATION_DEMO_NOT_FULL_UNIVERSE_OPPORTUNITY_MODE",
        "PRODUCTION_OPPORTUNITY_GATE_BLOCKED_BY_TRUST",
    )

    @field_validator(
        "evaluated_at",
        "valid_until",
        "token_observed_at",
        "equity_observed_at",
        "liquidity_observed_at",
    )
    @classmethod
    def aware(cls, value):
        return utc(value) if value is not None else None

    @model_validator(mode="after")
    def consistent(self):
        if (self.status == "ACTIONABLE") != (self.action == "BUY"):
            raise ValueError("Conflicting analytical action")
        if self.status == "ACTIONABLE" and (
            self.source_trust_classification != "LIKELY_INFORMATION"
            or self.economics is None
            or self.economics.net_hypothetical_edge_usd < self.inputs.minimum_net_edge_usd
        ):
            raise ValueError("Actionable decision needs qualifying economics and Trust")
        return self
