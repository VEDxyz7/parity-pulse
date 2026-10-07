"""Actual discovery/Ask/API/DEMO downstream composition; LIVE uses offline test doubles."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models.routing import RouteDecision
from app.providers.demo import DemoEquityProvider, DemoRWAProvider, load_data_fixture
from app.repositories.data import DataRepository
from app.services.asset_discovery import AssetDiscoveryService
from app.services.calendar import USEquityCalendar
from app.services.routing import RoutingService

NOW = datetime(2026, 10, 7, 15, tzinfo=UTC)


def changed(model, **values):
    return type(model).model_validate({**model.model_dump(), **values})


class OfflineDiscoveredLayer:
    """Explicitly synthetic provider stand-in, not actual LIVE entitlement evidence."""

    def __init__(self, settings, database):
        self.mode = "DEMO" if settings.data_mode == "DEMO" else "LIVE"
        self.repository = DataRepository(database)
        self.clients = []
        self.calendar = USEquityCalendar(mode=self.mode)
        self.records = load_data_fixture()
        for key, rows in self.records.items():
            self.records[key] = [
                changed(
                    r,
                    data_mode=self.mode,
                    data_quality="DEMO" if self.mode == "DEMO" else "LIVE",
                    source="DEMO_TEST" if self.mode == "DEMO" else "OFFLINE_TEST_NOT_PROVIDER",
                    ingestion_timestamp=NOW,
                    source_timestamp=NOW,
                )
                for r in rows
            ]
        if self.mode == "LIVE":
            for key in ("metadata", "tokens"):
                self.records[key] = [
                    changed(r, chain_id="56", contract="test-only-" + r.ticker)
                    for r in self.records[key]
                ]
            self.records["issuers"] = [changed(r, chains=("56",)) for r in self.records["issuers"]]
        original = next(t for t in self.records["metadata"] if t.ticker == "NVDA")
        original_price = next(p for p in self.records["tokens"] if p.ticker == "NVDA")
        self.records["issuers"].append(
            changed(
                self.records["issuers"][0],
                platform_id="test-second-issuer",
                provider_identifier="test-second-issuer",
            )
        )
        token = changed(
            original,
            platform_id="test-second-issuer",
            provider_identifier="test-only-second-NVDA",
            contract="demo:second-NVDA" if self.mode == "DEMO" else "test-only-second-NVDA",
            token_symbol="TEST_NVDA_B",
            token_to_share_ratio="2",
        )
        price = changed(
            original_price,
            issuer=token.platform_id,
            provider_identifier="test-only-second-NVDA-price",
            contract=token.contract,
            token_symbol=token.token_symbol,
            token_to_share_ratio="2",
            token_price="250",
        )
        self.records["metadata"].append(token)
        self.records["tokens"].append(price)
        self.rwa = DemoRWAProvider(
            self.records
        )  # offline fake only, never normal LIVE runtime code
        self.equity = DemoEquityProvider(self.records)
        self.market = None
        self.discovery = AssetDiscoveryService(
            self.rwa, mode=self.mode, chain="56" if self.mode == "LIVE" else "DEMO"
        )

    def catalog_limitations(self):
        return {}

    def close(self):
        pass


@pytest.mark.parametrize("mode", ["DEMO", "LIVE_READ_ONLY"])
def test_discovery_normalization_routing_persistence_same_class_and_no_external_calls(
    tmp_path, monkeypatch, mode
):
    def forbidden(*args, **kwargs):
        raise AssertionError("No provider transport or execution allowed")

    monkeypatch.setattr("app.main.DataLayer", OfflineDiscoveredLayer)
    monkeypatch.setattr("httpx.HTTPTransport.handle_request", forbidden)
    monkeypatch.setattr("socket.socket.connect", forbidden)
    app = create_app(
        Settings(_env_file=None, data_mode=mode, database_url=f"sqlite:///{tmp_path}/isolated.db")
    )
    with TestClient(app) as c:
        app.state.exposure.clock = lambda: NOW
        result = c.post("/api/exposure/quote", json={"text": "I have $50 of Nvidia"})
        assert result.status_code == 200
        row = result.json()
        route = RouteDecision.model_validate(row["route_decision"])
        assert route.status == "ROUTE_SELECTED" and len(route.candidates) == 2
        assert (
            route.issuer == "test-second-issuer"
            and route.selected_candidate.effective_cost_per_share_usd == 125
        )
        assert row["selected"]["contract"] == route.selected_representation.contract
        assert type(app.state.exposure.router) is RoutingService
        assert c.get("/api/exposure/proposals/" + row["proposal_id"]).status_code == 200
        # Fixed receipt clock is used for expiry retrieval, not fabricated provider freshness.
        app.state.exposure.clock = lambda: NOW + timedelta(seconds=30)
        expired = c.get("/api/exposure/proposals/" + row["proposal_id"]).json()
        assert expired["status"] == "EXPIRED" and expired["route_decision"]["status"] == "NO_ROUTE"
        assert all(
            not candidate["eligible"] for candidate in expired["route_decision"]["candidates"]
        )
        assert row["execution_ready"] is row["transaction_broadcast"] is False
        app.state.exposure.clock = lambda: NOW
        direct = c.post("/api/exposure/quote", json={"text": "Buy $50 NVDA"})
        assert (
            direct.status_code == 200
            and direct.json()["route_decision"]["issuer"] == "test-second-issuer"
        )
        assert direct.json()["route_decision"]["provider_execution_mode"] is None
        assert (
            c.post("/api/exposure/quote?execute=true", json={"text": "Buy $50 NVDA"}).status_code
            == 404
        )
        assert (
            c.post(
                "/api/exposure/quote",
                json={"text": "Buy $50 NVDA", "policy": {"require_trust": False}},
            ).status_code
            == 422
        )


def test_default_readonly_api_no_route_and_discovered_restrictions_fail_safely(client, application):
    route = client.post("/api/exposure/quote", json={"text": "Buy $50 UnsupportedStockXYZ"}).json()[
        "route_decision"
    ]
    assert route["status"] == "NO_ROUTE" and not route["candidates"]
    layer = application.state.data_layer
    token = next(t for t in layer.rwa.records["metadata"] if t.ticker == "NVDA")
    layer.rwa.records["metadata"] = [
        changed(t, reason_code="ASSET_LIMITED") if t == token else t
        for t in layer.rwa.records["metadata"]
    ]
    route = client.post("/api/exposure/quote", json={"text": "Buy $50 NVDA"}).json()[
        "route_decision"
    ]
    assert route["status"] == "NO_ROUTE"
    assert "UNSUPPORTED_OR_INVALID_NORMALIZATION" in route["candidates"][0]["rejection_reasons"]


@pytest.mark.parametrize(
    "scenario,route_status",
    [("steady", "NO_ROUTE"), ("thin-move", "NO_ROUTE"), ("supported-move", "ROUTE_SELECTED")],
)
def test_demo_router_is_shared_and_information_downstream_remains_complete(
    tmp_path, scenario, route_status
):
    protected = tmp_path / "protected.db"
    app = create_app(
        Settings(_env_file=None, runtime_mode="DEMO", database_url=f"sqlite:///{protected}")
    )
    with TestClient(app) as c:
        trust = c.get("/api/demo/trust/scenarios/" + scenario).json()
        opp = c.post(
            "/api/demo/opportunity",
            json={"trust_assessment_id": trust["assessment"]["assessment_id"]},
        ).json()
        route = opp["route_decision"]
        assert route["status"] == route_status and route["policy"]["purpose"] == "OPPORTUNITY"
        assert (
            type(app.state.demo_opportunity.router)
            is type(app.state.exposure.router)
            is RoutingService
        )
        assert opp["production_gates"] == trust["production_gates"]
        risk = c.post(
            "/api/demo/risk", json={"opportunity_id": opp["opportunity"]["opportunity_id"]}
        ).json()
        q = c.post("/api/demo/quote", json={"risk_id": risk["risk"]["risk_id"]}).json()
        if scenario != "supported-move":
            assert q["status"] == "BLOCKED" and q["quote"] is None
        else:
            assert q["status"] == "QUOTED" and q["route_decision"]["status"] == "ROUTE_SELECTED"
            assert q["quote"]["contract"] == route["selected_representation"]["contract"]
            p = c.post("/api/demo/prepare", json={"quote_id": q["quote"]["quote_id"]}).json()
            s = c.post(
                "/api/demo/simulate", json={"transaction_id": p["transaction"]["transaction_id"]}
            ).json()
            assert s["simulation"]["status"] == "SIMULATION_PASS"
            paper = c.post(
                "/api/demo/paper/fills",
                json={
                    "transaction_id": p["transaction"]["transaction_id"],
                    "simulation_id": s["simulation"]["simulation_id"],
                },
            ).json()
            base = "/api/demo/paper/positions/" + paper["position"]["position_id"]
            monitor = c.post(base + "/monitor").json()
            assert (
                c.post(
                    base + "/exit",
                    json={"observation_id": monitor["observation"]["observation_id"]},
                ).json()["position"]["state"]
                == "EXITED"
            )
            assert c.get(base + "/scorecard").status_code == 200
    assert not Path(protected).exists()
