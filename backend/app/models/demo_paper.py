"""Non-executable, explicitly synthetic paper lifecycle records."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.models.data import DataModel, utc
from app.models.demo_execution import DemoQuote, DemoSimulation, PreparedDemoRequest
from app.models.demo_sandbox import DemoMarker, DemoProductionGates, ScenarioId
from app.models.opportunity import Amount, Money, OpportunityDecision, Price
from app.models.risk import RiskDecision


class PaperRecord(DemoMarker):
    dataset_type: Literal["DEMO_FIXTURE"] = "DEMO_FIXTURE"
    synthetic: Literal[True] = True
    production_eligible: Literal[False] = False
    source: Literal["DEMO"] = "DEMO"
    execution_mode: Literal["PAPER"] = "PAPER"
    signed: Literal[False] = False
    transaction_broadcast: Literal[False] = False
    funds_moved: Literal[False] = False


class PaperOrder(PaperRecord):
    order_id: UUID
    transaction_id: UUID
    quote_id: UUID
    simulation_id: UUID
    opportunity_id: UUID
    risk_id: UUID
    status: Literal["PAPER_FILLED"] = "PAPER_FILLED"
    created_at: datetime

    _utc = field_validator("created_at")(utc)


class PaperFill(PaperRecord):
    fill_id: UUID
    order_id: UUID
    filled_at: datetime
    quantity: Price
    price_usd: Price
    notional_usd: Price
    fees_usd: Amount
    gas_usd: Amount
    reserve_usd: Amount
    fill_type: Literal["SYNTHETIC_QUOTE_FILL"] = "SYNTHETIC_QUOTE_FILL"

    _utc = field_validator("filled_at")(utc)


class PaperPosition(PaperRecord):
    position_id: UUID
    fill_id: UUID
    ticker: str
    issuer: str
    token: str = Field(pattern=r"^demo:")
    quantity: Price
    entry_price_usd: Price
    entry_notional_usd: Price
    entry_costs_usd: Amount
    reserved_usd: Amount
    entered_at: datetime
    state: Literal["OPEN", "EXITED"]
    exited_at: datetime | None = None

    _utc = field_validator("entered_at")(utc)


class PaperEvent(PaperRecord):
    event_id: UUID
    position_id: UUID
    kind: Literal["ENTRY", "MONITOR", "EXIT"]
    occurred_at: datetime
    reference_id: UUID

    _utc = field_validator("occurred_at")(utc)


class ExitFixture(DemoMarker):
    version: Literal["demo-paper-exit-1"]
    scenario_id: ScenarioId
    seconds_after_entry: int = Field(strict=True, ge=1, le=86400)
    token_mark_price_usd: Price
    slippage_bps: Amount = Field(lt=10000)
    fees_usd: Amount
    gas_usd: Amount
    description: str


class PaperObservation(PaperRecord):
    observation_id: UUID
    position_id: UUID
    observed_at: datetime
    token_mark_price_usd: Price
    sell_price_usd: Price
    fees_usd: Amount
    gas_usd: Amount
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    description: str
    clock_mode: Literal["EXPLICIT_SYNTHETIC_TIME_ADVANCE"] = "EXPLICIT_SYNTHETIC_TIME_ADVANCE"

    _utc = field_validator("observed_at")(utc)


class PaperExit(PaperRecord):
    exit_id: UUID
    position_id: UUID
    observation_id: UUID
    exited_at: datetime
    quantity: Price
    price_usd: Price
    notional_usd: Price
    fees_usd: Amount
    gas_usd: Amount
    released_reserve_usd: Amount

    _utc = field_validator("exited_at")(utc)


class PaperPnL(PaperRecord):
    position_id: UUID
    gross_pnl_usd: Money
    costs_usd: Amount
    net_pnl_usd: Money
    return_pct: Money
    entry_cost_basis_usd: Price
    convention: Literal["SLIPPAGE_IN_PRICES_RESERVE_RELEASED_NOT_EXPENSE"] = (
        "SLIPPAGE_IN_PRICES_RESERVE_RELEASED_NOT_EXPENSE"
    )


class PaperLifecycle(PaperRecord):
    runtime_mode: Literal["DEMO"] = "DEMO"
    production_gates: DemoProductionGates = DemoProductionGates()
    scenario_id: ScenarioId
    order: PaperOrder
    fill: PaperFill
    position: PaperPosition
    events: list[PaperEvent]
    opportunity: OpportunityDecision
    risk: RiskDecision
    quote: DemoQuote
    preparation: PreparedDemoRequest
    simulation: DemoSimulation
    fill_revalidation: DemoSimulation
    trust_reason_codes: list[str]
    exit_fixture: ExitFixture
    observation: PaperObservation | None = None
    exit: PaperExit | None = None
    pnl: PaperPnL | None = None


class PaperScorecard(PaperRecord):
    runtime_mode: Literal["DEMO"] = "DEMO"
    production_gates: DemoProductionGates = DemoProductionGates()
    scenario_id: ScenarioId
    position_id: UUID
    trust_assessment_id: UUID
    trust_classification: str
    opportunity_status: Literal["ACTIONABLE"] = "ACTIONABLE"
    risk_status: Literal["PASS"] = "PASS"
    execution_status: Literal["PAPER_FILLED"] = "PAPER_FILLED"
    simulation_status: Literal["SIMULATION_PASS"] = "SIMULATION_PASS"
    entry: PaperFill
    exit: PaperExit
    pnl: PaperPnL
    event_ids: list[UUID]
    reason_codes: list[str]
    evidence_quality: str
    confidence: str
    quote_id: UUID
    transaction_id: UUID
    simulation_id: UUID
    risk_id: UUID


class PaperFillRequest(DataModel):
    transaction_id: UUID
    simulation_id: UUID


class PaperExitRequest(DataModel):
    observation_id: UUID


class PaperMonitorRequest(DataModel):
    pass
