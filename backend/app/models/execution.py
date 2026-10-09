"""Phase 8 exact, immutable safety contracts. No contract authorizes live execution."""

import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BeforeValidator, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.clients.common import unique_object
from app.models.data import DataModel, Nonnegative, Positive, utc
from app.models.risk import OpportunityRiskContext, RiskCheck


def address(value):
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
        raise ValueError("Invalid EVM address")
    if int(value[2:], 16) == 0:
        raise ValueError("Zero address is unavailable")
    return value.lower()


def units(value):
    if not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]{0,77}", value):
        raise ValueError("Canonical uint256 integer string required")
    if int(value) >= 2**256:
        raise ValueError("Amount exceeds uint256")
    return value


def hex_data(value):
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})+", value):
        raise ValueError("Complete hex bytes required")
    if len(value) > 262146:
        raise ValueError("Payload too large")
    return value.lower()


Address = Annotated[str, BeforeValidator(address)]
Units = Annotated[str, BeforeValidator(units)]
HexData = Annotated[str, BeforeValidator(hex_data)]
Identifier = Annotated[str, Field(strict=True, pattern=r"^[A-Za-z0-9_-]{1,128}$")]
Hash = Annotated[str, Field(strict=True, pattern=r"^0x[0-9a-fA-F]{64}$")]
Digest = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
Mode = Literal["DEMO", "LIVE_READ_ONLY"]
ExecutionMode = Literal["SWAP", "RFQ"]


def canonical(value):
    if isinstance(value, DataModel):
        value = value.model_dump(mode="json", by_alias=True)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def parse_object(value):
    if not isinstance(value, str) or len(value) > 262144:
        raise ValueError("Bounded JSON string required")
    result = json.loads(
        value,
        object_pairs_hook=unique_object,
        parse_float=Decimal,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid JSON number")),
    )
    if not isinstance(result, dict):
        raise ValueError("JSON object required")
    return result


class ExecutionModel(DataModel):
    @field_validator("*", mode="after")
    @classmethod
    def aware(cls, value):
        if isinstance(value, datetime):
            return utc(value)
        if isinstance(value, Decimal) and (
            len(value.as_tuple().digits) > 96 or abs(value.adjusted()) > 72
        ):
            raise ValueError("Financial precision outside supported bounds")
        return value


class FundingAsset(ExecutionModel):
    chain_id: Literal["56"]
    contract: Address
    symbol: Identifier
    decimals: int = Field(strict=True, ge=0, le=36)
    source: Identifier
    observed_at: datetime
    data_mode: Mode


class FundingState(ExecutionModel):
    asset: FundingAsset
    wallet: Address
    balance_base_units: Units
    native_gas_balance_wei: Units
    gas_reserve_wei: Units
    native_unit_price_usd: Positive
    native_price_observed_at: datetime
    unit_price_usd: Positive
    price_observed_at: datetime
    balance_observed_at: datetime
    conversion_cost_usd: Nonnegative
    conversion_cost_observed_at: datetime
    conversion_required: bool = Field(strict=True)
    conversion_verified: bool = Field(strict=True)
    identity_verified: bool = Field(strict=True)
    source: Identifier


class FundingCheck(ExecutionModel):
    status: Literal["PASS", "FAIL"]
    reasons: tuple[str, ...]
    state: FundingState | None
    usd_notional: Positive
    required_base_units: Units | None
    conversion_cost_usd: Nonnegative | None
    evaluated_at: datetime


class QuoteRequest(ExecutionModel):
    binanceChainId: Literal["56"]
    amount: Units
    fromTokenAddress: Address
    toTokenAddress: Address
    userWalletAddress: Address

    @model_validator(mode="after")
    def valid(self):
        if int(self.amount) <= 0 or self.fromTokenAddress == self.toTokenAddress:
            raise ValueError("Positive amount and different assets required")
        return self


class QuoteToken(ExecutionModel):
    tokenContractAddress: Address
    tokenSymbol: Identifier
    tokenUnitPrice: Positive
    decimal: Units
    isHoneyPot: bool = Field(strict=True)
    taxRate: Nonnegative = Field(le=1)

    @model_validator(mode="after")
    def valid(self):
        if int(self.decimal) > 36 or self.isHoneyPot or self.taxRate != 0:
            raise ValueError("Unverified taxed/honeypot token is blocked")
        return self


class SegmentToken(ExecutionModel):
    tokenContractAddress: Address
    tokenSymbol: Identifier
    # Current API repeats the full token descriptor per route segment (informational only).
    # Excluded from dumps so route fingerprints keep their established canonical form.
    tokenUnitPrice: Positive | None = Field(default=None, exclude=True)
    decimal: Units | None = Field(default=None, exclude=True)
    isHoneyPot: bool | None = Field(default=None, strict=True, exclude=True)
    taxRate: Nonnegative | None = Field(default=None, le=1, exclude=True)


class DexProtocol(ExecutionModel):
    dexName: str = Field(strict=True, pattern=r"^[A-Za-z0-9 ._()-]{1,128}$")
    percent: Nonnegative = Field(le=100)


class DexSegment(ExecutionModel):
    dexProtocol: DexProtocol
    fromToken: SegmentToken
    toToken: SegmentToken
    fromTokenIndex: Units
    toTokenIndex: Units


class RouterResult(ExecutionModel):
    binanceChainId: Literal["56"]
    vendorName: Identifier
    fromTokenAmount: Units
    toTokenAmount: Units
    tradeFee: Nonnegative | None = None  # USD network fee, not token units
    estimateGasFee: Units | None = None  # provider estimate; never silently USD
    priceImpactPercent: Annotated[Decimal, BeforeValidator(lambda v: signed_decimal(v))] | None = (
        None
    )
    router: str = Field(strict=True, min_length=1, max_length=4096)
    fromToken: QuoteToken
    toToken: QuoteToken
    dexRouterList: tuple[DexSegment, ...] = Field(max_length=100)
    feeAmount: Units | None = None
    feeToken: Address | None = None
    actualSwapAmount: Units | None = None

    @model_validator(mode="after")
    def valid(self):
        if int(self.fromTokenAmount) <= 0 or int(self.toTokenAmount) <= 0:
            raise ValueError("Positive quote amounts required")
        hops = self.router.split("--")
        if any(address(v) != v.lower() for v in hops):
            raise ValueError("Invalid route path")
        if (
            address(hops[0]) != self.fromToken.tokenContractAddress
            or address(hops[-1]) != self.toToken.tokenContractAddress
        ):
            raise ValueError("Route endpoints mismatch")
        if (
            self.feeAmount is not None
            or self.feeToken is not None
            or self.actualSwapAmount is not None
        ):
            raise ValueError(
                "Custom referral fees require a separately verified supported contract"
            )
        return self


def signed_decimal(value):
    from app.models.data import financial

    return financial(value)


class QuoteRoute(RouterResult):
    quoteId: Identifier
    executionMode: ExecutionMode
    approveTarget: Address | None = None
    isBest: bool | None = Field(default=None, strict=True, exclude=True)


class ProviderQuote(ExecutionModel):
    request: QuoteRequest
    route: QuoteRoute
    data_mode: Mode
    source: Literal["BINANCE_WEB3", "TEST_FIXTURE"]
    requested_at: datetime
    received_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def binding(self):
        r, q = self.route, self.request
        if (
            r.binanceChainId,
            r.fromTokenAmount,
            r.fromToken.tokenContractAddress,
            r.toToken.tokenContractAddress,
        ) != (q.binanceChainId, q.amount, q.fromTokenAddress, q.toTokenAddress):
            raise ValueError("Quote/request mismatch")
        if (
            not self.requested_at <= self.received_at < self.expires_at
            or (self.expires_at - self.requested_at).total_seconds() > 30
        ):
            raise ValueError("Quote lifetime must be bounded from request start")
        if self.source == "TEST_FIXTURE" and self.data_mode != "DEMO":
            raise ValueError("Fixtures cannot become real-provider evidence")
        return self


class EvmTransaction(ExecutionModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, hide_input_in_errors=True, populate_by_name=True
    )
    sender: Address = Field(alias="from")
    to: Address
    data: HexData
    value: Units
    gas: Units
    gasPrice: Units
    maxPriorityFeePerGas: Units | None = None
    minReceiveAmount: Units | None = None
    slippagePercent: Nonnegative | None = Field(default=None, le=100)
    signatureData: tuple[str, ...] = Field(default=(), max_length=10)
    computeUnitPrice: None = None
    computeUnitLimit: None = None

    @field_validator("signatureData", mode="before")
    @classmethod
    def empty_signatures(cls, value):
        return () if value is None else value

    @model_validator(mode="after")
    def gas_valid(self):
        if int(self.gas) <= 0 or int(self.gasPrice) <= 0:
            raise ValueError("Explicit positive gas fields required")
        # BSC builds repeat gasPrice as the priority fee; that is an unambiguous legacy price.
        if self.maxPriorityFeePerGas is not None and self.maxPriorityFeePerGas != self.gasPrice:
            raise ValueError("Ambiguous mixed legacy/EIP1559 fees require verified rebuild")
        return self

    def evm_payload(self):
        # Official simulator accepts these four fields only. Gas coverage remains explicit.
        return {"from": self.sender, "to": self.to, "value": self.value, "data": self.data}


class RFQPayload(ExecutionModel):
    vendor: Literal["InchFusion", "CowSwap", "PcsXRfq"]
    txType: Literal["EIP712"]
    typedDataToSign: str = Field(strict=True, min_length=2, max_length=262144)
    signingScheme: Literal["EIP712"]
    signatureData: tuple[str, ...] = Field(default=(), max_length=10)
    # Documented by order/submit prose, omitted from published /swap properties. Required safely.
    orderId: Identifier

    @model_validator(mode="after")
    def typed(self):
        if self.typedDataToSign.startswith("0x"):
            hex_data(self.typedDataToSign)  # opaque bytes retained, never called fully verified
        else:
            typed = parse_object(self.typedDataToSign)
            if set(typed) != {"types", "domain", "primaryType", "message"}:
                raise ValueError("Complete EIP712 structure required")
            if not all(isinstance(typed[v], dict) for v in ("types", "domain", "message")):
                raise ValueError("Invalid EIP712 objects")
            if typed["domain"].get("chainId") not in (56, "56"):
                raise ValueError("Wrong typed-data chain")
            address(typed["domain"].get("verifyingContract"))
            primary = typed["primaryType"]
            if (
                not isinstance(primary, str)
                or primary not in typed["types"]
                or primary == "EIP712Domain"
            ):
                raise ValueError("Unknown EIP712 primary type")
            for name, fields in typed["types"].items():
                if not isinstance(name, str) or not isinstance(fields, list) or len(fields) > 100:
                    raise ValueError("Invalid EIP712 type")
                names = []
                for field in fields:
                    if (
                        not isinstance(field, dict)
                        or set(field) != {"name", "type"}
                        or not all(isinstance(v, str) for v in field.values())
                    ):
                        raise ValueError("Invalid EIP712 field")
                    names.append(field["name"])
                if len(names) != len(set(names)):
                    raise ValueError("Duplicate EIP712 field")
            if set(typed["message"]) != {v["name"] for v in typed["types"][primary]}:
                raise ValueError("Incomplete EIP712 message")
            from app.services.eip712_validation import validate_typed_data

            validate_typed_data(typed)
        return self


class BuildResponse(ExecutionModel):
    routerResult: RouterResult
    executionMode: ExecutionMode
    tx: EvmTransaction | None = None
    rfq: RFQPayload | None = None

    @model_validator(mode="after")
    def branch(self):
        if self.executionMode == "SWAP" and (self.tx is None or self.rfq is not None):
            raise ValueError("SWAP requires exactly one EVM transaction")
        if self.executionMode == "RFQ" and (self.rfq is None or self.tx is not None):
            raise ValueError("RFQ requires exactly one RFQ payload")
        return self


class AllowanceState(ExecutionModel):
    data_mode: Mode
    token: Address
    owner: Address
    spender: Address
    amount: Units
    observed_at: datetime
    source: Identifier


class PreparedRoute(ExecutionModel):
    quote: ProviderQuote
    build: BuildResponse
    slippage_bps: Nonnegative = Field(le=10000)
    prepared_at: datetime
    approval_required: bool = Field(strict=True)
    allowance: AllowanceState | None
    fingerprint: Digest

    def critical(self):
        return self.model_dump(mode="json", by_alias=True, exclude={"fingerprint", "prepared_at"})

    @model_validator(mode="after")
    def valid(self):
        if fingerprint(self.critical()) != self.fingerprint:
            raise ValueError("Prepared route fingerprint mismatch")
        return self


class ApprovalBuild(ExecutionModel):
    data: HexData
    dexContractAddress: Address
    gasLimit: Units
    gasPrice: Units


class PreparedApproval(ExecutionModel):
    route_fingerprint: Digest
    token: Address
    spender: Address
    amount: Units
    pre_allowance_amount: Units
    transaction: EvmTransaction
    fingerprint: Digest

    def critical(self):
        return self.model_dump(mode="json", by_alias=True, exclude={"fingerprint"})

    @model_validator(mode="after")
    def valid(self):
        expected = "0x095ea7b3" + "0" * 24 + self.spender[2:] + format(int(self.amount), "064x")
        if (
            self.transaction.to != self.token
            or self.transaction.value != "0"
            or self.transaction.data.lower() != expected.lower()
            or not int(self.pre_allowance_amount) < int(self.amount) < 2**256 - 1
        ):
            raise ValueError("Exact bounded approval calldata required")
        if fingerprint(self.critical()) != self.fingerprint:
            raise ValueError("Approval fingerprint mismatch")
        return self


class BalanceChange(ExecutionModel):
    contractAddress: str = Field(strict=True, max_length=128)
    tokenType: Identifier
    change: str = Field(strict=True, pattern=r"^-?(0|[1-9][0-9]{0,77})$")
    owner: Address


class AllowanceChange(ExecutionModel):
    tokenAddress: Address
    owner: Address
    spender: Address
    preAmount: Units
    postAmount: Units


class SimulationResponse(ExecutionModel):
    status: Literal["SUCCESS", "FAILED"]
    failReason: str | None = Field(default=None, max_length=4096)
    balanceChanges: tuple[BalanceChange, ...] = Field(max_length=100)
    allowanceChanges: tuple[AllowanceChange, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "SUCCESS" and self.failReason:
            raise ValueError("Conflicting simulation success/failure")
        return self


class ExecutionSimulation(ExecutionModel):
    fingerprint: Digest
    payload_digest: Digest
    data_mode: Mode
    source: Literal["BINANCE_WEB3", "TEST_FIXTURE"]
    evaluated_at: datetime
    status: Literal["PASS", "FAIL", "UNAVAILABLE"]
    response: SimulationResponse | None
    reason_codes: tuple[str, ...]
    coverage: Literal["EVM_FROM_TO_VALUE_DATA_ONLY", "RFQ_SETTLEMENT_UNAVAILABLE"]
    live_equivalence_verified: Literal[False] = False

    @model_validator(mode="after")
    def valid(self):
        if self.source == "TEST_FIXTURE" and self.data_mode != "DEMO":
            raise ValueError("Fixture simulation cannot become production evidence")
        if self.status == "PASS" and (
            self.response is None
            or self.response.status != "SUCCESS"
            or self.response.failReason
            or self.coverage != "EVM_FROM_TO_VALUE_DATA_ONLY"
        ):
            raise ValueError("Successful exact EVM simulation required")
        if self.status == "UNAVAILABLE" and self.response is not None:
            raise ValueError("Unavailable simulation cannot carry a successful response")
        return self


class ExecutionRiskEvidence(ExecutionModel):
    decision_id: Identifier
    data_mode: Mode
    purpose: Literal["DIRECT_EXPOSURE", "OPPORTUNITY"]
    budget_usd: Positive
    risk_budget_usd: Positive
    notional_usd: Positive
    costs_usd: Nonnegative
    conversion_cost_usd: Nonnegative
    slippage_bps: Nonnegative = Field(le=10000)
    net_expected_edge_usd: Annotated[Decimal, BeforeValidator(signed_decimal)]
    liquidity_usd: Positive | None
    liquidity_p50_usd: Positive | None
    context: OpportunityRiskContext | None
    confidence: Literal["LOW", "MEDIUM", "HIGH"]
    trust_state: Literal["NORMAL", "LIKELY_INFORMATION", "LIKELY_NOISE", "INSUFFICIENT_EVIDENCE"]
    trust_required: bool = Field(strict=True)
    tradable: bool = Field(strict=True)
    route_available: bool = Field(strict=True)
    token_observed_at: datetime
    equity_observed_at: datetime
    evidence_observed_at: datetime
    required_evidence_valid: bool = Field(strict=True)
    system_resolved: bool = Field(strict=True)

    @model_validator(mode="after")
    def trust_mandatory(self):
        # Only a configured portfolio rebalance (direct exposure) may run without Trust;
        # Opportunity selection is a Trust-derived signal and keeps it mandatory.
        if not self.trust_required and self.purpose != "DIRECT_EXPOSURE":
            raise ValueError("Trust cannot be disabled for opportunity execution preparation")
        if self.context is not None and self.context.data_mode != self.data_mode:
            raise ValueError("Mixed risk evidence modes")
        return self


class ExecutionRiskDecision(ExecutionModel):
    evidence_digest: Digest
    evaluated_at: datetime
    data_mode: Mode
    decision_id: Identifier
    status: Literal["PASS", "FAIL"]
    checks: tuple[RiskCheck, ...]
    stress_loss_usd: Nonnegative | None
    maximum_notional_usd: Nonnegative | None
    risk_semantics: Literal["EX_ANTE_NOT_A_GUARANTEED_MAXIMUM_REALIZED_LOSS"] = (
        "EX_ANTE_NOT_A_GUARANTEED_MAXIMUM_REALIZED_LOSS"
    )

    @model_validator(mode="after")
    def valid(self):
        if (self.status == "PASS") != (bool(self.checks) and all(c.passed for c in self.checks)):
            raise ValueError("Risk cannot override failed checks")
        return self


class RFQSubmission(ExecutionModel):
    requestId: UUID
    userSignature: SecretStr = Field(exclude=True, repr=False)
    vendor: Literal["InchFusion", "CowSwap", "PcsXRfq"]
    quoteId: Identifier
    signingScheme: Literal["EIP712"]

    @model_validator(mode="after")
    def valid(self):
        if self.requestId.version != 4 or not re.fullmatch(
            r"0x[0-9a-fA-F]{130}", self.userSignature.get_secret_value()
        ):
            raise ValueError("UUIDv4 attempt and exact 65-byte signature required")
        return self

    def wire_body(self):
        # Only the execution gateway may pass this ephemeral body to a future verified transport.
        return {
            **self.model_dump(mode="json"),
            "userSignature": self.userSignature.get_secret_value(),
        }

    def wire_request(self):
        """Ephemeral contract representation; never logged/persisted or sent in Phase 8."""
        return "POST", "/api/v1/dex/aggregator/order/submit", self.wire_body()


class RFQStatus(ExecutionModel):
    orderId: Identifier
    status: Identifier  # unknown provider enums remain UNKNOWN, never success
    txHash: Hash | None = None
    fromAmount: Units | None = None
    toAmount: Units | None = None
    filledAt: int | None = Field(default=None, strict=True, gt=0)
    createdAt: int = Field(strict=True, gt=0)


class SwapStatus(ExecutionModel):
    binanceChainId: Literal["56"]
    txHash: Hash
    height: Units
    txTime: Units
    status: Identifier
    fromAddress: Address
    toAddress: Address
    errorMsg: str | None = None
    gasLimit: Units | None = None
    gasUsed: Units | None = None
    gasPrice: Units | None = None
    txFee: Units | None = None
    priorityFee: Units | None = None
    txType: str | None = None
    dexRouter: Address | None = None
    fromTokenDetails: tuple[dict, ...] | None = None
    toTokenDetails: tuple[dict, ...] | None = None


class SettlementIdentity(ExecutionModel):
    execution_id: UUID
    request_id: UUID
    decision_id: Identifier
    data_mode: Mode
    source: Literal["BINANCE_WEB3", "TEST_FIXTURE"]
    execution_mode: ExecutionMode
    quote_id: Identifier
    vendor: Identifier
    wallet: Address
    order_id: Identifier | None
    route_fingerprint: Digest


class SettlementEvidence(ExecutionModel):
    """Captured response plus exact host request context, never a success-label override."""

    identity: SettlementIdentity
    received_at: datetime
    corroborated_tx_hash: Hash | None = None
    rfq: RFQStatus | None = None
    swap: SwapStatus | None = None

    @model_validator(mode="after")
    def branch(self):
        if (self.identity.execution_mode == "RFQ") != (self.rfq is not None):
            raise ValueError("Settlement mode/response mismatch")
        if (self.identity.execution_mode == "SWAP") != (self.swap is not None):
            raise ValueError("Settlement requires exactly one matching response")
        return self


class ExecutionControls(ExecutionModel):
    data_mode: Mode
    execution_mode: Literal["DRY_RUN"] = "DRY_RUN"
    approval_mode: Literal["PROPOSE_ONLY", "AUTONOMOUS"] = "PROPOSE_ONLY"
    live_trading_enabled: Literal[False] = False
    require_simulation: Literal[True] = True
    swap_live_gate: Literal["BLOCKED"] = "BLOCKED"
    rfq_live_gate: Literal["BLOCKED"] = "BLOCKED"
    agentic_wallet_live_gate: Literal["BLOCKED"] = "BLOCKED"


ExecutionState = Literal[
    "PROPOSAL",
    "RISK_APPROVED",
    "QUOTE_CREATED",
    "ROUTE_BUILT",
    "SIMULATION_PASSED",
    "APPROVAL_REQUIRED",
    "APPROVAL_CONFIRMED",
    "EXECUTION_SUBMITTED",
    "EXECUTION_PENDING",
    "EXECUTION_CONFIRMED",
    "EXECUTION_FAILED",
    "EXECUTION_EXPIRED",
    "EXECUTION_CANCELLED",
    "EXECUTION_UNKNOWN",
    "BLOCKED",
]


class UserConfirmation(ExecutionModel):
    route_fingerprint: Digest
    decision_id: Identifier
    confirmed_at: datetime
    expires_at: datetime
    source: Literal["HOST_EXPLICIT_USER_CONFIRMATION"]

    @model_validator(mode="after")
    def valid(self):
        if not self.confirmed_at < self.expires_at:
            raise ValueError("Invalid confirmation validity")
        return self


class ExecutionAttempt(ExecutionModel):
    schema_version: Literal["execution-1"] = "execution-1"
    execution_id: UUID
    request_id: UUID
    rfq_request_digest: Digest | None = None
    decision_id: Identifier
    correlation_id: Identifier
    data_mode: Mode
    source: Literal["BINANCE_WEB3", "TEST_FIXTURE"]
    state: ExecutionState
    version: int = Field(strict=True, ge=0)
    generation: int = Field(strict=True, ge=0)
    created_at: datetime
    updated_at: datetime
    evidence: ExecutionRiskEvidence
    risk: ExecutionRiskDecision | None = None
    funding: FundingCheck | None = None
    quote: ProviderQuote | None = None
    route: PreparedRoute | None = None
    simulation: ExecutionSimulation | None = None
    approval: PreparedApproval | None = None
    approval_simulation: ExecutionSimulation | None = None
    approval_allowance: AllowanceState | None = None
    user_confirmation: UserConfirmation | None = None
    order_id: Identifier | None = None
    tx_hash: Hash | None = None
    external_status: Identifier | None = None
    external_tracking_only: bool = Field(default=False, strict=True)
    filled_quantity_base_units: Units | None = None
    average_execution_price: Positive | None = None
    fees_native_base_units: Units | None = None
    settled_at: datetime | None = None
    settlement_evidence: SettlementEvidence | None = None
    conflicting_tx_hashes: tuple[Hash, ...] = Field(default=(), max_length=10)
    last_conflicting_tx_hash: Hash | None = None
    settlement_conflict: bool = Field(default=False, strict=True)
    reason_codes: tuple[str, ...] = ()
    execution_ready: Literal[False] = False
    broadcast: Literal[False] = False
    signed: Literal[False] = False
    funds_moved: Literal[False] = False

    @model_validator(mode="after")
    def valid(self):
        if self.request_id.version != 4 or self.execution_id.version != 4:
            raise ValueError("UUIDv4 execution and RFQ attempt IDs required")
        if (
            self.evidence.data_mode != self.data_mode
            or self.evidence.decision_id != self.decision_id
        ):
            raise ValueError("Evidence/attempt binding mismatch")
        if self.source == "TEST_FIXTURE" and self.data_mode != "DEMO":
            raise ValueError("Fixtures cannot authorize production")
        if self.risk and (
            self.risk.evidence_digest != fingerprint(self.evidence)
            or self.risk.decision_id != self.decision_id
            or self.risk.data_mode != self.data_mode
        ):
            raise ValueError("Risk evidence binding mismatch")
        if self.quote and (
            self.quote.data_mode != self.data_mode or self.quote.source != self.source
        ):
            raise ValueError("Quote provenance mismatch")
        if self.route and self.quote != self.route.quote:
            raise ValueError("Prepared route differs from quoted route")
        if self.simulation and (
            self.route is None or self.simulation.fingerprint != self.route.fingerprint
        ):
            raise ValueError("Simulation fingerprint mismatch")
        if self.approval and (
            self.route is None or self.approval.route_fingerprint != self.route.fingerprint
        ):
            raise ValueError("Approval route mismatch")
        if self.approval_simulation and (
            self.approval is None
            or self.approval_simulation.fingerprint != self.approval.fingerprint
        ):
            raise ValueError("Approval simulation mismatch")
        external = {
            "EXECUTION_SUBMITTED",
            "EXECUTION_PENDING",
            "EXECUTION_CONFIRMED",
            "EXECUTION_UNKNOWN",
        }
        if self.state in external and not (
            self.external_tracking_only and (self.order_id or self.tx_hash)
        ):
            raise ValueError("Submitted/observed states require independently tracked identifiers")
        if self.state == "EXECUTION_CONFIRMED":
            from app.services.execution_confirmation import validate_confirmation

            validate_confirmation(self)
        return self
