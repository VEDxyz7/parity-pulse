from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_complete_ask_endpoint_returns_persisted_dry_run(client, caplog):
    response = client.post("/api/exposure/quote", json={"text": "I have $50 of Nvidia"})
    assert response.status_code == 200
    result = response.json()
    assert result["ticker"] == "NVDA" and result["status"] == "DRY_RUN"
    UUID(result["proposal_id"])
    assert result["request_id"] == response.headers["x-request-id"]
    assert result["correlation_id"] == response.headers["x-correlation-id"]
    assert result["run_id"] == response.headers["x-run-id"]
    assert result["requested_budget_usd"] == "50"
    assert isinstance(result["selected"]["token_price_usd"], str)
    assert result["simulation_status"] == "UNAVAILABLE" and result["execution_ready"] is False
    assert result["transaction_broadcast"] is False and result["live_trading_enabled"] is False
    assert client.get(f"/api/exposure/proposals/{result['proposal_id']}").json() == result
    logs = caplog.text
    records = [r for r in caplog.records if r.getMessage() == "DRY_RUN_PROPOSAL_PERSISTED"]
    assert records[-1].event_fields["proposal_id"] == result["proposal_id"]
    assert "DRY_RUN_PROPOSAL_PERSISTED" in logs
    assert "I have $50" not in logs


def test_intent_endpoint_and_quote_use_same_strict_budget(client):
    parsed = client.post("/api/intent/parse", json={"text": "Buy $50 Apple"}).json()
    quote = client.post("/api/exposure/quote", json={"text": "Buy $50 Apple"}).json()
    assert quote["intent"] == parsed and quote["ticker"] == "AAPL"
    assert parsed["approval_required"] is True


@pytest.mark.parametrize(
    "body",
    [
        {"text": "Buy $50 Apple", "live_trading_enabled": True},
        {"text": "Buy $50 Apple", "simulation_status": "PASS"},
        {"text": None},
        {"text": "x" * 241},
    ],
)
def test_request_fields_cannot_enable_live_behavior(client, body):
    assert client.post("/api/exposure/quote", json=body).status_code == 422


def test_proposal_get_not_found_and_invalid_ids(client):
    assert (
        client.get("/api/exposure/proposals/00000000-0000-0000-0000-000000000000").status_code
        == 404
    )
    assert client.get("/api/exposure/proposals/invalid").status_code == 422


def test_readonly_unavailable_credentials_do_not_seed_or_use_demo(tmp_path):
    settings = Settings(
        _env_file=None, data_mode="LIVE_READ_ONLY", database_url=f"sqlite:///{tmp_path}/live.db"
    )
    with TestClient(create_app(settings)) as client:
        result = client.post("/api/exposure/quote", json={"text": "I have $50 of Nvidia"}).json()
        assert result["data_mode"] == "LIVE" and result["status"] == "NO_PROPOSAL"
        assert result["selected"] is None and result["representations"] == []
        assert result["transaction_broadcast"] is False
        assert client.get("/api/system-status").json()["demo_fixture"] is None


def test_secret_in_request_not_logged_or_persisted(tmp_path, capsys):
    secret = "synthetic_secret_value"
    settings = Settings(
        _env_file=None,
        binance_web3_secret_key=secret,
        database_url=f"sqlite:///{tmp_path}/secret.db",
    )
    with TestClient(create_app(settings)) as client:
        for path in ["/api/exposure/quote", "/api/intent/parse"]:
            response = client.post(path, json={"text": "Buy $50 " + secret})
            assert response.status_code == 422 and secret not in response.text
    assert secret not in capsys.readouterr().out
    assert secret.encode() not in (tmp_path / "secret.db").read_bytes()
