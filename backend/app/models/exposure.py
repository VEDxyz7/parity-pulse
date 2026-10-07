"""Non-executable exposure estimates. Financial JSON values are decimal strings."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictStr

from app.models.data import DataMode, DataModel, Nonnegative, Positive, Quality
from app.models.routing import RouteDecision


class AskRequest(DataModel):
    text: StrictStr = Field(min_length=1, max_length=240)


class ParsedIntent(DataModel):
    status: Literal["VALID", "NEEDS_CLARIFICATION"]
    intent: Literal["DIRECT_EXPOSURE"] = "DIRECT_EXPOSURE"
    stock_query: str | None = None
    budget_usd: Positive | None = None
    approval_required: Literal[True] = True
    reason: str


class RepresentationEstimate(DataModel):
    issuer: str
    chain_id: str
    contract: str
    token_symbol: str
    ticker: str
    company_name: str
    token_to_share_ratio: Positive
    token_price_usd: Positive | None
    effective_cost_per_share_usd: Positive | None = None
    decimals: int | None
    market_state: str
    price_source: str
    price_timestamp: datetime | None
    price_quality: Quality
    ratio_source: str
    ratio_observed_at: datetime
    ratio_source_timestamp: datetime | None
    data_mode: DataMode
    estimate_eligible: bool
    exclusion_reasons: list[str]
    estimated_token_quantity: Nonnegative | None = None
    token_base_units: str | None = None
    estimated_real_share_exposure: Nonnegative | None = None
    estimated_token_cost_usd: Nonnegative | None = None
    unallocated_budget_usd: Nonnegative | None = None
    # Neither zero fees nor liquidity/trust is inferred from token prices.
    fees_usd: None = None
    liquidity_usd: None = None
    trust_status: Literal["NOT_IMPLEMENTED"] = "NOT_IMPLEMENTED"


class IndependentReference(DataModel):
    status: Literal["DEMO", "AVAILABLE", "STALE", "UNAVAILABLE", "UNVERIFIED"]
    price_usd_per_share: Positive | None = None
    source: str | None = None
    source_timestamp: datetime | None = None
    reason: str


class ExposureProposal(DataModel):
    route_decision: RouteDecision | None = None
    schema_version: Literal["ask-1"] = "ask-1"
    policy_version: Literal["indicative-exposure-1"] = "indicative-exposure-1"
    proposal_id: UUID
    created_at: datetime
    valid_until: datetime
    run_id: str
    request_id: str
    correlation_id: str
    data_mode: DataMode
    status: Literal["DRY_RUN", "NO_PROPOSAL", "EXPIRED"]
    intent: ParsedIntent
    ticker: str | None = None
    company_name: str | None = None
    requested_budget_usd: Positive | None = None
    representations: list[RepresentationEstimate] = Field(default_factory=list)
    selected: RepresentationEstimate | None = None
    independent_equity: IndependentReference
    route_type: Literal["INDICATIVE_MARKET_ESTIMATE", "NONE"]
    route_selection_reason: str
    quote_status: Literal["INDICATIVE_ONLY", "UNAVAILABLE"]
    provider_quote_id: None = None
    simulation_status: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    execution_ready: Literal[False] = False
    execution_mode: Literal["DRY_RUN"] = "DRY_RUN"
    approval_mode: Literal["PROPOSE_ONLY"] = "PROPOSE_ONLY"
    require_simulation: Literal[True] = True
    live_trading_enabled: Literal[False] = False
    transaction_broadcast: Literal[False] = False
    broadcast_statement: Literal["No real transaction was broadcast."] = (
        "No real transaction was broadcast."
    )
    execution_blockers: list[str]
    limitations: dict[str, str] = Field(default_factory=dict)
    fee_status: Literal["UNKNOWN"] = "UNKNOWN"
    budget_semantics: Literal["USD_NOTIONAL_BEFORE_UNAVAILABLE_FEES"] = (
        "USD_NOTIONAL_BEFORE_UNAVAILABLE_FEES"
    )
