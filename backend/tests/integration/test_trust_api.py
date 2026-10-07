from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.clients.common import ProviderError
from app.config import Settings
from app.main import create_app


def test_trust_endpoint_insufficient_demo_persisted_and_non_executable(client, application, caplog):
    response = client.get("/api/assets/NVDA/trust")
    assert response.status_code == 200
    result = response.json()
    UUID(result["assessment_id"])
    assert result["data_mode"] == "DEMO" and result["ticker"] == "NVDA"
    assert result["status"] == "ASSESSED"
    assert result["execution_ready"] is False and result["transaction_broadcast"] is False
    assert result["llm_authoritative"] is False and result["trust_gate"] == "BLOCKED"
    assert result["representations"][0]["classification"] == "INSUFFICIENT_EVIDENCE"
    assert result["representations"][0]["confidence"] is None
    assert isinstance(result["representations"][0]["token_price_usd"], str)
    for name in ["request_id", "correlation_id", "run_id"]:
        assert result[name] == response.headers["x-" + name.replace("_", "-")]
    stored = application.state.trust.repository.get(result["assessment_id"], "DEMO")
    assert stored.model_dump(mode="json") == result
    assert application.state.trust.repository.get(result["assessment_id"], "LIVE") is None
    assert any(record.getMessage() == "TRUST_ASSESSMENT_PERSISTED" for record in caplog.records)
    assert not {"orders", "transactions", "positions", "wallets"} & set(
        inspect(application.state.database.engine).get_table_names()
    )


@pytest.mark.parametrize("path", ["NVDA?live=true", "nvidia", "NVDA%0A", "a" * 16])
def test_trust_input_cannot_enable_behavior_or_accept_unbounded_queries(client, path):
    assert (
        client.get(
            "/api/assets/"
            + path.split("?")[0]
            + "/trust"
            + ("?" + path.split("?")[1] if "?" in path else "")
        ).status_code
        == 422
    )


def test_unsupported_trust_is_explicit_unavailable(client):
    result = client.get("/api/assets/ZZZZ/trust").json()
    assert result["status"] == "UNAVAILABLE" and result["representations"] == []
    assert "NO_VERIFIED_MATCH" in result["limitations"]
    assert result["transaction_broadcast"] is False
    assert client.post("/api/assets/NVDA/trust", json={"execute": True}).status_code == 405


def test_readonly_missing_entitlement_never_uses_demo(tmp_path):
    app = create_app(
        Settings(
            _env_file=None, data_mode="LIVE_READ_ONLY", database_url=f"sqlite:///{tmp_path}/live.db"
        )
    )
    with TestClient(app) as client:
        result = client.get("/api/assets/NVDA/trust").json()
        assert result["data_mode"] == "LIVE" and result["representations"] == []
        assert result["status"] == "UNAVAILABLE" and result["transaction_broadcast"] is False
        assert client.get("/api/system-status").json()["demo_fixture"] is None
        assert all(
            v == "BLOCKED"
            for k, v in client.get("/api/system-status").json()["gates"].items()
            if "LIVE" in k
        )


def test_trust_secret_input_not_persisted_or_logged(tmp_path, capsys):
    secret = "SECRETNVDA"
    app = create_app(
        Settings(
            _env_file=None,
            binance_web3_secret_key=secret,
            database_url=f"sqlite:///{tmp_path}/protected.db",
        )
    )
    with TestClient(app) as client:
        response = client.get(f"/api/assets/{secret}/trust")
        assert response.status_code == 422 and secret not in response.text
    assert secret not in capsys.readouterr().out
    assert secret.encode() not in (tmp_path / "protected.db").read_bytes()


def test_current_403_persists_insufficient_without_referenceprice_fallback(
    client, application, monkeypatch
):
    from backend.tests.unit.test_trust import NOW, inputs

    token, price, _, _ = inputs()
    layer = application.state.data_layer
    original_resolve = layer.discovery.resolve
    found = original_resolve("NVDA")
    found["tokens"] = [token]
    monkeypatch.setattr(layer.discovery, "resolve", lambda _: found)
    monkeypatch.setattr(layer.rwa, "profile", lambda _: token)
    monkeypatch.setattr(
        layer.rwa,
        "observation",
        lambda _: price.model_copy(update={"binance_reference_price": Decimal("100")}),
    )
    monkeypatch.setattr(
        layer.equity,
        "get_snapshot",
        lambda _: (_ for _ in ()).throw(ProviderError("MASSIVE", "PERMISSION_DENIED")),
    )
    monkeypatch.setattr(application.state.trust, "clock", lambda: NOW)
    result = client.get("/api/assets/NVDA/trust").json()
    assert "INDEPENDENT_EQUITY_PERMISSION_DENIED" in result["limitations"]
    row = result["representations"][0]
    assert row["reference"]["observation"] is None
    assert row["economic_comparison"] is None and row["classification"] == "INSUFFICIENT_EVIDENCE"
    assert row["confidence"] is None and result["transaction_broadcast"] is False


def test_trust_database_upgrade_preserves_existing_proposals(tmp_path):
    from sqlalchemy import text

    from app.database import Database

    db = Database(f"sqlite:///{tmp_path}/upgrade.db")
    db.initialize()
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE schema_metadata SET value='3' WHERE key='schema_version'"))
        connection.execute(
            text("INSERT INTO schema_metadata(key,value) VALUES('prior','preserved')")
        )
        for name in ("trust_assessments", "trust_samples", "trust_episodes"):
            connection.execute(text("DROP TABLE " + name))
    db.initialize()
    with db.engine.connect() as connection:
        assert (
            connection.execute(text("SELECT value FROM schema_metadata WHERE key='prior'")).scalar()
            == "preserved"
        )
        assert (
            connection.execute(
                text("SELECT value FROM schema_metadata WHERE key='schema_version'")
            ).scalar()
            == "4"
        )
    assert "exposure_proposals" in inspect(db.engine).get_table_names()
    db.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("token_to_share_ratio", None),
        ("token_to_share_ratio", Decimal("0")),
        ("token_to_share_ratio", Decimal("-1")),
    ],
)
def test_malformed_or_missing_ratio_has_no_positive_assessment(
    client, application, monkeypatch, field, value
):
    from backend.tests.unit.test_trust import NOW, inputs

    token, price, _, _ = inputs()
    malformed = token.model_copy(update={field: value})
    layer = application.state.data_layer
    monkeypatch.setattr(layer.rwa, "profile", lambda _: malformed)
    monkeypatch.setattr(layer.rwa, "observation", lambda _: price)
    monkeypatch.setattr(application.state.trust, "clock", lambda: NOW)
    result = client.get("/api/assets/NVDA/trust").json()
    assert result["status"] == "UNAVAILABLE" and result["representations"] == []
    assert result["transaction_broadcast"] is False
    assert "MALFORMED_OR_CONFLICTING_TRUST_INPUT" in result["limitations"]


@pytest.mark.parametrize("classification", ["NORMAL", "LIKELY_NOISE", "LIKELY_INFORMATION"])
def test_full_api_classifications_with_explicit_synthetic_completed_history(
    client, application, monkeypatch, classification
):
    from datetime import timedelta
    from types import SimpleNamespace

    from backend.tests.unit.test_trust import NOW, history, inputs, news_event, sample

    token, price, equity, _ = inputs()
    info = classification == "LIKELY_INFORMATION"
    normal = classification == "NORMAL"
    deviation = Decimal("0.007" if normal else "0.02")
    price = price.model_copy(
        update={
            "token_price": Decimal("50") * (1 + deviation),
            "volume": Decimal("3000" if info else "1000" if normal else "100"),
            "provider_metadata": {"liquidity": "5000" if normal or info else "10"},
        }
    )
    layer = application.state.data_layer
    found = layer.discovery.resolve("NVDA")
    found["tokens"] = [token]
    monkeypatch.setattr(layer.discovery, "resolve", lambda _: found)
    monkeypatch.setattr(layer.rwa, "profile", lambda _: token)
    monkeypatch.setattr(layer.rwa, "observation", lambda _: price)
    monkeypatch.setattr(layer.equity, "get_snapshot", lambda _: equity)
    monkeypatch.setattr(layer.equity, "get_news", lambda *a, **k: [news_event()] if info else [])
    layer.market = SimpleNamespace(prices=lambda *a, **k: [price])
    service = application.state.trust
    monkeypatch.setattr(service, "clock", lambda: NOW)

    def scope(point):
        return point.model_copy(
            update={
                "issuer": token.platform_id,
                "contract": token.contract,
                "chain_id": token.chain_id,
                "ratio": token.token_to_share_ratio,
            }
        )

    for episode in history(
        outcome="PERSISTED" if info else "REVERSED",
        news="CORROBORATING" if info else "NO_RELEVANT_NEWS",
    ):
        service.repository.save(episode.model_copy(update={"sample": scope(episode.sample)}))
    if normal or info:
        for minutes in range(1, 16):
            service.repository.save(
                scope(
                    sample(
                        NOW - timedelta(minutes=minutes),
                        deviation=str(deviation),
                        news="CORROBORATING" if info else "NO_RELEVANT_NEWS",
                    )
                )
            )
    result = client.get("/api/assets/NVDA/trust").json()
    row = result["representations"][0]
    assert row["classification"] == classification
    assert row["baseline"]["sample_count"] == 40
    assert row["analogues"]["retrieved_sample_count"] == 3
    assert row["economic_comparison"]["deviation"] == str(deviation)
    assert row["evidence_quality"] == "SYNTHETIC_DEMO" and row["confidence"] == "LOW"
    assert row["missing_evidence"] == [] and result["trust_gate"] == "BLOCKED"
    assert result["transaction_broadcast"] is False and result["llm_authoritative"] is False
    assert service.repository.get(result["assessment_id"], "DEMO").model_dump(mode="json") == result
