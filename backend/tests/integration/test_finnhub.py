"""Offline Finnhub protocol/normalization verification, never entitlement evidence."""

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.clients.common import ProviderError
from app.clients.finnhub import FinnhubClient
from app.config import Settings
from app.database import Database
from app.models.data import EquityObservation, NewsEvent
from app.models.events import CompanyNewsEvent, EventBatch
from app.providers.alpaca import AlpacaProvider
from app.providers.finnhub import FinnhubEventProvider
from app.providers.massive import MassiveProvider
from app.services.calendar import USEquityCalendar
from app.services.data_layer import DataLayer

NOW = datetime(2026, 10, 10, 12, tzinfo=UTC)
START, END = "2026-10-03", "2026-10-10"
PATHS = {
    "/company-news": "company_news",
    "/calendar/earnings": "earnings_calendar",
    "/stock/market-status": "market_status",
    "/stock/market-holiday": "market_holiday",
}
FIXTURES = Path(__file__).parents[1] / "fixtures/finnhub"


def fixture(name):
    return json.loads((FIXTURES / (name + ".json")).read_text())


def provider(
    *, raw=None, path="/company-news", handler=None, key="synthetic-finnhub-key", **kwargs
):
    calls = []

    def handle(request):
        calls.append(request)
        if handler:
            return handler(request)
        body = (
            raw
            if raw is not None and request.url.path == "/api/v1" + path
            else fixture(PATHS[request.url.path.removeprefix("/api/v1")])
        )
        return httpx.Response(200, json=body)

    kwargs.setdefault("attempts", 1)
    kwargs.setdefault("clock", lambda: NOW)
    client = FinnhubClient(
        SecretStr(key) if key is not None else None,
        http=httpx.Client(transport=httpx.MockTransport(handle)),
        sleep=lambda _: None,
        min_interval=0,
        **kwargs,
    )
    return FinnhubEventProvider(client), calls


def news(p):
    return p.get_company_news("NVDA", START, END)


def test_all_four_endpoints_use_shared_fixed_host_and_header_auth():
    p, calls = provider()
    news(p)
    p.get_earnings_calendar("NVDA", END, "2027-01-08")
    p.get_market_status()
    p.get_market_holidays()
    assert len(calls) == 4 and {r.url.path for r in calls} == {"/api/v1" + p for p in PATHS}
    for request in calls:
        assert request.method == "GET" and request.url.host == "finnhub.io"
        assert request.headers["X-Finnhub-Token"] == "synthetic-finnhub-key"
        assert "synthetic-finnhub-key" not in str(request.url)
    assert dict(calls[0].url.params) == {"symbol": "NVDA", "from": START, "to": END}
    assert not hasattr(p, "get_news") and not hasattr(p, "get_latest_quote")
    assert not hasattr(p, "get_historical_bars")


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/company-news"),
        ("GET", "/quote"),
        ("GET", "/stock/candle"),
        ("GET", "/orders"),
        ("GET", "https://evil.invalid/company-news"),
    ],
)
def test_disallowed_operations_never_reach_transport(method, path):
    p, calls = provider()
    with pytest.raises(ProviderError, match="READ_ONLY"):
        p.client.read(method, path)
    assert not calls


@pytest.mark.parametrize(
    "body,params", [({}, {}), (None, {"token": "secret"}), (None, {"apiKey": "secret"})]
)
def test_no_body_or_query_credentials(body, params):
    p, calls = provider()
    with pytest.raises(ProviderError, match="READ_ONLY"):
        p.client.read("GET", "/company-news", params, body)
    assert not calls


@pytest.mark.parametrize("key", [None, ""])
def test_unavailable_credentials_no_request(key):
    p, calls = provider(key=key)
    with pytest.raises(ProviderError, match="NOT_CONFIGURED"):
        news(p)
    assert not calls


def test_config_reuses_exact_name_excludes_and_redacts_secret(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "synthetic-finnhub-key")
    settings = Settings(_env_file=None)
    assert settings.finnhub_api_key.get_secret_value() == "synthetic-finnhub-key"
    assert "synthetic-finnhub-key" not in repr(settings) + settings.model_dump_json()
    assert settings.redaction_values() == ("synthetic-finnhub-key",)
    assert Settings(_env_file=None, finnhub_api_key="").finnhub_api_key is None


def test_news_preserves_source_publication_retrieval_mapping_and_date():
    p, _ = provider()
    batch = news(p)
    row = batch.records[0]
    assert isinstance(batch, EventBatch) and isinstance(row, CompanyNewsEvent)
    assert row.source == "FINNHUB_EVENTS" and row.publisher == "Synthetic Publisher"
    assert row.provider_identifier == "NEWS:1001" and row.related_tickers == ("NVDA", "TSLA")
    assert row.ticker_mapping == "PROVIDER_CONFIRMED"
    assert row.published_timestamp == row.source_timestamp == datetime(2026, 10, 9, 15, tzinfo=UTC)
    assert row.ingestion_timestamp == NOW and row.event_date.isoformat() == "2026-10-09"
    assert row.data_quality == "HISTORICAL" and row.timestamp_unit == "s"
    assert row.raw_source_timestamp == str(fixture("company_news")[0]["datetime"])
    assert not batch.coverage_complete and batch.status == "PARTIAL"


def test_news_duplicate_identity_and_order_are_deterministic():
    rows = fixture("company_news")
    p, _ = provider(raw=[rows[1], rows[0], rows[0]])
    batch = news(p)
    q, _ = provider(raw=[rows[0], rows[1], rows[0]])
    assert batch == news(q)
    assert batch.duplicate_count == 1 and len(batch.records) == 2 and not batch.rejections


def test_conflicting_same_id_quarantines_all_versions():
    rows = fixture("company_news")
    conflict = dict(rows[0], headline="Different synthetic version")
    p, _ = provider(raw=[rows[0], conflict, rows[1]])
    batch = news(p)
    assert [r.provider_identifier for r in batch.records] == ["NEWS:1002"]
    assert [(r.row, r.reason) for r in batch.rejections] == [
        (0, "CONFLICTING_EVENT_ID"),
        (1, "CONFLICTING_EVENT_ID"),
    ]


@pytest.mark.parametrize("stamp", [None, 0, "omit"])
def test_missing_publication_never_becomes_ingestion_timestamp(stamp):
    row = fixture("company_news")[0]
    row["datetime"] = stamp
    if stamp == "omit":
        del row["datetime"]
    p, _ = provider(raw=[row])
    event = news(p).records[0]
    assert event.published_timestamp is event.source_timestamp is event.event_date is None
    assert event.data_quality == "MISSING" and "MISSING_PUBLICATION_TIME" in event.quality_flags
    assert event.ingestion_timestamp == NOW


@pytest.mark.parametrize("field", ["headline", "source", "url"])
def test_missing_metadata_is_explicit(field):
    row = fixture("company_news")[0]
    del row[field]
    p, _ = provider(raw=[row])
    result = news(p).records[0]
    assert result.data_quality == "MISSING" and result.quality_flags


def test_missing_related_is_request_scope_only():
    row = fixture("company_news")[0]
    del row["related"]
    p, _ = provider(raw=[row])
    result = news(p).records[0]
    assert result.ticker == "NVDA" and result.related_tickers == ()
    assert result.ticker_mapping == "REQUEST_SCOPE_ONLY" and result.data_quality == "UNKNOWN"


@pytest.mark.parametrize(
    "patch",
    [
        {"datetime": True},
        {"datetime": -1},
        {"datetime": "1791558000"},
        {"datetime": int((NOW + timedelta(days=1)).timestamp())},
        {"datetime": 1700000000},
        {"related": "TSLA"},
        {"url": "javascript:bad"},
        {"url": "https://user:password@example.com"},
        {"id": 0},
    ],
)
def test_invalid_news_is_quarantined_not_promoted(patch):
    row = dict(fixture("company_news")[0], **patch)
    p, _ = provider(raw=[row])
    result = news(p)
    assert result.status == "UNAVAILABLE" and not result.records
    assert result.rejections[0].reason == "INVALID_EVENT"


@pytest.mark.parametrize(
    "start,end", [("bad", END), (END, START), ("2026-01-01", END), (START, "2026-10-11")]
)
def test_news_bounds_rejected_before_request(start, end):
    p, calls = provider()
    with pytest.raises(ValueError):
        p.get_company_news("NVDA", start, end)
    assert not calls


def test_earnings_date_and_fiscal_period_are_not_publication_time():
    p, _ = provider()
    result = p.get_earnings_calendar("NVDA", END, "2027-01-08").records[0]
    assert result.event_date.isoformat() == "2026-11-17" and result.fiscal_year == 2027
    assert result.timing == "AFTER_CLOSE" and result.provider_hour == "amc"
    assert result.published_timestamp is result.source_timestamp is None
    assert result.ingestion_timestamp == NOW and result.data_quality == "UNKNOWN"
    assert "PUBLICATION_TIME_UNAVAILABLE" in result.quality_flags


@pytest.mark.parametrize(
    "patch",
    [
        {"symbol": "TSLA"},
        {"date": "2026-02-30"},
        {"quarter": 5},
        {"year": "2027"},
        {"date": "2028-01-01"},
    ],
)
def test_malformed_earnings_or_context_rejected(patch):
    raw = fixture("earnings_calendar")
    raw["earningsCalendar"][0].update(patch)
    p, _ = provider(raw=raw, path="/calendar/earnings")
    result = p.get_earnings_calendar("NVDA", END, "2027-01-08")
    assert not result.records and result.rejections


def test_unknown_earnings_hour_is_not_invented():
    raw = fixture("earnings_calendar")
    raw["earningsCalendar"][0]["hour"] = "unexpected"
    p, _ = provider(raw=raw, path="/calendar/earnings")
    row = p.get_earnings_calendar("NVDA", END, "2027-01-08").records[0]
    assert row.timing == "UNKNOWN" and row.provider_hour == "unexpected"


def test_holidays_preserve_schedule_dates_and_malformed_hours():
    p, _ = provider()
    rows = p.get_market_holidays().records
    closed, early, malformed = rows
    assert closed.kind == "CLOSED" and closed.regular_open is None
    assert early.kind == "EARLY_CLOSE" and early.regular_close == datetime(
        2026, 11, 27, 18, tzinfo=UTC
    )
    assert early.postmarket_close == datetime(2026, 11, 27, 22, tzinfo=UTC)
    assert malformed.raw_postmarket_hours == "13:00:17:00" and malformed.postmarket_close is None
    assert malformed.data_quality == "INVALID" and malformed.source_timestamp is None
    assert early.published_timestamp is None and early.ingestion_timestamp == NOW


@pytest.mark.parametrize("day,utc_hour", [("2026-03-06", 14), ("2026-03-09", 13)])
def test_calendar_dst_wall_times_are_converted_with_date(day, utc_hour):
    raw = fixture("market_holiday")
    raw["data"] = [dict(raw["data"][1], atDate=day)]
    p, _ = provider(raw=raw, path="/stock/market-holiday")
    row = p.get_market_holidays().records[0]
    assert row.regular_open.hour == utc_hour and row.regular_open.minute == 30


@pytest.mark.parametrize(
    "day,hours",
    [("2026-03-08", "02:30-04:00"), ("2026-11-01", "01:30-04:00"), ("2026-11-27", "13:00-09:30")],
)
def test_ambiguous_nonexistent_or_reversed_hours_are_not_guessed(day, hours):
    raw = fixture("market_holiday")
    raw["data"] = [dict(raw["data"][0], atDate=day, tradingHour=hours)]
    p, _ = provider(raw=raw, path="/stock/market-holiday")
    row = p.get_market_holidays().records[0]
    assert row.regular_open is row.regular_close is None and row.data_quality == "INVALID"


def test_missing_holiday_hours_is_not_a_closed_market_claim():
    raw = fixture("market_holiday")
    raw["data"] = [{"atDate": "2026-11-27", "eventName": "Synthetic incomplete"}]
    p, _ = provider(raw=raw, path="/stock/market-holiday")
    row = p.get_market_holidays().records[0]
    assert row.kind == "UNKNOWN" and row.data_quality == "MISSING"


@pytest.mark.parametrize(
    "age,quality", [(0, "UNKNOWN"), (121, "STALE"), (-10, "INVALID"), (None, "MISSING")]
)
def test_status_time_is_actual_provider_time_not_receipt(age, quality):
    raw = fixture("market_status")
    raw["t"] = int((NOW - timedelta(seconds=age)).timestamp()) if age is not None else None
    p, _ = provider(raw=raw, path="/stock/market-status")
    row = p.get_market_status()
    assert row.data_quality == quality and row.ingestion_timestamp == NOW
    assert row.session == "UNKNOWN" and not row.is_open


@pytest.mark.parametrize("patch", [{"exchange": "L"}, {"timezone": "UTC"}, {"isOpen": "false"}])
def test_conflicting_market_context_fails_closed(patch):
    raw = dict(fixture("market_status"), **patch)
    p, _ = provider(raw=raw, path="/stock/market-status")
    with pytest.raises(ProviderError):
        p.get_market_status()


def test_utc_normalization_preserves_instant_and_rejects_naive_provenance():
    p, _ = provider(clock=lambda: NOW.astimezone(ZoneInfo("Asia/Kolkata")))
    row = news(p).records[0]
    assert row.ingestion_timestamp == NOW and row.ingestion_timestamp.tzinfo == UTC
    for field in ("source_timestamp", "ingestion_timestamp", "published_timestamp"):
        payload = row.model_dump()
        payload[field] = NOW.replace(tzinfo=None)
        with pytest.raises(ValidationError):
            CompanyNewsEvent.model_validate(payload)


@pytest.mark.parametrize(
    "status,kind",
    [(401, "UNAUTHORIZED"), (403, "FORBIDDEN"), (429, "RATE_LIMITED"), (500, "HTTP_FAILURE")],
)
def test_provider_errors_are_sanitized(status, kind):
    p, calls = provider(
        handler=lambda _: httpx.Response(status, json={"error": "synthetic-finnhub-key"})
    )
    with pytest.raises(ProviderError, match=kind) as error:
        news(p)
    assert len(calls) == 1 and "synthetic-finnhub-key" not in str(error.value) + str(
        p.client.evidence
    )


@pytest.mark.parametrize("raw", [{"error": "denied"}, {"message": "limit"}, "bad"])
def test_business_and_non_json_object_failures(raw):
    p, _ = provider(raw=raw)
    with pytest.raises(ProviderError):
        news(p)


def test_credential_echo_and_malformed_duplicate_json_are_rejected():
    for text in ('[{"echo":"synthetic-finnhub-key"}]', '{"a":1,"a":2}', "not json"):
        p, _ = provider(handler=lambda _, text=text: httpx.Response(200, text=text))
        with pytest.raises(ProviderError):
            news(p)


def test_timeout_retries_are_bounded_and_do_not_leak_request():
    def timeout(request):
        raise httpx.ReadTimeout("untrusted exception", request=request)

    p, calls = provider(handler=timeout, attempts=2)
    with pytest.raises(ProviderError, match="TRANSPORT_UNAVAILABLE"):
        news(p)
    assert len(calls) == 2


def test_long_retry_after_stops_future_reads_without_sleeping_or_hammering():
    p, calls = provider(
        handler=lambda _: httpx.Response(429, headers={"Retry-After": "120"}), attempts=3
    )
    for _ in range(2):
        with pytest.raises(ProviderError):
            news(p)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "method,path,raw",
    [
        ("get_company_news", "/company-news", {}),
        ("get_earnings_calendar", "/calendar/earnings", {"earningsCalendar": {}}),
        (
            "get_market_holidays",
            "/stock/market-holiday",
            {"exchange": "US", "timezone": "America/New_York", "data": {}},
        ),
    ],
)
def test_wrong_response_collections_never_become_empty_success(method, path, raw):
    p, _ = provider(raw=raw, path=path)
    args = ("NVDA", START, END) if method != "get_market_holidays" else ()
    with pytest.raises(ProviderError):
        getattr(p, method)(*args)


def test_repeat_fetch_has_stable_identity_without_backdating_new_receipt():
    clock = [NOW]
    p, calls = provider(clock=lambda: clock[0])
    first = news(p).records[0]
    clock[0] += timedelta(hours=1)
    p.client.cache.clear()
    second = news(p).records[0]
    assert first.provider_identifier == second.provider_identifier
    assert first.published_timestamp == second.published_timestamp
    assert first.ingestion_timestamp == NOW and second.ingestion_timestamp == clock[0]
    assert len(calls) == 2


def test_live_events_opt_in_preserves_equity_news_calendar_and_never_fetches(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected network")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    settings = Settings(
        _env_file=None,
        data_mode="LIVE_READ_ONLY",
        equity_provider="ALPACA",
        finnhub_api_key="synthetic-finnhub-key",
        database_url=f"sqlite:///{tmp_path}/test.db",
    )
    database = Database(settings.database_url)
    database.initialize()
    layer = DataLayer(settings, database)
    try:
        assert isinstance(layer.events, FinnhubEventProvider)
        assert isinstance(layer.equity, AlpacaProvider) and isinstance(layer.news, MassiveProvider)
        assert isinstance(layer.calendar, USEquityCalendar)
    finally:
        layer.close()
        database.close()


def test_explicit_event_reads_do_not_persist_or_replace_trust_news(monkeypatch, tmp_path):
    events, calls = provider()
    monkeypatch.setattr("app.services.data_layer.FinnhubClient", lambda *_: events.client)
    settings = Settings(
        _env_file=None,
        data_mode="LIVE_READ_ONLY",
        finnhub_api_key="synthetic-finnhub-key",
        database_url=f"sqlite:///{tmp_path}/events.db",
    )
    database = Database(settings.database_url)
    database.initialize()
    layer = DataLayer(settings, database)
    try:
        result = news(layer.events)
        assert len(result.records) == 2 and len(calls) == 1
        assert isinstance(layer.news, MassiveProvider)
        assert layer.repository.list(NewsEvent, mode="LIVE") == []
        assert layer.repository.list(EquityObservation, mode="LIVE") == []
    finally:
        layer.close()
        database.close()


def test_demo_or_missing_key_has_no_event_reader(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("DEMO/missing key must not construct Finnhub")

    monkeypatch.setattr("app.services.data_layer.FinnhubClient", forbidden)
    for mode in ("DEMO", "LIVE_READ_ONLY"):
        settings = Settings(
            _env_file=None,
            data_mode=mode,
            finnhub_api_key="synthetic-finnhub-key" if mode == "DEMO" else None,
            database_url=f"sqlite:///{tmp_path}/{mode}.db",
        )
        db = Database(settings.database_url)
        db.initialize()
        layer = DataLayer(settings, db)
        assert layer.events is None
        layer.close()
        db.close()


def load_diagnostic():
    path = Path(__file__).parents[3] / "scripts/verify-finnhub-events.py"
    spec = importlib.util.spec_from_file_location("verify_finnhub_events", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_diagnostic_missing_credentials_and_secret_free_bounded_summary():
    module = load_diagnostic()
    p, calls = provider(key=None)
    result = module.diagnose(p, ("NVDA",), START, END, END, "2027-01-08")
    assert not calls and result["request_count"] == 0
    assert all(c["status"] == "NOT_CONFIGURED" for c in result["checks"])
    p, calls = provider()
    result = module.diagnose(p, ("NVDA",), START, END, END, "2027-01-08")
    assert len(calls) == result["request_count"] == 4
    assert "synthetic-finnhub-key" not in json.dumps(result)
    assert "headline" not in result["checks"][2]["result"]["samples"][0]
    assert result["checks"][2]["result"]["normalized_count"] == 2


def test_diagnostic_requires_flag_and_refuses_overwrite_before_client(monkeypatch, tmp_path):
    module = load_diagnostic()
    output = tmp_path / "evidence.json"
    base = [
        "verify-finnhub-events.py",
        "--news-start",
        START,
        "--news-end",
        END,
        "--earnings-start",
        END,
        "--earnings-end",
        "2027-01-08",
        "--output",
        str(output),
    ]

    def forbidden(*args, **kwargs):
        raise AssertionError("Must reject before client construction")

    monkeypatch.setattr(module, "DiagnosticClient", forbidden)
    monkeypatch.setattr("sys.argv", base)
    with pytest.raises(SystemExit):
        module.main()
    output.write_text("preserve")
    monkeypatch.setattr("sys.argv", base + ["--live-read-only"])
    with pytest.raises(SystemExit):
        module.main()
    assert output.read_text() == "preserve"
