"""Explicit synthetic financial mandate, policy and non-executable risk decision."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.models.data import DataModel, utc
from app.models.demo_sandbox import DemoMarker
from app.models.opportunity import Amount, AnalyticalSafety, Fraction, Price


class RiskInputs(DemoMarker):
    version: Literal["demo-risk-1"]
    budget_usd: Price
    risk_budget_usd: Price
    adverse_move_fraction: Fraction
    wallet_available_usd: Amount
    existing_exposure_usd: Amount
    daily_loss_usd: Amount
    trades_today: int = Field(strict=True, ge=0)
    last_trade_at: datetime | None

    @field_validator("last_trade_at")
    @classmethod
    def aware(cls, value):
        return utc(value) if value is not None else None


class RiskPolicy(DemoMarker):
    version: Literal["demo-risk-policy-1"]
    max_position_usd: Price
    max_portfolio_exposure_usd: Price
    max_daily_loss_usd: Price
    max_risk_budget_usd: Price
    max_trades_per_day: int = Field(strict=True, ge=1)
    min_confidence: Literal["LOW", "MEDIUM", "HIGH"]
    min_liquidity_usd: Price
    min_liquidity_percentile: Literal[50]
    max_liquidity_fraction: Fraction
    max_slippage_bps: Annotated[Amount, Field(le=10000)]
    min_net_edge_usd: Price
    max_data_staleness_seconds: Literal[120]
    max_timestamp_skew_seconds: Literal[30]
    cooldown_seconds: int = Field(strict=True, ge=1)
    # LOW is permitted solely by this synthetic policy, never a production default.
    policy_scope: Literal["SYNTHETIC_DEMO_ONLY"]


class RiskCheck(DataModel):
    code: str
    passed: bool = Field(strict=True)
    detail: str


class RiskDecision(AnalyticalSafety):
    risk_id: UUID
    opportunity_id: UUID
    evaluated_at: datetime
    status: Literal["PASS", "FAIL"]
    approved_for_demo_analysis: bool = Field(strict=True)
    reason_codes: list[str]
    checks: list[RiskCheck]
    inputs: RiskInputs
    policy: RiskPolicy
    maximum_allowed_notional_usd: Amount
    proposed_notional_usd: Price | None
    proposed_token_quantity: Amount | None
    proposed_share_exposure: Amount | None
    stress_loss_usd: Amount | None
    slippage_tolerance_bps: Amount
    liquidity_notional_cap_usd: Amount
    limitations: tuple[str, ...] = (
        "PASS_APPROVES_SYNTHETIC_ANALYSIS_ONLY_NOT_TRADING",
        "STRESS_LOSS_IS_A_SCENARIO_ESTIMATE_NOT_A_GUARANTEED_MAXIMUM_LOSS",
        "PRODUCTION_GATES_REMAIN_BLOCKED",
    )

    @field_validator("evaluated_at")
    @classmethod
    def aware(cls, value):
        return utc(value)

    @model_validator(mode="after")
    def consistent(self):
        passed = self.status == "PASS"
        if passed != self.approved_for_demo_analysis or passed != all(
            c.passed for c in self.checks
        ):
            raise ValueError("Risk status must agree with all deterministic checks")
        if passed and (
            not self.checks
            or self.proposed_notional_usd is None
            or self.proposed_notional_usd > self.maximum_allowed_notional_usd
            or self.proposed_token_quantity is None
            or self.proposed_token_quantity <= 0
            or self.proposed_share_exposure is None
            or self.stress_loss_usd is None
        ):
            raise ValueError("Passing risk decision needs a constrained positive size")
        if not passed and any(
            v is not None
            for v in (
                self.proposed_notional_usd,
                self.proposed_token_quantity,
                self.proposed_share_exposure,
                self.stress_loss_usd,
            )
        ):
            raise ValueError("Failed risk decision cannot propose an approved size")
        return self


class OpportunityRiskContext(DataModel):
    """Server-supplied read-only constraints; never derived from agent confidence/budget."""

    data_mode: Literal["DEMO", "LIVE_READ_ONLY"]
    observed_at: datetime
    source: str = Field(min_length=1, max_length=128)
    stress_adverse_move_fraction: Fraction
    wallet_available_usd: Amount
    existing_exposure_usd: Amount
    daily_loss_usd: Amount
    trades_today: int = Field(strict=True, ge=0)
    last_trade_at: datetime | None
    system_resolved: bool = Field(strict=True)
    wallet_allowed: bool = Field(strict=True)
    max_position_usd: Price
    max_portfolio_exposure_usd: Price
    max_daily_loss_usd: Price
    max_risk_budget_usd: Price
    max_trades_per_day: int = Field(strict=True, ge=1)
    max_liquidity_fraction: Fraction
    min_confidence: Literal["LOW", "MEDIUM", "HIGH"]
    min_liquidity_usd: Price
    min_liquidity_percentile: Literal[50]
    max_slippage_bps: Amount = Field(le=10000)
    min_net_edge_usd: Price
    cooldown_seconds: int = Field(strict=True, ge=1)

    @field_validator("observed_at", "last_trade_at")
    @classmethod
    def aware(cls, value):
        return utc(value) if value is not None else None
