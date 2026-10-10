"""ASGI only; live endpoints cannot bypass gates, authorization or public schemas."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.clients.binance_trading import AGGREGATOR, LiveTradingClient
from app.config import Settings
from app.main import create_app
from app.services.execution_gates import LiveExecutionError
from backend.tests.unit.test_live_execution import claimed


@pytest.fixture
def application(settings):
    return create_app(
        settings.model_copy(update={"execution_worker_token": SecretStr("test-worker")})
    )


def test_default_application_does_not_expose_worker_routes():
    app = create_app(Settings(_env_file=None, app_env="test", database_url="sqlite:///:memory:"))
    with TestClient(app) as client:
        assert not any(
            p.startswith("/api/live") for p in client.get("/openapi.json").json()["paths"]
        )
        assert (
            client.post("/api/live/plans/plan/execute", json={"confirmations": []}).status_code
            == 404
        )


def test_status_and_fills_are_sanitized_and_live_gates_unchanged(client, application):
    state = application.state
    record, _ = claimed(state.live.journal)
    # Inject a legacy raw row to prove endpoint schema protects old unsafe records too.
    state.live.journal.db.execute(
        "UPDATE fills SET evidence=? WHERE action_id=?",
        (
            '{"rfq_signature":"SYNTHETIC_SIGNATURE_SENTINEL","private_key":"SECRET_SENTINEL"}',
            record["action_id"],
        ),
    )
    state.live.journal.db.commit()
    for url in ("/api/live/fills", "/api/live/plans/plan/fills"):
        response = client.get(url)
        assert response.status_code == 200 and "SENTINEL" not in response.text
        assert "evidence" not in response.json()[0]
    statuses = client.get("/api/live/status").json()
    assert statuses["gates"]["TRUST_GATE"] == "BLOCKED"
    assert statuses["gates"]["OPPORTUNITY_GATE"] == "BLOCKED_BY_TRUST"
    assert statuses["gates"]["SWAP_LIVE_GATE"] == "BLOCKED"
    assert not statuses["live_execution"]
    assert client.get("/api/system-status").json()["execution_mode"] == "DRY_RUN"


def test_execute_and_retire_require_worker_auth(client):
    for suffix, body in (("execute", {"confirmations": []}), ("retire", {})):
        response = client.post(f"/api/live/plans/plan/{suffix}", json=body)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "EXECUTION_WORKER_ACCESS_DENIED"


def test_authenticated_worker_cannot_bypass_server_gates_or_retire_unknown():
    settings = Settings(
        _env_file=None,
        app_env="test",
        execution_worker_token=SecretStr("test-worker"),
        database_url="sqlite:///:memory:",
    )
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 1234)) as client:
        headers = {"x-execution-worker-token": "test-worker"}
        app.state.live.prepared["plan"] = [
            SimpleNamespace(
                route=SimpleNamespace(
                    quote=SimpleNamespace(route=SimpleNamespace(executionMode="SWAP"))
                )
            )
        ]
        result = client.post(
            "/api/live/plans/plan/execute", json={"confirmations": []}, headers=headers
        )
        assert (
            result.status_code == 409 and result.json()["error"]["code"] == "SWAP_LIVE_GATE_BLOCKED"
        )
        claimed(app.state.live.journal)
        app.state.live.journal.upsert("action", status="RECONCILIATION_REQUIRED")
        result = client.post("/api/live/plans/plan/retire", headers=headers)
        assert (
            result.status_code == 409
            and result.json()["error"]["code"] == "LEG_UNRESOLVED_RECONCILE_FIRST"
        )
        for invalid in (
            {"origin": "https://evil.example"},
            {"x-forwarded-for": "127.0.0.1"},
            {"origin": "null"},
            {"origin": "https://127.0.0.1"},
        ):
            result = client.post("/api/live/plans/plan/retire", headers={**headers, **invalid})
            assert result.status_code == 403


def test_direct_live_client_transport_authorization_is_gated():
    client = LiveTradingClient(SecretStr("fixture-key"), SecretStr("fixture-secret"))
    try:
        for operation in (
            lambda: client.authorize("POST", AGGREGATOR + "order/submit"),
            lambda: client.submit_rfq(None),
        ):
            try:
                operation()
            except LiveExecutionError as error:
                assert error.code == "RFQ_LIVE_GATE_BLOCKED"
            else:
                raise AssertionError("Live gate bypass")
    finally:
        client.close()
