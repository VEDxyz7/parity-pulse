"""Explicit synthetic Phase 8 protocol fixtures; not real quotes or live gate evidence."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.models.execution import (
    AllowanceState,
    ApprovalBuild,
    BuildResponse,
    ExecutionRiskEvidence,
    FundingAsset,
    FundingState,
    ProviderQuote,
    QuoteRoute,
    RFQPayload,
    RouterResult,
    SimulationResponse,
)
from app.models.risk import OpportunityRiskContext

NOW = datetime(2026, 10, 8, 15, tzinfo=UTC)
SELL = "0x" + "1" * 40
BUY = "0x" + "2" * 40
WALLET = "0x" + "3" * 40
SPENDER = "0x" + "4" * 40
TXHASH = "0x" + "5" * 64
D = Decimal


def mutate(model, **updates):
    return type(model).model_validate({**model.model_dump(), **updates})


def funding(**updates):
    state = FundingState(
        asset=FundingAsset(
            chain_id="56",
            contract=SELL,
            symbol="USDT",
            decimals=6,
            source="TEST_FIXTURE",
            observed_at=NOW,
            data_mode="DEMO",
        ),
        wallet=WALLET,
        balance_base_units="100000000",
        native_gas_balance_wei="100000000000000000",
        gas_reserve_wei="1000000000000000",
        native_unit_price_usd="100",
        native_price_observed_at=NOW,
        unit_price_usd="1.0002",
        price_observed_at=NOW,
        balance_observed_at=NOW,
        conversion_cost_usd="0.1",
        conversion_cost_observed_at=NOW,
        conversion_required=False,
        conversion_verified=False,
        identity_verified=True,
        source="TEST_FIXTURE",
    )
    return mutate(state, **updates)


def evidence(**updates):
    context = OpportunityRiskContext(
        data_mode="DEMO",
        source="TEST_FIXTURE",
        observed_at=NOW,
        stress_adverse_move_fraction="0.02",
        wallet_available_usd="100",
        existing_exposure_usd="0",
        daily_loss_usd="0",
        trades_today=0,
        last_trade_at=None,
        system_resolved=True,
        wallet_allowed=True,
        max_position_usd="50",
        max_portfolio_exposure_usd="100",
        max_daily_loss_usd="5",
        max_risk_budget_usd="5",
        max_trades_per_day=5,
        max_liquidity_fraction="0.01",
        min_confidence="MEDIUM",
        min_liquidity_usd="1000",
        min_liquidity_percentile=50,
        max_slippage_bps="50",
        min_net_edge_usd="0.25",
        cooldown_seconds=60,
    )
    e = ExecutionRiskEvidence(
        decision_id="test-decision",
        data_mode="DEMO",
        purpose="OPPORTUNITY",
        budget_usd="60",
        risk_budget_usd="2",
        notional_usd="40",
        costs_usd="0.2",
        conversion_cost_usd="0.1",
        slippage_bps="50",
        net_expected_edge_usd="1",
        liquidity_usd="100000",
        liquidity_p50_usd="10000",
        context=context,
        confidence="HIGH",
        trust_state="LIKELY_INFORMATION",
        trust_required=True,
        tradable=True,
        route_available=True,
        token_observed_at=NOW,
        equity_observed_at=NOW,
        evidence_observed_at=NOW,
        required_evidence_valid=True,
        system_resolved=True,
    )
    return mutate(e, **updates)


def allowance(amount="100000000", **updates):
    return mutate(
        AllowanceState(
            data_mode="DEMO",
            token=SELL,
            owner=WALLET,
            spender=SPENDER,
            amount=amount,
            observed_at=NOW,
            source="TEST_FIXTURE",
        ),
        **updates,
    )


def route_data(request, *, execution_mode="SWAP", quote_id="quote1"):
    def token(contract, symbol, price):
        return dict(
            tokenContractAddress=contract,
            tokenSymbol=symbol,
            tokenUnitPrice=price,
            decimal="6",
            isHoneyPot=False,
            taxRate="0",
        )

    return dict(
        binanceChainId="56",
        vendorName="Pancake" if execution_mode == "SWAP" else "PcsXRfq",
        fromTokenAmount=request.amount,
        toTokenAmount="400000",
        tradeFee="0.12",
        estimateGasFee="10000",
        priceImpactPercent="-0.1",
        router=SELL + "--" + BUY,
        fromToken=token(SELL, "USDT", "1.0002"),
        toToken=token(BUY, "NVDA", "100"),
        dexRouterList=[],
        quoteId=quote_id,
        executionMode=execution_mode,
        approveTarget=SPENDER,
    )


def quote(request, *, execution_mode="SWAP", quote_id="quote1", now=NOW):
    return ProviderQuote(
        request=request,
        route=QuoteRoute(**route_data(request, execution_mode=execution_mode, quote_id=quote_id)),
        data_mode="DEMO",
        source="TEST_FIXTURE",
        requested_at=now,
        received_at=now,
        expires_at=now + timedelta(seconds=30),
    )


def build(q, *, slippage_bps=None):
    router = RouterResult.model_validate(
        q.route.model_dump(exclude={"quoteId", "executionMode", "approveTarget"})
    )
    if q.route.executionMode == "SWAP":
        return BuildResponse(
            routerResult=router,
            executionMode="SWAP",
            tx={
                "from": WALLET,
                "to": SPENDER,
                "data": "0x12345678",
                "value": "0",
                "gas": "200000",
                "gasPrice": "5000000000",
                "minReceiveAmount": "398000",
                "slippagePercent": "0.5",
            },
        )
    return BuildResponse(
        routerResult=router,
        executionMode="RFQ",
        rfq=RFQPayload(
            vendor="PcsXRfq",
            txType="EIP712",
            typedDataToSign="0x1901abcd",
            signingScheme="EIP712",
            signatureData=(),
            orderId="vendor-order-1",
        ),
    )


def approval_response(amount):
    return ApprovalBuild(
        data="0x095ea7b3" + "0" * 24 + SPENDER[2:] + format(int(amount), "064x"),
        dexContractAddress=SPENDER,
        gasLimit="50000",
        gasPrice="5000000000",
    )


class FixtureProvider:
    fixture_only = True

    def __init__(self, clock=lambda: NOW, execution_mode="SWAP"):
        self.clock = clock
        self.execution_mode = execution_mode
        self.calls = []
        self.count = 0
        self.simulation_status = "SUCCESS"
        self.response_override = None
        self.build_delay = None

    def quote(self, request, *, mode):
        assert mode == "DEMO"
        self.calls.append(("quote", request.model_dump()))
        self.count += 1
        return [
            quote(
                request,
                execution_mode=self.execution_mode,
                quote_id=f"quote{self.count}",
                now=self.clock(),
            )
        ]

    def build(self, q, *, slippage_bps):
        self.calls.append(("build", q.route.quoteId))
        if self.build_delay:
            self.build_delay()
        return build(q, slippage_bps=slippage_bps)

    def approval(self, route):
        self.calls.append(("approval", route.fingerprint))
        return approval_response(route.quote.request.amount)

    def simulate(self, tx, *, mode):
        assert mode == "DEMO"
        self.calls.append(("simulate", tx.evm_payload()))
        # Explicit synthetic approve effects, derived from the actual tested calldata.
        # This is protocol evidence only, never a provider/runtime capability claim.
        changes = ()
        if tx.data.startswith("0x095ea7b3"):
            changes = (
                dict(
                    tokenAddress=tx.to,
                    owner=tx.sender,
                    spender="0x" + tx.data[34:74],
                    preAmount="0",
                    postAmount=str(int(tx.data[74:138], 16)),
                ),
            )
        return self.response_override or SimulationResponse(
            status=self.simulation_status,
            failReason=None if self.simulation_status == "SUCCESS" else "reverted",
            balanceChanges=(),
            allowanceChanges=changes,
        ), self.clock()


class Clock:
    def __init__(self):
        self.value = NOW

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


def market():
    row = SimpleNamespace(
        binanceChainId="56", tokenContractAddress=SELL, tokenSymbol="USDT", decimals=6
    )
    return SimpleNamespace(search=lambda *_: [row], basic_info=lambda _: row)


def request():
    from app.models.execution import QuoteRequest

    return QuoteRequest(
        binanceChainId="56",
        amount="39992002",
        fromTokenAddress=SELL,
        toTokenAddress=BUY,
        userWalletAddress=WALLET,
    )
