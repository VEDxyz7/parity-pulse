from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from app.models.execution import BuildResponse, SimulationResponse
from app.repositories.live_fills import LiveFillStore
from app.services.live_execution import LiveExecutionError, LiveRebalanceExecutor
from app.services.live_portfolio_source import USDT

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
WALLET = "0x" + "a" * 40
TOKEN = "0x02fca66c1d1afb4e2a7884261eb00f63598a7436"
ROUTER = "0x" + "b" * 40
E18 = 10**18


def action(side="BUY", notional="10", qty=str(42 * 10**15), **kw):
    return NS(
        action_id=kw.get("action_id", side + "-1"),
        priority=1,
        asset="NVDA",
        side=side,
        notional_usd=Decimal(notional),
        quantity_base_units=qty,
        decimals=18,
        eligible_for_preparation=kw.get("eligible", True),
        risk=NS(status="PASS"),
        risk_inputs=NS(slippage_bps=Decimal(10)),
        route=NS(
            selected_representation=NS(contract=TOKEN),
            selected_candidate=NS(inputs=NS(token_price_usd=Decimal("235"))),
        ),
    )


class Portfolio:
    inventory, mode = "WALLET", "LIVE_READ_ONLY"

    def __init__(self, actions, wallet=WALLET):
        self.plan = NS(
            plan_id="p1",
            status="REBALANCE_REQUIRED",
            created_at=NOW,
            actions=actions,
            snapshot=NS(inputs=NS(funding=NS(wallet=wallet, unit_price_usd=Decimal(1)))),
        )
        self.executed = False
        self.store = NS(get=lambda pid, mode: self.plan, pending=lambda mode: self.plan)

    def mark_executed(self, plan_id):
        self.executed = True


class Rpc:
    def __init__(self, usdt=100 * E18, token=0, native=E18, allowance=0, status="0x1"):
        self.balances = {USDT: usdt, TOKEN: token}
        self.native, self.allow, self.status = native, allowance, status
        self.sent = []

    def erc20_balance(self, token, owner):
        return self.balances[token]

    def allowance(self, token, owner, spender):
        return self.allow

    def native_balance(self, owner):
        return self.native

    def gas_price(self):
        return 50_000_000

    def receipt(self, tx_hash):
        if tx_hash.endswith("01"):  # approval
            self.allow = 10**30
        else:  # swap settles
            self.balances[USDT] -= 10 * E18
            self.balances[TOKEN] += 42_400_000_000_000_000
        return {"status": self.status, "gasUsed": "0x3d090", "blockNumber": "0x10"}


class Signer:
    kind = "TEST"
    address = WALLET

    def __init__(self, rpc):
        self.rpc, self.count = rpc, 0

    def send(self, **tx):
        self.count += 1
        self.rpc.sent.append(tx)
        return "0x" + "0" * 62 + format(self.count, "02x")


USDT_TOKEN = {
    "tokenContractAddress": USDT,
    "tokenSymbol": "USDT",
    "tokenUnitPrice": "1",
    "decimal": "18",
    "isHoneyPot": False,
    "taxRate": "0",
}
ROUTER_RESULT = {
    "binanceChainId": "56",
    "vendorName": "LiquidMesh",
    "fromTokenAmount": str(10 * E18),
    "toTokenAmount": "42400000000000000",
    "router": USDT + "--" + TOKEN,
    "fromToken": USDT_TOKEN,
    "toToken": {**USDT_TOKEN, "tokenContractAddress": TOKEN, "tokenSymbol": "NVDAB"},
    "dexRouterList": [],
}


def route(out="42400000000000000", mode="SWAP", impact="0.0009"):
    return NS(
        executionMode=mode,
        approveTarget=ROUTER,
        toTokenAmount=out,
        priceImpactPercent=Decimal(impact),
        quoteId="q1",
        vendorName="LiquidMesh",
    )


class Trading:
    def __init__(self, quote_route=None, sim="SUCCESS", min_receive="42000000000000000"):
        self.route = quote_route or route()
        self.sim, self.min_receive = sim, min_receive
        self.simulated = []

    def quote(self, request, mode):
        return [NS(route=self.route, expires_at=NOW + timedelta(seconds=30), request=request)]

    def build(self, quote, slippage_bps):
        return BuildResponse.model_validate(
            {
                "executionMode": "SWAP",
                "routerResult": ROUTER_RESULT,
                "tx": {
                    "from": WALLET,
                    "to": ROUTER,
                    "data": "0xad43f73d",
                    "value": "0",
                    "gas": "250000",
                    "gasPrice": "50000000",
                    "minReceiveAmount": self.min_receive,
                },
            }
        )

    def simulate(self, tx, mode):
        self.simulated.append(tx)
        return (
            SimulationResponse(
                status=self.sim,
                failReason=None if self.sim == "SUCCESS" else "reverted",
                balanceChanges=(),
                allowanceChanges=(),
            ),
            NOW,
        )


def executor(portfolio, trading, rpc, **kw):
    return LiveRebalanceExecutor(
        portfolio,
        trading,
        rpc,
        kw.pop("signer", None) or Signer(rpc),
        LiveFillStore(),
        max_notional_usd=kw.pop("cap", 25),
        max_slippage_bps=100,
        gas_reserve_wei=2 * 10**15,
        clock=lambda: NOW,
        sleep=lambda _: None,
    )


def test_buy_approves_exact_amount_simulates_sends_and_reconciles():
    rpc, trading, p = Rpc(), Trading(), Portfolio([action()])
    legs = executor(p, trading, rpc).execute("p1")
    assert [leg["status"] for leg in legs] == ["CONFIRMED"]
    leg = legs[0]
    assert leg["approve_tx"] and leg["swap_tx"]
    assert leg["evidence"]["received"] == "42400000000000000"
    # approval is exact (10 USDT), never unlimited
    approve = rpc.sent[0]["data"]
    assert int(approve[-64:], 16) == 10 * E18 and rpc.sent[0]["to"] == USDT
    assert len(trading.simulated) == 2 and p.executed


def test_rerun_never_resends_a_journaled_leg():
    rpc, trading, p = Rpc(), Trading(), Portfolio([action()])
    ex = executor(p, trading, rpc)
    ex.execute("p1")
    sent = len(rpc.sent)
    p.plan.status = "REBALANCE_REQUIRED"
    ex.execute("p1")
    assert len(rpc.sent) == sent


@pytest.mark.parametrize(
    "kwargs,code",
    [
        (dict(trading=Trading(route(mode="RFQ"))), "NO_SIMULATABLE_SWAP_ROUTE"),
        (dict(trading=Trading(route(impact="0.02"))), "PRICE_IMPACT_LIMIT"),
        (dict(trading=Trading(route(out="1"))), "QUOTE_BELOW_PLAN_MINIMUM"),
        (dict(trading=Trading(sim="FAILED")), "APPROVAL_SIMULATION_FAILED"),
        (dict(trading=Trading(min_receive="1")), "BUILD_MIN_RECEIVE_BELOW_PLAN_MINIMUM"),
        (dict(rpc=Rpc(usdt=1)), "INSUFFICIENT_ON_CHAIN_BALANCE"),
        (dict(rpc=Rpc(native=1)), "INSUFFICIENT_NATIVE_GAS_AND_RESERVE"),
        (dict(cap=5), "LIVE_NOTIONAL_CAP"),
    ],
)
def test_every_failed_check_rejects_before_any_swap_is_sent(kwargs, code):
    rpc = kwargs.pop("rpc", Rpc())
    trading = kwargs.pop("trading", Trading())
    p = Portfolio([action()])
    legs = executor(p, trading, rpc, **kwargs).execute("p1")
    assert legs[0]["status"] == "REJECTED" and legs[0]["reasons"] == [code]
    assert not legs[0]["swap_tx"] and not p.executed


def test_reverted_swap_is_failed_not_confirmed():
    rpc = Rpc(allowance=10**30, status="0x0")
    legs = executor(Portfolio([action()]), Trading(), rpc).execute("p1")
    assert legs[0]["status"] == "FAILED" and legs[0]["reasons"] == ["SWAP_REVERTED_ON_CHAIN"]


def test_plan_wallet_must_be_signer_wallet_and_plan_must_be_pending():
    with pytest.raises(LiveExecutionError):
        executor(Portfolio([action()], wallet="0x" + "c" * 40), Trading(), Rpc()).execute("p1")
    p = Portfolio([action()])
    p.plan.status = "BLOCKED"
    with pytest.raises(LiveExecutionError):
        executor(p, Trading(), Rpc()).execute("p1")


def test_requires_wallet_inventory_portfolio():
    p = Portfolio([action()])
    p.inventory = "POSITIONS"
    with pytest.raises(ValueError):
        executor(p, Trading(), Rpc())


def test_altana_signer_posts_call_and_requires_hash():
    import httpx
    from pydantic import SecretStr

    from app.services.live_signer import AltanaSigner

    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path == "/altana/status":
            return httpx.Response(200, json={"wallet": WALLET.upper().replace("0X", "0x")})
        if request.headers.get("x-sidecar-token") != "t" * 20:
            return httpx.Response(401, json={})
        return httpx.Response(200, json={"transactionHash": "0x" + "d" * 64, "status": "PENDING"})

    signer = AltanaSigner(
        "http://127.0.0.1:8787",
        SecretStr("t" * 20),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert signer.address == WALLET
    assert signer.send(to=ROUTER, data="0x01", value=0, gas=1, gas_price=1) == "0x" + "d" * 64
    bad = AltanaSigner(
        "http://127.0.0.1:8787",
        SecretStr("x" * 20),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(LiveExecutionError):
        bad.send(to=ROUTER, data="0x01", value=0, gas=1, gas_price=1)


def test_error_after_swap_sent_is_reconciled_not_rejected():
    rpc, trading, p = Rpc(allowance=10**30), Trading(), Portfolio([action()])
    calls = {"n": 0}
    original = rpc.erc20_balance

    def flaky(token, owner):
        calls["n"] += 1
        if calls["n"] > 3:  # balances read after the swap was sent
            raise ValueError("rpc hiccup")
        return original(token, owner)

    rpc.erc20_balance = flaky
    legs = executor(p, trading, rpc).execute("p1")
    assert legs[0]["swap_tx"] and legs[0]["status"] == "CONFIRMED"


def test_stale_plan_must_be_reevaluated():
    p = Portfolio([action()])
    p.plan.created_at = NOW - timedelta(minutes=11)
    with pytest.raises(LiveExecutionError):
        executor(p, Trading(), Rpc()).execute("p1")
