"""Durable, single-account lifecycle contracts. No contract authorizes execution."""

from datetime import datetime
from decimal import Decimal, localcontext
from typing import Literal
from uuid import UUID

from pydantic import Field, computed_field, model_validator

from app.models.data import Nonnegative, Positive
from app.models.execution import Address, ExecutionAttempt, ExecutionModel, Identifier, Mode, Units

PositionState = Literal[
    "PROPOSED",
    "OPENING",
    "OPEN",
    "EXIT_PENDING",
    "EXITING",
    "CLOSED",
    "FAILED",
    "UNKNOWN",
    "RECONCILIATION_REQUIRED",
]

TRANSITIONS = {
    "PROPOSED": {"OPENING", "OPEN", "FAILED", "UNKNOWN", "RECONCILIATION_REQUIRED"},
    "OPENING": {"OPEN", "FAILED", "UNKNOWN", "RECONCILIATION_REQUIRED"},
    "OPEN": {"EXIT_PENDING", "UNKNOWN", "RECONCILIATION_REQUIRED"},
    "EXIT_PENDING": {"EXITING", "OPEN", "CLOSED", "UNKNOWN", "RECONCILIATION_REQUIRED"},
    "EXITING": {"OPEN", "CLOSED", "UNKNOWN", "RECONCILIATION_REQUIRED"},
    "UNKNOWN": {
        "OPENING",
        "OPEN",
        "EXIT_PENDING",
        "EXITING",
        "CLOSED",
        "FAILED",
        "RECONCILIATION_REQUIRED",
    },
    "CLOSED": set(),
    "FAILED": set(),
    "RECONCILIATION_REQUIRED": set(),
}


def quantity(amount, decimals):
    with localcontext() as ctx:
        ctx.prec = 160
        return Decimal(amount) / Decimal(10) ** decimals


class PositionInstrument(ExecutionModel):
    ticker: Identifier
    company: str = Field(strict=True, min_length=1, max_length=128)
    representation: Identifier
    token: Identifier
    contract: Address
    issuer: Identifier
    platform: Identifier
    chain_id: Literal["56"] = "56"
    decimals: int = Field(strict=True, ge=0, le=36)
    shares_per_token: Positive
    ratio_observed_at: datetime
    ratio_available_at: datetime
    source: Literal["BINANCE_RWA", "TEST_FIXTURE"]
    data_mode: Mode

    @model_validator(mode="after")
    def provenance(self):
        if self.ratio_available_at < self.ratio_observed_at:
            raise ValueError("Ratio unavailable as-of observation")
        if (self.source == "TEST_FIXTURE") != (self.data_mode == "DEMO"):
            raise ValueError("Ratio fixture mode mismatch")
        return self


class PositionJob(ExecutionModel):
    job_id: UUID
    status: Literal["WAITING", "RUNNING", "BLOCKED", "FINISHED"] = "WAITING"
    next_check_at: datetime
    attempts: int = Field(default=0, strict=True, ge=0, le=3)
    lease_id: UUID | None = None
    lease_until: datetime | None = None

    @model_validator(mode="after")
    def lease(self):
        if (self.status == "RUNNING") != (
            self.lease_id is not None and self.lease_until is not None
        ):
            raise ValueError("Running jobs require a complete bounded lease")
        if self.status != "RUNNING" and (self.lease_id is not None or self.lease_until is not None):
            raise ValueError("Inactive job cannot retain a lease")
        return self


class ExitIntent(ExecutionModel):
    ordinal: int = Field(strict=True, ge=1, le=100)
    decision_id: Identifier
    quantity_base_units: Units
    created_at: datetime
    execution: ExecutionAttempt | None = None


class SettlementValuation(ExecutionModel):
    """Host-verified as-of USD reference and actual costs, never quote estimates.

    Optional: current Phase 8/9 endpoints do not expose all actual USD cost inputs.
    The public API cannot provide or create this evidence.
    """

    execution_id: UUID
    cash_contract: Address
    cash_unit_price_usd: Positive
    price_observed_at: datetime
    price_available_at: datetime
    source: Identifier
    data_mode: Mode
    actual_fees_usd: Nonnegative | None = None
    actual_gas_usd: Nonnegative | None = None
    cost_source: Identifier | None = None

    @model_validator(mode="after")
    def valid(self):
        if (self.source == "TEST_FIXTURE") != (self.data_mode == "DEMO"):
            raise ValueError("Valuation fixture provenance cannot cross modes")
        if self.price_available_at < self.price_observed_at:
            raise ValueError("Invalid as-of price availability")
        if (self.actual_fees_usd is not None or self.actual_gas_usd is not None) and (
            self.cost_source is None
            or (self.cost_source == "TEST_FIXTURE") != (self.data_mode == "DEMO")
        ):
            raise ValueError("Actual costs require mode-bound external receipt provenance")
        return self


def cash_notional(attempt):
    """Actual settled cash units, converted only by matching as-of funding evidence."""
    funding = attempt.funding.state if attempt.funding else None
    q = attempt.quote
    if not funding or not q or attempt.state != "EXECUTION_CONFIRMED":
        return None
    if (
        not funding.identity_verified
        or funding.wallet != q.request.userWalletAddress
        or funding.asset.data_mode != attempt.data_mode
        or funding.asset.contract != q.request.fromTokenAddress
    ):
        return None
    if not 0 <= (attempt.settled_at - funding.price_observed_at).total_seconds() <= 120:
        return None
    with localcontext() as ctx:
        ctx.prec = 160
        return quantity(q.request.amount, funding.asset.decimals) * funding.unit_price_usd


class Position(ExecutionModel):
    position_id: UUID
    account_scope: Literal["LOCAL_SINGLE_ACCOUNT"] = "LOCAL_SINGLE_ACCOUNT"
    data_mode: Mode
    application_execution_mode: Literal["DRY_RUN"] = "DRY_RUN"
    instrument: PositionInstrument
    entry_execution: ExecutionAttempt
    state: PositionState
    version: int = Field(strict=True, ge=0)
    requested_quantity_base_units: Units
    filled_quantity_base_units: Units = "0"
    remaining_quantity_base_units: Units = "0"
    applied_exit_executions: tuple[ExecutionAttempt, ...] = Field(default=(), max_length=100)
    valuations: tuple[SettlementValuation, ...] = Field(default=(), max_length=101)
    exit_intent: ExitIntent | None = None
    entry_at: datetime | None = None
    market_open_at: datetime | None = None
    exit_due_at: datetime | None = None
    closed_at: datetime | None = None
    postopen_exit_minutes: int = Field(default=10, strict=True, ge=1, le=120)
    exit_rule: Literal["FIRST_REGULAR_OPEN_PLUS_MINUTES", "PORTFOLIO_DRIFT"] = (
        "FIRST_REGULAR_OPEN_PLUS_MINUTES"
    )
    calendar_version: Identifier | None = None
    job: PositionJob
    reasons: tuple[Identifier, ...] = Field(default=(), max_length=32)
    created_at: datetime
    updated_at: datetime
    broadcast: Literal[False] = False
    signed: Literal[False] = False
    funds_moved: Literal[False] = False

    @model_validator(mode="after")
    def evidence(self):
        a, i = self.entry_execution, self.instrument
        if a.data_mode != self.data_mode or i.data_mode != self.data_mode:
            raise ValueError("Position mode is immutable and isolated")
        q = a.quote
        if q is None or a.route is None:
            raise ValueError("An identified prepared entry route is required")
        if (
            q.request.toTokenAddress,
            q.route.toToken.tokenSymbol,
            int(q.route.toToken.decimal),
        ) != (i.contract, i.token, i.decimals) or i.ratio_available_at > q.requested_at:
            raise ValueError("Representation or as-of ratio does not match entry")
        if self.requested_quantity_base_units != q.route.toTokenAmount:
            raise ValueError("Requested output must retain the original quote estimate")
        confirmed = a.state == "EXECUTION_CONFIRMED"
        filled = int(a.filled_quantity_base_units) if confirmed else 0
        if int(self.filled_quantity_base_units) != filled:
            raise ValueError("Filled quantity requires Phase 8/9 confirmed settlement evidence")
        sold = 0
        seen = set()
        for exit_a in self.applied_exit_executions:
            self.validate_exit(exit_a)
            if exit_a.state != "EXECUTION_CONFIRMED" or exit_a.execution_id in seen:
                raise ValueError("Exit application requires unique confirmed evidence")
            seen.add(exit_a.execution_id)
            sold += int(exit_a.quote.request.amount)
        if int(self.remaining_quantity_base_units) != filled - sold or sold > filled:
            raise ValueError("Remaining exposure must equal confirmed entry minus confirmed sales")
        if confirmed != (self.entry_at is not None) or (
            confirmed and self.entry_at != a.settled_at
        ):
            raise ValueError("Entry timestamp must be the proven settlement timestamp")
        if self.state in {"OPEN", "EXIT_PENDING", "EXITING", "CLOSED"} and not confirmed:
            raise ValueError("Preparation or unknown settlement cannot establish an open position")
        if self.state in {"OPEN", "EXIT_PENDING", "EXITING"} and filled - sold <= 0:
            raise ValueError("Open state requires positive confirmed remaining exposure")
        if self.exit_rule == "PORTFOLIO_DRIFT" and any(
            v is not None for v in (self.market_open_at, self.exit_due_at, self.calendar_version)
        ):
            raise ValueError("Portfolio holdings cannot acquire a timer-based exit schedule")
        if (
            self.exit_rule == "FIRST_REGULAR_OPEN_PLUS_MINUTES"
            and self.state in {"OPEN", "EXIT_PENDING", "EXITING", "CLOSED"}
            and (
                self.market_open_at is None
                or self.exit_due_at is None
                or self.calendar_version is None
                or self.market_open_at < self.entry_at
                or (self.exit_due_at - self.market_open_at).total_seconds()
                != self.postopen_exit_minutes * 60
            )
        ):
            raise ValueError(
                "Established positions require their immutable deterministic exit schedule"
            )
        if self.state == "CLOSED" and (
            filled <= 0
            or filled != sold
            or not self.applied_exit_executions
            or self.closed_at != self.applied_exit_executions[-1].settled_at
        ):
            raise ValueError("Closed state requires complete confirmed disposition")
        if self.state != "CLOSED" and self.closed_at is not None:
            raise ValueError("Unclosed exposure cannot have a closing timestamp")
        if self.exit_intent:
            if int(self.exit_intent.quantity_base_units) <= 0:
                raise ValueError("Exit intent requires a positive known quantity")
            if self.exit_intent.execution:
                self.validate_exit(self.exit_intent.execution)
                if (
                    self.exit_intent.execution.decision_id != self.exit_intent.decision_id
                    or self.exit_intent.execution.quote.request.amount
                    != self.exit_intent.quantity_base_units
                ):
                    raise ValueError("Exit intent/execution binding mismatch")
        if self.state == "EXITING" and (
            self.exit_intent is None
            or self.exit_intent.execution is None
            or not self.exit_intent.execution.external_tracking_only
        ):
            raise ValueError("Exiting requires an identified external attempt")
        if self.created_at > self.updated_at:
            raise ValueError("Invalid lifecycle timestamps")
        if (
            self.job.status == "RUNNING"
            and not 0 < (self.job.lease_until - self.updated_at).total_seconds() <= 30
        ):
            raise ValueError("Monitor lease must be bounded to 30 seconds")
        executions = {e.execution_id: e for e in (a, *self.applied_exit_executions)}
        seen_values = set()
        for v in self.valuations:
            e = executions.get(v.execution_id)
            cash_contract = q.request.fromTokenAddress
            if (
                e is None
                or e.state != "EXECUTION_CONFIRMED"
                or v.execution_id in seen_values
                or v.data_mode != self.data_mode
                or v.cash_contract != cash_contract
                or not 0 <= (e.settled_at - v.price_observed_at).total_seconds() <= 120
                or v.price_available_at > e.settled_at
            ):
                raise ValueError(
                    "USD valuation must be available as-of the exact confirmed settlement"
                )
            seen_values.add(v.execution_id)
        return self

    def validate_exit(self, attempt):
        q, entry_q = attempt.quote, self.entry_execution.quote
        if (
            q is None
            or attempt.route is None
            or attempt.data_mode != self.data_mode
            or q.request.fromTokenAddress != self.instrument.contract
            or q.request.toTokenAddress != entry_q.request.fromTokenAddress
            or q.request.userWalletAddress != entry_q.request.userWalletAddress
            or int(q.route.fromToken.decimal) != self.instrument.decimals
            or int(q.route.toToken.decimal) != int(entry_q.route.fromToken.decimal)
            or (
                self.exit_rule == "FIRST_REGULAR_OPEN_PLUS_MINUTES"
                and (self.exit_due_at is None or q.requested_at < self.exit_due_at)
            )
            or (
                self.exit_rule == "PORTFOLIO_DRIFT"
                and (self.entry_at is None or q.requested_at < self.entry_at)
            )
        ):
            raise ValueError("Exit must match the held asset, cash asset, wallet, mode and window")

    @computed_field
    @property
    def synthetic(self) -> bool:
        return self.data_mode == "DEMO"

    @computed_field
    @property
    def execution_mode(self) -> str:
        return self.entry_execution.quote.route.executionMode

    @computed_field
    @property
    def requested_quantity(self) -> Decimal:
        return quantity(self.requested_quantity_base_units, self.instrument.decimals)

    @computed_field
    @property
    def filled_quantity(self) -> Decimal:
        return quantity(self.filled_quantity_base_units, self.instrument.decimals)

    @computed_field
    @property
    def remaining_quantity(self) -> Decimal:
        return quantity(self.remaining_quantity_base_units, self.instrument.decimals)

    @computed_field
    @property
    def unfilled_quoted_quantity_base_units(self) -> str:
        return str(
            max(0, int(self.requested_quantity_base_units) - int(self.filled_quantity_base_units))
        )

    @computed_field
    @property
    def normalized_share_exposure(self) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = 160
            return self.remaining_quantity * self.instrument.shares_per_token

    @computed_field
    @property
    def entry_share_exposure(self) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = 160
            return self.filled_quantity * self.instrument.shares_per_token

    @computed_field
    @property
    def close_state(self) -> str:
        if self.state == "CLOSED":
            return "CONFIRMED"
        if self.state in {"UNKNOWN", "RECONCILIATION_REQUIRED"}:
            return "UNRESOLVED"
        if self.state == "EXITING":
            return "PENDING"
        if self.state == "EXIT_PENDING":
            return "PREPARATION" if self.exit_intent else "DUE"
        return "NOT_STARTED"

    @computed_field
    @property
    def entry_notional_usd(self) -> Decimal | None:
        value = next(
            (v for v in self.valuations if v.execution_id == self.entry_execution.execution_id),
            None,
        )
        if value is not None:
            with localcontext() as ctx:
                ctx.prec = 160
                return (
                    quantity(
                        self.entry_execution.quote.request.amount,
                        int(self.entry_execution.quote.route.fromToken.decimal),
                    )
                    * value.cash_unit_price_usd
                )
        return cash_notional(self.entry_execution)

    @computed_field
    @property
    def average_execution_price_usd(self) -> Decimal | None:
        with localcontext() as ctx:
            ctx.prec = 160
            return (
                self.entry_notional_usd / self.filled_quantity
                if (self.entry_notional_usd is not None and self.filled_quantity > 0)
                else None
            )

    @computed_field
    @property
    def effective_cost_per_share_usd(self) -> Decimal | None:
        with localcontext() as ctx:
            ctx.prec = 160
            return (
                self.average_execution_price_usd / self.instrument.shares_per_token
                if (self.average_execution_price_usd is not None)
                else None
            )

    @computed_field
    @property
    def exit_notional_usd(self) -> Decimal | None:
        if not self.applied_exit_executions:
            return None
        values = {v.execution_id: v for v in self.valuations}
        if any(a.execution_id not in values for a in self.applied_exit_executions):
            return None
        with localcontext() as ctx:
            ctx.prec = 160
            return sum(
                (
                    quantity(a.filled_quantity_base_units, int(a.quote.route.toToken.decimal))
                    * values[a.execution_id].cash_unit_price_usd
                    for a in self.applied_exit_executions
                ),
                Decimal(0),
            )

    @computed_field
    @property
    def fees_usd(self) -> Decimal | None:
        ids = {a.execution_id for a in (self.entry_execution, *self.applied_exit_executions)}
        values = {v.execution_id: v for v in self.valuations}
        if any(i not in values or values[i].actual_fees_usd is None for i in ids):
            return None
        with localcontext() as ctx:
            ctx.prec = 160
            return sum((values[i].actual_fees_usd for i in ids), Decimal(0))

    @computed_field
    @property
    def gas_usd(self) -> Decimal | None:
        ids = {a.execution_id for a in (self.entry_execution, *self.applied_exit_executions)}
        values = {v.execution_id: v for v in self.valuations}
        if any(i not in values or values[i].actual_gas_usd is None for i in ids):
            return None
        with localcontext() as ctx:
            ctx.prec = 160
            return sum((values[i].actual_gas_usd for i in ids), Decimal(0))

    @computed_field
    @property
    def gas_native_base_units(self) -> tuple[str | None, ...]:
        return tuple(
            a.fees_native_base_units for a in (self.entry_execution, *self.applied_exit_executions)
        )

    @computed_field
    @property
    def gross_pnl_usd(self) -> Decimal | None:
        if self.entry_notional_usd is None or self.exit_notional_usd is None:
            return None
        with localcontext() as ctx:
            ctx.prec = 160
            sold = Decimal(
                int(self.filled_quantity_base_units) - int(self.remaining_quantity_base_units)
            )
            return self.exit_notional_usd - self.entry_notional_usd * sold / Decimal(
                self.filled_quantity_base_units
            )

    @computed_field
    @property
    def net_pnl_usd(self) -> Decimal | None:
        if self.gross_pnl_usd is None or self.fees_usd is None or self.gas_usd is None:
            return None
        with localcontext() as ctx:
            ctx.prec = 160
            return self.gross_pnl_usd - self.fees_usd - self.gas_usd

    @computed_field
    @property
    def holding_duration_seconds(self) -> int | None:
        return int((self.closed_at - self.entry_at).total_seconds()) if self.closed_at else None

    def payload(self):
        return self.model_dump_json(exclude_computed_fields=True)
