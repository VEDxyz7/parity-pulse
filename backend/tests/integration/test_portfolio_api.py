"""Public mandate-only portfolio API; host facts and execution never accepted."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from backend.tests.unit.test_portfolio import rules


def body(**updates):
    return {**rules().model_dump(mode="json"), "expected_version": 0, **updates}


def test_default_source_is_explicitly_blocked_and_audited(client):
    assert client.get("/api/portfolio").json()["config"] is None
    assert client.put("/api/portfolio/config", json=body()).status_code == 200
    key = str(uuid4())
    response = client.post("/api/portfolio/drift", json={"idempotency_key": key})
    assert response.status_code == 200
    plan = response.json()
    assert plan["status"] == "BLOCKED" and plan["total_value_usd"] is None
    assert "CURRENT_FUNDING_UNAVAILABLE" in plan["reasons"]
    assert not plan["broadcast"] and not plan["actions"]
    assert client.post("/api/portfolio/plans", json={"idempotency_key": key}).json() == plan
    assert client.get(f"/api/portfolio/plans/{plan['plan_id']}").json() == plan
    assert client.get("/api/portfolio/pending").json()["actions"] == []
    assert len(client.get("/api/portfolio/audit").json()) == 2
    gates = client.get("/api/system-status").json()["gates"]
    assert all(
        gates[g] == "BLOCKED"
        for g in ("SWAP_LIVE_GATE", "RFQ_LIVE_GATE", "AGENTIC_WALLET_LIVE_GATE")
    )
    assert client.get("/api/portfolio").json()["latest_decision"]["plan_id"] == plan["plan_id"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("funding", {}),
        ("positions", []),
        ("routes", []),
        ("trust_state", "NORMAL"),
        ("data_mode", "DEMO"),
        ("live_trading_enabled", True),
        ("execution_mode", "LIVE"),
        ("approval_mode", "AUTO"),
        ("crypto_enabled", True),
        ("expected_version", True),
    ],
)
def test_public_config_cannot_install_authorization_or_mode(client, field, value):
    assert client.put("/api/portfolio/config", json=body(**{field: value})).status_code == 422
    assert client.get("/api/portfolio").json()["config"] is None


def test_version_conflicts_invalid_plan_and_execution_routes(client):
    assert (
        client.post("/api/portfolio/plans", json={"idempotency_key": str(uuid4())}).status_code
        == 409
    )
    assert client.put("/api/portfolio/config", json=body()).status_code == 200
    assert client.put("/api/portfolio/config", json=body()).status_code == 409
    assert client.put("/api/portfolio/config", json=body(expected_version=1)).json()["version"] == 2
    assert client.get("/api/portfolio/plans/" + "a" * 64).status_code == 404
    assert (
        client.post(
            "/api/portfolio/plans", json={"idempotency_key": str(uuid4()), "prices": {}}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/portfolio/plans?execution_mode=LIVE", json={"idempotency_key": str(uuid4())}
        ).status_code
        == 422
    )
    for path in ["execute", "prepare", "sign", "broadcast", "rebalance", "cancel"]:
        assert client.post(f"/api/portfolio/{path}", json={}).status_code == 404


def test_production_demo_instances_do_not_share_configuration(tmp_path):
    common = dict(_env_file=None, app_env="test", database_url=f"sqlite:///{tmp_path}/app.db")
    with (
        TestClient(create_app(Settings(**common))) as live,
        TestClient(create_app(Settings(**common, runtime_mode="DEMO", data_mode="DEMO"))) as demo,
    ):
        assert demo.put("/api/portfolio/config", json=body()).status_code == 200
        assert live.get("/api/portfolio").json()["config"] is None
        assert demo.get("/api/portfolio").json()["config"]["data_mode"] == "DEMO"
        assert live.get("/api/positions").json() == []


def test_autopilot_alias_is_configuration_only(client):
    result = client.post("/api/autopilot", json=body())
    assert result.status_code == 200
    assert client.get("/api/autopilot").json() == client.get("/api/portfolio").json()
    assert client.post("/api/autopilot", json=body(broadcast=True)).status_code == 422
