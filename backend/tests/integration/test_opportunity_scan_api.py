"""Analytical scan API and existing Binance-discovery contract; no real provider calls."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.clients.binance_web3 import PREFIX, BinanceWeb3Client
from app.clients.common import ProviderError
from app.config import Settings
from app.main import create_app
from app.models.opportunity_scan import OpportunityRequest, ScanPolicy
from app.models.trust import TrustAssessment
from app.providers.binance import BinanceMarketProvider, BinanceRWAProvider
from app.services.asset_discovery import AssetDiscoveryService
from app.services.opportunity_scan import OpportunityScanService
from app.services.opportunity_sources import DataLayerScanSource

FIXTURES = Path(__file__).parents[1] / "fixtures/binance"
NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)


@pytest.fixture
def demo_client(tmp_path):
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            runtime_mode="DEMO",
            data_mode="DEMO",
            database_url=f"sqlite:///{tmp_path}/unused.db",
        )
    )
    with TestClient(app) as client:
        yield client
    assert not (tmp_path / "unused.db").exists()


def body(scenario="supported-move"):
    return dict(
        budget_usd="60", risk_budget_usd="2", time_window="PRE_OPEN", demo_scenario=scenario
    )


@pytest.mark.parametrize(
    "scenario,action",
    [
        ("steady", "NO_QUALIFYING_OPPORTUNITY"),
        ("thin-move", "NO_QUALIFYING_OPPORTUNITY"),
        ("supported-move", "BUY"),
    ],
)
def test_scan_api_roundtrip(demo_client, scenario, action):
    r = demo_client.post("/api/opportunities/scan", json=body(scenario))
    assert r.status_code == 200
    data = r.json()
    assert data["final_action"] == action
    assert data["data_mode"] == "DEMO"
    assert data["transaction_broadcast"] is False
    assert data["opportunity_gate"] == "BLOCKED_BY_TRUST"
    assert demo_client.get("/api/opportunities/" + data["run_id"]).json() == data
    assert demo_client.post("/api/opportunities/scan", json=body(scenario)).json() == data


@pytest.mark.parametrize(
    "update",
    [
        {"budget_usd": 100.0},
        {"risk_budget_usd": None},
        {"time_window": "UNKNOWN"},
        {"costs": {"fees_usd": "0"}},
        {"candidate_table": []},
        {"risk_policy": {}},
        {"live_trading_enabled": True},
        {"execution_mode": "LIVE"},
        {"approval_mode": "AUTONOMOUS"},
    ],
)
def test_public_cannot_supply_evidence_policy_or_execution(demo_client, update):
    r = demo_client.post("/api/opportunities/scan", json={**body(), **update})
    assert r.status_code == 422
    assert not any(k in r.json()["error"] for k in ["input", "body"])


def test_ordinary_runtime_does_not_accept_demo_sandbox_selection(client):
    assert client.post("/api/opportunities/scan", json=body()).status_code == 422
    assert client.get("/api/opportunities/" + "0" * 64).status_code == 404
    assert client.get("/api/opportunities/not-a-run").status_code == 422


def test_production_scan_gate_stays_blocked_without_credentials(tmp_path):
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            data_mode="LIVE_READ_ONLY",
            database_url=f"sqlite:///{tmp_path}/read-only.db",
        )
    )
    with TestClient(app) as client:
        r = client.post(
            "/api/opportunities/scan",
            json={"budget_usd": "100", "risk_budget_usd": "10", "time_window": "PRE_OPEN"},
        )
        assert r.status_code == 200
        assert r.json()["final_action"] == "DEFER"
        assert r.json()["agent_run"] is None
        assert "PRODUCTION_OPPORTUNITY_GATE_BLOCKED_BY_TRUST" in r.json()["blockers"]
        status = client.get("/api/system-status").json()
        assert status["live_trading_enabled"] is False
        for g in ("SWAP_LIVE_GATE", "RFQ_LIVE_GATE", "AGENTIC_WALLET_LIVE_GATE"):
            assert status["gates"][g] == "BLOCKED"


@pytest.mark.parametrize("malformed", [False, True])
def test_actual_dynamic_discovery_adapter_read_contract_and_quarantine(malformed):
    calls = []

    def handler(request):
        calls.append(request)
        name = request.url.path.removeprefix("/build" + PREFIX).replace("/", "_")
        value = json.loads((FIXTURES / (name + ".json")).read_text())
        if malformed and name == "rwa_tokens":
            value["data"][0]["tokenToShareRatio"] = "0"
        return httpx.Response(200, json=value)

    client = BinanceWeb3Client(
        SecretStr("test-key"),
        SecretStr("test-secret"),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: NOW,
        min_interval=0,
        sleep=lambda _: None,
    )
    rwa, market = BinanceRWAProvider(client), BinanceMarketProvider(client)
    discovery = AssetDiscoveryService(rwa, market)

    def trust(ticker, **kw):
        return TrustAssessment(
            assessment_id="00000000-0000-0000-0000-000000000001",
            run_id="test",
            request_id="test",
            correlation_id="test",
            data_mode="LIVE",
            evaluated_at=NOW,
            ticker=ticker,
            status="UNAVAILABLE",
            regime=None,
            representations=[],
            limitations=["SYNTHETIC_HTTP_CONTRACT_TEST_NOT_REAL_EVIDENCE"],
        )

    source = DataLayerScanSource(
        SimpleNamespace(
            mode="LIVE",
            discovery=discovery,
            rwa=rwa,
            repository=SimpleNamespace(list=lambda *a, **kw: []),
        ),
        SimpleNamespace(assess=trust),
        clock=lambda: NOW,
    )
    r = OpportunityRequest(budget_usd="100", risk_budget_usd="10", time_window="PRE_OPEN")
    snapshot = source.capture(r, ScanPolicy())
    result = asyncio.run(OpportunityScanService().scan(r, snapshot))
    assert result.universe_count == 2 and result.rejected_count == 2
    assert result.final_action == "DEFER" and result.agent_run is None
    assert {p.url.path for p in calls} == {
        "/build/api/v1/dex/market/supported/chain",
        "/build/api/v1/dex/market/rwa/platforms",
        "/build/api/v1/dex/market/rwa/tokens",
    }
    assert all(p.method == "GET" for p in calls)
    assert calls[-1].url.params["binanceChainId"] == "56"
    assert result.catalog_rejections == snapshot.catalog_rejections
    if malformed:
        assert result.rejection_counts["PAYLOAD_SCHEMA_INVALID"] == 1
    client.close()


def test_source_outage_defers_never_falls_back():
    def unavailable():
        raise ProviderError("BINANCE", "PROVIDER_UNAVAILABLE")

    source = DataLayerScanSource(
        SimpleNamespace(
            mode="LIVE",
            discovery=SimpleNamespace(universe=unavailable),
            rwa=SimpleNamespace(catalog_rejections=[]),
        ),
        None,
        clock=lambda: NOW,
    )
    r = OpportunityRequest(budget_usd="100", risk_budget_usd="10", time_window="PRE_OPEN")
    result = asyncio.run(OpportunityScanService().scan(r, source.capture(r, ScanPolicy())))
    assert result.final_action == "DEFER" and result.universe_count == 0
    assert "DISCOVERY_UNAVAILABLE" in result.blockers
