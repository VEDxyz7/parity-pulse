import io
import json
import logging

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.utils.logging import JsonFormatter


def test_public_responses_and_logs_never_contain_secrets(tmp_path, capsys):
    secret = "synthetic-provider-secret-value"
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path}/safe.db",
        binance_web3_api_key=secret,
        binance_web3_secret_key=secret,
        massive_api_key=secret,
        llm_api_key=secret,
    )
    with TestClient(create_app(settings)) as client:
        for path in ["/api/health", "/api/system-status", "/openapi.json"]:
            response = client.get(path)
            assert secret not in response.text
            assert "binance_web3_secret_key" not in response.text
        try:
            raise RuntimeError(secret)
        except RuntimeError:
            logging.getLogger("uvicorn.error").exception("SYNTHETIC_SERVER_FAILURE")
    assert secret not in capsys.readouterr().out


def test_log_redactor_scrubs_values_and_drops_sensitive_metadata():
    stream = io.StringIO()
    logger = logging.Logger("redaction-test")
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(("synthetic-log-secret",)))
    logger.addHandler(handler)
    logger.warning(
        "synthetic-log-secret Authorization=abc Bearer unknown-token",
        extra={
            "event_fields": {"api_key": "do-not-retain", "run_id": "safe-run"},
        },
    )
    logged = stream.getvalue()
    assert all(
        value not in logged
        for value in [
            "synthetic-log-secret",
            "abc",
            "unknown-token",
            "do-not-retain",
        ]
    )
    assert json.loads(logged)["run_id"] == "safe-run"
    logger.warning(
        "NESTED_METADATA",
        extra={
            "event_fields": {"run_id": {"secret": "synthetic-log-secret"}},
        },
    )
    assert "synthetic-log-secret" not in stream.getvalue()


def test_frontend_input_cannot_change_config_or_activate_execution(client):
    assert client.post("/api/system-status", json={"live_trading_enabled": True}).status_code == 405
    response = client.get("/api/system-status?execution_mode=LIVE&live_trading_enabled=true")
    assert response.json()["execution_mode"] == "DRY_RUN"
    assert response.json()["live_trading_enabled"] is False
    for route in [
        "/api/orders",
        "/api/rfq/submit",
        "/api/broadcast",
        "/api/wallet/settings",
    ]:
        assert client.post(route, json={}).status_code == 404
    assert client.post("/api/portfolio", json={}).status_code == 405
    assert client.post("/api/autopilot", json={}).status_code == 422
    assert (
        client.put("/api/portfolio/config", json={"live_trading_enabled": True}).status_code == 422
    )
    # Phase 7 adds analytical scanning only; unvalidated or execution-bearing input is rejected.
    assert client.post("/api/opportunities/scan", json={}).status_code == 422
    assert (
        client.post(
            "/api/opportunities/scan",
            json={
                "budget_usd": "100",
                "risk_budget_usd": "10",
                "time_window": "PRE_OPEN",
                "live_trading_enabled": True,
            },
        ).status_code
        == 422
    )


def test_exact_allowlisted_data_and_proposal_routes(client):
    paths = set(client.get("/openapi.json").json()["paths"])
    assert paths == {
        "/api/health",
        "/api/system-status",
        "/api/assets",
        "/api/assets/{ticker}",
        "/api/assets/{ticker}/trust",
        "/api/intent/parse",
        "/api/exposure/quote",
        "/api/exposure/proposals/{proposal_id}",
        "/api/opportunities/scan",
        "/api/opportunities/{run_id}",
        "/api/positions",
        "/api/positions/{position_id}",
        "/api/portfolio",
        "/api/portfolio/config",
        "/api/autopilot",
        "/api/portfolio/drift",
        "/api/portfolio/plans",
        "/api/portfolio/plans/{plan_id}",
        "/api/portfolio/pending",
        "/api/portfolio/audit",
    }
    for path in ("/api/positions", "/api/positions/00000000-0000-4000-8000-000000000001"):
        assert client.post(path, json={"state": "OPEN", "broadcast": True}).status_code == 405
