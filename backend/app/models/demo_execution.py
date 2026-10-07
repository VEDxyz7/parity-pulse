"""Synthetic quote/request/local simulation contracts. No executable chain payload exists."""

import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, field_validator, model_validator

from app.models.data import DataModel, utc
from app.models.demo_sandbox import DemoMarker, DemoProductionGates, ScenarioId
from app.models.opportunity import Amount, Money, OpportunityDecision, OpportunityInputs, Price
from app.models.risk import RiskCheck, RiskDecision
from app.models.routing import RouteDecision


def digest(value):
    if isinstance(value, DataModel):
        value = value.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def artifact_digest(value, id_field):
    return digest(value.model_dump(mode="json", exclude={id_field, "fingerprint"}))


def artifact_id(kind, fingerprint):
    return uuid5(NAMESPACE_URL, f"parity:synthetic:{kind}:{fingerprint}")


class DemoSafety(DemoMarker):
    source: Literal["DEMO"] = "DEMO"
    execution_mode: Literal["DRY_RUN"] = "DRY_RUN"
    approval_mode: Literal["PROPOSE_ONLY"] = "PROPOSE_ONLY"
    require_simulation: Literal[True] = True
    live_trading_enabled: Literal[False] = False
    execution_ready: Literal[False] = False
    transaction_broadcast: Literal[False] = False
    signed: Literal[False] = False
    funds_moved: Literal[False] = False
    no_broadcast_statement: Literal["No real transaction was broadcast."] = (
        "No real transaction was broadcast."
    )


class DemoQuote(DemoSafety):
    quote_id: UUID
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    opportunity_id: UUID
    source_risk_id: UUID
    ticker: str
    issuer: str
    chain_id: Literal["DEMO"]
    contract: str = Field(pattern=r"^demo:")
    symbol: str
    decimals: int = Field(strict=True, ge=0, le=255)
    direction: Literal["BUY"] = "BUY"
    input_asset: Literal["DEMO_USD"] = "DEMO_USD"
    quote_type: Literal["SYNTHETIC_ECONOMIC_QUOTE"] = "SYNTHETIC_ECONOMIC_QUOTE"
    provider_quote_id: None = None
    executable: Literal[False] = False
    quoted_at: datetime
    valid_until: datetime
    market_observed_at: datetime
    market_observation_kind: Literal["PRICE_INFO", "PRICE"]
    mark_price_usd: Price
    execution_price_usd: Price
    token_to_share_ratio: Price
    requested_notional_usd: Price
    base_notional_usd: Price
    input_amount_usd: Price
    output_token_quantity: Price
    share_exposure: Price
    fees_usd: Amount
    gas_usd: Amount
    execution_buffer_usd: Amount
    slippage_bps: Amount
    estimated_slippage_usd: Amount
    total_cash_required_usd: Price
    net_hypothetical_edge_usd: Money
    economics_inputs: OpportunityInputs
    limitations: tuple[str, ...] = (
        "SYNTHETIC_QUOTE_NOT_PROVIDER_EXECUTION_QUOTE",
        "FROZEN_DEMO_MARKET_OBSERVATION_NOT_LIVE_DATA",
        "SLIPPAGE_EMBEDDED_IN_EXECUTION_PRICE_NOT_CHARGED_TWICE",
    )

    @field_validator("quoted_at", "valid_until", "market_observed_at")
    @classmethod
    def aware(cls, value):
        return utc(value)


class DemoBuyParameters(DemoMarker):
    ticker: str
    issuer: str
    chain_id: Literal["DEMO"]
    target_token: str = Field(pattern=r"^demo:")
    token_symbol: str
    token_decimals: int = Field(strict=True, ge=0, le=255)
    token_base_units: str = Field(pattern=r"^[1-9][0-9]{0,511}$")
    direction: Literal["BUY"] = "BUY"
    input_asset: Literal["DEMO_USD"] = "DEMO_USD"
    quote_id: UUID
    quantity: Price
    base_notional_usd: Price
    maximum_input_usd: Price
    minimum_output_tokens: Price
    maximum_slippage_bps: Amount
    fees_usd: Amount
    gas_usd: Amount
    execution_buffer_usd: Amount
    total_cash_required_usd: Price


class PreparedDemoRequest(DemoSafety):
    transaction_id: UUID
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    quote_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    quote_id: UUID
    opportunity_id: UUID
    prepared_at: datetime
    valid_until: datetime
    transaction_type: Literal["DEMO_BUY_REQUEST"] = "DEMO_BUY_REQUEST"
    encoding: Literal["CANONICAL_JSON_DEMO_REQUEST"] = "CANONICAL_JSON_DEMO_REQUEST"
    parameters: DemoBuyParameters
    calldata: None = None
    signature: None = None
    broadcastable: Literal[False] = False

    @field_validator("prepared_at", "valid_until")
    @classmethod
    def aware(cls, value):
        return utc(value)


class DemoSimulation(DemoSafety):
    simulation_id: UUID
    transaction_id: UUID
    transaction_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    quote_id: UUID
    quote_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluated_at: datetime
    valid_until: datetime
    method: Literal["LOCAL_DEMO_CONSTRAINT_EVALUATION"] = "LOCAL_DEMO_CONSTRAINT_EVALUATION"
    chain_simulation: Literal[False] = False
    status: Literal["SIMULATION_PASS", "SIMULATION_FAIL"]
    reason_codes: list[str]
    checks: list[RiskCheck]
    risk_revalidation: RiskDecision

    @field_validator("evaluated_at", "valid_until")
    @classmethod
    def aware(cls, value):
        return utc(value)

    @model_validator(mode="after")
    def consistent(self):
        if not self.checks or (self.status == "SIMULATION_PASS") != all(
            c.passed for c in self.checks
        ):
            raise ValueError("Simulation status must agree with every constraint check")
        return self


class DemoStageResult(DemoSafety):
    runtime_mode: Literal["DEMO"] = "DEMO"
    scenario_id: ScenarioId
    inputs_fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    production_gates: DemoProductionGates = DemoProductionGates()
    reason_codes: list[str]


class DemoQuoteResult(DemoStageResult):
    route_decision: RouteDecision | None = None
    status: Literal["QUOTED", "BLOCKED"]
    quote: DemoQuote | None
    opportunity: OpportunityDecision
    risk_before_quote: RiskDecision
    quoted_opportunity: OpportunityDecision | None
    risk_revalidation: RiskDecision | None

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "QUOTED" and (
            self.quote is None
            or self.quoted_opportunity is None
            or self.risk_before_quote.status != "PASS"
            or self.risk_revalidation is None
            or self.risk_revalidation.status != "PASS"
            or self.quote.opportunity_id != self.opportunity.opportunity_id
            or self.quote.opportunity_id != self.quoted_opportunity.opportunity_id
            or self.quote.opportunity_id != self.risk_revalidation.opportunity_id
        ):
            raise ValueError("A quoted result needs matching revalidated Risk and Opportunity")
        return self


class DemoPreparationResult(DemoStageResult):
    status: Literal["PREPARED", "BLOCKED"]
    transaction: PreparedDemoRequest | None
    risk_revalidation: RiskDecision

    @model_validator(mode="after")
    def consistent(self):
        if (self.status == "PREPARED") != (self.transaction is not None):
            raise ValueError("Preparation status must match its request")
        if self.transaction is not None and (
            self.risk_revalidation.status != "PASS"
            or self.transaction.opportunity_id != self.risk_revalidation.opportunity_id
        ):
            raise ValueError("Preparation requires matching revalidated Risk")
        return self


class DemoSimulationResult(DemoStageResult):
    simulation: DemoSimulation


class QuoteRequest(DataModel):
    risk_id: UUID


class PreparationRequest(DataModel):
    quote_id: UUID


class SimulationRequest(DataModel):
    transaction_id: UUID
