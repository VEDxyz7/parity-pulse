"""Bounded event context; never an EquityDataProvider or authoritative exchange calendar."""

import re
from datetime import date, datetime, time, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, StrictStr, ValidationError

from app.clients.common import ProviderError
from app.models.data import quality_at, source_time, utc
from app.models.events import (
    CompanyNewsEvent,
    EarningsCalendarEvent,
    EventBatch,
    EventRejection,
    MarketHoliday,
    USMarketStatus,
)
from app.providers.massive import ticker_path

NY = ZoneInfo("America/New_York")


class WireModel(BaseModel):
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)


class Article(WireModel):
    id: StrictInt
    datetime: StrictInt | None = None
    headline: StrictStr | None = None
    source: StrictStr | None = None
    url: StrictStr | None = None
    related: StrictStr | None = None
    category: StrictStr | None = None


class Earnings(WireModel):
    symbol: StrictStr
    date: StrictStr
    hour: StrictStr | None = None
    year: StrictInt | None = None
    quarter: StrictInt | None = None


class Holiday(WireModel):
    atDate: StrictStr
    eventName: StrictStr | None = None
    tradingHour: StrictStr | None = None
    postMarket: StrictStr | None = None


class Status(WireModel):
    exchange: StrictStr
    timezone: StrictStr
    isOpen: StrictBool
    session: StrictStr | None = None
    holiday: StrictStr | None = None
    t: StrictInt | None = None


def iso_day(value):
    if not isinstance(value, str) or not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Explicit ISO date required")
    return date.fromisoformat(value)


def date_bounds(start, end, max_days):
    begin, finish = iso_day(start), iso_day(end)
    if not 0 <= (finish - begin).days < max_days:
        raise ValueError("Invalid or unbounded event date window")
    return begin, finish


def optional_text(value):
    return value.strip() or None if value is not None else None


def provenance(identifier, received, raw=None, *, quality="UNKNOWN", flags=()):
    observed = source_time(raw * 1000) if raw not in (None, 0) else None
    return dict(
        provider_identifier=identifier,
        source_timestamp=observed,
        raw_source_timestamp=str(raw) if raw is not None else None,
        timestamp_unit="s" if raw is not None else "UNKNOWN",
        ingestion_timestamp=received,
        data_mode="LIVE",
        data_quality=quality,
        quality_flags=tuple(sorted(set(flags))),
    )


def session_hours(value, day):
    if value in (None, ""):
        return None, None
    if not re.fullmatch(r"[0-2][0-9]:[0-5][0-9]-[0-2][0-9]:[0-5][0-9]", value):
        raise ValueError("Malformed session hours")
    results = []
    for clock in value.split("-"):
        local = datetime.combine(day, time.fromisoformat(clock))
        a, b = local.replace(tzinfo=NY, fold=0), local.replace(tzinfo=NY, fold=1)
        # Reject ambiguous/nonexistent DST wall times instead of guessing a fold.
        if a.utcoffset() != b.utcoffset() or utc(a).astimezone(NY).replace(tzinfo=None) != local:
            raise ValueError("Ambiguous session timezone")
        results.append(utc(a))
    if results[0] >= results[1]:
        raise ValueError("Invalid session order")
    return tuple(results)


class FinnhubEventProvider:
    def __init__(self, client):
        self.client = client

    def batch(self, model, endpoint, rows, received, normalize, **context):
        if not isinstance(rows, list) or len(rows) > 2000:
            raise ProviderError("FINNHUB", "PAYLOAD_SCHEMA_INVALID")
        groups, rejected = {}, []
        for index, row in enumerate(rows):
            try:
                record = normalize(row)
                groups.setdefault(record.provider_identifier, []).append((index, record))
            except (ValidationError, ValueError, TypeError, KeyError, OverflowError):
                rejected.append(EventRejection(row=index, reason="INVALID_EVENT"))
        records, duplicates = [], 0
        for group in groups.values():
            first = group[0][1]
            if any(record != first for _, record in group[1:]):
                rejected.extend(
                    EventRejection(row=index, reason="CONFLICTING_EVENT_ID") for index, _ in group
                )
            else:
                duplicates += len(group) - 1
                records.append(first)
        return EventBatch[model](
            endpoint=endpoint,
            ingestion_timestamp=received,
            status="UNAVAILABLE" if rows and not records else "PARTIAL",
            received_count=len(rows),
            duplicate_count=duplicates,
            records=tuple(sorted(records, key=lambda r: r.provider_identifier)),
            rejections=tuple(sorted(rejected, key=lambda r: r.row)),
            **context,
        )

    def get_company_news(self, ticker, start, end):
        ticker = ticker_path(ticker)
        begin, finish = date_bounds(start, end, 31)
        if finish > utc(self.client.clock()).date():
            raise ValueError("News window cannot end in the future")
        data, received, _ = self.client.read(
            "GET", "/company-news", {"symbol": ticker, "from": start, "to": end}, ttl=30
        )

        def normalize(raw):
            row = Article.model_validate(raw)
            if row.id <= 0:
                raise ValueError("Invalid news identity")
            related = tuple(
                sorted(
                    {ticker_path(s.strip()) for s in (row.related or "").split(",") if s.strip()}
                )
            )
            if related and ticker not in related:
                raise ValueError("Conflicting news ticker")
            flags = []
            if not related:
                flags.append("REQUEST_SCOPE_TICKER_ONLY")
            prov = provenance("NEWS:" + str(row.id), received, row.datetime)
            published = prov["source_timestamp"]
            if published and (
                published > received + timedelta(seconds=5)
                or not begin <= published.date() <= finish
            ):
                raise ValueError("Publication outside observation window")
            if published is None:
                flags.append("MISSING_PUBLICATION_TIME")
            headline, publisher, url = map(optional_text, (row.headline, row.source, row.url))
            for name, value in (("HEADLINE", headline), ("PUBLISHER", publisher), ("URL", url)):
                if value is None:
                    flags.append("MISSING_" + name)
            if url:
                parts = urlsplit(url)
                if (
                    parts.scheme not in {"https", "http"}
                    or not parts.hostname
                    or parts.username
                    or parts.password
                ):
                    raise ValueError("Unsafe event URL")
            quality = (
                "MISSING"
                if any(f.startswith("MISSING_") for f in flags)
                else "UNKNOWN"
                if flags
                else "HISTORICAL"
            )
            prov.update(data_quality=quality, quality_flags=tuple(sorted(flags)))
            return CompanyNewsEvent(
                **prov,
                ticker=ticker,
                related_tickers=related,
                ticker_mapping="PROVIDER_CONFIRMED" if related else "REQUEST_SCOPE_ONLY",
                headline=headline,
                publisher=publisher,
                url=url,
                published_timestamp=published,
                event_date=published.date() if published else None,
                categories=(row.category,) if row.category else (),
            )

        return self.batch(
            CompanyNewsEvent,
            "/company-news",
            data,
            received,
            normalize,
            ticker=ticker,
            requested_start=begin,
            requested_end=finish,
        )

    def get_earnings_calendar(self, ticker, start, end):
        ticker = ticker_path(ticker)
        begin, finish = date_bounds(start, end, 366)
        data, received, _ = self.client.read(
            "GET", "/calendar/earnings", {"symbol": ticker, "from": start, "to": end}, ttl=60
        )
        if not isinstance(data, dict):
            raise ProviderError("FINNHUB", "PAYLOAD_SCHEMA_INVALID")

        def normalize(raw):
            row = Earnings.model_validate(raw)
            day = iso_day(row.date)
            if row.symbol != ticker or not begin <= day <= finish:
                raise ValueError("Conflicting earnings context")
            if (
                row.year is not None
                and not 2000 <= row.year <= 2100
                or row.quarter is not None
                and not 1 <= row.quarter <= 4
            ):
                raise ValueError("Invalid fiscal period")
            timing = {"bmo": "BEFORE_OPEN", "amc": "AFTER_CLOSE", "dmh": "DURING_SESSION"}.get(
                row.hour, "UNKNOWN"
            )
            flags = ["PUBLICATION_TIME_UNAVAILABLE", "SCHEDULE_REVISION_ASOF_UNVERIFIED"]
            if timing == "UNKNOWN":
                flags.append("UNKNOWN_EARNINGS_HOUR")
            return EarningsCalendarEvent(
                **provenance(f"EARNINGS:{ticker}:{day}", received, flags=flags),
                ticker=ticker,
                event_date=day,
                fiscal_year=row.year,
                fiscal_quarter=row.quarter,
                provider_hour=row.hour,
                timing=timing,
            )

        return self.batch(
            EarningsCalendarEvent,
            "/calendar/earnings",
            data.get("earningsCalendar"),
            received,
            normalize,
            ticker=ticker,
            requested_start=begin,
            requested_end=finish,
        )

    @staticmethod
    def us_context(data):
        if (
            not isinstance(data, dict)
            or data.get("exchange") != "US"
            or data.get("timezone") != "America/New_York"
        ):
            raise ProviderError("FINNHUB", "CONFLICTING_EXCHANGE_CONTEXT")

    def get_market_status(self):
        data, received, _ = self.client.read(
            "GET", "/stock/market-status", {"exchange": "US"}, ttl=10
        )
        self.us_context(data)
        try:
            row = Status.model_validate(data)
            prov = provenance("US:MARKET_STATUS", received, row.t)
            flags = []
            observed = prov["source_timestamp"]
            if observed is None:
                flags.append("MISSING_STATUS_TIME")
            session = {
                "pre-market": "PREMARKET",
                "regular": "REGULAR",
                "post-market": "POSTMARKET",
            }.get(row.session, "UNKNOWN")
            if session == "UNKNOWN" and (row.session is not None or row.isOpen):
                flags.append("UNKNOWN_SESSION")
            prov.update(
                data_quality=quality_at("LIVE", observed, received, base="UNKNOWN"),
                quality_flags=tuple(flags),
            )
            return USMarketStatus(
                **prov,
                is_open=row.isOpen,
                session=session,
                provider_session=row.session,
                holiday=row.holiday,
            )
        except (ValueError, TypeError, OverflowError):
            raise ProviderError("FINNHUB", "PAYLOAD_SCHEMA_INVALID") from None

    def get_market_holidays(self):
        data, received, _ = self.client.read(
            "GET", "/stock/market-holiday", {"exchange": "US"}, ttl=3600
        )
        self.us_context(data)

        def normalize(raw):
            row = Holiday.model_validate(raw)
            day = iso_day(row.atDate)
            flags = ["PUBLICATION_TIME_UNAVAILABLE", "SCHEDULE_REVISION_ASOF_UNVERIFIED"]
            times = []
            for name, value in (("TRADING", row.tradingHour), ("POSTMARKET", row.postMarket)):
                try:
                    times.extend(session_hours(value, day))
                    if value is None:
                        flags.append("MISSING_" + name + "_HOURS")
                except ValueError:
                    times.extend((None, None))
                    flags.append("MALFORMED_" + name + "_HOURS")
            opening, closing, post_open, post_close = times
            kind = "CLOSED" if row.tradingHour == "" else "UNKNOWN"
            if opening and closing:
                kind = (
                    "EARLY_CLOSE"
                    if opening.astimezone(NY).time() == time(9, 30)
                    and closing.astimezone(NY).time() < time(16)
                    else "SPECIAL_SESSION"
                )
            if closing and post_open and post_open < closing or kind == "CLOSED" and post_open:
                flags.append("CONFLICTING_SESSION_HOURS")
                post_open = post_close = None
            quality = (
                "INVALID"
                if any(f.startswith(("MALFORMED_", "CONFLICTING_")) for f in flags)
                else "MISSING"
                if any(f.startswith("MISSING_") for f in flags)
                else "UNKNOWN"
            )
            return MarketHoliday(
                **provenance(f"HOLIDAY:US:{day}", received, quality=quality, flags=flags),
                event_date=day,
                name=optional_text(row.eventName),
                kind=kind,
                regular_open=opening,
                regular_close=closing,
                postmarket_open=post_open,
                postmarket_close=post_close,
                raw_trading_hours=row.tradingHour,
                raw_postmarket_hours=row.postMarket,
            )

        return self.batch(
            MarketHoliday, "/stock/market-holiday", data.get("data"), received, normalize
        )
