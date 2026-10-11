import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app

ORIGIN = "https://frontend.example.test"


@pytest.fixture
def cors_app():
    return create_app(
        Settings(
            _env_file=None,
            app_env="production",
            runtime_mode="DEMO",
            cors_origins=(ORIGIN,),
        )
    )


def preflight(client, origin=ORIGIN, method="POST", headers="content-type,x-correlation-id"):
    return client.options(
        "/api/presentation/research",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": headers,
        },
    )


def test_default_has_no_cross_origin_permission(client):
    assert client.get("/api/health").status_code == 200
    response = preflight(client)
    assert response.status_code == 405
    assert "access-control-allow-origin" not in response.headers


def test_allowlist_environment_normalizes_and_deduplicates(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        json.dumps([" HTTPS://FRONTEND.EXAMPLE.TEST:443/ ", ORIGIN, "http://[::1]:5173/"]),
    )
    assert Settings(_env_file=None).cors_origins == (ORIGIN, "http://[::1]:5173")


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_explicit_loopback_development_preflight(origin):
    app = create_app(Settings(_env_file=None, runtime_mode="DEMO", cors_origins=(origin,)))
    with TestClient(app) as client:
        response = preflight(client, origin=origin)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_invalid_environment_refuses_factory_without_exposing_configuration(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", json.dumps(["https://private-config@example.test"]))
    with pytest.raises(RuntimeError, match="startup refused") as caught:
        create_app()
    assert "private-config" not in str(caught.value)


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "null",
        "https://*.example.test",
        "//frontend.example.test",
        "https:/frontend.example.test",
        "http://frontend.example.test",
        "https://user:password@frontend.example.test",
        "https://@frontend.example.test",
        "https://frontend.example.test/path/..",
        "https://frontend.example.test/?",
        "https://frontend.example.test/#",
        "https://frontend.example.test?query=value",
        "https://frontend.example.test#fragment",
        "https://frontend.example.test\\evil",
        "https://frontend.example.test\nevil",
        "https://%66rontend.example.test",
        "https://frontend.example.test:0",
        "https://frontend.example.test:99999",
    ],
)
def test_invalid_origin_configuration_refuses_startup(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=(origin,))


@pytest.mark.parametrize("method", ["GET", "POST", "PUT"])
def test_required_preflights_without_cookie_permission(cors_app, method):
    with TestClient(cors_app) as client:
        response = preflight(client, method=method)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == ORIGIN
        assert "access-control-allow-credentials" not in response.headers
        assert set(response.headers["access-control-allow-methods"].split(", ")) == {
            "GET", "POST", "PUT"
        }
        assert "Origin" in response.headers["vary"]


@pytest.mark.parametrize("origin", ["https://unlisted.example.test", ORIGIN + ".evil", "null"])
def test_unlisted_origins_receive_no_cors_permission(cors_app, origin):
    with TestClient(cors_app) as client:
        response = preflight(client, origin=origin)
        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers
        # CORS controls browser access, not authentication or server-side admission.
        read = client.get("/api/health", headers={"Origin": origin})
        assert read.status_code == 200
        assert "access-control-allow-origin" not in read.headers


@pytest.mark.parametrize(
    ("method", "headers"),
    [("DELETE", "content-type"), ("PATCH", "content-type"), ("POST", "authorization"),
     ("POST", "x-execution-worker-token"), ("POST", "x-forwarded-for")],
)
def test_unnecessary_methods_and_privileged_headers_fail_preflight(cors_app, method, headers):
    with TestClient(cors_app) as client:
        assert preflight(client, method=method, headers=headers).status_code == 400


def test_success_and_handled_errors_expose_ids_without_changing_safety(cors_app):
    @cors_app.get("/test-unavailable")
    def unavailable():
        raise HTTPException(503)

    @cors_app.get("/test-unhandled")
    def unhandled():
        raise RuntimeError("synthetic-error-details-must-stay-private")

    with TestClient(cors_app, raise_server_exceptions=False) as client:
        for path, status in [("/api/health", 200), ("/api/missing", 404),
                             ("/test-unavailable", 503), ("/test-unhandled", 500)]:
            response = client.get(path, headers={"Origin": ORIGIN})
            assert response.status_code == status
            assert response.headers["access-control-allow-origin"] == ORIGIN
            assert set(response.headers["access-control-expose-headers"].split(", ")) == {
                "X-Request-ID", "X-Correlation-ID", "X-Run-ID"
            }
            assert response.headers["x-request-id"]
            assert "synthetic-error-details" not in response.text
        invalid = client.post(
            "/api/presentation/research", json={"ticker": "UNSUPPORTED"}, headers={"Origin": ORIGIN}
        )
        assert invalid.status_code == 422
        assert invalid.headers["access-control-allow-origin"] == ORIGIN
        status = client.get("/api/system-status", headers={"Origin": ORIGIN}).json()
        assert status["runtime_mode"] == status["data_mode"] == "DEMO"
        assert status["execution_mode"] == "DRY_RUN"
        assert status["approval_mode"] == "PROPOSE_ONLY"
        assert status["live_trading_enabled"] is False and status["require_simulation"] is True
        assert cors_app.state.settings.llm_enabled is False
        assert status["gates"]["SWAP_LIVE_GATE"] == "BLOCKED"
        assert status["gates"]["RFQ_LIVE_GATE"] == "BLOCKED"
        assert status["gates"]["AGENTIC_WALLET_LIVE_GATE"] == "BLOCKED"
        assert client.get("/api/assets/NVDA/trust").json()["trust_gate"] == "BLOCKED"
        paths = client.get("/openapi.json").json()["paths"]
        assert not any(p.startswith("/api/live/") for p in paths)


def test_cors_does_not_grant_remote_access_to_local_agent_tools(cors_app):
    with TestClient(
        cors_app, base_url="https://backend.example.test", client=("198.51.100.1", 12345)
    ) as client:
        response = client.post(
            "/api/agent/tools/get_portfolio", json={}, headers={"Origin": ORIGIN}
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "TOOL_ACCESS_DENIED"
        assert response.headers["access-control-allow-origin"] == ORIGIN
