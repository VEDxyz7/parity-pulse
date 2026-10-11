"""Non-capital checks against retained interfaces, not proof of live readiness.

Missing live capabilities remain blockers in AGENTIC_READINESS_TEST_RECONCILIATION.md.
No production gates, network, real CLI, signing or transport are enabled here.
"""

import importlib.util
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.clients.baw_cli import WalletReadError, command, verify_argv
from app.clients.baw_preview import BawPreviewClient, preview_command, verify_preview_argv
from app.clients.bsc_rpc import BscRpcClient
from app.clients.common import ProviderError
from app.config import Settings
from app.models.execution_envelope import BoundSwapEnvelope
from app.models.live import ExecutionConsent
from app.repositories.live_fills import LiveFillStore
from app.services.agentic_wallet import AgenticWalletAdapter, WalletSafetyChecks
from app.services.agentic_wallet_signer import AgenticWalletSigner, validate_preview
from app.services.execution_authorization import (
    RuntimeExecutionPolicy,
    require_write,
    wallet_gate_required,
)
from app.services.execution_builders import ApprovalService, ExecutionRouteBuilder, current_quote
from app.services.execution_gates import LIVE_GATES, LiveExecutionError
from app.services.funding import FundingService
from app.services.live_execution import LiveRebalanceExecutor, validate_swap_effects
from app.services.live_settlement import verify_swap
from app.services.live_wiring import LiveRuntime
from backend.tests.fixtures.execution_fixtures import (
    NOW,
    SPENDER,
    WALLET,
    approval_response,
    funding,
    mutate,
)
from backend.tests.fixtures.wallet_fixtures import WalletWire
from backend.tests.unit.test_execution_safety import prepared
from backend.tests.unit.test_live_execution import claimed, route_and_sim
from backend.tests.unit.test_live_settlement import HASH, rpc_fixture
from backend.tests.unit.test_wallet_signer_remediation import preview


@pytest.fixture(autouse=True)
def no_network_or_signing(monkeypatch):
    import socket
    import subprocess

    from eth_account import Account

    def denied(*args, **kwargs):
        raise AssertionError("Readiness regression attempted network, CLI or signing")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)
    monkeypatch.setattr(Account, "sign_transaction", denied)
    monkeypatch.setattr(Account, "sign_typed_data", denied)


def worker(store, rpc=None, signer=None):
    """Real worker and production gates; dependencies have no write implementations."""
    return LiveRebalanceExecutor(
        SimpleNamespace(inventory="WALLET", mode="LIVE_READ_ONLY"),
        None,
        rpc,
        signer or SimpleNamespace(kind="AGENTIC_WALLET", address=WALLET),
        store,
        max_notional_usd="25",
        max_slippage_bps="100",
        gas_reserve_wei=0,
        clock=lambda: NOW,
    )


def consent():
    return ExecutionConsent(
        action_id="action",
        confirmation_id="readiness-consent",
        payload_digest="a" * 64,
        confirmed_at=NOW,
        expires_at=NOW + timedelta(seconds=20),
        source="HOST_EXPLICIT_USER_CONFIRMATION",
    )


def test_settlement_rejects_output_below_journaled_minimum():
    rpc, _, _, _, expected = rpc_fixture()
    expected["minimum_out"] = str(int(expected["minimum_out"]) + 1)
    with pytest.raises(LiveExecutionError, match="SETTLEMENT_MIN_OUTPUT_VIOLATED"):
        verify_swap(rpc, HASH, expected)


def test_settlement_enforces_prepared_minimum_even_if_plan_is_weaker():
    # Preserve the original security expectation. Current verification must not
    # confirm a fill that satisfies only the weaker plan/journal minimum.
    rpc, _, _, _, expected = rpc_fixture()
    expected["transaction"]["minReceiveAmount"] = str(int(expected["minimum_out"]) + 1)
    with pytest.raises(LiveExecutionError, match="MIN_OUTPUT"):
        verify_swap(rpc, HASH, expected)


def test_settlement_rejects_changed_journaled_nonce():
    rpc, _, transaction, _, expected = rpc_fixture()
    transaction["nonce"] = "0x7"
    expected["nonce"] = 8
    expected["transaction"]["minReceiveAmount"] = expected["minimum_out"]
    with pytest.raises(LiveExecutionError, match="NONCE"):
        verify_swap(rpc, HASH, expected)


def test_settlement_requires_exact_prepared_minimum():
    rpc, _, _, _, expected = rpc_fixture()
    # The incoming test's requirement is still valid; the fixture now explicitly
    # distinguishes the required prepared field from the weaker journal minimum.
    del expected["transaction"]["minReceiveAmount"]
    assert "minReceiveAmount" not in expected["transaction"]
    with pytest.raises(LiveExecutionError, match="PREPARED_MIN"):
        verify_swap(rpc, HASH, expected)


def test_simulation_rejects_output_below_exact_prepared_minimum():
    route, sim = route_and_sim()
    changes = list(sim.response.balanceChanges)
    changes[1] = mutate(changes[1], change=str(int(route.build.tx.minReceiveAmount) - 1))
    sim = mutate(sim, response=mutate(sim.response, balanceChanges=tuple(changes)))
    with pytest.raises(LiveExecutionError, match="SIMULATION_MIN_OUTPUT_VIOLATED"):
        validate_swap_effects(route, sim, now=NOW)


def test_missing_journaled_minimum_fails_closed():
    rpc, _, _, _, expected = rpc_fixture()
    del expected["minimum_out"]
    with pytest.raises(LiveExecutionError, match="MALFORMED_SETTLEMENT_EVIDENCE"):
        verify_swap(rpc, HASH, expected)


@pytest.mark.parametrize(
    "field,value",
    [
        ("execution_mode", "LIVE"),
        ("live_trading_enabled", True),
        ("require_simulation", False),
        ("approval_mode", "AUTONOMOUS"),
    ],
)
def test_public_configuration_cannot_enable_execution(field, value):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **{field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("execution_mode", "DRY_RUN"),
        ("live_trading_enabled", False),
        ("require_simulation", False),
        ("approval_mode", "AUTONOMOUS"),
        ("data_mode", "DEMO"),
    ],
)
def test_standalone_runtime_policy_checks_each_control(field, value):
    # This pure policy is not yet wired into the retained live transports.
    nominal = RuntimeExecutionPolicy(execution_mode="LIVE", live_trading_enabled=True)
    with pytest.raises(LiveExecutionError, match="LIVE_RUNTIME_DISABLED"):
        replace(nominal, **{field: value}).require()


@pytest.mark.parametrize("route", ["SWAP", "RFQ"])
def test_nominal_standalone_runtime_cannot_override_production_gates(route):
    nominal = RuntimeExecutionPolicy(execution_mode="LIVE", live_trading_enabled=True)
    with pytest.raises(LiveExecutionError, match=route + "_LIVE_GATE_BLOCKED"):
        require_write(LIVE_GATES, nominal, route, wallet=True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("nonce", 8),
        ("recipient", SPENDER),
        ("spender", "0x" + "6" * 40),
        ("amount_in", "1"),
        ("minimum_out", "1"),
        ("chain_id", 1),
    ],
)
def test_envelope_rejects_changed_intent_fields(field, value):
    route, _ = route_and_sim()
    envelope = BoundSwapEnvelope.bind(route, nonce=7).model_copy(update={field: value})
    with pytest.raises((LiveExecutionError, ValueError)):
        envelope.matches(route, route.build.tx, nonce=7)


@pytest.mark.parametrize(
    "field,value",
    [
        ("to", "0x" + "6" * 40),
        ("data", "0x5678"),
        ("value", "1"),
        ("gas", "200001"),
        ("gasPrice", "2"),
        ("sender", SPENDER),
    ],
)
def test_envelope_rejects_changed_transaction_fields(field, value):
    route, _ = route_and_sim()
    envelope = BoundSwapEnvelope.bind(route, nonce=7)
    with pytest.raises(LiveExecutionError, match="ENVELOPE_CHANGED"):
        envelope.matches(route, mutate(route.build.tx, **{field: value}), nonce=7)


def test_provider_success_and_structural_binding_are_not_execution_equivalence():
    route, sim = route_and_sim()
    envelope = BoundSwapEnvelope.bind(route, nonce=7)
    envelope.matches(route, route.build.tx, nonce=7)
    assert validate_swap_effects(route, sim, now=NOW) == (10000000, 398000)
    assert sim.live_equivalence_verified is False
    with pytest.raises(ValueError):
        BoundSwapEnvelope.model_validate(
            {**envelope.model_dump(), "calldata_semantics_verified": True}
        )
    with pytest.raises(LiveExecutionError, match="SWAP_LIVE_GATE_BLOCKED"):
        LIVE_GATES.require("SWAP", wallet=True)


@pytest.mark.parametrize("seconds", [30, 31])
def test_expired_quote_cannot_be_prepared(seconds):
    route, _ = route_and_sim()
    now = NOW + timedelta(seconds=seconds)
    with pytest.raises(ValueError, match="QUOTE_EXPIRED"):
        current_quote(route.quote, now)
    with pytest.raises(ValueError, match="QUOTE_EXPIRED"):
        ExecutionRouteBuilder().build(
            route.quote,
            route.build,
            slippage_bps=route.slippage_bps,
            allowance=route.allowance,
            now=now,
        )


@pytest.mark.parametrize("seconds", [20, 21, 31])
def test_expired_consent_cannot_be_recorded_or_consumed(seconds):
    store = LiveFillStore()
    try:
        c = consent()
        store.confirm(c, now=NOW)
        late = NOW + timedelta(seconds=seconds)
        with pytest.raises(ValueError, match="CONFIRMATION_EXPIRED"):
            store.confirm(c, now=late)
        with pytest.raises(ValueError, match="INVALID_OR_STALE"):
            store.consume_consent(c, payload_digest=c.payload_digest, now=late)
        assert store.submission("action", "SWAP") is None
    finally:
        store.close()


def test_consent_binds_digest_and_is_single_use_across_restart(tmp_path):
    path = tmp_path / "consent.sqlite"
    store = LiveFillStore(path)
    c = consent()
    store.confirm(c, now=NOW)
    with pytest.raises(ValueError, match="INVALID_OR_STALE"):
        store.consume_consent(c, payload_digest="b" * 64, now=NOW)
    store.consume_consent(c, payload_digest=c.payload_digest, now=NOW)
    store.close()
    recovered = LiveFillStore(path)
    try:
        with pytest.raises(ValueError, match="MISSING_OR_CONSUMED"):
            recovered.consume_consent(c, payload_digest=c.payload_digest, now=NOW)
    finally:
        recovered.close()


@pytest.mark.parametrize("kind", ["LOCAL_KEY", "AGENTIC_WALLET", "ALTANA"])
def test_worker_blocks_before_signer_or_submission_identity(kind):
    def denied(*args, **kwargs):
        pytest.fail("Production worker reached signer despite blocked gate")

    store = LiveFillStore()
    route, _ = route_and_sim()
    signer = SimpleNamespace(kind=kind, address=WALLET, prepare=denied, broadcast=denied)
    try:
        with pytest.raises(LiveExecutionError, match="SWAP_LIVE_GATE_BLOCKED"):
            worker(store, signer=signer)._broadcast("action", route.build.tx)
        assert store.get("action") is None and store.submission("action", "SWAP") is None
    finally:
        store.close()


def test_shared_gas_budget_and_native_reserve_checks():
    route, _ = route_and_sim()
    tx = mutate(route.build.tx, gasPrice="1000000000")
    service = FundingService()
    with pytest.raises(ValueError, match="EXCEEDS_RISK_COST"):
        service.check_gas(funding(), (tx,), costs_usd=Decimal("0.001"), now=NOW)
    assert service.check_gas(funding(), (tx,), costs_usd=Decimal("1"), now=NOW) == (
        200000000000000,
        Decimal("0.02"),
    )
    with pytest.raises(ValueError, match="INSUFFICIENT_NATIVE_GAS_AND_RESERVE"):
        service.check_gas(
            funding(native_gas_balance_wei="1000000000000000"),
            (tx,),
            costs_usd=Decimal("1"),
            now=NOW,
        )


@pytest.mark.parametrize(
    "state",
    [
        None,
        funding(native_price_observed_at=NOW - timedelta(seconds=121)),
    ],
)
def test_missing_or_stale_native_price_cannot_satisfy_gas_budget(state):
    route, _ = route_and_sim()
    with pytest.raises(ValueError, match="NATIVE_GAS_PRICE_UNAVAILABLE_OR_STALE"):
        FundingService().check_gas(state, (route.build.tx,), costs_usd=Decimal("1"), now=NOW)


@pytest.mark.parametrize("operation", ["raw", "send", "read", "estimate"])
def test_rpc_has_no_public_write_or_estimation_bypass(operation):
    calls = []
    http = httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(r)))
    rpc = BscRpcClient(http=http, allow_send=True)
    try:
        if operation in {"raw", "send"}:
            with pytest.raises(LiveExecutionError, match="SWAP_LIVE_GATE_BLOCKED"):
                if operation == "raw":
                    rpc._rpc("eth_sendRawTransaction", ["0xab"])
                else:
                    rpc.send_raw_transaction("0xab")
        else:
            method = "eth_estimateGas" if operation == "estimate" else "eth_sendRawTransaction"
            with pytest.raises(ProviderError, match="READ_ONLY_OPERATION_REQUIRED"):
                rpc.read(method, {})
        assert calls == []
    finally:
        rpc.close()


@pytest.mark.parametrize("complete", [True, False])
def test_restart_reconciliation_uses_existing_worker_without_signer(tmp_path, complete):
    path = tmp_path / "pending.sqlite"
    store = LiveFillStore(path)
    claimed(store)
    rpc, receipt, _, _, expected = rpc_fixture()
    if not complete:
        receipt["logs"] = []
    store.upsert("action", status="QUOTED", evidence={"route": "SWAP", **expected})
    store.begin_submission(
        "action", kind="SWAP", identity=HASH, nonce=7, payload_digest=expected["transaction_digest"]
    )
    store.close()
    recovered = LiveFillStore(path)
    try:
        result = worker(recovered, rpc).reconcile("action")
        assert result["status"] == ("CONFIRMED" if complete else "RECONCILIATION_REQUIRED")
        assert recovered.submission("action", "SWAP") == {
            "identity": HASH,
            "nonce": 7,
            "payload_digest": expected["transaction_digest"],
        }
        assert recovered.get("action")["swap_tx"] == HASH
        assert recovered.unresolved("plan") is (not complete)
    finally:
        recovered.close()


@pytest.mark.parametrize("route", ["SWAP", "RFQ"])
@pytest.mark.parametrize("kind", ["LOCAL_KEY", "AGENTIC_WALLET", "ALTANA"])
def test_runtime_never_attaches_worker_while_production_gates_are_blocked(route, kind):
    runtime = LiveRuntime(LiveFillStore())
    try:
        with pytest.raises(LiveExecutionError, match=route + "_LIVE_GATE_BLOCKED"):
            runtime.attach(None, None, None, SimpleNamespace(kind=kind), route=route)
        assert runtime.executor is None and runtime.prepared == {}
        status = runtime.status()
        assert status["live_execution"] is False and status["worker_attached"] is False
        assert status["execution_mode"] == "DRY_RUN"
        assert status["approval_mode"] == "PROPOSE_ONLY"
        assert status["require_simulation"] is True
    finally:
        runtime.close()


def test_wallet_policy_is_shared_and_unknown_signers_fail_closed():
    assert wallet_gate_required("LOCAL_KEY") is False
    assert wallet_gate_required("AGENTIC_WALLET") is True
    assert wallet_gate_required("ALTANA") is True
    with pytest.raises(LiveExecutionError, match="SIGNER_KIND"):
        wallet_gate_required("unverified")


def test_preview_command_is_bound_to_exact_call_and_cannot_execute():
    route, _ = route_and_sim()
    args = preview_command(route.build.tx)
    verify_preview_argv(args)
    assert args == (
        "contract-call",
        "preview",
        "--binanceChainId",
        "56",
        "--from",
        route.build.tx.sender,
        "--to",
        route.build.tx.to,
        "--value",
        route.build.tx.value,
        "--inputData",
        route.build.tx.data,
        "--json",
    )
    with pytest.raises(WalletReadError):
        verify_argv(args)
    for unsafe in (
        ("contract-call", "execute", "--requestId", "x", "--json"),
        ("auth", "signin", "--json"),
        (*args[:-1], "--nonce", "7", "--json"),
        (*args[:-1], "--gas", "200000", "--json"),
    ):
        with pytest.raises(WalletReadError, match="COMMAND_DENIED"):
            verify_preview_argv(unsafe)


def test_preview_client_requires_verified_version_without_cli_call():
    route, _ = route_and_sim()
    reader = BawPreviewClient(enabled=False)
    with pytest.raises(WalletReadError, match="CLI_VERSION_NOT_VERIFIED"):
        reader.preview(route.build.tx)


@pytest.mark.parametrize("defect", ["disconnect", "wrong_chain", "session_switch", "mode"])
def test_existing_readonly_wallet_snapshot_fails_closed(defect):
    class SessionWire(WalletWire):
        def _run(self, args):
            if defect == "session_switch" and args == command("address"):
                prior = sum(c == command("address") for c in self.calls)
                if prior:
                    self.values["address"]["addresses"][0]["address"] = SPENDER
            return super()._run(args)

    reader = SessionWire()
    if defect == "disconnect":
        reader.values["status"] = {"status": "UNCONNECTED"}
    elif defect == "wrong_chain":
        reader.values["chains"][0]["binanceChainId"] = "1"
    adapter = AgenticWalletAdapter(
        reader,
        data_mode="LIVE_READ_ONLY" if defect == "mode" else "DEMO",
        clock=lambda: NOW,
    )
    snapshot = adapter.snapshot()
    if defect == "wrong_chain":
        # Read verification is distinct from admission for chain 56.
        assert "56" not in snapshot.supported_chains and not snapshot.balances
    else:
        assert snapshot.capability_status == "UNAVAILABLE" and snapshot.errors
    service, attempt = prepared()
    try:
        result = WalletSafetyChecks().evaluate(snapshot, attempt, funding(), now=NOW)
        assert result.status == "BLOCKED"
        if defect == "wrong_chain":
            assert "WALLET_BSC_SUPPORTED" in result.reasons
    finally:
        service.store.close()
    assert snapshot.live_authorized is False
    assert not any("execute" in call or "sign-message" in call for call in reader.calls)


def test_valid_synthetic_wallet_reads_cannot_claim_production_readiness():
    reader = WalletWire()
    snapshot = AgenticWalletAdapter(reader, data_mode="DEMO", clock=lambda: NOW).snapshot()
    assert snapshot.capability_status == "FIXTURE_VERIFIED"
    assert snapshot.pending_state == "CLEAR" and snapshot.bsc_address == WALLET
    assert "LIVE_EXECUTION_BLOCKED" in snapshot.limitations
    assert LIVE_GATES.statuses()["AGENTIC_WALLET_LIVE_GATE"] == "BLOCKED"


def test_valid_preview_still_cannot_authorize_agentic_execution():
    assert validate_preview(preview()) == "fixture"
    signer = AgenticWalletSigner.__new__(AgenticWalletSigner)
    signer.gates = LIVE_GATES
    with pytest.raises(LiveExecutionError, match="SWAP_LIVE_GATE_BLOCKED"):
        signer.send()
    with pytest.raises(LiveExecutionError, match="RFQ_LIVE_GATE_BLOCKED"):
        signer.sign_typed_data({}, order=None)


def approval_fixture():
    route, _ = route_and_sim()
    route = ExecutionRouteBuilder().build(
        route.quote,
        route.build,
        slippage_bps=route.slippage_bps,
        allowance=mutate(route.allowance, amount="0"),
        now=NOW,
    )
    approval = ApprovalService().prepare(
        route,
        approval_response(route.quote.request.amount),
        now=NOW,
    )
    return route, approval


@pytest.mark.parametrize(
    "defect",
    [
        None,
        "spender",
        "allowance",
        "owner",
        "token",
        "mode",
        "stale",
        "expired",
    ],
)
def test_supported_approval_confirmation_requires_exact_fresh_allowance(defect):
    route, approval = approval_fixture()
    observation = mutate(route.allowance, amount=approval.amount)
    field = {"spender": "spender", "owner": "owner", "token": "token"}.get(defect)
    if field:
        observation = mutate(observation, **{field: "0x" + "6" * 40})
    elif defect == "allowance":
        observation = mutate(observation, amount="0")
    elif defect == "mode":
        observation = mutate(observation, data_mode="DEMO")
    elif defect == "stale":
        observation = mutate(observation, observed_at=NOW - timedelta(seconds=121))
    now = NOW + timedelta(seconds=30) if defect == "expired" else NOW
    assert ApprovalService().confirmed(approval, route, observation, now=now) is (defect is None)


def test_supported_external_approval_observation_requotes_rebuilds_and_resimulates():
    service, attempt = prepared(balance="0")
    try:
        assert attempt.state == "APPROVAL_REQUIRED"
        start = len(service.provider.calls)
        result = service.observe_approval(
            attempt,
            mutate(attempt.route.allowance, amount=attempt.approval.amount),
            funding_state=funding(),
        )
        assert result.quote.route.quoteId != attempt.quote.route.quoteId
        assert result.route.fingerprint != attempt.route.fingerprint
        assert result.simulation.fingerprint == result.route.fingerprint
        assert [c[0] for c in service.provider.calls[start:]] == ["quote", "build", "simulate"]
        assert result.state == "APPROVAL_CONFIRMED" and result.broadcast is False
    finally:
        service.store.close()


def diagnostic_module():
    path = Path(__file__).resolve().parents[3] / "scripts/check-agentic-wallet-readiness.py"
    spec = importlib.util.spec_from_file_location("readiness_diagnostic_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_diagnostic_missing_cli_cannot_claim_authentication_or_execution(monkeypatch):
    diagnostic = diagnostic_module()
    monkeypatch.setattr(diagnostic.shutil, "which", lambda _: None)
    result = diagnostic.check()
    assert result["installed_on_path"] is False
    for key in (
        "authenticated",
        "bsc_session",
        "preview_execution_commands",
        "execution_equivalence",
    ):
        assert result[key] == "NOT_VERIFIED"
    assert result["signing_approval_broadcast_calls"] == 0
    assert result["gates"] == LIVE_GATES.statuses()


@pytest.mark.parametrize("outcome", ["bad_version", "read_error", "help_only"])
def test_diagnostic_help_or_provider_failure_never_unlocks_gates(monkeypatch, outcome):
    diagnostic = diagnostic_module()

    class DiagnosticWire(WalletWire):
        def __init__(self, **kwargs):
            super().__init__()

        def read(self, operation, **params):
            if outcome == "read_error":
                raise WalletReadError("CLI_READ_FAILED")
            if operation == "cli-check" and outcome == "bad_version":
                return {"currentCliVersion": "0.0.0", "needUpdateCli": True}, NOW, NOW
            return super().read(operation, **params)

        def _run(self, args):
            if args == command("contract-help"):
                return b"contract-call preview execute"
            return super()._run(args)

    monkeypatch.setattr(diagnostic.shutil, "which", lambda _: "/synthetic/not-executed/baw")
    monkeypatch.setattr(diagnostic, "BawReadOnlyClient", DiagnosticWire)
    result = diagnostic.check()
    assert result["gates"] == LIVE_GATES.statuses()
    assert result["bsc_session"] == result["execution_equivalence"] == "NOT_VERIFIED"
    assert result["signing_approval_broadcast_calls"] == 0
    if outcome == "help_only":
        assert result["preview_execution_commands"] == "HELP_OBSERVED"
        assert result["authenticated"] == "UNKNOWN"
    elif outcome == "bad_version":
        assert result["version_matches"] is False
    else:
        assert result["runtime_check"] == "UNAVAILABLE_OR_INVALID"


def test_gate_statuses_remain_exactly_unchanged():
    assert LIVE_GATES.statuses() == {
        "DATA_GATE": "PASS",
        "DRY_RUN_GATE": "PASS",
        "TRUST_GATE": "BLOCKED",
        "OPPORTUNITY_GATE": "BLOCKED_BY_TRUST",
        "SWAP_LIVE_GATE": "BLOCKED",
        "RFQ_LIVE_GATE": "BLOCKED",
        "AGENTIC_WALLET_LIVE_GATE": "BLOCKED",
    }
