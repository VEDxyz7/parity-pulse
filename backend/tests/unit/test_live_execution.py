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
            selected_candidate=NS(inputs=NS(token_price_usd=Decimal("235"), market_state=kw.get("state", "regular"))),
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


def test_closed_underlying_leg_gets_half_cap():
    legs = executor(Portfolio([action(notional="15", state="offhours")]), Trading(), Rpc()).execute("p1")
    assert legs[0]["status"] == "REJECTED" and legs[0]["reasons"] == ["LIVE_NOTIONAL_CAP"]


# ---- RFQ legs -----------------------------------------------------------------------------
from pydantic import SecretStr  # noqa: E402

from app.services.live_signer import LocalKeySigner  # noqa: E402
from app.services.rfq_orders import PERMIT2, parse_allowlist  # noqa: E402
from backend.tests.unit import test_rfq_orders as orders  # noqa: E402

KEY = SecretStr("0x" + "42" * 32)
LOCAL = LocalKeySigner(KEY, rpc=None)
REACTOR = orders.REACTOR
ALLOW = parse_allowlist(f"PcsXRfq:{REACTOR}")


def rfq_typed(min_out=42_000_000_000_000_000, permitted=10 * E18):
    typed = orders.pcsx(
        permitted=permitted,
        deadline=int(NOW.timestamp()) + 120,
        outputs=[{"token": TOKEN, "startAmount": str(min_out + 10**14), "endAmount": str(min_out),
                  "recipient": LOCAL.address}],
        info={"swapper": LOCAL.address, "deadline": str(int(NOW.timestamp()) + 120)},
    )
    typed["message"]["witness"]["outputs"][0]["token"] = TOKEN
    return typed


class RfqSigner(Signer):
    address = LOCAL.address
    rfq_signing_scheme = "eip712"

    def sign_typed_data(self, typed):
        self.signed = getattr(self, "signed", 0) + 1
        return LOCAL.sign_typed_data(typed)


class RfqTrading(Trading):
    live_writes = True

    def __init__(self, rfq_out="43000000000000000", swap_out="42400000000000000", typed=None,
                 status="FILLED", spender=PERMIT2, **kw):
        super().__init__(route(out=swap_out), **kw)
        self.rfq_route = NS(executionMode="RFQ", approveTarget=None, toTokenAmount=rfq_out,
                            priceImpactPercent=Decimal("0.0005"), quoteId="r1", vendorName="PcsXRfq")
        self.typed = typed or rfq_typed()
        self.status, self.spender = status, spender
        self.submissions = []

    def quote(self, request, mode):
        expires = NOW + timedelta(seconds=30)
        return [NS(route=self.route, expires_at=expires, request=request),
                NS(route=self.rfq_route, expires_at=expires, request=request)]

    def rfq_approval(self, *, token, amount, vendor):
        return NS(data="0x095ea7b3" + self.spender[2:].rjust(64, "0") + format(amount, "064x"))

    def build_rfq(self, quote, slippage_bps):
        import json as _json
        return {"executionMode": "RFQ", "rfq": {"vendor": "PcsXRfq", "typedDataToSign": _json.dumps(self.typed),
                "orderId": "o1", "signingScheme": "EIP712", "txType": "EIP712"}}

    def submit_rfq(self, submission):
        self.submissions.append(submission.wire_body())
        return "o1"

    def order_status(self, order_id):
        return NS(status=self.status, txHash="0x" + "f" * 64, fromAmount=str(10 * E18),
                  toAmount="42400000000000000"), NOW


def rfq_executor(trading, rpc, signer=None):
    p = Portfolio([action()], wallet=LOCAL.address)
    ex = LiveRebalanceExecutor(
        p, trading, rpc, signer or RfqSigner(rpc), LiveFillStore(),
        max_notional_usd=25, max_slippage_bps=100, gas_reserve_wei=2 * 10**15,
        clock=lambda: NOW, sleep=lambda _: None, rfq_allowlist=ALLOW,
    )
    return ex, p


def test_rfq_leg_verifies_signs_submits_and_settles_within_signed_bounds():
    rpc, trading = Rpc(), RfqTrading()
    ex, p = rfq_executor(trading, rpc)
    legs = ex.execute("p1")
    leg = legs[0]
    assert leg["status"] == "CONFIRMED", leg["reasons"]
    ev = leg["evidence"]
    assert ev["route"] == "RFQ" and ev["verification"] == "SIGNED_ORDER_BOUND"
    assert ev["order"]["settlement"] == REACTOR and ev["rfq_request_id"]
    body = trading.submissions[0]
    assert body["quoteId"] == "o1" and body["vendor"] == "PcsXRfq"
    assert int(rpc.sent[0]["data"][-64:], 16) == 10 * E18  # exact approval
    assert rpc.sent[0]["data"][34:74] == PERMIT2[2:]  # to Permit2, the vendor spender
    assert p.executed
    assert ex.journal.rfq_captures()[0]["verdict"] == "ACCEPTED"


def test_swap_wins_ties_and_closed_market_never_uses_rfq():
    trading = RfqTrading(rfq_out="42400000000000000")
    legs, = [rfq_executor(trading, Rpc())[0].execute("p1")]
    assert legs[0]["evidence"]["route"] == "SWAP" and not trading.submissions
    trading = RfqTrading()
    p = Portfolio([action(state="offhours", notional="10")], wallet=LOCAL.address)
    ex = LiveRebalanceExecutor(p, trading, Rpc(), RfqSigner(Rpc()), LiveFillStore(),
        max_notional_usd=25, max_slippage_bps=100, gas_reserve_wei=0, clock=lambda: NOW,
        sleep=lambda _: None, rfq_allowlist=ALLOW)
    assert ex.execute("p1")[0]["evidence"]["route"] == "SWAP" and not trading.submissions


def test_rejected_order_is_captured_and_never_signed_or_submitted():
    rpc, signer = Rpc(), None
    trading = RfqTrading(typed=rfq_typed(min_out=1))
    ex, _ = rfq_executor(trading, rpc)
    signer = ex.signer
    leg = ex.execute("p1")[0]
    assert leg["status"] == "REJECTED" and leg["reasons"] == ["RFQ_MIN_OUTPUT_BELOW_PLAN_MINIMUM"]
    assert not trading.submissions and not getattr(signer, "signed", 0)
    capture = ex.journal.rfq_captures()[0]
    assert capture["verdict"] == "REJECTED" and capture["vendor"] == "PcsXRfq"


def test_approval_spender_mismatch_refuses_before_any_transaction():
    rpc = Rpc()
    ex, _ = rfq_executor(RfqTrading(spender="0x" + "9" * 40), rpc)
    leg = ex.execute("p1")[0]
    assert leg["reasons"] == ["RFQ_APPROVAL_SPENDER_MISMATCH"] and not rpc.sent


def test_expired_order_is_not_filled_and_revokes_allowance():
    rpc = Rpc()
    ex, p = rfq_executor(RfqTrading(status="EXPIRED"), rpc)
    leg = ex.execute("p1")[0]
    assert leg["status"] == "NOT_FILLED" and leg["reasons"] == ["RFQ_EXPIRED"]
    assert int(rpc.sent[-1]["data"][-64:], 16) == 0 and not p.executed


def test_fill_outside_signed_bounds_requires_reconciliation():
    rpc = Rpc()
    rpc.receipt_delta = 1  # vendor delivered almost nothing
    original = rpc.receipt

    def short(tx_hash):
        result = original(tx_hash)
        if not tx_hash.endswith("01"):
            rpc.balances[TOKEN] -= 42_399_999_999_999_999
        return result

    rpc.receipt = short
    ex, p = rfq_executor(RfqTrading(), rpc)
    leg = ex.execute("p1")[0]
    assert leg["status"] == "RECONCILIATION_REQUIRED" and not p.executed


def test_crash_after_signing_resubmits_same_request_never_resigns():
    rpc, trading = Rpc(), RfqTrading()
    ex, p = rfq_executor(trading, rpc)
    trading.submit_rfq = lambda s: (_ for _ in ()).throw(ProviderErrorStub())
    leg = ex.execute("p1")[0]
    assert leg["status"] == "SIGNED" or leg["evidence"].get("rfq_request_id")
    request_id = leg["evidence"]["rfq_request_id"]
    signed = ex.signer.signed
    trading.submit_rfq = RfqTrading.submit_rfq.__get__(trading)
    p.plan.status = "REBALANCE_REQUIRED"
    leg = ex.execute("p1")[0]
    assert trading.submissions[0]["requestId"] == request_id
    assert ex.signer.signed == signed and leg["status"] == "CONFIRMED"


from app.clients.common import ProviderError  # noqa: E402


class ProviderErrorStub(ProviderError):
    def __init__(self):
        super().__init__("BINANCE_SAFETY", "TRANSPORT_UNAVAILABLE")


def test_altana_signs_typed_data_through_sidecar():
    import httpx

    from app.services.live_signer import AltanaSigner

    def handler(request):
        if request.url.path == "/altana/sign-typed-data":
            assert request.headers.get("x-sidecar-token") == "t" * 20
            return httpx.Response(200, json={"signature": "0x" + "ab" * 98})
        return httpx.Response(404, json={})

    signer = AltanaSigner(
        "http://127.0.0.1:8787", SecretStr("t" * 20),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert signer.rfq_signing_scheme == "eip1271"
    assert signer.sign_typed_data({"domain": {"chainId": 56}}) == "0x" + "ab" * 98


def test_local_key_typed_signature_recovers_to_wallet():
    from eth_account import Account
    from eth_account.messages import encode_typed_data

    from app.services.rfq_orders import order_hash

    typed = rfq_typed()
    signature = LOCAL.sign_typed_data(typed)
    _, full = order_hash(typed)
    assert Account.recover_message(encode_typed_data(full_message=full), signature=signature).lower() == LOCAL.address


def test_resubmit_failure_leaves_leg_signed_without_raising():
    rpc, trading = Rpc(), RfqTrading()
    ex, p = rfq_executor(trading, rpc)
    trading.submit_rfq = lambda s: (_ for _ in ()).throw(ProviderErrorStub())
    ex.execute("p1")
    p.plan.status = "REBALANCE_REQUIRED"
    leg = ex.execute("p1")[0]  # resubmit fails again: no exception, still SIGNED
    assert leg["status"] == "SIGNED" and leg["reasons"] == ["TRANSPORT_UNAVAILABLE"]


def test_signing_scheme_mismatch_is_refused_before_submit():
    trading = RfqTrading()
    original = trading.build_rfq

    def ethsign(quote, slippage_bps):
        raw = original(quote, slippage_bps)
        raw["rfq"]["signingScheme"] = "ethsign"
        return raw

    trading.build_rfq = ethsign
    leg = rfq_executor(trading, Rpc())[0].execute("p1")[0]
    assert leg["reasons"] == ["RFQ_SIGNING_SCHEME_MISMATCH"] and not trading.submissions


def test_retire_refuses_in_flight_legs_and_releases_terminal_ones():
    from fastapi import HTTPException

    from app.api.live import retire

    journal = LiveFillStore()
    retired = []
    portfolio = NS(retire=lambda pid: retired.append(pid) or NS(status="RETIRED"))
    request = NS(query_params={}, app=NS(state=NS(live=NS(journal=journal), portfolio=portfolio)))
    journal.upsert("a1", plan_id="p1", asset="NVDA", side="BUY", status="SUBMITTED", notional_usd="1")
    with pytest.raises(HTTPException) as caught:
        retire("p1", request)
    assert caught.value.status_code == 409 and not retired
    journal.upsert("a1", status="NOT_FILLED")
    assert retire("p1", request)["plan_status"] == "RETIRED" and retired == ["p1"]


def test_planning_capture_is_bounded_per_vendor_and_pair():
    from app.services.live_portfolio_source import LiveLimits, LivePortfolioSource

    captured = []
    trading = RfqTrading()
    source = LivePortfolioSource(
        rwa=None, trading=trading, market=None, equity=None, rpc=None, wallet=WALLET,
        limits=LiveLimits(max_notional_usd=25, max_slippage_bps=100),
        capture_rfq=lambda raw, verdict: captured.append(verdict),
    )
    request = NS(fromTokenAddress=USDT, toTokenAddress=TOKEN)
    quotes = [NS(route=trading.rfq_route, request=request)]
    source._capture_rfq_payloads(quotes)
    source._capture_rfq_payloads(quotes)
    assert captured == ["PLANNING_CAPTURE"]
