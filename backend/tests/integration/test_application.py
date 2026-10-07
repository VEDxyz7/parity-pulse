from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_startup_health_and_shutdown(application):
    assert not application.state.ready
    with TestClient(application) as client:
        assert application.state.ready
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["database_status"] == "connected"
    assert not application.state.ready
    assert application.state.database is None


def test_system_status_is_safe_and_does_not_claim_later_capabilities(client):
    response = client.get("/api/system-status")
    assert response.status_code == 200
    status = response.json()
    assert status["execution_mode"] == "DRY_RUN" and status["approval_mode"] == "PROPOSE_ONLY"
    assert status["live_trading_enabled"] is False and status["require_simulation"] is True
    assert status["data_mode"] == "DEMO" and status["phase"] == 2
    assert status["demo_fixture"]["execution_allowed"] is False
    assert status["gates"] == {
        "DATA_GATE": "PASS",
        "DRY_RUN_GATE": "PASS",
        "SWAP_LIVE_GATE": "BLOCKED",
        "RFQ_LIVE_GATE": "BLOCKED",
        "AGENTIC_WALLET_LIVE_GATE": "BLOCKED",
    }
    assert set(status) == {
        "environment",
        "data_mode",
        "execution_mode",
        "approval_mode",
        "live_trading_enabled",
        "require_simulation",
        "database_status",
        "service_version",
        "phase",
        "run_id",
        "gates",
        "demo_fixture",
    }


def test_request_ids_are_unique_and_correlation_is_preserved(client):
    correlation = str(uuid4())
    first = client.get("/api/health", headers={"X-Correlation-ID": correlation})
    second = client.get("/api/system-status", headers={"X-Correlation-ID": correlation})
    assert first.headers["x-correlation-id"] == second.headers["x-correlation-id"] == correlation
    assert first.headers["x-request-id"] != second.headers["x-request-id"]
    for response in [first, second]:
        UUID(response.headers["x-request-id"])
        assert response.headers["x-run-id"] == response.json()["run_id"]


def test_untrusted_ids_replaced_and_errors_keep_ids(client):
    response = client.get("/api/not-a-route", headers={"X-Correlation-ID": "secret=untrusted"})
    assert response.status_code == 404
    UUID(response.headers["x-correlation-id"])
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert response.json()["correlation_id"] == response.headers["x-correlation-id"]
    assert "untrusted" not in response.text


def test_database_failure_is_not_reported_healthy(client, application, monkeypatch):
    monkeypatch.setattr(application.state.database, "healthy", lambda: False)
    assert client.get("/api/health").status_code == 503
    response = client.get("/api/system-status")
    assert response.status_code == 503
    assert response.json()["database_status"] == "unavailable"


def test_live_read_only_does_not_load_demo_data(tmp_path):
    settings = Settings(
        _env_file=None, data_mode="LIVE_READ_ONLY", database_url=f"sqlite:///{tmp_path}/readonly.db"
    )
    with TestClient(create_app(settings)) as client:
        status = client.get("/api/system-status").json()
        assert status["demo_fixture"] is None
        assert status["live_trading_enabled"] is False


def test_unhandled_error_is_sanitized(application):
    @application.get("/test-failure")
    def failure():
        raise RuntimeError("synthetic-private-error-detail")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/test-failure")
        assert response.status_code == 500
        assert "synthetic-private-error-detail" not in response.text
        assert response.json()["request_id"] == response.headers["x-request-id"]


def test_database_startup_failure_refuses_start(application, monkeypatch):
    from app.database import Database

    monkeypatch.setattr(Database, "initialize", lambda _: (_ for _ in ()).throw(RuntimeError()))
    try:
        with TestClient(application):
            raise AssertionError("Startup unexpectedly succeeded")
    except RuntimeError as exc:
        assert "lifecycle failed" in str(exc)
    assert not application.state.ready
