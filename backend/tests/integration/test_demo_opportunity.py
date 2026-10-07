"""Conditional DEMO APIs consume server evidence and cannot access real history or execution."""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import Settings
from app.main import create_app
from app.services.demo_opportunity import DemoOpportunityFlow
from app.services.demo_sandbox import DemoTrustSandbox
from app.services.opportunity import OpportunityEngine
from app.services.risk import RiskEngine


@pytest.fixture
def demo_app(tmp_path):
    return create_app(
        Settings(
            _env_file=None, runtime_mode="DEMO", database_url=f"sqlite:///{tmp_path}/production.db"
        )
    )


def analyze(client, scenario):
    trust = client.get("/api/demo/trust/scenarios/" + scenario)
    assert trust.status_code == 200
    opportunity = client.post(
        "/api/demo/opportunity",
        json={
            "trust_assessment_id": trust.json()["assessment"]["assessment_id"],
        },
    )
    assert opportunity.status_code == 200
    risk = client.post(
        "/api/demo/risk",
        json={
            "opportunity_id": opportunity.json()["opportunity"]["opportunity_id"],
        },
    )
    assert risk.status_code == 200
    return trust.json(), opportunity.json(), risk.json()


@pytest.mark.parametrize(
    "scenario,status,risk_status",
    [
        ("steady", "NO_OPPORTUNITY", "FAIL"),
        ("thin-move", "REJECTED_BY_TRUST", "FAIL"),
        ("supported-move", "ACTIONABLE", "PASS"),
    ],
)
def test_exact_trust_result_reaches_shared_engines_and_safe_envelopes(
    demo_app,
    monkeypatch,
    scenario,
    status,
    risk_status,
):
    received = []
    risk_inputs = []
    original = OpportunityEngine.evaluate
    original_risk = RiskEngine.evaluate

    def evaluate(self, assessment, *args, **kwargs):
        received.append(assessment)
        return original(self, assessment, *args, **kwargs)

    def risk(self, opportunity, *args, **kwargs):
        risk_inputs.append(opportunity)
        return original_risk(self, opportunity, *args, **kwargs)

    monkeypatch.setattr(OpportunityEngine, "evaluate", evaluate)
    monkeypatch.setattr(RiskEngine, "evaluate", risk)
    with TestClient(demo_app) as client:
        trust, o, r = analyze(client, scenario)
        flow = demo_app.state.demo_opportunity
        assessment = received[0]
        assert flow.trust_results[assessment.assessment_id][0].assessment is assessment
        assert str(assessment.assessment_id) == o["opportunity"]["trust_assessment_id"]
        assert risk_inputs[0] is flow.opportunities[risk_inputs[0].opportunity_id][0].opportunity
        assert o["opportunity"]["status"] == status and r["risk"]["status"] == risk_status
        assert o["trust_fixture_sha256"] == trust["fixture_sha256"]
        for result in (trust, o, r):
            assert result["synthetic"] is True and result["production_eligible"] is False
            assert result["production_gates"] == trust["production_gates"]
            assert result["production_gates"]["OPPORTUNITY_GATE"] == "BLOCKED_BY_TRUST"
        for decision in (o["opportunity"], r["risk"]):
            assert decision["transaction_broadcast"] is decision["execution_ready"] is False
            assert (
                decision["live_trading_enabled"] is False and decision["require_simulation"] is True
            )
            assert (
                decision["quote_status"]
                == decision["preparation_status"]
                == decision["simulation_status"]
                == "UNAVAILABLE"
            )
            assert decision["no_broadcast_statement"] == "No real transaction was broadcast."


def test_no_providers_network_production_history_or_execution(demo_app, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No real client, transport or execution allowed")

    monkeypatch.setattr("app.clients.binance_web3.BinanceWeb3Client.__init__", forbidden)
    monkeypatch.setattr("app.clients.massive.MassiveClient.__init__", forbidden)
    monkeypatch.setattr("httpx.HTTPTransport.handle_request", forbidden)
    monkeypatch.setattr("socket.socket.connect", forbidden)
    with TestClient(demo_app) as client:
        for scenario in ("steady", "thin-move", "supported-move"):
            analyze(client, scenario)
        with demo_app.state.database.engine.connect() as connection:
            for table in ("trust_samples", "trust_episodes", "trust_assessments"):
                assert connection.execute(text("SELECT count(*) FROM " + table)).scalar() == 0
        paths = demo_app.openapi()["paths"]
        assert not any(
            any(s in p for s in ("broadcast", "execute", "wallet", "swap", "rfq")) for p in paths
        )
        for path in ("/api/demo/opportunity/execute", "/api/demo/risk/execute", "/api/opportunity"):
            assert client.post(path, json={}).status_code == 404
    assert not Path(demo_app.state.settings.database_url.removeprefix("sqlite:///")).exists()


def test_live_runtime_does_not_construct_flow_or_register_routes(settings, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("LIVE runtime cannot construct demo Opportunity flow")

    monkeypatch.setattr("app.main.DemoOpportunityFlow", forbidden)
    with TestClient(create_app(settings)) as client:
        for path in ("/api/demo/opportunity", "/api/demo/risk"):
            assert client.post(path, json={}).status_code == 404
        result = client.get("/api/assets/NVDA/trust").json()
        assert result["trust_gate"] == "BLOCKED"
        assert result["representations"][0]["classification"] == "INSUFFICIENT_EVIDENCE"
        assert "runtime_mode" not in client.get("/api/system-status").json()


def test_unknown_ids_and_client_supplied_financial_values_are_rejected(demo_app):
    with TestClient(demo_app) as client:
        for path, key in (
            ("/api/demo/opportunity", "trust_assessment_id"),
            ("/api/demo/risk", "opportunity_id"),
        ):
            assert client.post(path, json={key: str(uuid4())}).status_code == 410
            assert client.post(path, json={key: "not-a-uuid"}).status_code == 422
            assert client.post(path, json={key: str(uuid4()), "execute": True}).status_code == 422
            assert client.post(path + "?execute=true", json={key: str(uuid4())}).status_code == 404
            assert client.get(path).status_code == 405
            assert client.post(path, json={key: str(uuid4()), "net_edge": "100"}).status_code == 422


def test_actual_wall_elapsed_expiry_and_bounded_restart_local_cache(demo_app):
    with TestClient(demo_app) as client:
        flow = demo_app.state.demo_opportunity
        elapsed = [0]
        flow.clock = lambda: elapsed[0]
        _, o, _ = analyze(client, "supported-move")
        elapsed[0] = 60
        rejected = client.post(
            "/api/demo/risk", json={"opportunity_id": o["opportunity"]["opportunity_id"]}
        ).json()
        assert rejected["risk"]["status"] == "FAIL"
        assert "DECISION_VALID" in rejected["risk"]["reason_codes"]
        elapsed[0] = 120
        assert (
            client.post(
                "/api/demo/opportunity",
                json={
                    "trust_assessment_id": o["opportunity"]["trust_assessment_id"],
                },
            ).status_code
            == 410
        )
        assert (
            client.post(
                "/api/demo/risk",
                json={
                    "opportunity_id": o["opportunity"]["opportunity_id"],
                },
            ).status_code
            == 410
        )
    sandbox = DemoTrustSandbox()
    flow = DemoOpportunityFlow(sandbox, clock=lambda: 0)
    result = sandbox.assess("steady", run_id="cache", request_id="cache", correlation_id="cache")
    for _ in range(flow.capacity + 1):
        flow._save(flow.trust_results, uuid4(), result)
    assert len(flow.trust_results) == flow.capacity
    fresh = DemoOpportunityFlow(sandbox, clock=lambda: 0)
    with pytest.raises(LookupError):
        fresh.risk(uuid4())
