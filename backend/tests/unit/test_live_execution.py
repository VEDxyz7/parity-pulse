"""Audit regression probes using isolated SQLite and mock signers/RPC only."""

import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.clients.bsc_rpc import BscRpcClient
from app.models.execution import ExecutionSimulation, QuoteRequest, fingerprint
from app.models.live import ExecutionConsent, PublicFill
from app.repositories.live_fills import LiveFillStore
from app.services.execution_builders import ExecutionRouteBuilder
from app.services.execution_gates import LIVE_GATES, LiveExecutionError
from app.services.live_execution import LiveRebalanceExecutor, validate_swap_effects
from app.services.live_signer import LocalKeySigner
from backend.tests.fixtures.execution_fixtures import (
    BUY,
    NOW,
    SELL,
    SPENDER,
    WALLET,
    allowance,
    build,
    mutate,
    quote,
)
from backend.tests.unit.test_live_settlement import HASH, rpc_fixture


@pytest.fixture(autouse=True)
def no_outbound_network(monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("Offline test attempted outbound network")

    monkeypatch.setattr(socket.socket, "connect", denied)


class OfflinePolicy:
    """Test double, not configurable through settings/HTTP or production wiring."""

    def require(self, _route, *, wallet=False):
        pass


def claimed(store, action="action"):
    return store.claim(
        action,
        wallet=WALLET,
        intent_digest="a" * 64,
        plan_id="plan",
        asset="NVDA",
        side="BUY",
        token=BUY,
        notional_usd="10",
        signer="MOCK",
    )


def executor(journal, rpc=None, signer=None):
    return LiveRebalanceExecutor(
        SimpleNamespace(inventory="WALLET", mode="LIVE_READ_ONLY"),
        SimpleNamespace(),
        rpc,
        signer or SimpleNamespace(kind="LOCAL_KEY", address=WALLET),
        journal,
        max_notional_usd="25",
        max_slippage_bps="100",
        gas_reserve_wei=0,
        clock=lambda: NOW,
        gates=OfflinePolicy(),
    )


def route_and_sim(changes=None):
    request = QuoteRequest(
        binanceChainId="56",
        amount="10000000",
        fromTokenAddress=SELL,
        toTokenAddress=BUY,
        userWalletAddress=WALLET,
    )
    q = mutate(quote(request), data_mode="LIVE_READ_ONLY", source="BINANCE_WEB3")
    a = mutate(allowance(amount=request.amount), data_mode="LIVE_READ_ONLY", source="BSC_RPC")
    b = build(q)
    route = ExecutionRouteBuilder().build(
        q, b, slippage_bps=__import__("decimal").Decimal(50), allowance=a, now=NOW
    )
    response = {
        "status": "SUCCESS",
        "balanceChanges": changes
        if changes is not None
        else [
            {"contractAddress": SELL, "tokenType": "ERC20", "owner": WALLET, "change": "-10000000"},
            {"contractAddress": BUY, "tokenType": "ERC20", "owner": WALLET, "change": "398000"},
        ],
        "allowanceChanges": [],
    }
    from app.models.execution import SimulationResponse

    sim = ExecutionSimulation(
        fingerprint=route.fingerprint,
        payload_digest=fingerprint({"binanceChainId": "56", "evmTx": b.tx.evm_payload()}),
        data_mode="LIVE_READ_ONLY",
        source="BINANCE_WEB3",
        evaluated_at=NOW,
        status="PASS",
        response=SimulationResponse(**response),
        reason_codes=(),
        coverage="EVM_FROM_TO_VALUE_DATA_ONLY",
    )
    return route, sim


def test_bounded_swap_effects_are_required():
    route, sim = route_and_sim()
    assert validate_swap_effects(route, sim, now=NOW) == (10000000, 398000)
    assert not sim.live_equivalence_verified


@pytest.mark.parametrize(
    "defect",
    [
        "empty",
        "zero",
        "overspend",
        "other_debit",
        "wrong_token",
        "changed_gas",
        "expired",
        "duplicate",
    ],
)
def test_simulation_original_failure_cases_rejected(defect):
    route, sim = route_and_sim()
    if defect == "empty":
        sim = mutate(sim, response=mutate(sim.response, balanceChanges=()))
    elif defect in {"zero", "overspend", "other_debit", "wrong_token", "duplicate"}:
        changes = list(sim.response.balanceChanges)
        if defect == "zero":
            changes[1] = mutate(changes[1], change="0")
        elif defect == "overspend":
            changes[0] = mutate(changes[0], change="-20000000")
        elif defect == "other_debit":
            changes.append(mutate(changes[0], contractAddress=SPENDER))
        elif defect == "wrong_token":
            changes[1] = mutate(changes[1], contractAddress=SPENDER)
        else:
            changes.append(changes[0])
        sim = mutate(sim, response=mutate(sim.response, balanceChanges=tuple(changes)))
    elif defect == "changed_gas":
        route = route.model_copy(
            update={"build": mutate(route.build, tx=mutate(route.build.tx, gas="200001"))}
        )
    with pytest.raises((LiveExecutionError, ValueError)):
        validate_swap_effects(
            route, sim, now=NOW + timedelta(seconds=31) if defect == "expired" else NOW
        )


def test_atomic_claim_across_connections_and_wallet_nonce_stream(tmp_path):
    path = tmp_path / "fills.sqlite"
    stores = [LiveFillStore(path), LiveFillStore(path)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claimed, stores))
    assert sum(owner is not None for _, owner in results) == 1
    with pytest.raises(ValueError, match="WALLET_EXECUTION_UNRESOLVED"):
        claimed(stores[1], "different_action")
    with pytest.raises(ValueError, match="ACTION_IDENTITY_CONFLICT"):
        stores[0].claim("action", wallet=WALLET, intent_digest="b" * 64)
    for store in stores:
        store.close()


def test_no_insert_replace_and_crash_after_claim_never_resubmits(tmp_path):
    path = tmp_path / "fills.sqlite"
    store = LiveFillStore(path)
    claimed(store)
    store.close()
    restarted = LiveFillStore(path)
    assert claimed(restarted)[1] is None
    record = executor(restarted).reconcile("action")
    assert record["status"] == "RECONCILIATION_REQUIRED"
    assert restarted.unresolved("plan")
    with pytest.raises(ValueError, match="ATOMIC"):
        restarted.upsert("unclaimed", status="CONFIRMED")
    restarted.close()


def test_accepted_broadcast_lost_response_persists_hash_nonce_unknown(tmp_path):
    store = LiveFillStore(tmp_path / "fills.sqlite")
    claimed(store)
    calls = []
    route, _ = route_and_sim()
    store.upsert("action", status="QUOTED")
    prepared = SimpleNamespace(tx_hash=HASH, nonce=7, payload_digest=fingerprint(route.build.tx))

    def lost_response(*_args, **_kwargs):
        assert store.submission("action", "SWAP")["identity"] == HASH
        calls.append("accepted")
        raise TimeoutError("response lost")

    signer = SimpleNamespace(
        kind="LOCAL_KEY", address=WALLET, prepare=lambda _: prepared, broadcast=lost_response
    )
    result = executor(store, signer=signer)._broadcast("action", route.build.tx)
    assert calls == ["accepted"] and result["status"] == "SUBMISSION_UNKNOWN"
    assert result["swap_tx"] == HASH and store.submission("action", "SWAP")["nonce"] == 7
    with pytest.raises(ValueError, match="RECONCILIATION"):
        store.upsert("action", status="REJECTED")
    store.close()
    restarted = LiveFillStore(tmp_path / "fills.sqlite")
    assert claimed(restarted)[1] is None
    assert restarted.unresolved()
    restarted.close()


def test_receipt_only_recovery_fails_then_complete_evidence_recovers():
    store = LiveFillStore()
    claimed(store)
    rpc, receipt, _, _, expected = rpc_fixture()
    store.upsert("action", status="QUOTED", evidence={"route": "SWAP", **expected})
    store.begin_submission("action", kind="SWAP", identity=HASH, nonce=7, payload_digest="a" * 64)
    store.upsert("action", status="SUBMITTED", swap_tx=HASH)
    logs = receipt["logs"]
    receipt["logs"] = []
    worker = executor(store, rpc)
    assert worker.reconcile("action")["status"] == "RECONCILIATION_REQUIRED"
    receipt["logs"] = logs
    assert worker.reconcile("action")["status"] == "CONFIRMED"
    assert not store.unresolved()


@pytest.mark.parametrize("status", ["FAILED", "EXPIRED", "CANCELLED", "PENDING_ONCHAIN"])
def test_provider_nonfill_status_never_releases_wallet(status):
    store = LiveFillStore()
    claimed(store)
    store.upsert(
        "action",
        status="SIGNED",
        evidence={
            "route": "RFQ",
            "rfq_status_order_id": "platform-order",
        },
    )
    store.begin_submission(
        "action", kind="RFQ", identity="request-1", nonce=None, payload_digest="a" * 64
    )
    store.upsert("action", status="SUBMITTED")
    worker = executor(store)
    worker.trading = SimpleNamespace(order_status=lambda _: (SimpleNamespace(status=status), NOW))
    assert worker.reconcile("action")["status"] == "RECONCILIATION_REQUIRED"
    assert store.unresolved("plan")


def test_consent_exact_fingerprint_expiry_and_single_use():
    store = LiveFillStore()
    consent = ExecutionConsent(
        action_id="action",
        confirmation_id="consent1",
        payload_digest="a" * 64,
        confirmed_at=NOW,
        expires_at=NOW + timedelta(seconds=20),
        source="HOST_EXPLICIT_USER_CONFIRMATION",
    )
    store.confirm(consent, now=NOW)
    with pytest.raises(ValueError, match="STALE"):
        store.consume_consent(consent, payload_digest="b" * 64, now=NOW)
    store.consume_consent(consent, payload_digest="a" * 64, now=NOW)
    with pytest.raises(ValueError, match="CONSUMED"):
        store.consume_consent(consent, payload_digest="a" * 64, now=NOW)
    with pytest.raises(ValueError, match="STALE"):
        store.consume_consent(consent, payload_digest="a" * 64, now=NOW + timedelta(seconds=21))


def test_public_positive_schema_excludes_legacy_sentinel_signatures():
    store = LiveFillStore()
    record, _ = claimed(store)
    record["evidence"] = {
        "rfq_signature": "SYNTHETIC_SIGNATURE_SENTINEL",
        "nested": {"private_key": "SYNTHETIC_SECRET_SENTINEL"},
    }
    text = PublicFill.from_record(record).model_dump_json()
    assert "SENTINEL" not in text and "evidence" not in text


@pytest.mark.parametrize("gate", ["SWAP", "RFQ"])
def test_all_production_gates_block_even_direct_internal_calls(gate):
    with pytest.raises(LiveExecutionError, match=gate + "_LIVE_GATE_BLOCKED"):
        LIVE_GATES.require(gate, wallet=True)


def test_raw_rpc_and_signer_cannot_bypass_gate():
    rpc = BscRpcClient(allow_send=True)
    with pytest.raises(LiveExecutionError, match="SWAP_LIVE_GATE_BLOCKED"):
        rpc._rpc("eth_sendRawTransaction", ["0xab"])
    rpc.close()
    signer = LocalKeySigner(SecretStr("0x" + "1" * 64), SimpleNamespace())
    with pytest.raises(LiveExecutionError, match="SWAP_LIVE_GATE_BLOCKED"):
        signer.send(to=SPENDER, data="0x1234", value=0, gas=1, gas_price=1)


def test_local_signer_durable_identity_matches_broadcast():
    sends = []
    rpc = SimpleNamespace(chain_id=lambda: 56, nonce=lambda _: 7)
    rpc.send_raw_transaction = lambda raw: (
        sends.append(raw) or "0x" + __import__("eth_utils").keccak(bytes.fromhex(raw[2:])).hex()
    )
    signer = LocalKeySigner(SecretStr("0x" + "1" * 64), rpc, gates=OfflinePolicy())
    route, _ = route_and_sim()
    tx = mutate(route.build.tx, sender=signer.address)
    prepared = signer.prepare(tx)
    store = LiveFillStore()
    claimed(store)
    with pytest.raises(LiveExecutionError, match="DURABLE_SIGNED"):
        signer.broadcast(prepared, journal=store, action_id="action", kind="SWAP")
    store.upsert("action", status="QUOTED")
    store.begin_submission(
        "action",
        kind="SWAP",
        identity=prepared.tx_hash,
        nonce=prepared.nonce,
        payload_digest=prepared.payload_digest,
    )
    assert (
        signer.broadcast(prepared, journal=store, action_id="action", kind="SWAP")
        == prepared.tx_hash
    )
    assert len(sends) == 1 and "raw" not in repr(prepared)


def test_two_executor_instances_claim_before_any_submission(tmp_path):
    from app.services.live_execution import PreparedLeg

    path = tmp_path / "concurrent.sqlite"
    stores = [LiveFillStore(path), LiveFillStore(path)]
    workers = [executor(store) for store in stores]
    route, sim = route_and_sim()
    q = quote(route.quote.request, execution_mode="RFQ")
    leg = PreparedLeg("action", SimpleNamespace(quote=q, fingerprint="a" * 64), sim, "b" * 64, 1)
    consent = ExecutionConsent(
        action_id="action",
        payload_digest=leg.digest,
        confirmation_id="concurrent",
        confirmed_at=NOW,
        expires_at=NOW + timedelta(seconds=20),
        source="HOST_EXPLICIT_USER_CONFIRMATION",
    )
    stores[0].confirm(consent, now=NOW)
    action = SimpleNamespace(
        action_id="action",
        asset="NVDA",
        side="BUY",
        notional_usd="10",
        route=SimpleNamespace(selected_representation=SimpleNamespace(contract=BUY)),
    )
    plan = SimpleNamespace(plan_id="plan")
    submissions = []
    for worker in workers:
        # Isolate claim behavior; these test doubles are not source/risk admission.
        worker._risk = lambda *_: SimpleNamespace(evidence_digest=leg.risk_digest)
        worker.rpc = SimpleNamespace(
            chain_id=lambda: 56,
            allowance=lambda *_: int(q.request.amount),
            erc20_balance=lambda *_: int(q.request.amount),
        )

        def submit(_action, _leg, worker=worker):
            worker.journal.upsert("action", status="SIGNED")
            worker.journal.begin_submission(
                "action", kind="RFQ", identity="request-1", nonce=None, payload_digest=leg.digest
            )
            submissions.append("mock_submit")
            return worker.journal.upsert("action", status="SUBMITTED")

        worker._submit_rfq = submit
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda w: w._leg(plan, action, leg, consent), workers))
    assert len(submissions) == 1
    assert all(r["status"] in {"PREPARING", "SIGNED", "SUBMITTING", "SUBMITTED"} for r in results)
    assert workers[1]._leg(plan, action, leg, consent)["status"] == "SUBMITTED"
    assert len(submissions) == 1
    for store in stores:
        store.close()


def test_crash_after_durable_identity_before_presentation_update_recovers(tmp_path):
    path = tmp_path / "crash.sqlite"
    store = LiveFillStore(path)
    claimed(store)
    rpc, _, _, _, expected = rpc_fixture()
    store.upsert("action", status="QUOTED", evidence={"route": "SWAP", **expected})
    store.begin_submission("action", kind="SWAP", identity=HASH, nonce=7, payload_digest="a" * 64)
    store.close()  # Crash before swap_tx assignment/response: persisted hash remains usable.
    recovered = LiveFillStore(path)
    assert executor(recovered, rpc).reconcile("action")["status"] == "CONFIRMED"
    assert recovered.get("action")["swap_tx"] == HASH
    recovered.close()


def test_canonical_settlement_reorg_relocks_wallet():
    store = LiveFillStore()
    claimed(store)
    rpc, _, _, _, expected = rpc_fixture()
    store.upsert("action", status="QUOTED", evidence={"route": "SWAP", **expected})
    store.begin_submission("action", kind="SWAP", identity=HASH, nonce=7, payload_digest="a" * 64)
    worker = executor(store, rpc)
    assert worker.reconcile("action")["status"] == "CONFIRMED"
    assert worker.reconcile("action")["status"] == "CONFIRMED"
    rpc.read = lambda *_: {"hash": "0x" + "f" * 64}
    assert worker.reconcile("action")["status"] == "RECONCILIATION_REQUIRED"
    assert store.unresolved("plan")
    with pytest.raises(ValueError, match="UNRESOLVED"):
        claimed(store, "another")


def test_invalid_transitions_cannot_restart_an_unknown_submission():
    store = LiveFillStore()
    claimed(store)
    store.upsert("action", status="QUOTED")
    store.begin_submission("action", kind="SWAP", identity=HASH, nonce=7, payload_digest="a" * 64)
    store.upsert("action", status="SUBMISSION_UNKNOWN")
    for status in ("PREPARING", "QUOTED", "SIGNED", "NOT_FILLED"):
        with pytest.raises(ValueError, match="TRANSITION"):
            store.upsert("action", status=status)
    with pytest.raises(ValueError, match="STATE_INVALID"):
        store.begin_submission(
            "action", kind="SWAP", identity=HASH, nonce=7, payload_digest="a" * 64
        )


def test_execution_risk_revalidates_expired_evidence_and_production_admission():
    from app.services.risk import RiskEngine
    from backend.tests.fixtures.execution_fixtures import evidence

    e = evidence()
    risk = RiskEngine()
    assert risk.evaluate_execution(e, now=NOW).status == "PASS"
    stale = risk.evaluate_execution(e, now=NOW + timedelta(seconds=121))
    assert stale.status == "FAIL"
    assert any(c.code == "DATA_FRESHNESS" and not c.passed for c in stale.checks)
    live = mutate(
        e, data_mode="LIVE_READ_ONLY", context=mutate(e.context, data_mode="LIVE_READ_ONLY")
    )
    admitted = risk.evaluate_execution(live, now=NOW)
    assert admitted.status == "FAIL"
    assert any(c.code == "PRODUCTION_TRUST_GATE" and not c.passed for c in admitted.checks)
    with pytest.raises(LiveExecutionError, match="PLAN_TOO_OLD"):
        executor(LiveFillStore())._risk(
            SimpleNamespace(created_at=NOW - timedelta(seconds=121)), None
        )


@pytest.mark.parametrize("value", [None, "0x", "0x0", [], "0x" + "f" * 66])
def test_missing_erc20_rpc_evidence_never_becomes_zero(value):
    from app.clients.common import ProviderError

    rpc = BscRpcClient()
    rpc.read = lambda *_: value
    try:
        with pytest.raises(ProviderError, match="ERC20_RESULT_MISSING_OR_INVALID"):
            rpc.erc20_balance(SELL, WALLET)
        with pytest.raises(ProviderError, match="ERC20_RESULT_MISSING_OR_INVALID"):
            rpc.allowance(SELL, WALLET, SPENDER)
    finally:
        rpc.close()


@pytest.mark.parametrize("outcome", ["timeout", "unavailable", "success", "echo"])
def test_rfq_transport_one_attempt_no_signature_cache_or_echo(monkeypatch, outcome):
    import base64
    import hashlib
    import hmac
    import json
    from uuid import uuid4

    import httpx

    from app.clients.binance_trading import LiveTradingClient
    from app.clients.common import ProviderError
    from app.models.execution import RFQSubmission
    from app.services import execution_gates

    monkeypatch.setattr(execution_gates, "LIVE_GATES", OfflinePolicy())
    submission = RFQSubmission(
        requestId=uuid4(),
        userSignature=SecretStr("0x" + "ab" * 65),
        vendor="CowSwap",
        quoteId="synthetic-order",
        signingScheme="EIP712",
    )
    sends = []

    def respond(request):
        sends.append(request)
        timestamp = request.headers["X-OC-TIMESTAMP"]
        msg = (timestamp + "POST" + request.url.raw_path.decode()).encode() + request.content
        expected = base64.b64encode(
            hmac.new(b"synthetic-secret", msg, hashlib.sha256).digest()
        ).decode()
        assert request.headers["X-OC-SIGN"] == expected
        assert json.loads(request.content)["requestId"] == str(submission.requestId)
        if outcome == "timeout":
            raise httpx.ReadTimeout("Synthetic accepted request; response lost", request=request)
        if outcome == "unavailable":
            return httpx.Response(503)
        data = {"orderId": "platform-order"}
        if outcome == "echo":
            data["echo"] = submission.userSignature.get_secret_value()
        return httpx.Response(
            200,
            json={
                "code": 0,
                "success": True,
                "msg": "",
                "timestamp": int(NOW.timestamp() * 1000),
                "data": data,
            },
        )

    client = LiveTradingClient(
        SecretStr("synthetic-key"),
        SecretStr("synthetic-secret"),
        http=httpx.Client(transport=httpx.MockTransport(respond)),
        attempts=3,
        min_interval=0,
    )
    try:
        if outcome == "success":
            assert client.submit_rfq(submission) == "platform-order"
        else:
            with pytest.raises(ProviderError):
                client.submit_rfq(submission)
        assert len(sends) == 1 and not client.cache
        assert submission.userSignature.get_secret_value() not in json.dumps(client.evidence)
    finally:
        client.close()


def test_wallet_gate_and_route_gates_remain_independent(monkeypatch):
    from app.services.execution_gates import LiveGatePolicy

    policy = LiveGatePolicy()
    statuses = policy.statuses()
    statuses["SWAP_LIVE_GATE"] = "PASS"  # local test instance only, never global settings
    monkeypatch.setattr(policy, "statuses", lambda: statuses)
    policy.require("SWAP")
    with pytest.raises(LiveExecutionError, match="AGENTIC_WALLET_LIVE_GATE_BLOCKED"):
        policy.require("SWAP", wallet=True)
    with pytest.raises(LiveExecutionError, match="RFQ_LIVE_GATE_BLOCKED"):
        policy.require("RFQ")
    assert LIVE_GATES.statuses()["SWAP_LIVE_GATE"] == "BLOCKED"
