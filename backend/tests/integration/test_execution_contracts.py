"""Official Phase 8 wire-contract tests via in-memory MockTransport, no real providers."""

import asyncio
import json
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.agents.tools import ToolRegistry
from app.clients.binance_trading import AGGREGATOR, SIMULATOR, BinanceSafetyClient
from app.clients.binance_web3 import sign_request
from app.clients.common import ProviderError
from app.config import Settings
from app.main import create_app
from app.models.execution import ExecutionControls
from app.repositories.execution import ExecutionStore
from app.services.execution import SafetyExecutionService
from app.services.execution_builders import ExecutionRouteBuilder
from backend.tests.fixtures.execution_fixtures import (
    NOW,
    TXHASH,
    FixtureProvider,
    allowance,
    approval_response,
    build,
    evidence,
    funding,
    quote,
    request,
)


class Wire:
    def __init__(self):
        self.requests = []
        self.override = None

    def __call__(self, r):
        self.requests.append(r)
        path = r.url.path.removeprefix("/build")
        q = quote(request())
        if self.override:
            return self.override(r)
        if path.endswith("/supported/chain"):
            data = [{"binanceChainId": "56"}]
        elif path.endswith("/quote"):
            data = [q.route.model_dump(mode="json")]
        elif path.endswith("/swap"):
            data = build(q).model_dump(mode="json", by_alias=True)
        elif path.endswith("/approve-transaction"):
            data = [approval_response(q.request.amount).model_dump(mode="json")]
        elif path.endswith("/simulate"):
            data = {
                "status": "SUCCESS",
                "failReason": None,
                "balanceChanges": [],
                "allowanceChanges": [],
            }
        elif path.endswith("/history"):
            data = None
        else:
            data = {
                "orderId": "platform-id",
                "status": "PENDING_VENDOR",
                "createdAt": int(NOW.timestamp() * 1000),
            }
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "success",
                "data": data,
                "success": True,
                "timestamp": int(NOW.timestamp() * 1000),
            },
        )


def client(wire, **kwargs):
    return BinanceSafetyClient(
        SecretStr("unit-test-api-key"),
        SecretStr("unit-test-secret"),
        http=httpx.Client(transport=httpx.MockTransport(wire)),
        clock=lambda: NOW,
        sleep=lambda _: None,
        min_interval=0,
        cache_ttl=0,
        **kwargs,
    )


def test_quote_swap_approve_simulate_exact_contracts_and_central_signer():
    w = Wire()
    c = client(w)
    q = c.quote(request(), mode="LIVE_READ_ONLY")[0]
    assert q.data_mode == "LIVE_READ_ONLY" and q.source == "BINANCE_WEB3"
    r = w.requests[-1]
    assert r.method == "GET" and r.url.path == "/build" + AGGREGATOR + "quote"
    assert dict(r.url.params) == request().model_dump()
    assert r.url.params["amount"] == "39992002" and not r.content
    assert r.headers["X-OC-SIGN"] == sign_request(
        c.secret_key, r.headers["X-OC-TIMESTAMP"], r.method, r.url.raw_path.decode(), b""
    )
    built = c.build(q, slippage_bps=Decimal(50))
    params = dict(w.requests[-1].url.params)
    assert params == {
        **request().model_dump(),
        "quoteId": "quote1",
        "slippagePercent": "0.5",
        "autoSlippage": "false",
    }
    real_allowance = allowance(data_mode="LIVE_READ_ONLY")
    route = ExecutionRouteBuilder().build(
        q, built, slippage_bps=Decimal(50), allowance=real_allowance, now=NOW
    )
    approved = c.approval(route)
    assert dict(w.requests[-1].url.params) == dict(
        binanceChainId="56",
        tokenContractAddress=request().fromTokenAddress,
        approveAmount=request().amount,
    )
    assert approved.dexContractAddress == q.route.approveTarget
    result, received = c.simulate(built.tx, mode="LIVE_READ_ONLY")
    assert result.status == "SUCCESS" and received == NOW
    r = w.requests[-1]
    assert r.method == "POST" and r.url.path == "/build" + SIMULATOR + "simulate"
    assert json.loads(r.content) == {"binanceChainId": "56", "evmTx": built.tx.evm_payload()}
    assert r.headers["X-OC-SIGN"] == sign_request(
        c.secret_key, r.headers["X-OC-TIMESTAMP"], r.method, r.url.raw_path.decode(), r.content
    )
    assert "gas" not in json.loads(r.content)["evmTx"]
    assert not any("/submit" in r.url.path or "broadcast" in r.url.path for r in w.requests)
    c.close()


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", AGGREGATOR + "order/submit"),
        ("GET", AGGREGATOR + "order/submit"),
        ("POST", SIMULATOR + "broadcast-transaction"),
        ("GET", AGGREGATOR + "quote-and-swap"),
        ("GET", AGGREGATOR + "swap-instruction"),
        ("POST", "/api/v1/dex/wallet/settings"),
        ("GET", AGGREGATOR + "order/../../submit"),
        ("GET", "https://evil.example/trade"),
    ],
)
def test_execution_or_arbitrary_paths_rejected_before_network(method, path):
    w = Wire()
    c = client(w)
    with pytest.raises(ProviderError):
        c.read(method, path)
    assert w.requests == []
    with pytest.raises(ProviderError):
        c.submit_rfq(None)
    with pytest.raises(ProviderError):
        c.broadcast(None)
    assert w.requests == []
    c.close()


@pytest.mark.parametrize("status", [401, 403, 404, 408, 409, 429, 500, 502, 503, 504])
def test_failure_statuses_bounded_and_no_mutating_retry(status):
    w = Wire()
    w.override = lambda _: httpx.Response(status, headers={"Retry-After": "0"})
    c = client(w)
    with pytest.raises(ProviderError):
        c.quote(request(), mode="LIVE_READ_ONLY")
    assert 1 <= len(w.requests) <= 3
    assert all(r.method == "GET" and r.url.path.endswith("/supported/chain") for r in w.requests)
    c.close()


def test_rate_limit_long_retry_and_outages_fail_closed():
    w = Wire()
    w.override = lambda _: httpx.Response(429, headers={"Retry-After": "60"})
    c = client(w)
    with pytest.raises(ProviderError):
        c.quote(request(), mode="LIVE_READ_ONLY")
    assert len(w.requests) == 1
    with pytest.raises(ProviderError, match="CIRCUIT"):
        c.quote(request(), mode="LIVE_READ_ONLY")
    assert len(w.requests) == 1
    c.close()

    def timeout(r):
        raise httpx.ReadTimeout("test timeout", request=r)

    w = Wire()
    w.override = timeout
    c = client(w)
    with pytest.raises(ProviderError):
        c.quote(request(), mode="LIVE_READ_ONLY")
    assert len(w.requests) == 3
    c.close()


@pytest.mark.parametrize(
    "data",
    [
        {},
        None,
        [{}],
        [],
        [{"executionMode": "UNKNOWN"}],
    ],
)
def test_malformed_quotes_never_construct_executable_output(data):
    w = Wire()

    def response(r):
        payload = [{"binanceChainId": "56"}] if r.url.path.endswith("/supported/chain") else data
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "success",
                "data": payload,
                "timestamp": int(NOW.timestamp() * 1000),
                "success": True,
            },
        )

    w.override = response
    c = client(w)
    with pytest.raises(ProviderError):
        c.quote(request(), mode="LIVE_READ_ONLY")
    c.close()


def test_duplicate_json_and_secret_echo_are_rejected_without_exposure():
    for content in [b'{"code":0,"code":0}', b"unit-test-api-key"]:
        w = Wire()
        w.override = lambda r, content=content: httpx.Response(200, content=content)
        c = client(w)
        with pytest.raises(ProviderError) as exc:
            c.quote(request(), mode="LIVE_READ_ONLY")
        assert "unit-test-api-key" not in str(exc.value)
        c.close()


def test_order_status_is_read_only_and_unknown_is_not_success():
    w = Wire()
    c = client(w)
    status, _ = c.order_status("platform-id")
    assert status.status == "PENDING_VENDOR"
    assert w.requests[-1].url.path == "/build" + AGGREGATOR + "order/platform-id"
    assert c.swap_status(TXHASH)[0] is None
    for value in ["../submit", "submit", "/evil", "bad?query=yes"]:
        with pytest.raises(ValueError):
            c.order_status(value)
    c.close()


def test_real_provider_refuses_demo_before_any_network_and_expired_quote_does_not_build():
    w = Wire()
    c = client(w)
    with pytest.raises(ProviderError):
        c.quote(request(), mode="DEMO")
    assert not w.requests
    q = c.quote(request(), mode="LIVE_READ_ONLY")[0]
    q = type(q).model_validate(
        {
            **q.model_dump(),
            "requested_at": NOW - timedelta(seconds=31),
            "received_at": NOW - timedelta(seconds=31),
            "expires_at": NOW - timedelta(seconds=1),
        }
    )
    count = len(w.requests)
    with pytest.raises(ProviderError, match="QUOTE_EXPIRED"):
        c.build(q, slippage_bps=Decimal(50))
    assert len(w.requests) == count
    c.close()


def test_application_wires_safe_service_but_public_and_agent_execution_unavailable():
    app = create_app(
        Settings(
            _env_file=None, app_env="test", data_mode="DEMO", database_url="sqlite:///:memory:"
        )
    )
    with TestClient(app) as web:
        assert isinstance(app.state.safety_execution, SafetyExecutionService)
        assert app.state.safety_execution.controls == ExecutionControls(data_mode="DEMO")
        for path in [
            "/api/execution/submit",
            "/api/decisions/x/approve",
            "/api/rfq/submit",
            "/api/broadcast",
        ]:
            assert web.post(path, json={"live_trading_enabled": True}).status_code == 404
        status = web.get("/api/system-status").json()
        gates = status["gates"]
        assert gates == {
            "DATA_GATE": "PASS",
            "DRY_RUN_GATE": "PASS",
            "SWAP_LIVE_GATE": "BLOCKED",
            "RFQ_LIVE_GATE": "BLOCKED",
            "AGENTIC_WALLET_LIVE_GATE": "BLOCKED",
        }
        assert status["execution_mode"] == "DRY_RUN" and not status["live_trading_enabled"]
        assert not any(
            "execute" in name.lower() or "gateway" in name.lower() for name in ToolRegistry.__dict__
        )


def test_phase7_real_defer_never_becomes_execution_and_demo_manifest_not_evm():
    from app.models.opportunity_scan import OpportunityRequest
    from app.services.opportunity_scan import OpportunityScanService
    from app.services.opportunity_sources import DemoScanSource

    req = OpportunityRequest(
        budget_usd="60", risk_budget_usd="2", time_window="PRE_OPEN", demo_scenario="supported-move"
    )
    scans = OpportunityScanService()
    snapshot = DemoScanSource().capture(req, scans.policy)
    scan = asyncio.run(scans.scan(req, snapshot))
    assert scan.final_action == "BUY" and scan.selected_candidate.contract.startswith("demo:")
    s = SafetyExecutionService(
        FixtureProvider(), ExecutionStore(), ExecutionControls(data_mode="DEMO"), clock=lambda: NOW
    )
    e = evidence(
        decision_id=scan.run_id, notional_usd=scan.selected_candidate.proposed_notional_usd
    )
    # Safely refuses fictional demo contract instead of converting it into a real address.
    result = s.prepare_scan(
        scan,
        evidence=e,
        funding_state=funding(),
        allowance=allowance(),
        correlation_id="phase7-boundary",
    )
    assert result.state == "BLOCKED" and not s.provider.calls
    scan = type(scan).model_validate({**scan.model_dump(), "final_action": "DEFER"})
    with pytest.raises(ValueError):
        s.prepare_scan(
            scan,
            evidence=e,
            funding_state=funding(),
            allowance=allowance(),
            correlation_id="phase7-boundary",
        )


def test_every_agent_is_denied_execution_gateway_tools():
    from app.agents.adapters import DemoEvidenceAdapter
    from app.agents.schemas import AgentPolicy
    from app.agents.tools import ALLOWLIST, ToolDenied

    registry = ToolRegistry(DemoEvidenceAdapter().load("supported-move"), AgentPolicy())
    for agent in ALLOWLIST:
        for tool in [
            "ExecutionGateway",
            "execute_trade",
            "submit_rfq",
            "broadcast_transaction",
            "wallet_settings",
        ]:
            with pytest.raises(ToolDenied):
                registry.for_agent(agent).read(tool)
    assert not registry.calls


def test_approve_rfq_vendor_parameter_is_preserved():
    from backend.tests.fixtures.execution_fixtures import build, quote

    w = Wire()
    c = client(w)
    q = quote(request(), execution_mode="RFQ")
    q = type(q).model_validate(
        {**q.model_dump(), "source": "BINANCE_WEB3", "data_mode": "LIVE_READ_ONLY"}
    )
    r = ExecutionRouteBuilder().build(
        q,
        build(q),
        slippage_bps=Decimal(50),
        allowance=allowance(data_mode="LIVE_READ_ONLY"),
        now=NOW,
    )
    c.approval(r)
    assert dict(w.requests[-1].url.params)["vendor"] == "PcsXRfq"
    c.close()


def test_central_signer_never_signs_unreviewed_or_non_build_paths():
    for method, path in [
        ("GET", AGGREGATOR + "quote"),
        ("POST", "/build" + AGGREGATOR + "order/submit"),
        ("POST", "/build" + SIMULATOR + "broadcast-transaction"),
        ("DELETE", "/build/api/v1/dex/market/rwa/search"),
    ]:
        with pytest.raises(ValueError):
            sign_request(
                SecretStr("test-only-secret"), "2026-10-08T15:00:00.000Z", method, path, b""
            )
