"""Synthetic transport verification, never real provider entitlement evidence."""

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import select

from app.clients.alpaca import AlpacaClient
from app.clients.common import ProviderError
from app.config import Settings
from app.database import Database
from app.models.data import EquityObservation
from app.models.data_tables import EquityObservationRow
from app.providers.alpaca import AlpacaProvider
from app.providers.demo import DemoEquityProvider
from app.providers.massive import MassiveProvider
from app.repositories.data import DataRepository
from app.services.asset_discovery import AssetDiscoveryService
from app.services.data_layer import DataLayer
from app.services.ingestion import HistoricalIngestion

NOW = datetime(2026, 10, 9, 15, tzinfo=UTC)
START, END = "2026-10-08T13:30:00Z", "2026-10-08T13:40:00Z"
QUOTE = {
    "t": "2026-10-09T14:59:50.123456789Z",
    "bp": "200.10",
    "ap": "200.12",
    "bs": "10",
    "as": "20",
}
BAR = {"t": START, "o": "199", "h": "202", "l": "198", "c": "200", "v": "100"}


def provider(handler=None, *, feed="iex", freshness="UNKNOWN", **kwargs):
    calls = []

    def handle(request):
        calls.append(request)
        return (
            handler(request) if handler else httpx.Response(200, json={"quotes": {"NVDA": QUOTE}})
        )

    client = AlpacaClient(
        SecretStr("synthetic-alpaca-key"),
        SecretStr("synthetic-alpaca-secret"),
        http=httpx.Client(transport=httpx.MockTransport(handle)),
        clock=lambda: NOW,
        sleep=lambda _: None,
        min_interval=0,
        **kwargs,
    )
    return AlpacaProvider(client, feed=feed, freshness=freshness), calls


def test_quote_source_precision_midpoint_headers_and_no_entitlement_assumption():
    p, calls = provider()
    row = p.get_snapshot("NVDA")
    assert row.kind == "QUOTE" and row.source == "ALPACA" and row.price == Decimal("200.11")
    assert row.source_timestamp == NOW - timedelta(seconds=9, microseconds=876544)
    assert row.raw_source_timestamp == QUOTE["t"] and row.feed == "iex"
    assert row.data_quality == "UNKNOWN" and row.is_delayed is None
    assert "SINGLE_EXCHANGE_NOT_NBBO" in row.quality_flags
    request = calls[0]
    assert request.url.host == "data.alpaca.markets"
    assert dict(request.url.params) == {"symbols": "NVDA", "feed": "iex", "currency": "USD"}
    assert request.headers["APCA-API-KEY-ID"] == "synthetic-alpaca-key"
    assert request.headers["APCA-API-SECRET-KEY"] == "synthetic-alpaca-secret"
    assert "synthetic" not in str(request.url) + row.model_dump_json()
    assert p.get_latest_quote("NVDA") == row and len(calls) == 1


@pytest.mark.parametrize("feed", ["iex", "sip", "delayed_sip", "boats", "overnight"])
def test_feed_is_explicit_and_not_silently_switched(feed):
    p, calls = provider(feed=feed)
    row = p.get_latest_quote("NVDA")
    assert row.feed == calls[0].url.params["feed"] == feed
    assert row.data_quality == ("DELAYED" if feed == "delayed_sip" else "UNKNOWN")
    if feed in {"boats", "overnight"}:
        assert "OVERNIGHT_NOT_OFFICIAL_REGULAR_REFERENCE" in row.quality_flags


@pytest.mark.parametrize("age,quality", [(120, "LIVE"), (121, "STALE"), (-1, "INVALID")])
def test_configured_realtime_never_overrides_timestamp_quality(age, quality):
    quote = dict(QUOTE, t=(NOW - timedelta(seconds=age)).isoformat())
    p, _ = provider(
        lambda _: httpx.Response(200, json={"quotes": {"NVDA": quote}}), freshness="REALTIME"
    )
    assert p.get_latest_quote("NVDA").data_quality == quality


@pytest.mark.parametrize(
    "patch",
    [
        {"bp": "0"},
        {"ap": "199"},
        {"bp": "NaN"},
        {"bs": 0},
        {"as": None},
        {"t": "2026-10-09T14:59:50"},
    ],
)
def test_malformed_quote_fails_closed(patch):
    p, _ = provider(lambda _: httpx.Response(200, json={"quotes": {"NVDA": dict(QUOTE, **patch)}}))
    with pytest.raises(ProviderError):
        p.get_latest_quote("NVDA")


@pytest.mark.parametrize(
    "quotes", [{}, {"NVDA": None}, {"AAPL": QUOTE}, {"NVDA": QUOTE, "AAPL": QUOTE}]
)
def test_unavailable_or_conflicting_ticker(quotes):
    p, _ = provider(lambda _: httpx.Response(200, json={"quotes": quotes}))
    with pytest.raises(ProviderError):
        p.get_latest_quote("NVDA")


@pytest.mark.parametrize("status", [401, 403, 422])
def test_denial_does_not_retry_fallback_or_echo(status):
    p, calls = provider(
        lambda _: httpx.Response(status, json={"message": "synthetic-alpaca-secret"})
    )
    with pytest.raises(ProviderError) as caught:
        p.get_latest_quote("NVDA")
    assert len(calls) == 1 and caught.value.http_status == status
    assert "synthetic" not in str(caught.value) + json.dumps(p.client.evidence)


def test_rate_limit_bounded_and_secret_echo_rejected():
    p, calls = provider(lambda _: httpx.Response(429, headers={"Retry-After": "120"}))
    for _ in range(2):
        with pytest.raises(ProviderError):
            p.get_latest_quote("NVDA")
    assert len(calls) == 1
    p, _ = provider(lambda _: httpx.Response(200, json={"echo": "synthetic-alpaca-secret"}))
    with pytest.raises(ProviderError, match="UNSAFE_RESPONSE"):
        p.get_latest_quote("NVDA")
    p, _ = provider(lambda _: httpx.Response(200, json={"code": 403, "message": "denied"}))
    with pytest.raises(ProviderError, match="BUSINESS_FAILURE"):
        p.get_latest_quote("NVDA")


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/v2/orders"),
        ("GET", "/v2/account"),
        ("DELETE", "/v2/orders"),
        ("GET", "https://evil.invalid/v2/stocks/bars"),
        ("GET", "/v2/stocks/bars/../orders"),
        ("POST", "/v2/stocks/quotes/latest"),
    ],
)
def test_non_data_operations_never_reach_transport(method, path):
    p, calls = provider()
    with pytest.raises(ProviderError, match="READ_ONLY"):
        p.client.read(method, path)
    assert not calls


def test_missing_credentials_and_body_never_reach_transport():
    p, calls = provider()
    with pytest.raises(ProviderError, match="READ_ONLY"):
        p.client.read("GET", "/v2/stocks/bars", body={})
    p.client.api_key = None
    with pytest.raises(ProviderError, match="NOT_CONFIGURED"):
        p.get_latest_quote("NVDA")
    assert not calls


def test_bars_page_token_feed_raw_adjustment_and_persisted_idempotency():
    def handler(request):
        second = "page_token" in request.url.params
        assert request.url.params["feed"] == "sip"
        assert request.url.params["adjustment"] == "raw" and request.url.params["asof"] == "-"
        return httpx.Response(
            200,
            json={
                "bars": {"NVDA": [dict(BAR, t="2026-10-08T13:35:00Z") if second else BAR]},
                "next_page_token": None if second else "page-2",
            },
        )

    p, calls = provider(handler, feed="sip")
    rows = p.get_historical_bars("NVDA", START, END, multiplier=5)
    assert len(calls) == len(rows) == 2 and p.last_page_complete
    assert all(
        r.interval == "5minute"
        and r.data_quality == "HISTORICAL"
        and r.adjusted is False
        and "HISTORICAL_REVISION_ASOF_UNVERIFIED" in r.quality_flags
        for r in rows
    )
    db = Database("sqlite:///:memory:")
    db.initialize()
    try:
        repo = DataRepository(db)
        assert repo.save(rows) == 2 and repo.save(rows) == 0
        assert len(repo.list(EquityObservation, mode="LIVE")) == 2
        assert repo.list(EquityObservation, mode="DEMO") == []
    finally:
        db.close()


def test_bar_page_bounds_and_partial_coverage():
    p, calls = provider(
        lambda _: httpx.Response(200, json={"bars": {"NVDA": [BAR]}, "next_page_token": "more"})
    )
    assert len(p.get_historical_bars("NVDA", START, END, max_pages=1)) == 1
    assert len(calls) == 1 and p.last_page_complete is False
    with pytest.raises(ProviderError, match="ORDER"):
        p.get_historical_bars("NVDA", START, END, max_pages=2)


@pytest.mark.parametrize(
    "bar", [dict(BAR, t="2026-10-08T13:00:00Z"), dict(BAR, h="190"), dict(BAR, v=-1)]
)
def test_bad_historical_data_is_not_accepted(bar):
    p, _ = provider(lambda _: httpx.Response(200, json={"bars": {"NVDA": [bar]}}))
    with pytest.raises(ProviderError):
        p.get_historical_bars("NVDA", START, END)


def test_incomplete_bar_and_unsupported_history_feed():
    p, _ = provider(
        lambda _: httpx.Response(200, json={"bars": {"NVDA": [dict(BAR, t=NOW.isoformat())]}})
    )
    with pytest.raises(ProviderError, match="INCOMPLETE"):
        p.get_historical_bars("NVDA", NOW.isoformat(), (NOW + timedelta(minutes=1)).isoformat())
    p, calls = provider(feed="delayed_sip")
    with pytest.raises(ProviderError, match="FEED_NOT_SUPPORTED"):
        p.get_historical_bars("NVDA", START, END)
    assert not calls


def test_legacy_json_without_additive_fields_is_still_idempotent():
    p, _ = provider()
    # Emulate pre-adapter Massive data lacking the new optional fields.
    row = p.get_latest_quote("NVDA").model_copy(
        update={"source": "MASSIVE", "feed": None, "is_delayed": None, "quality_flags": ()}
    )
    db = Database("sqlite:///:memory:")
    db.initialize()
    try:
        repo = DataRepository(db)
        repo.save([row])
        with db.sessions.begin() as session:
            saved = session.scalar(select(EquityObservationRow))
            payload = json.loads(saved.payload)
            for key in ("feed", "is_delayed", "quality_flags"):
                payload.pop(key)
            saved.payload = json.dumps(payload)
        assert repo.save([row]) == 0
    finally:
        db.close()


def test_feed_identity_is_part_of_persisted_key():
    db = Database("sqlite:///:memory:")
    db.initialize()
    try:
        repo = DataRepository(db)
        assert (
            repo.save([provider(feed=f)[0].get_latest_quote("NVDA") for f in ("iex", "sip")]) == 2
        )
    finally:
        db.close()


def test_explicit_provider_selection_no_demo_or_massive_fallback():
    db = Database("sqlite:///:memory:")
    db.initialize()
    try:
        for choice in ("MASSIVE", "ALPACA"):
            layer = DataLayer(
                Settings(_env_file=None, data_mode="LIVE_READ_ONLY", equity_provider=choice), db
            )
            try:
                assert isinstance(layer.news, MassiveProvider)
                assert isinstance(
                    layer.equity, AlpacaProvider if choice == "ALPACA" else MassiveProvider
                )
                if choice == "ALPACA":
                    with pytest.raises(ProviderError, match="NOT_CONFIGURED"):
                        layer.equity.get_snapshot("NVDA")
                    with pytest.raises(ProviderError, match="CHECKPOINT_NOT_SUPPORTED"):
                        HistoricalIngestion(layer.repository, equity=layer.equity).equity_bars(
                            "NVDA", "2026-10-08", "2026-10-08"
                        )
            finally:
                layer.close()
        demo = DataLayer(Settings(_env_file=None, equity_provider="ALPACA"), db)
        assert isinstance(demo.equity, DemoEquityProvider) and demo.clients == []
        assert demo.news is demo.equity
    finally:
        db.close()


def test_alpaca_secrets_config_redaction_and_invalid_policy():
    s = Settings(
        _env_file=None,
        alpaca_api_key="synthetic-alpaca-key",
        alpaca_secret_key="synthetic-alpaca-secret",
    )
    assert "synthetic" not in repr(s) + s.model_dump_json()
    assert s.redaction_values() == ("synthetic-alpaca-key", "synthetic-alpaca-secret")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, alpaca_feed="made-up")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, equity_provider="AUTO")


def test_alpaca_is_not_automatically_admitted_to_trust():
    from app.services.trust_evidence import IndependentReferenceService
    from backend.tests.unit.test_trust import inputs

    token, price, equity, regime = inputs()
    at = regime.evaluated_at
    token = token.model_copy(
        update={
            "source": "BINANCE_RWA",
            "data_mode": "LIVE",
            "data_quality": "LIVE",
            "chain_id": "56",
            "contract": "0x" + "a" * 40,
        }
    )
    price = price.model_copy(
        update={
            "data_mode": "LIVE",
            "data_quality": "LIVE",
            "chain_id": token.chain_id,
            "contract": token.contract,
        }
    )
    equity = equity.model_copy(
        update={"source": "ALPACA", "data_mode": "LIVE", "data_quality": "LIVE"}
    )
    result = IndependentReferenceService().evaluate(token, price, equity, regime, at, "LIVE")
    assert result.status != "AVAILABLE"
    assert "REFERENCE_SOURCE_NOT_INDEPENDENT_VERIFIED" in result.reason_codes


def diagnostic_module():
    path = Path(__file__).parents[3] / "scripts/verify-alpaca-readonly.py"
    spec = importlib.util.spec_from_file_location("verify_alpaca", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_diagnostic_reports_observed_freshness_without_certifying_feed():
    def handler(request):
        data = (
            {"quotes": {"NVDA": QUOTE}}
            if request.url.path.endswith("latest")
            else {"bars": {"NVDA": [BAR]}, "next_page_token": None}
        )
        return httpx.Response(200, json=data)

    p, calls = provider(handler)
    report = diagnostic_module().diagnose(p, START, END)
    assert len(calls) == 3 and all(c.method == "GET" for c in calls)
    assert report["feed_entitlement"] == "NOT_VERIFIED" and report["trust_eligible"] is False
    assert report["checks"][0]["within_120_seconds"] is True
    assert report["checks"][1]["count"] == report["checks"][2]["count"] == 1
    assert "synthetic" not in json.dumps(report)


def test_diagnostic_missing_credentials_proves_no_http_calls():
    p, calls = provider()
    p.client.api_key = None
    report = diagnostic_module().diagnose(p, START, END)
    assert calls == []
    assert all(r["status"] == "NOT_CONFIGURED" and r["requests"] == [] for r in report["checks"])


def test_diagnostic_requires_explicit_readonly_authorization(monkeypatch):
    monkeypatch.setattr("sys.argv", ["verify-alpaca-readonly.py", "--start", START, "--end", END])
    with pytest.raises(SystemExit) as caught:
        diagnostic_module().main()
    assert caught.value.code == 2


def test_data_layer_uses_selected_equity_and_keeps_news_failure_separate():
    from backend.tests.integration.test_data_providers import providers

    db = Database("sqlite:///:memory:")
    db.initialize()
    layer = DataLayer(
        Settings(_env_file=None, data_mode="LIVE_READ_ONLY", equity_provider="ALPACA"), db
    )
    rwa, market, _ = providers()
    p, calls = provider()
    try:
        layer.rwa, layer.market, layer.equity = rwa, market, p
        layer.discovery = AssetDiscoveryService(rwa, market)
        found = layer.discovery.resolve("Nvidia")
        # The existing profile fixture covers Ondo; do not pretend it describes BStock.
        found["tokens"] = [t for t in found["tokens"] if t.platform_id == "ondo"]
        layer.discovery.resolve = lambda _: found
        result = layer.asset("Nvidia")
        assert result["data_mode"] == "LIVE" and len(result["tokens"]) == 1
        assert result["equity_observations"][0].source == "ALPACA"
        assert result["limitations"]["news"] == "NOT_CONFIGURED"
        assert len(calls) == 1
        assert layer.repository.list(EquityObservation, mode="LIVE")[0].feed == "iex"
        assert layer.repository.list(EquityObservation, mode="DEMO") == []
    finally:
        layer.close()
        rwa.client.close()
        p.client.close()
        db.close()


@pytest.mark.parametrize("mode", ["DEMO", "LIVE_READ_ONLY"])
def test_public_gates_and_no_startup_fetch_with_alpaca_selected(mode, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app

    def deny_send(*args, **kwargs):
        pytest.fail("No provider or execution request permitted in this inspection")

    monkeypatch.setattr(httpx.Client, "send", deny_send)
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite:///:memory:",
            data_mode=mode,
            equity_provider="ALPACA",
        )
    )
    # TestClient sends through its own overridden send; keep external clients trapped.
    with TestClient(app) as client:
        status = client.get("/api/system-status").json()
        assert status["gates"]["DATA_GATE"] == "PASS"
        assert status["gates"]["DRY_RUN_GATE"] == "PASS"
        assert all(v == "BLOCKED" for k, v in status["gates"].items() if "LIVE" in k)
        workspace = client.get("/api/workspace").json()
        assert workspace["production_gates"]["TRUST_GATE"] == "BLOCKED"
        assert workspace["production_gates"]["OPPORTUNITY_GATE"] == "BLOCKED_BY_TRUST"
        assert workspace["execution_ready"] is workspace["broadcast"] is False
