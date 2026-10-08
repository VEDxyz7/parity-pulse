"""Typed host-only Agentic Wallet reads. Nothing here grants execution authority."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.models.data import Nonnegative, Positive
from app.models.execution import Address, Digest, ExecutionModel, Hash, Identifier, Mode

Capability = Literal["VERIFIED_READ", "FIXTURE_VERIFIED", "UNAVAILABLE", "NOT_VERIFIED", "INVALID"]


class WalletBalance(ExecutionModel):
    chain_id: Literal["56"]
    contract: Address
    symbol: Identifier
    quantity: Nonnegative  # Human token units, never assumed USD or base units.
    indicative_unit_price_usd: Nonnegative
    indicative_value_usd: Nonnegative
    price_observed_at: None = None  # CLI does not document an observation timestamp.


class WalletSettings(ExecutionModel):
    daily_limit_usd: Nonnegative
    quota_used_usd: Nonnegative
    quota_left_usd: Nonnegative
    quota_date: date
    quota_timezone: None = None  # Do not invent a quota reset timezone.
    trade_all_tokens: bool = Field(strict=True)
    allowed_tokens: None = None  # Restricted list is not exposed by the reviewed command.
    abnormal_handling: Literal["AutoReject", "NeedConfirmation"]
    session_expires_at: datetime
    inactive_signout_at: datetime
    developer_enabled: bool = Field(strict=True)
    developer_expires_at: datetime | None
    developer_daily_limit_usd: Nonnegative
    developer_quota_used_usd: Nonnegative
    developer_quota_date: date
    developer_balance_exceeded: bool = Field(strict=True)

    @model_validator(mode="after")
    def consistent(self):
        from decimal import localcontext

        with localcontext() as ctx:
            ctx.prec = 256
            if self.quota_used_usd + self.quota_left_usd > self.daily_limit_usd:
                raise ValueError("Inconsistent wallet quota")
        if self.developer_enabled and self.developer_expires_at is None:
            raise ValueError("Enabled Developer Mode needs expiry")
        return self


class WalletOrder(ExecutionModel):
    order_id: Identifier
    chain_id: Literal["56"]
    sell_token: Address
    buy_token: Address
    sell_quantity: Positive
    status: Literal["PENDING", "FINISHED", "FAILED", "UNKNOWN"]
    tx_hash: Hash | None
    created_at: datetime
    updated_at: datetime
    received_quantity: None = None  # Not in documented list response; never invented.
    execution_equivalence_verified: Literal[False] = False

    @model_validator(mode="after")
    def chronology(self):
        if self.updated_at < self.created_at:
            raise ValueError("Order chronology invalid")
        return self


class WalletTransaction(ExecutionModel):
    chain_id: Literal["56"]
    tx_hash: Hash
    transaction_type: Identifier
    status: Literal["pending", "confirmed", "failed", "UNKNOWN"]
    occurred_at: datetime
    # History is corroboration, not proof of the exact Phase 8 settlement.
    execution_equivalence_verified: Literal[False] = False


class WalletIndicativeQuote(ExecutionModel):
    sell_symbol: Identifier
    sell_quantity: Positive
    buy_symbol: Identifier
    buy_quantity: Positive
    slippage_fraction: Nonnegative = Field(le=1)
    phase8_route_binding_verified: Literal[False] = False


class WalletSnapshot(ExecutionModel):
    data_mode: Mode
    source: Literal["BINANCE_BAW", "TEST_FIXTURE", "UNAVAILABLE"]
    capability_status: Capability
    requested_at: datetime
    received_at: datetime
    timestamp_basis: Literal["HOST_READ_WINDOW_NOT_MARKET_OBSERVATION"] = (
        "HOST_READ_WINDOW_NOT_MARKET_OBSERVATION"
    )
    connection: Literal["CONNECTED", "UNCONNECTED", "CREATING", "UNKNOWN"]
    supported_chains: tuple[Identifier, ...] = ()
    bsc_address: Address | None = Field(default=None, repr=False)
    balances: tuple[WalletBalance, ...] = Field(default=(), repr=False, max_length=1000)
    settings: WalletSettings | None = Field(default=None, repr=False)
    transaction_lock: Literal["UNLOCKED", "LOCKED", "UNKNOWN"] = "UNKNOWN"
    pending_state: Literal["CLEAR", "PENDING", "UNKNOWN"] = "UNKNOWN"
    limitations: tuple[Identifier, ...] = ()
    errors: tuple[Identifier, ...] = ()
    live_authorized: Literal[False] = False

    @model_validator(mode="after")
    def consistent(self):
        if self.requested_at > self.received_at:
            raise ValueError("Invalid read timestamps")
        if self.source == "TEST_FIXTURE" and self.data_mode != "DEMO":
            raise ValueError("Fixture wallet cannot become real data")
        if self.capability_status == "VERIFIED_READ" and (
            self.source != "BINANCE_BAW" or self.data_mode != "LIVE_READ_ONLY"
        ):
            raise ValueError("Actual reads required")
        if self.capability_status == "FIXTURE_VERIFIED" and self.source != "TEST_FIXTURE":
            raise ValueError("Explicit fixture required")
        if self.capability_status in {"VERIFIED_READ", "FIXTURE_VERIFIED"} and (
            self.connection != "CONNECTED" or self.settings is None
        ):
            raise ValueError("Verified snapshot requires connection and settings")
        keys = [(b.chain_id, b.contract) for b in self.balances]
        if len(keys) != len(set(keys)) or len(set(self.supported_chains)) != len(
            self.supported_chains
        ):
            raise ValueError("Conflicting wallet identities")
        return self


class WalletReadResult(ExecutionModel):
    capability: Identifier
    capability_status: Capability
    data_mode: Mode
    source: Literal["BINANCE_BAW", "TEST_FIXTURE", "UNAVAILABLE"]
    requested_at: datetime
    received_at: datetime
    orders: tuple[WalletOrder, ...] = Field(default=(), max_length=100)
    transactions: tuple[WalletTransaction, ...] = Field(default=(), max_length=100)
    quote: WalletIndicativeQuote | None = None
    more_available: bool = Field(default=False, strict=True)
    limitations: tuple[Identifier, ...] = ()
    errors: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def consistent(self):
        if self.requested_at > self.received_at:
            raise ValueError("Invalid read timestamps")
        if self.source == "TEST_FIXTURE" and self.data_mode != "DEMO":
            raise ValueError("Fixture cannot become real data")
        if self.capability_status == "VERIFIED_READ" and (
            self.source != "BINANCE_BAW" or self.data_mode != "LIVE_READ_ONLY"
        ):
            raise ValueError("Actual read required")
        if self.capability_status == "FIXTURE_VERIFIED" and self.source != "TEST_FIXTURE":
            raise ValueError("Fixture required")
        return self


class WalletCheck(ExecutionModel):
    code: Identifier
    passed: bool = Field(strict=True)


class WalletPreflight(ExecutionModel):
    status: Literal["PASS", "BLOCKED"]
    data_mode: Mode
    evaluated_at: datetime
    snapshot_digest: Digest
    route_fingerprint: Digest | None
    checks: tuple[WalletCheck, ...]
    reasons: tuple[Identifier, ...]
    live_authorized: Literal[False] = False


class WalletDryRunResult(ExecutionModel):
    execution_id: UUID
    decision_id: Identifier
    request_id: UUID
    route_fingerprint: Digest | None
    evaluated_at: datetime
    data_mode: Mode
    wallet: WalletPreflight
    reasons: tuple[Identifier, ...]
    execution_ready: Literal[False] = False
    signed: Literal[False] = False
    broadcast: Literal[False] = False
    funds_moved: Literal[False] = False


class WalletReconciliation(ExecutionModel):
    execution_id: UUID
    request_id: UUID
    decision_id: Identifier
    evaluated_at: datetime
    data_mode: Mode
    wallet_capability: Capability
    wallet_order_state: Literal["PENDING", "FINISHED", "FAILED", "UNKNOWN"]
    execution_state: Identifier
    reasons: tuple[Identifier, ...]
    new_order_created: Literal[False] = False
