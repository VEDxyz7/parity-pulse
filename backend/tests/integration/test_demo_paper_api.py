"""The actual HTTP paper lifecycle, no network providers and no production persistence."""

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
        Settings(_env_file=None, runtime_mode="DEMO", database_url=f"sqlite:///{tmp_path}/never.db")
    )


def steps(c, scenario="supported-move"):
    t = c.get("/api/demo/trust/scenarios/" + scenario).json()
    o = c.post(
        "/api/demo/opportunity", json={"trust_assessment_id": t["assessment"]["assessment_id"]}
    ).json()
    r = c.post("/api/demo/risk", json={"opportunity_id": o["opportunity"]["opportunity_id"]}).json()
    q = c.post("/api/demo/quote", json={"risk_id": r["risk"]["risk_id"]}).json()
    if q["status"] == "BLOCKED":
        return t, o, r, q, None, None
    p = c.post("/api/demo/prepare", json={"quote_id": q["quote"]["quote_id"]}).json()
    s = c.post(
        "/api/demo/simulate", json={"transaction_id": p["transaction"]["transaction_id"]}
    ).json()
    return t, o, r, q, p, s


def test_http_lifecycle_offline_idempotent_isolated_and_unchanged_gates(demo_app, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No network, provider or wallet permitted")

    monkeypatch.setattr("app.clients.binance_web3.BinanceWeb3Client.__init__", forbidden)
    monkeypatch.setattr("app.clients.massive.MassiveClient.__init__", forbidden)
    monkeypatch.setattr("httpx.HTTPTransport.handle_request", forbidden)
    monkeypatch.setattr("socket.socket.connect", forbidden)
    with TestClient(demo_app) as c:
        t, o, r, q, p, s = steps(c)
        body = {
            "transaction_id": p["transaction"]["transaction_id"],
            "simulation_id": s["simulation"]["simulation_id"],
        }
        fill = c.post("/api/demo/paper/fills", json=body)
        assert fill.status_code == 200 and fill.json()["position"]["state"] == "OPEN"
        assert c.post("/api/demo/paper/fills", json=body).json() == fill.json()
        key = fill.json()["position"]["position_id"]
        base = "/api/demo/paper/positions/" + key
        assert c.get(base).json() == fill.json()
        assert c.get(base + "/scorecard").status_code == 409
        assert c.post(base + "/exit", json={"observation_id": str(uuid4())}).status_code == 409
        assert c.post(base + "/monitor", json={"signed": True}).status_code == 422
        monitor = c.post(base + "/monitor").json()
        exit = c.post(
            base + "/exit", json={"observation_id": monitor["observation"]["observation_id"]}
        )
        assert exit.status_code == 200 and exit.json()["position"]["state"] == "EXITED"
        score = c.get(base + "/scorecard").json()
        assert score["pnl"] == exit.json()["pnl"] and score["entry"] == fill.json()["fill"]
        assert score["trust_classification"] == "LIKELY_INFORMATION"
        for row in (fill.json(), monitor, exit.json(), score):
            assert row["production_gates"] == t["production_gates"]
            assert row["production_gates"]["TRUST_GATE"] == "BLOCKED"
            assert row["production_gates"]["OPPORTUNITY_GATE"] == "BLOCKED_BY_TRUST"
            assert row["source"] == "DEMO" and row["execution_mode"] == "PAPER"
            assert row["funds_moved"] is row["signed"] is row["transaction_broadcast"] is False
        assert (
            c.post(
                base + "/exit", json={"observation_id": monitor["observation"]["observation_id"]}
            ).status_code
            == 409
        )
        assert c.post(base + "/monitor").status_code == 409
        assert c.post("/api/demo/paper/fills", json=body).json() == exit.json()
        for path in [
            "/api/demo/execute",
            "/api/demo/broadcast",
            "/api/wallet",
            "/api/demo/swap",
            "/api/demo/rfq",
        ]:
            assert c.post(path, json={}).status_code == 404
        with demo_app.state.database.engine.connect() as conn:
            for table in ("trust_samples", "trust_episodes", "trust_assessments"):
                assert conn.execute(text("SELECT count(*) FROM " + table)).scalar() == 0
    assert not Path(demo_app.state.settings.database_url.removeprefix("sqlite:///")).exists()


@pytest.mark.parametrize("scenario", ["steady", "thin-move"])
def test_non_information_api_has_no_paper_records(demo_app, scenario):
    with TestClient(demo_app) as c:
        _, _, r, q, _, _ = steps(c, scenario)
        assert r["risk"]["status"] == "FAIL" and q["status"] == "BLOCKED"
        assert not demo_app.state.demo_paper.rows


def test_unknown_extra_fields_query_flags_and_expired_sources_fail_closed(demo_app):
    with TestClient(demo_app) as c:
        body = {"transaction_id": str(uuid4()), "simulation_id": str(uuid4())}
        assert c.post("/api/demo/paper/fills", json=body).status_code == 410
        assert c.post("/api/demo/paper/fills", json={**body, "signed": True}).status_code == 422
        assert c.post("/api/demo/paper/fills?execute=true", json=body).status_code == 404
        core = demo_app.state.demo_opportunity
        elapsed = [0]
        core.clock = lambda: elapsed[0]
        _, _, _, _, p, s = steps(c)
        elapsed[0] = 30
        assert (
            c.post(
                "/api/demo/paper/fills",
                json={
                    "transaction_id": p["transaction"]["transaction_id"],
                    "simulation_id": s["simulation"]["simulation_id"],
                },
            ).status_code
            == 409
        )
        assert not demo_app.state.demo_paper.rows


def test_live_never_constructs_ledger_or_registers_paper_apis(settings, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Ordinary runtime must not load the paper ledger")

    monkeypatch.setattr("app.main.DemoPaperLedger", forbidden)
    with TestClient(create_app(settings)) as c:
        assert c.post("/api/demo/paper/fills", json={}).status_code == 404
        assert c.get("/api/demo/paper/positions/" + str(uuid4())).status_code == 404
        assert c.get("/api/assets/NVDA/trust").json()["trust_gate"] == "BLOCKED"
        assert "runtime_mode" not in c.get("/api/system-status").json()
