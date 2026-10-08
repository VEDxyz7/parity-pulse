"""Host boundary and real subprocess mechanics with explicitly fake local executables."""

import json

import pytest
from fastapi.testclient import TestClient

from app.agents.adapters import DemoEvidenceAdapter
from app.agents.schemas import AgentPolicy
from app.agents.tools import ALLOWLIST, ToolDenied, ToolRegistry
from app.clients.baw_cli import BawReadOnlyClient, WalletReadError, command
from app.clients.execution_gateway import AgenticWalletCliGateway
from app.config import Settings
from app.main import create_app
from app.models.execution import ExecutionControls, RFQStatus
from app.repositories.execution import ExecutionStore
from app.services.execution_status import ExecutionStatusTracker
from app.services.wallet_reconciliation import WalletReconciler
from backend.tests.fixtures.execution_fixtures import (
    BUY,
    NOW,
    SELL,
    TXHASH,
    funding,
    mutate,
)
from backend.tests.fixtures.wallet_fixtures import WalletWire, wallet_order
from backend.tests.unit.test_agentic_wallet import adapter, external, prepared


@pytest.mark.parametrize(
    "operation,expected",
    [
        ("status", ("wallet", "status", "--json")),
        ("chains", ("wallet", "chains", "--json")),
        ("address", ("wallet", "address", "--json")),
        ("settings", ("wallet", "settings", "--json")),
        ("balance", ("wallet", "balance", "--binanceChainId", "56", "--json")),
        ("tx-lock", ("wallet", "tx-lock", "--binanceChainId", "56", "--json")),
    ],
)
def test_exact_official_read_commands(operation, expected):
    assert command(operation) == expected


def test_orders_history_quotes_exact_verified_flags_and_units():
    assert command("orders", order_id="known-id") == (
        "market-order",
        "list",
        "--orderId",
        "known-id",
        "--json",
    )
    assert command("history", tx_hash=TXHASH) == (
        "wallet",
        "tx-history",
        "--binanceChainId",
        "56",
        "--size",
        "100",
        "--tx",
        TXHASH,
        "--json",
    )
    args = command("quote", sell=SELL, buy=BUY, quantity="0.000001", slippage_bps="50")
    assert args == (
        "market-order",
        "quote",
        "--fromTokenQty",
        "0.000001",
        "--fromToken",
        SELL,
        "--toToken",
        BUY,
        "--binanceChainId",
        "56",
        "--slippage",
        "0.5",
        "--json",
    )


@pytest.mark.parametrize(
    "operation,params",
    [
        ("status", {"auth_token": "private-secret"}),
        ("orders", {"order_id": "id; $(echo bad)"}),
        ("orders", {"order_id": "--execute"}),
        ("orders", {"pending": 1}),
        ("history", {"tx_hash": "0x123 --execute"}),
        ("balance", {"chain": "1"}),
        ("quote", {"sell": SELL, "buy": BUY, "quantity": "1e-1000000", "slippage_bps": "50"}),
        ("quote", {"sell": SELL, "buy": BUY, "quantity": "1", "slippage_bps": "1e-1000000"}),
    ],
)
def test_argument_injection_and_unsupported_options_never_spawn(operation, params):
    w = WalletWire()
    with pytest.raises(WalletReadError):
        w.read(operation, **params)
    assert not w.calls


def fake_cli(tmp_path, body):
    import sys

    path = tmp_path / "baw-fixture"
    from pathlib import Path

    path.write_text("#!" + str(Path(sys.executable).resolve()) + "\n" + body + "\n")
    path.chmod(0o700)
    return path


def test_subprocess_hermetic_environment_stdin_closed_no_shell_no_credential_leak(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("BINANCE_WEB3_SECRET_KEY", "private-secret")
    monkeypatch.setenv("NODE_OPTIONS", "--fake-dangerous-option")
    path = fake_cli(
        tmp_path,
        "import json,os,sys\n"
        'assert "BINANCE_WEB3_SECRET_KEY" not in os.environ\n'
        'assert "NODE_OPTIONS" not in os.environ\n'
        'assert sys.stdin.read() == ""\n'
        'assert sys.argv[1:] == ["wallet","status","--json"]\n'
        'print(json.dumps({"success":True,"data":{"status":"CONNECTED"}}))',
    )
    c = BawReadOnlyClient(enabled=True, executable=path, clock=lambda: NOW)
    c.version_verified = (
        True  # This test covers transport, not actual official-runtime verification.
    )
    data, _, _ = c.read("status")
    assert data == {"status": "CONNECTED"}


@pytest.mark.parametrize(
    "body,code",
    [
        ("import time\ntime.sleep(2)", "WALLET_READ_TIMEOUT"),
        ('import sys\nsys.stdout.write("x"*1048577)', "OUTPUT_TOO_LARGE"),
        ('import sys\nsys.stderr.write("private-secret")\nsys.exit(1)', "CLI_READ_FAILED"),
        ('print("private-secret")', "OUTPUT_INVALID"),
    ],
)
def test_process_timeout_output_limit_stderr_and_parse_errors_fail_safely(tmp_path, body, code):
    c = BawReadOnlyClient(enabled=True, executable=fake_cli(tmp_path, body), timeout=1)
    c.version_verified = True
    with pytest.raises(WalletReadError) as exc:
        c.read("status")
    assert exc.value.code == code and "private-secret" not in str(exc.value)


@pytest.mark.parametrize(
    "data",
    [
        {"currentCliVersion": "1.9.0", "needUpdateCli": True},
        {"currentCliVersion": "1.11.0", "needUpdateCli": False},
        {"currentCliVersion": "1.10.0", "needUpdateCli": "false"},
        {},
    ],
)
def test_unverified_runtime_version_blocks_before_wallet_reads(tmp_path, data):
    path = fake_cli(
        tmp_path,
        'import json,sys\nassert sys.argv[1] == "cli-check"\nprint('
        + repr(json.dumps({"success": True, "data": data}))
        + ")",
    )
    c = BawReadOnlyClient(enabled=True, executable=path)
    with pytest.raises(WalletReadError, match="CLI_VERSION_NOT_VERIFIED"):
        c.read("status")
    assert not c.version_verified


def test_app_worker_disabled_no_cli_startup_public_wallet_mutation_unavailable(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Public app must not spawn a wallet CLI")

    monkeypatch.setattr("app.clients.baw_cli.subprocess.Popen", forbidden)
    app = create_app(
        Settings(
            _env_file=None, app_env="test", data_mode="DEMO", database_url="sqlite:///:memory:"
        )
    )
    with TestClient(app) as web:
        assert isinstance(app.state.safety_execution.gateway, AgenticWalletCliGateway)
        assert app.state.safety_execution.gateway.adapter.client is None
        for path in [
            "/api/wallet/settings",
            "/api/wallet/send",
            "/api/wallet/execute",
            "/api/wallet/sign",
            "/api/execution/submit",
        ]:
            assert web.post(path, json={"limit": "1000000", "live": True}).status_code == 404
        status = web.get("/api/system-status").json()
        assert status["gates"] == {
            "DATA_GATE": "PASS",
            "DRY_RUN_GATE": "PASS",
            "SWAP_LIVE_GATE": "BLOCKED",
            "RFQ_LIVE_GATE": "BLOCKED",
            "AGENTIC_WALLET_LIVE_GATE": "BLOCKED",
        }
        assert status["execution_mode"] == "DRY_RUN" and not status["live_trading_enabled"]


def test_every_agent_denied_wallet_mutation_and_raw_cli_access():
    registry = ToolRegistry(DemoEvidenceAdapter().load("supported-move"), AgentPolicy())
    for agent in ALLOWLIST:
        for tool in [
            "baw",
            "AgenticWalletCliGateway",
            "wallet_send",
            "wallet_sign",
            "wallet_settings_update",
            "increase_wallet_limits",
            "expand_token_scope",
        ]:
            with pytest.raises(ToolDenied):
                registry.for_agent(agent).read(tool)


def test_phase8_orchestration_reuses_wallet_gateway_without_extra_financial_engine():
    s, a = prepared()
    gateway = AgenticWalletCliGateway(ExecutionControls(data_mode="DEMO"), adapter())
    s.gateway = gateway
    result = gateway.dry_run(a, now=NOW, funding_state=funding())
    assert result.wallet.status == "PASS" and result.route_fingerprint == a.route.fingerprint
    assert result.execution_id == a.execution_id and result.request_id == a.request_id
    assert not result.execution_ready
    risk_bad = mutate(a, evidence=mutate(a.evidence, required_evidence_valid=False), risk=None)
    assert "RISK_NOT_APPROVED" in gateway.submit(risk_bad, now=NOW, funding_state=funding())
    expired = mutate(a, quote=None, route=None, simulation=None)
    assert "ROUTE_UNAVAILABLE" in gateway.submit(expired, now=NOW, funding_state=funding())
    assert "FUNDING_REVALIDATION_FAILED" in gateway.submit(
        a, now=NOW, funding_state=mutate(funding(), balance_base_units="1")
    )


def test_conflicting_wallet_terminal_and_phase8_terminal_remain_unknown():
    store = ExecutionStore()
    s, a = external(store)
    w = WalletWire()
    w.values["orders"]["list"][0]["status"] = "FAILED"
    record = RFQStatus(
        orderId="platform-order",
        status="FILLED",
        txHash=TXHASH,
        fromAmount=a.quote.request.amount,
        toAmount=a.quote.route.toTokenAmount,
        createdAt=int(NOW.timestamp() * 1000),
        filledAt=int(NOW.timestamp() * 1000),
    )
    s.provider.order_status = lambda _: (record, NOW)
    result = WalletReconciler(
        adapter(w), store, execution_tracker=ExecutionStatusTracker(s.provider, store)
    ).reconcile(a, now=NOW, wallet_order_id="wallet-order")
    saved = store.get(a.execution_id, mode="DEMO")
    assert (
        result.execution_state == "EXECUTION_UNKNOWN"
        and "CONFLICTING_EXTERNAL_TERMINAL_EVIDENCE" in saved.reason_codes
    )


def test_malformed_order_units_and_pagination_cannot_authorize_reconciliation():
    store = ExecutionStore()
    _, a = external(store)
    w = WalletWire()
    w.values["orders"]["list"][0]["fromTokenQty"] = "39.9920021"
    result = WalletReconciler(adapter(w), store).reconcile(
        a, now=NOW, wallet_order_id="wallet-order"
    )
    assert result.execution_state == "EXECUTION_UNKNOWN" and not result.new_order_created
    w = WalletWire()
    w.values["pending_orders"] = {
        "total": 101,
        "page": 1,
        "pageSize": 100,
        "list": [wallet_order(status="PENDING")],
    }
    assert adapter(w).snapshot().pending_state == "UNKNOWN"


def test_settings_cannot_activate_live_or_autonomous_application_startup():
    for options in [
        {"execution_mode": "LIVE"},
        {"live_trading_enabled": True},
        {"approval_mode": "AUTONOMOUS"},
        {"require_simulation": False},
    ]:
        with pytest.raises(ValueError):
            Settings(_env_file=None, **options)


@pytest.mark.parametrize(
    "args",
    [
        ("wallet", "send", "--json"),
        ("auth", "signin", "--json"),
        ("sign-message", "execute", "--requestId", "known", "--json"),
        ("wallet", "settings", "--dailyLimit", "1000000", "--json"),
        ("market-order", "swap", "--json"),
        ("contract-call", "preview", "--json"),
        ("wallet", "tx-history", "--binanceChainId", "1", "--size", "100", "--json"),
    ],
)
def test_even_private_transport_cannot_run_writes_or_unreviewed_arguments(args, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Unsafe arguments must be denied before subprocess")

    monkeypatch.setattr("app.clients.baw_cli.subprocess.Popen", forbidden)
    c = BawReadOnlyClient(enabled=True)
    with pytest.raises(WalletReadError, match="COMMAND_DENIED"):
        c._run(args)
