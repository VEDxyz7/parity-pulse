"""Explicitly non-production, bounded presentation contracts. No execution capability."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, field_validator

from app.models.data import DataModel, Nonnegative, Positive, utc
from app.models.demo_execution import DemoPreparationResult, DemoQuoteResult, DemoSimulationResult
from app.models.opportunity import OpportunityDecision
from app.models.risk import RiskDecision
from app.models.routing import RouteDecision
from app.models.trust import TrustAssessment

Preset = Literal["normal", "above", "below", "low-liquidity", "news"]
BoundedPrice = Annotated[Positive, Field(le=1000000)]


class ScenarioRequest(DataModel):
    ticker: Literal["NVDA", "AAPL"] = "NVDA"
    representation: Literal["atlas", "meridian"] = "atlas"
    preset: Preset = "news"
    token_price: BoundedPrice | None = None
    equity_price: BoundedPrice | None = None
    liquidity: Annotated[Nonnegative, Field(le=100000000)] | None = None
    fees: Annotated[Nonnegative, Field(le=1000)] = Decimal("0.10")
    slippage_bps: Annotated[Nonnegative, Field(le=10000)] = Decimal("20")
    budget: Annotated[Positive, Field(le=100000)] = Decimal("60")
    risk_budget: Annotated[Positive, Field(le=1000)] = Decimal("2")
    window: Literal["regular", "reopening"] = "regular"

    @field_validator(
        "token_price", "equity_price", "liquidity", "fees", "slippage_bps", "budget", "risk_budget"
    )
    @classmethod
    def bounded_precision(cls, value):
        if value is not None and (
            len(value.as_tuple().digits) > 24 or value.as_tuple().exponent < -8
        ):
            raise ValueError("Scenario inputs support at most eight decimal places")
        return value


class ScanRequest(DataModel):
    budget: Annotated[Positive, Field(le=100000)] = Decimal("60")
    risk_budget: Annotated[Positive, Field(le=1000)] = Decimal("2")
    universe: list[Literal["NVDA", "AAPL"]] = Field(
        default=["NVDA", "AAPL"], min_length=1, max_length=2
    )
    window: Literal["regular", "reopening"] = "regular"

    _precision = field_validator("budget", "risk_budget")(
        ScenarioRequest.bounded_precision.__func__
    )


class PresentationProvenance(DataModel):
    source_kind: Literal["PRESENTATION_SCENARIO"] = "PRESENTATION_SCENARIO"
    version: Literal["presentation-1"] = "presentation-1"
    production_eligible: Literal[False] = False
    execution_ready: Literal[False] = False
    transaction_broadcast: Literal[False] = False
    as_of: datetime
    source: str = "Isolated scenario fixtures evaluated by deterministic application engines"
    assumptions: list[str]
    _utc = field_validator("as_of")(utc)


class PricePoint(DataModel):
    at: datetime
    token: Positive
    equity: Positive
    effective: Positive
    _utc = field_validator("at")(utc)


class PresentationAnalysis(DataModel):
    id: str
    inputs: ScenarioRequest
    provenance: PresentationProvenance
    company: str
    issuer_name: str
    token_symbol: str
    contract: str
    share_ratio: Positive
    token_price: Positive
    equity_price: Positive
    effective_cost: Positive
    deviation: Decimal
    liquidity: Nonnegative
    volume: Nonnegative
    token_quantity: Nonnegative
    share_exposure: Nonnegative
    estimated_costs: Nonnegative
    history: list[PricePoint]
    trust: TrustAssessment
    opportunity: OpportunityDecision
    risk: RiskDecision
    route: RouteDecision
    quote: DemoQuoteResult | None = None
    preparation: DemoPreparationResult | None = None
    simulation: DemoSimulationResult | None = None
    explanation: str
    rank: int | None = None


class Holding(DataModel):
    ticker: str
    issuer: str
    sector: str
    quantity: Positive
    share_exposure: Positive
    cost_basis: Positive
    value: Positive
    pnl: Decimal
    weight: Nonnegative
    target_weight: Nonnegative
    drift: Decimal
    suggested_notional: Decimal


class EvaluationRecord(DataModel):
    id: str
    ticker: str
    at: datetime
    evaluation: Literal["Baseline reversion"] = "Baseline reversion"
    prediction: Literal["REVERSED", "PERSISTED"]
    outcome: str
    correct: bool
    initial_deviation: Decimal
    final_deviation: Decimal
    evidence: str
    _utc = field_validator("at")(utc)


class PresentationWorkspace(DataModel):
    provenance: PresentationProvenance
    assets: list[PresentationAnalysis]
    holdings: list[Holding]
    portfolio_value: Positive
    portfolio_cost: Positive
    portfolio_pnl: Decimal
    concentration: Nonnegative
    stress_loss: Nonnegative
    evaluations: list[EvaluationRecord]
    evaluation_count: int
    correct_count: int
    accuracy: Decimal | None


class PresentationScan(DataModel):
    provenance: PresentationProvenance
    request: ScanRequest
    candidates: list[PresentationAnalysis]
    ranking: str
    explanation: str
