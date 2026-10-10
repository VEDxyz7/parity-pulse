"""Mode-independent route analysis. A selection is never execution authorization."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.models.data import DataMode, DataModel, Quality, utc
from app.models.opportunity import Amount, Price


class RouteIdentity(DataModel):
    underlying: str
    issuer: str
    chain_id: str
    contract: str
    token: str


class RoutePolicy(DataModel):
    version: Literal["routing-1"] = "routing-1"
    purpose: Literal["INDICATIVE_EXPOSURE", "OPPORTUNITY"] = "INDICATIVE_EXPOSURE"
    require_costs: bool = Field(default=False, strict=True)
    require_liquidity: bool = Field(default=False, strict=True)
    require_trust: bool = Field(default=False, strict=True)
    require_risk: bool = Field(default=False, strict=True)
    min_liquidity_usd: Amount | None = None
    max_slippage_bps: Amount | None = Field(default=None, le=10000)
    max_age_seconds: Literal[120] = 120
    ranking: Literal["MIN_EXACT_EFFECTIVE_COST_THEN_IDENTITY"] = (
        "MIN_EXACT_EFFECTIVE_COST_THEN_IDENTITY"
    )
    weights: None = None
    unknown_cost_behavior: Literal["COMMON_PRICE_ONLY_BASIS_OR_REJECT_IF_REQUIRED"] = (
        "COMMON_PRICE_ONLY_BASIS_OR_REJECT_IF_REQUIRED"
    )

    @model_validator(mode="after")
    def strict_opportunity(self):
        if self.purpose == "OPPORTUNITY" and not (
            self.require_costs
            and self.require_liquidity
            and self.require_trust
            and self.require_risk
            and self.min_liquidity_usd is not None
            and self.max_slippage_bps is not None
        ):
            raise ValueError(
                "Opportunity routing requires every existing financial/evidence control"
            )
        return self


class RouteInput(DataModel):
    identity: RouteIdentity
    data_mode: DataMode
    token_price_usd: Price | None
    token_to_share_ratio: Price
    price_source: str
    price_timestamp: datetime | None
    price_quality: Quality
    ratio_source: str
    ratio_observed_at: datetime
    ratio_source_timestamp: datetime | None = None
    supported: bool = Field(default=True, strict=True)
    normalization_eligible: bool = Field(default=True, strict=True)
    normalization_reasons: list[str] = []
    market_state: str
    tradable: bool | None
    liquidity_usd: Amount | None = None
    liquidity_status: Literal["AVAILABLE", "UNAVAILABLE", "UNVERIFIED"] = "UNAVAILABLE"
    liquidity_source: str | None = None
    liquidity_timestamp: datetime | None = None
    volume_usd: Amount | None = None
    fees_usd: Amount | None = None
    gas_usd: Amount | None = None
    slippage_bps: Amount | None = Field(default=None, le=10000)
    cost_status: Literal["AVAILABLE", "UNAVAILABLE", "UNVERIFIED"] = "UNAVAILABLE"
    cost_source: str | None = None
    cost_timestamp: datetime | None = None
    trust_state: Literal[
        "UNKNOWN", "NORMAL", "LIKELY_INFORMATION", "LIKELY_NOISE", "INSUFFICIENT_EVIDENCE"
    ] = "UNKNOWN"
    trust_source: str | None = None
    trust_timestamp: datetime | None = None
    trust_assessment_id: UUID | None = None
    risk_state: Literal["UNKNOWN", "PASS", "FAIL"] = "UNKNOWN"
    risk_source: str | None = None
    risk_timestamp: datetime | None = None
    risk_id: UUID | None = None
    risk_max_notional_usd: Amount | None = None
    risk_reason_codes: list[str] = []
    route_available: bool | None = None
    route_support: Literal[
        "INDICATIVE_ONLY", "SYNTHETIC_DEMO_PREPARATION", "VERIFIED_PROVIDER_ROUTE", "UNAVAILABLE"
    ] = "INDICATIVE_ONLY"

    @field_validator(
        "price_timestamp",
        "ratio_observed_at",
        "ratio_source_timestamp",
        "liquidity_timestamp",
        "cost_timestamp",
        "trust_timestamp",
        "risk_timestamp",
    )
    @classmethod
    def aware(cls, value):
        return utc(value) if value is not None else None


class RouteCandidate(DataModel):
    candidate_id: UUID
    inputs: RouteInput
    eligible: bool
    rank: int | None = Field(default=None, ge=1)
    rejection_reasons: list[str]
    limitations: list[str]
    effective_cost_per_share_usd: Price | None
    estimated_costs_usd: Amount | None
    all_in_cost_per_share_usd: Price | None
    ranking_cost_per_share_usd: Price | None
    liquidity_state: Literal["AVAILABLE", "UNAVAILABLE", "UNVERIFIED", "STALE"]
    cost_state: Literal["AVAILABLE", "UNAVAILABLE", "UNVERIFIED", "STALE"]
    trust_state: str
    tradability: Literal["TRADABLE", "NOT_TRADABLE", "UNKNOWN"]


class RouteDecision(DataModel):
    schema_version: Literal["routing-1"] = "routing-1"
    route_id: UUID
    underlying: str | None
    requested_notional_usd: Price | None
    data_mode: DataMode
    source: Literal["DETERMINISTIC_ROUTER"] = "DETERMINISTIC_ROUTER"
    timestamp: datetime
    valid_until: datetime
    policy: RoutePolicy
    status: Literal["ROUTE_SELECTED", "NO_ROUTE"]
    selected_representation: RouteIdentity | None
    issuer: str | None
    candidates: list[RouteCandidate]
    selected_candidate: RouteCandidate | None
    ranking_basis: Literal["TOKEN_PRICE_ONLY", "ALL_IN_ESTIMATE", "NONE"]
    reason_codes: list[str]
    explanation: str
    execution_ready: Literal[False] = False
    transaction_broadcast: Literal[False] = False
    live_trading_enabled: Literal[False] = False
    execution_mode: Literal["DRY_RUN"] = "DRY_RUN"
    provider_execution_mode: None = None
    no_broadcast_statement: Literal["No real transaction was broadcast."] = (
        "No real transaction was broadcast."
    )

    _utc = field_validator("timestamp", "valid_until")(utc)

    @model_validator(mode="after")
    def selected_consistency(self):
        if self.status == "ROUTE_SELECTED":
            c = self.selected_candidate
            if (
                c is None
                or not c.eligible
                or c.rank != 1
                or c not in self.candidates
                or self.selected_representation != c.inputs.identity
                or self.issuer != c.inputs.identity.issuer
            ):
                raise ValueError("Selected route must equal the first ranked eligible candidate")
        elif (
            self.selected_candidate is not None
            or self.selected_representation is not None
            or self.issuer is not None
        ):
            raise ValueError("NO_ROUTE cannot select a representation")
        return self
