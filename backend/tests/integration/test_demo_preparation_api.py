"""Actual DEMO APIs, production isolation and no external transport/execution capabilities."""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import Settings
from app.main import create_app


@pytest.fixture
def demo_app(tmp_path):
    return create_app(
        Settings(
            _env_file=None, runtime_mode="DEMO", database_url=f"sqlite:///{tmp_path}/protected.db"
        )
    )


def steps(client, scenario):
    t = client.get("/api/demo/trust/scenarios/" + scenario).json()
    o = client.post(
        "/api/demo/opportunity", json={"trust_assessment_id": t["assessment"]["assessment_id"]}
    ).json()
    r = client.post(
        "/api/demo/risk", json={"opportunity_id": o["opportunity"]["opportunity_id"]}
    ).json()
    response = client.post("/api/demo/quote", json={"risk_id": r["risk"]["risk_id"]})
    assert response.status_code == 200
    return t, o, r, response.json()


def test_real_api_information_reaches_simulation_and_all_safety_gates_unchanged(demo_app):
    with TestClient(demo_app) as client:
        t, _, r, q = steps(client, "supported-move")
        assert q["status"] == "QUOTED" and q["quote"]["source_risk_id"] == r["risk"]["risk_id"]
        p = client.post("/api/demo/prepare", json={"quote_id": q["quote"]["quote_id"]})
        assert p.status_code == 200 and p.json()["status"] == "PREPARED"
        s = client.post(
            "/api/demo/simulate", json={"transaction_id": p.json()["transaction"]["transaction_id"]}
        )
        assert s.status_code == 200 and s.json()["simulation"]["status"] == "SIMULATION_PASS"
        for result in (q, p.json(), s.json()):
            assert result["production_gates"] == t["production_gates"]
            assert result["synthetic"] is True and result["production_eligible"] is False
            assert (
                result["transaction_broadcast"]
                is result["execution_ready"]
                is result["funds_moved"]
                is False
            )
            assert result["source"] == "DEMO"
        assert s.json()["simulation"]["chain_simulation"] is False
        assert len(s.headers["x-request-id"]) == 36


@pytest.mark.parametrize("scenario", ["steady", "thin-move"])
def test_ineligible_api_no_quote_no_transaction_no_simulation(demo_app, scenario):
    with TestClient(demo_app) as client:
        _, _, _, q = steps(client, scenario)
        assert q["status"] == "BLOCKED" and q["quote"] is None
        assert (
            not demo_app.state.demo_preparation.quotes
            and not demo_app.state.demo_preparation.transactions
        )


def test_full_flow_never_calls_provider_transport_wallet_or_production_database(
    demo_app, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError("No provider, wallet or network permitted")

    monkeypatch.setattr("app.clients.binance_web3.BinanceWeb3Client.__init__", forbidden)
    monkeypatch.setattr("app.clients.massive.MassiveClient.__init__", forbidden)
    monkeypatch.setattr("httpx.HTTPTransport.handle_request", forbidden)
    monkeypatch.setattr("socket.socket.connect", forbidden)
    with TestClient(demo_app) as client:
        _, _, _, q = steps(client, "supported-move")
        p = client.post("/api/demo/prepare", json={"quote_id": q["quote"]["quote_id"]}).json()
        assert (
            client.post(
                "/api/demo/simulate", json={"transaction_id": p["transaction"]["transaction_id"]}
            ).json()["simulation"]["status"]
            == "SIMULATION_PASS"
        )
        with demo_app.state.database.engine.connect() as connection:
            for table in ("trust_samples", "trust_episodes", "trust_assessments"):
                assert connection.execute(text("SELECT count(*) FROM " + table)).scalar() == 0
        for path in (
            "/api/wallet",
            "/api/demo/execute",
            "/api/demo/broadcast",
            "/api/demo/swap",
            "/api/demo/rfq",
        ):
            assert client.post(path, json={}).status_code == 404
    assert not Path(demo_app.state.settings.database_url.removeprefix("sqlite:///")).exists()


def test_live_runtime_does_not_construct_or_expose_downstream(settings, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("LIVE must not load DEMO downstream services")

    monkeypatch.setattr("app.main.DemoPreparationFlow", forbidden)
    with TestClient(create_app(settings)) as client:
        for path in ("/api/demo/quote", "/api/demo/prepare", "/api/demo/simulate"):
            assert client.post(path, json={}).status_code == 404
        assert "runtime_mode" not in client.get("/api/system-status").json()
        assert client.get("/api/assets/NVDA/trust").json()["trust_gate"] == "BLOCKED"


@pytest.mark.parametrize(
    "path,key", [("quote", "risk_id"), ("prepare", "quote_id"), ("simulate", "transaction_id")]
)
def test_id_only_requests_fail_closed_on_unknown_extra_fields_and_execution_flags(
    demo_app, path, key
):
    with TestClient(demo_app) as client:
        url = "/api/demo/" + path
        assert client.post(url, json={key: str(uuid4())}).status_code == 410
        assert client.post(url, json={key: "invalid"}).status_code == 422
        assert client.post(url, json={key: str(uuid4()), "signed": True}).status_code == 422
        assert client.post(url + "?execute=true", json={key: str(uuid4())}).status_code == 404
        assert client.get(url).status_code == 405


def test_quote_api_revalidates_current_risk_and_expiry(demo_app):
    with TestClient(demo_app) as client:
        core = demo_app.state.demo_opportunity
        elapsed = [0]
        core.clock = lambda: elapsed[0]
        _, _, _, q = steps(client, "supported-move")
        p = client.post("/api/demo/prepare", json={"quote_id": q["quote"]["quote_id"]}).json()
        elapsed[0] = 30
        response = client.post(
            "/api/demo/prepare", json={"quote_id": q["quote"]["quote_id"]}
        ).json()
        assert response["status"] == "BLOCKED" and response["transaction"] is None
        s = client.post(
            "/api/demo/simulate", json={"transaction_id": p["transaction"]["transaction_id"]}
        ).json()
        assert s["simulation"]["status"] == "SIMULATION_FAIL" and "QUOTE_VALID" in s["reason_codes"]
