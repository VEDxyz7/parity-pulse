import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import select
from test_data_providers import NOW, fixture, providers

from app.clients.common import ProviderError
from app.clients.massive import MassiveClient
from app.database import Database
from app.models.data import (
    EquityObservation,
    TokenMetadata,
    TokenObservation,
)
from app.models.data_tables import TokenObservationRow
from app.providers.demo import load_data_fixture
from app.providers.massive import MassiveProvider
from app.repositories.data import DataRepository
from app.services.calendar import USEquityCalendar
from app.services.ingestion import HistoricalIngestion


def equity(handler=None, freshness="UNKNOWN", mode="LIVE"):
    calls = []

    def response(request):
        calls.append(request)
        if handler:
            return handler(request)
        path = request.url.path
        name = (
            "minute_bars"
            if "/aggs/" in path
            else "news"
            if path.endswith("/news")
            else "status"
            if path.endswith("/now")
            else "holidays"
            if path.endswith("/upcoming")
            else "splits"
            if path.endswith("/splits")
            else "dividends"
        )
        return httpx.Response(200, text=json.dumps(fixture(name, "massive"), default=str))

    client = MassiveClient(
        SecretStr("synthetic-massive"),
        http=httpx.Client(transport=httpx.MockTransport(response)),
        min_interval=0,
        sleep=lambda _: None,
        clock=lambda: NOW,
    )
    return MassiveProvider(client, mode=mode, freshness=freshness), calls


def test_massive_real_fixtures_history_news_status_holidays_actions():
    p, calls = equity()
    bars = p.get_historical_bars("NVDA", "2026-10-05", "2026-10-05")
    assert len(bars) == 945 and bars[0].close == Decimal(
        fixture("minute_bars", "massive")["results"][0]["c"]
    )
    assert bars[0].data_quality == "HISTORICAL" and bars[0].source == "MASSIVE"
    news = p.get_news("NVDA", max_pages=1)
    assert len(news) == 2 and news[0].published_timestamp != news[0].ingestion_timestamp
    assert news[0].headline == fixture("news", "massive")["results"][0]["title"]
    assert news[0].raw_source_timestamp == fixture("news", "massive")["results"][0]["published_utc"]
    assert p.get_market_status().state in {"open", "closed", "extended-hours"}
    assert len(p.get_market_holidays()) == 24
    actions = p.get_corporate_actions("NVDA")
    assert {a["kind"] for a in actions} == {"splits", "dividends"}
    assert all("apiKey" in r.url.params for r in calls)


def test_snapshot_quote_ns_precision_delayed_and_unknown_entitlements():
    timestamp = 1791288000123456789

    def handler(request):
        if "/nbbo/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "status": "OK",
                    "results": {
                        "T": "NVDA",
                        "p": "100.00000000000000000001",
                        "P": "100.00000000000000000003",
                        "t": timestamp,
                        "y": timestamp,
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "status": "DELAYED",
                "ticker": {
                    "ticker": "NVDA",
                    "lastTrade": {"p": "100.1234567890123456789", "t": 1791287100123456789},
                },
            },
        )

    p, _ = equity(handler)
    quote = p.get_latest_quote("NVDA")
    assert quote.price == Decimal("100.00000000000000000002")
    assert quote.raw_source_timestamp == str(timestamp) and quote.timestamp_unit == "ns"
    assert quote.data_quality == "UNKNOWN"  # A successful request is not plan-wide real-time proof.
    snapshot = p.get_snapshot("NVDA")
    assert snapshot.data_quality == "DELAYED" and snapshot.source == "MASSIVE"
    assert snapshot.raw_source_timestamp == "1791287100123456789"
    assert snapshot.price == Decimal("100.1234567890123456789")


@pytest.mark.parametrize("status", [401, 403])
def test_missing_entitlement_has_no_binance_or_demo_fallback(status):
    p, calls = equity(
        lambda r: httpx.Response(
            status, json={"status": "NOT_AUTHORIZED", "message": "synthetic-massive"}
        )
    )
    with pytest.raises(ProviderError) as error:
        p.get_snapshot("NVDA")
    assert len(calls) == 1 and "synthetic-massive" not in str(error.value)


def test_snapshot_missing_fields_invalid_ohlc_and_future_news():
    p, _ = equity(
        lambda r: httpx.Response(
            200, json={"status": "OK", "ticker": {"ticker": "NVDA", "day": {"c": 100}}}
        )
    )
    row = p.get_snapshot("NVDA")
    assert row.price is None and row.data_quality == "MISSING" and row.source_timestamp is None
    p, _ = equity(
        lambda r: httpx.Response(
            200,
            json={
                "status": "OK",
                "results": [
                    {
                        "id": "x",
                        "title": "not instructions",
                        "publisher": {"name": "Publisher"},
                        "tickers": ["NVDA"],
                        "article_url": "https://example.invalid",
                        "published_utc": "2027-01-01T00:00:00Z",
                    }
                ],
            },
        )
    )
    with pytest.raises(ProviderError, match="FUTURE_NEWS"):
        p.get_news("NVDA", before=NOW)
    base = load_data_fixture()["equities"][0].model_dump()
    base.update(open="5", high="4", low="1", close="5")
    with pytest.raises(ValidationError):
        EquityObservation.model_validate(base)


def test_massive_pagination_dedup_and_safe_origin():
    page1 = fixture("minute_bars", "massive")
    page1["results"] = page1["results"][:1]
    page1["next_url"] = (
        "https://api.massive.com/v2/aggs/ticker/NVDA/range/1/minute/1791187200001/2026-10-05?cursor=second&apiKey=discard-me"
    )
    page2 = dict(page1)
    page2.pop("next_url")

    def handler(r):
        return httpx.Response(
            200, text=json.dumps(page2 if r.url.params.get("cursor") == "second" else page1)
        )

    p, calls = equity(handler)
    assert len(p.get_historical_bars("NVDA", "2026-10-05", "2026-10-05", max_pages=2)) == 2
    assert len(calls) == 2
    page1["next_url"] = "https://evil.invalid/steal"
    p, _ = equity(lambda r: httpx.Response(200, text=json.dumps(page1)))
    with pytest.raises(ProviderError, match="UNSAFE_PAGINATION"):
        p.get_historical_bars("NVDA", "2026-10-05", "2026-10-05")


@pytest.mark.parametrize(
    "instant,state",
    [
        ("2026-10-06T12:00:00Z", "PREMARKET"),
        ("2026-10-06T15:00:00Z", "REGULAR"),
        ("2026-10-06T21:00:00Z", "POSTMARKET"),
        ("2026-10-06T02:00:00Z", "WEEKDAY_OVERNIGHT"),
        ("2026-10-10T15:00:00Z", "WEEKEND"),
        ("2026-04-03T15:00:00Z", "HOLIDAY"),
    ],
)
def test_calendar_sessions(instant, state):
    calendar = USEquityCalendar()
    row = calendar.status(datetime.fromisoformat(instant.replace("Z", "+00:00")))
    assert row.state == state and row.next_open.tzinfo == UTC


def test_calendar_dst_early_close_reopen_multiday_and_boundaries():
    c = USEquityCalendar()
    assert c.session(datetime(2026, 3, 6).date())[0].hour == 14
    assert c.session(datetime(2026, 3, 9).date())[0].hour == 13
    assert c.session(datetime(2026, 11, 2).date())[0].hour == 14
    early = c.status(datetime(2026, 11, 27, 17, tzinfo=UTC))
    assert early.early_close and early.next_close.hour == 18
    closure = c.status(datetime(2026, 4, 4, 12, tzinfo=UTC))
    assert closure.multi_day_closure and closure.next_open.date().isoformat() == "2026-04-06"
    reopened = c.status(datetime(2026, 4, 6, 15, tzinfo=UTC))
    assert reopened.reopening
    with pytest.raises(ProviderError, match="OUTSIDE"):
        c.status(datetime(2025, 12, 1, tzinfo=UTC))
    with pytest.raises(ValueError):
        c.status(datetime(2026, 10, 6))


def test_last_actual_regular_close_not_last_after_hours_bar():
    p, _ = equity()
    close = p.get_previous_regular_close("NVDA", NOW, USEquityCalendar())
    assert (
        close.kind == "REGULAR_CLOSE"
        and close.source_timestamp.hour == 19
        and close.source_timestamp.minute == 59
    )
    assert close.price == next(
        b.close
        for b in p.get_historical_bars("NVDA", "2026-10-05", "2026-10-05")
        if b.source_timestamp == close.source_timestamp
    )


def test_repository_decimal_text_idempotence_conflicts_and_mode_isolation(tmp_path):
    db = Database(f"sqlite:///{tmp_path}/data.db")
    db.initialize()
    repo = DataRepository(db)
    demo = load_data_fixture()["tokens"][0]
    assert repo.save([demo]) == 1 and repo.save([demo, demo]) == 0
    live = TokenObservation.model_validate(
        dict(
            demo.model_dump(), data_mode="LIVE", data_quality="HISTORICAL", source="BINANCE_MARKET"
        )
    )
    assert repo.save([live]) == 1
    assert repo.list(TokenObservation, mode="DEMO") == [demo]
    assert repo.list(TokenObservation, mode="LIVE") == [live]
    with db.sessions() as session:
        rows = session.scalars(select(TokenObservationRow)).all()
        assert all("200.1234567890123456789" in r.payload for r in rows)
    altered = TokenObservation.model_validate(dict(live.model_dump(), token_price="201"))
    with pytest.raises(ProviderError, match="CONFLICTING"):
        repo.save([altered])
    with pytest.raises(ValueError):
        repo.list(TokenObservation, mode="LIVE_READ_ONLY")
    reopened = Database(f"sqlite:///{tmp_path}/data.db")
    reopened.initialize()
    assert DataRepository(reopened).list(TokenObservation, mode="LIVE")[0].token_price == Decimal(
        "200.1234567890123456789"
    )
    db.close()
    reopened.close()


def test_metadata_ratio_versions_and_ingestion_resumption(tmp_path):
    db = Database(f"sqlite:///{tmp_path}/data.db")
    db.initialize()
    repo = DataRepository(db)
    rwa, market, _ = providers()
    token = rwa.tokens()[0]
    assert repo.save([token]) == 1
    changed = TokenMetadata.model_validate(dict(token.model_dump(), token_to_share_ratio="2"))
    assert repo.save([changed]) == 1
    assert len(repo.list(TokenMetadata, mode="LIVE")) == 2
    ingest = HistoricalIngestion(repo, market=market)
    result = ingest.token_candles(token, bar="1h", max_pages=1, limit=10)
    assert result["inserted"] == 10 and result["complete"] is False
    calls = []

    class EmptyMarket:
        def candles(self, token, **kwargs):
            calls.append(kwargs)
            return []

    ingest.market = EmptyMarket()
    resumed = ingest.token_candles(token, bar="1h", max_pages=1, limit=10)
    assert (
        resumed["complete"] and resumed["inserted"] == 0 and calls[0]["after"] == result["cursor"]
    )
    assert (
        repo.resume(mode="DEMO", resource=f"candles:{token.chain_id}:{token.contract}:1h:None:None")
        is None
    )
    db.close()


def test_equity_ingestion_idempotent_paginated_and_resumable(tmp_path):
    db = Database(f"sqlite:///{tmp_path}/data.db")
    db.initialize()
    repo = DataRepository(db)
    first = fixture("minute_bars", "massive")
    first["results"] = first["results"][:1]
    second = dict(first)
    second["results"] = fixture("minute_bars", "massive")["results"][1:2]
    first["next_url"] = (
        "https://api.massive.com/v2/aggs/ticker/NVDA/range/1/minute/1791187200001/2026-10-05?cursor=second&apiKey=discard-me"
    )
    p, calls = equity(
        lambda r: httpx.Response(
            200, text=json.dumps(second if r.url.params.get("cursor") == "second" else first)
        )
    )
    ingest = HistoricalIngestion(repo, equity=p)
    result = ingest.equity_bars("NVDA", "2026-10-05", "2026-10-05", max_pages=1)
    assert result["inserted"] == 1 and result["complete"] is False
    assert "apiKey" not in repo.resume(
        mode="LIVE", resource="equity:/v2/aggs/ticker/NVDA/range/1/minute/2026-10-05/2026-10-05"
    )
    resumed = ingest.equity_bars("NVDA", "2026-10-05", "2026-10-05", max_pages=1)
    assert resumed["inserted"] == 1 and resumed["complete"] is True
    assert len(repo.list(EquityObservation, mode="LIVE")) == 2
    assert ingest.equity_bars("NVDA", "2026-10-05", "2026-10-05", max_pages=2)["inserted"] == 0
    db.close()


def test_data_api_decimal_strings_demo_boundary_and_no_execution(client, application):
    first = client.get("/api/assets").json()
    assert first["data_mode"] == "DEMO" and len(first["assets"]) == 2
    detail = client.get("/api/assets/Apple").json()
    assert detail["status"] == "DEMO" and detail["asset"]["ticker"] == "AAPL"
    assert detail["token_observations"][0]["token_price"] == "200.1234567890123456789"
    assert detail["equity_observations"][0]["source"] == "DEMO_EQUITY"
    assert (
        detail["equity_observations"][0]["price"] != detail["token_observations"][0]["token_price"]
    )
    assert client.get("/api/assets/UNAVAILABLE").json()["status"] == "UNAVAILABLE"
    assert client.post("/api/assets", json={"execution_mode": "LIVE"}).status_code == 405
    assert client.get("/api/system-status").json()["gates"]["RFQ_LIVE_GATE"] == "BLOCKED"
    assert all(
        r.data_mode == "DEMO"
        for r in application.state.data_layer.repository.list(TokenObservation, mode="DEMO")
    )


def test_provider_api_failure_has_safe_status_and_no_demo_fallback(tmp_path):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    app = create_app(
        Settings(
            _env_file=None, data_mode="LIVE_READ_ONLY", database_url=f"sqlite:///{tmp_path}/live.db"
        )
    )
    with TestClient(app) as client:
        result = client.get("/api/assets")
        assert result.status_code == 503 and result.json()["error"]["code"] == "NOT_CONFIGURED"
        assert not app.state.data_layer.repository.list(TokenObservation, mode="LIVE")
        assert not app.state.data_layer.repository.list(TokenObservation, mode="DEMO")


def test_trade_ingestion_idempotence_and_nonadvancing_cursor(tmp_path):
    db = Database(f"sqlite:///{tmp_path}/trades.db")
    db.initialize()
    repo = DataRepository(db)
    rwa, market, _ = providers()
    token = rwa.tokens()[0]
    ingest = HistoricalIngestion(repo, market=market)
    first = ingest.token_trades(token, max_pages=1, limit=5, resume=False)
    assert first["inserted"] == 5 and not first["complete"]
    assert ingest.token_trades(token, max_pages=1, limit=5, resume=False)["inserted"] == 0
    with pytest.raises(ProviderError, match="PAGINATION_NOT_ADVANCING"):
        ingest.token_trades(token, max_pages=1, limit=5)
    assert all(
        r.token_price is None and r.data_quality == "CONFLICTING"
        for r in repo.list(TokenObservation, mode="LIVE")
    )
    assert repo.list(TokenObservation, mode="DEMO") == []
    db.close()
