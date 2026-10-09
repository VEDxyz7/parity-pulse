"""Single-user portfolio mandates and deterministic, non-executable planning contracts."""

from datetime import datetime
from decimal import Decimal, localcontext
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from app.models.data import Nonnegative, Positive, financial
from app.models.execution import (
    Digest,
    ExecutionModel,
    ExecutionRiskDecision,
    ExecutionRiskEvidence,
    FundingState,
    Identifier,
    Mode,
    fingerprint,
    units,
)
from app.models.position import Position
from app.models.routing import RouteDecision, RouteInput


def portfolio_fingerprint(value):
    def canonical(v):
        if isinstance(v, BaseModel):
            return v.model_dump(mode="json", exclude_computed_fields=True)
        if isinstance(v, dict):
            return {k: canonical(item) for k, item in v.items()}
        if isinstance(v, (list, tuple)):
            return [canonical(item) for item in v]
        if isinstance(v, (Decimal, UUID)):
            return str(v)
        if isinstance(v, datetime):
            return v.isoformat().replace("+00:00", "Z")
        return v

    return fingerprint(canonical(value))


Fraction = Annotated[Nonnegative, Field(le=1)]
Signed = Annotated[Decimal, BeforeValidator(financial)]
AssetId = Annotated[str, Field(strict=True, pattern=r"^[A-Z][A-Z0-9.]{0,15}$")]


class Allocation(ExecutionModel):
    asset: AssetId
    kind: Literal["TOKENIZED_STOCK", "CASH", "CRYPTO"]
    weight: Fraction
    drift_band: Fraction = Decimal("0.05")

    @model_validator(mode="after")
    def identity(self):
        if (self.kind == "CASH") != (self.asset == "CASH"):
            raise ValueError("Explicit CASH identity required")
        if self.kind == "CRYPTO" and self.asset not in {"BTC", "ETH"}:
            raise ValueError("Only optional BTC/ETH crypto slots may be modelled")
        if self.kind == "TOKENIZED_STOCK" and self.asset in {"BTC", "ETH"}:
            raise ValueError("Crypto cannot be relabelled as a tokenized stock")
        return self


class PortfolioRules(ExecutionModel):
    targets: tuple[Allocation, ...] = Field(min_length=2, max_length=25)
    funding_symbol: Identifier = "USDT"
    max_rebalance_notional_usd: Positive
    risk_budget_usd: Positive
    max_drift: Fraction = Decimal("1")
    max_stock_exposure_usd: Positive
    crypto_enabled: Literal[False] = False
    approval_mode: Literal["PROPOSE_ONLY"] = "PROPOSE_ONLY"

    @model_validator(mode="after")
    def complete(self):
        assets = [t.asset for t in self.targets]
        with localcontext() as ctx:
            ctx.prec = 256
            total = sum((t.weight for t in self.targets), Decimal(0))
        if len(assets) != len(set(assets)) or assets.count("CASH") != 1 or total != 1:
            raise ValueError("Unique targets including CASH must sum exactly to one")
        if not any(t.kind == "TOKENIZED_STOCK" for t in self.targets):
            raise ValueError("At least one explicit stock target required")
        if any(t.kind == "CRYPTO" and t.weight != 0 for t in self.targets):
            raise ValueError(
                "Optional crypto data/execution path is NOT_VERIFIED; nonzero target denied"
            )
        return self


class PortfolioConfig(PortfolioRules):
    portfolio_id: Literal["LOCAL_SINGLE_PORTFOLIO"] = "LOCAL_SINGLE_PORTFOLIO"
    account_scope: Literal["LOCAL_SINGLE_ACCOUNT"] = "LOCAL_SINGLE_ACCOUNT"
    data_mode: Mode
    version: int = Field(strict=True, ge=1)
    source: Literal["VALIDATED_USER_CONFIGURATION"] = "VALIDATED_USER_CONFIGURATION"
    created_at: datetime
    updated_at: datetime


class ConfigRequest(PortfolioRules):
    expected_version: int = Field(default=0, strict=True, ge=0)


class PlanRequest(ExecutionModel):
    idempotency_key: UUID


class AssetRisk(ExecutionModel):
    asset: AssetId
    evidence: ExecutionRiskEvidence


class PortfolioInputs(ExecutionModel):
    data_mode: Mode
    captured_at: datetime
    position_verified_at: datetime | None
    inventory_complete: bool = Field(strict=True)
    funding: FundingState | None
    token_funding: tuple[FundingState, ...] = Field(default=(), max_length=100)
    routes: tuple[RouteInput, ...] = Field(default=(), max_length=100)
    risks: tuple[AssetRisk, ...] = Field(default=(), max_length=25)
    source: Identifier
    blockers: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def isolation(self):
        mode = "DEMO" if self.data_mode == "DEMO" else "LIVE"
        if (
            any(r.data_mode != mode for r in self.routes)
            or any(r.evidence.data_mode != self.data_mode for r in self.risks)
            or any(
                f.asset.data_mode != self.data_mode
                for f in (*((self.funding,) if self.funding else ()), *self.token_funding)
            )
        ):
            raise ValueError("Mixed portfolio evidence modes")
        if self.data_mode != "DEMO" and self.source.startswith(("TEST", "DEMO", "SYNTHETIC")):
            raise ValueError("Synthetic capture cannot become production evidence")
        keys = [(r.identity.chain_id, r.identity.contract) for r in self.routes]
        if len(set(keys)) != len(keys) or len({r.asset for r in self.risks}) != len(self.risks):
            raise ValueError("Ambiguous duplicate route/risk evidence")
        keys = [(f.asset.chain_id, f.asset.contract) for f in self.token_funding]
        if len(keys) != len(set(keys)):
            raise ValueError("Ambiguous duplicate token funding")
        if self.funding and any(f.wallet != self.funding.wallet for f in self.token_funding):
            raise ValueError("Single wallet funding required")
        return self


class PortfolioSnapshot(ExecutionModel):
    snapshot_id: Digest
    config_version: int = Field(strict=True, ge=1)
    data_mode: Mode
    inputs: PortfolioInputs
    positions: tuple[Position, ...] = Field(max_length=100)
    captured_at: datetime

    @model_validator(mode="after")
    def bound(self):
        if (
            self.inputs.data_mode != self.data_mode
            or self.captured_at != self.inputs.captured_at
            or any(p.data_mode != self.data_mode for p in self.positions)
            or self.snapshot_id
            != portfolio_fingerprint(
                self.model_dump(exclude={"snapshot_id"}, exclude_computed_fields=True)
            )
        ):
            raise ValueError("Captured snapshot identity/mode mismatch")
        return self


class DriftRow(ExecutionModel):
    asset: AssetId
    kind: Literal["TOKENIZED_STOCK", "CASH", "CRYPTO"]
    current_value_usd: Nonnegative | None
    target_value_usd: Nonnegative | None
    current_weight: Fraction | None
    target_weight: Fraction
    drift: Signed | None
    allowed_band: Fraction
    required_delta_usd: Signed | None
    position_ids: tuple[UUID, ...]
    current_share_exposure: Nonnegative | None
    state: Literal["WITHIN_BAND", "OUTSIDE_BAND", "UNAVAILABLE", "DISABLED"]
    reasons: tuple[Identifier, ...]


class RebalanceAction(ExecutionModel):
    action_id: Digest
    asset: AssetId
    side: Literal["BUY", "SELL"]
    priority: int = Field(strict=True, ge=1, le=100)
    notional_usd: Positive
    quantity_base_units: str = Field(strict=True, pattern=r"^[1-9][0-9]{0,77}$")
    decimals: int = Field(strict=True, ge=0, le=36)
    current_representation_base_units: str
    target_representation_base_units: str
    current_share_exposure: Nonnegative
    estimated_share_delta: Signed
    target_share_exposure: Nonnegative
    position_id: UUID | None = None
    inventory_source: Literal["PHASE10_POSITION", "WALLET_BALANCE"] = "PHASE10_POSITION"
    route: RouteDecision
    risk: ExecutionRiskDecision
    risk_inputs: ExecutionRiskEvidence
    eligible_for_preparation: bool = Field(strict=True)
    reasons: tuple[Identifier, ...]
    execution_decision_id: Identifier
    source: Literal["DETERMINISTIC_PORTFOLIO_SERVICE"] = "DETERMINISTIC_PORTFOLIO_SERVICE"
    execution_ready: Literal[False] = False

    @model_validator(mode="after")
    def bound(self):
        units(self.quantity_base_units)
        current = int(units(self.current_representation_base_units))
        target = int(units(self.target_representation_base_units))
        if target != current + int(self.quantity_base_units) * (1 if self.side == "BUY" else -1):
            raise ValueError("Target quantity must retain the exact base-unit delta")
        from app.models.execution import fingerprint as risk_digest

        if self.risk.evidence_digest != risk_digest(self.risk_inputs):
            raise ValueError("Risk decision is not bound to the action inputs")
        if self.inventory_source == "WALLET_BALANCE":
            if self.position_id is not None:
                raise ValueError("Wallet-balance actions are not bound to Phase 10 positions")
        elif (self.side == "SELL") != (self.position_id is not None):
            raise ValueError("Reductions require an identified owned position")
        if (
            self.risk_inputs.decision_id != self.execution_decision_id
            or self.risk_inputs.notional_usd != self.notional_usd
        ):
            raise ValueError("Risk must bind the exact action and notional")
        if self.route.status != "ROUTE_SELECTED" or self.route.underlying != self.asset:
            raise ValueError("Action requires the selected underlying route")
        if self.eligible_for_preparation and self.risk.status != "PASS":
            raise ValueError("Failed risk cannot authorize preparation")
        return self


class PreparationRecord(ExecutionModel):
    action_id: Digest
    execution_id: UUID | None
    status: Literal["DRY_RUN_PREPARED", "BLOCKED", "RECONCILIATION_REQUIRED"]
    observed_at: datetime
    reasons: tuple[Identifier, ...]
    broadcast: Literal[False] = False


class RebalancePlan(ExecutionModel):
    plan_id: Digest
    data_mode: Mode
    version: int = Field(default=0, strict=True, ge=0)
    config: PortfolioConfig
    snapshot: PortfolioSnapshot
    total_value_usd: Positive | None
    rows: tuple[DriftRow, ...]
    actions: tuple[RebalanceAction, ...] = Field(max_length=100)
    route_decisions: tuple[RouteDecision, ...] = Field(default=(), max_length=100)
    # EXECUTED: every leg of a wallet-inventory plan settled on-chain (see live fill journal).
    status: Literal[
        "NO_ACTION", "BLOCKED", "REBALANCE_REQUIRED", "RETIRED", "COMPLETED", "EXECUTED"
    ]
    reasons: tuple[Identifier, ...]
    preparations: tuple[PreparationRecord, ...] = Field(default=(), max_length=100)
    completion_snapshot: PortfolioSnapshot | None = None
    settled_execution_ids: tuple[UUID, ...] = Field(default=(), max_length=100)
    idempotency_key: UUID
    request_id: UUID
    correlation_id: UUID
    created_at: datetime
    updated_at: datetime
    execution_mode: Literal["DRY_RUN", "LIVE"] = "DRY_RUN"
    live_trading_enabled: bool = Field(default=False, strict=True)
    broadcast: bool = Field(default=False, strict=True)
    authority: Literal["DETERMINISTIC_BACKEND"] = "DETERMINISTIC_BACKEND"

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "COMPLETED":
            if (
                self.completion_snapshot is None
                or not self.actions
                or self.completion_snapshot.data_mode != self.data_mode
                or self.completion_snapshot.config_version != self.config.version
                or len(self.settled_execution_ids) != len(self.actions)
                or len(set(self.settled_execution_ids)) != len(self.settled_execution_ids)
            ):
                raise ValueError("Completion requires captured canonical settlement references")
        elif self.completion_snapshot is not None or self.settled_execution_ids:
            raise ValueError("Uncompleted proposals cannot claim settled completion")
        if self.config.data_mode != self.data_mode or self.snapshot.data_mode != self.data_mode:
            raise ValueError("Mixed plan mode")
        body = self.snapshot.model_dump(exclude={"snapshot_id"}, exclude_computed_fields=True)
        if self.snapshot.snapshot_id != portfolio_fingerprint(
            body
        ) or self.plan_id != portfolio_fingerprint(
            dict(config=self.config, snapshot=self.snapshot)
        ):
            raise ValueError("Captured portfolio input identity mismatch")
        if (
            any(p.data_mode != self.data_mode for p in self.snapshot.positions)
            or self.snapshot.inputs.data_mode != self.data_mode
        ):
            raise ValueError("Mixed position/input modes")
        if {r.asset for r in self.rows} != {t.asset for t in self.config.targets} or len(
            self.rows
        ) != len(self.config.targets):
            raise ValueError("Every configured allocation must have one drift row")
        if any(
            a.risk_inputs.data_mode != self.data_mode
            or a.route.data_mode != ("DEMO" if self.data_mode == "DEMO" else "LIVE")
            for a in self.actions
        ):
            raise ValueError("Mixed action modes")
        if self.snapshot.config_version != self.config.version:
            raise ValueError("Snapshot/config version mismatch")
        if self.status == "REBALANCE_REQUIRED" and (
            not self.actions or any(not a.eligible_for_preparation for a in self.actions)
        ):
            raise ValueError("Rebalance requires bounded eligible deterministic actions")
        if self.status == "NO_ACTION" and self.actions:
            raise ValueError("No-action decision cannot contain executable actions")
        if len({a.action_id for a in self.actions}) != len(self.actions):
            raise ValueError("Duplicate action")
        ids = {a.action_id for a in self.actions}
        if any(p.action_id not in ids for p in self.preparations) or len(
            {p.action_id for p in self.preparations}
        ) != len(self.preparations):
            raise ValueError("Unique action-bound preparation receipts required")
        return self

    def payload(self):
        return self.model_dump_json(exclude_computed_fields=True)
