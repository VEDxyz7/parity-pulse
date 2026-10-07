import re
from datetime import datetime, timedelta
from decimal import localcontext

from pydantic import StrictBool, StrictInt, StrictStr

from app.clients.common import ProviderError
from app.models.data import (
    EquityObservation,
    MarketStatus,
    NewsEvent,
    Nonnegative,
    Positive,
    quality_at,
    source_time,
    utc,
)
from app.providers.binance import WireModel
from app.providers.binance import validate as validate_wire


def validate(schema, data):
    return validate_wire(schema, data, provider="MASSIVE")


class Bar(WireModel):
    o: Positive
    h: Positive
    l: Positive  # noqa: E741 -- provider field name
    c: Positive
    v: Nonnegative
    t: StrictInt


class Snapshot(WireModel):
    ticker: StrictStr
    lastTrade: dict | None = None
    min: dict | None = None


class LatestQuote(WireModel):
    T: StrictStr
    p: Positive
    P: Positive
    t: StrictInt
    y: StrictInt | None = None


class Article(WireModel):
    id: StrictStr
    title: StrictStr
    publisher: dict
    tickers: list[StrictStr]
    article_url: StrictStr
    published_utc: StrictStr
    keywords: list[StrictStr] = []


class StockStatus(WireModel):
    market: StrictStr
    serverTime: StrictStr
    earlyHours: StrictBool
    afterHours: StrictBool


class Holiday(WireModel):
    date: StrictStr
    exchange: StrictStr
    status: StrictStr
    open: StrictStr | None = None
    close: StrictStr | None = None


def ticker_path(ticker):
    if not isinstance(ticker, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,14}", ticker):
        raise ValueError("Invalid stock ticker")
    return ticker


class MassiveProvider:
    """EquityDataProvider and NewsProvider. Entitlement failures never get Binance prices."""

    def __init__(self, client, *, mode="LIVE", freshness="UNKNOWN"):
        if mode not in {"DEMO", "LIVE"} or freshness not in {"UNKNOWN", "DELAYED", "REALTIME"}:
            raise ValueError("Invalid provider mode/entitlement")
        self.client, self.mode, self.freshness = client, mode, freshness

    def prov(self, identifier, received, raw=None, unit="ms", *, historical=False, delayed=False):
        observed = source_time(raw, unit) if raw is not None else None
        base = (
            "HISTORICAL"
            if historical
            else "DELAYED"
            if delayed or self.freshness == "DELAYED"
            else "LIVE"
            if self.freshness == "REALTIME"
            else "UNKNOWN"
        )
        return dict(
            source="DEMO_EQUITY" if self.mode == "DEMO" else "MASSIVE",
            provider_identifier=identifier,
            source_timestamp=observed,
            raw_source_timestamp=str(raw) if raw is not None else None,
            timestamp_unit=unit if raw is not None else "UNKNOWN",
            ingestion_timestamp=received,
            data_mode=self.mode,
            data_quality=quality_at(
                self.mode, observed, received, max_age=1200 if base == "DELAYED" else 120, base=base
            ),
        )

    def get_snapshot(self, ticker):
        ticker = ticker_path(ticker)
        data, received, _ = self.client.read(
            "GET", "/v2/snapshot/locale/us/markets/stocks/tickers/" + ticker
        )
        row = validate(Snapshot, data.get("ticker"))
        if row.ticker != ticker:
            raise ProviderError("MASSIVE", "CONFLICTING_TICKER")
        if row.lastTrade:
            p = validate(Positive, row.lastTrade.get("p"))
            t = validate(StrictInt, row.lastTrade.get("t"))
            return EquityObservation(
                **self.prov(
                    ticker + ":SNAPSHOT", received, t, "ns", delayed=data.get("status") == "DELAYED"
                ),
                ticker=ticker,
                price=p,
                close=p,
                kind="SNAPSHOT",
            )
        if row.min:
            bar = validate(Bar, row.min)
            return EquityObservation(
                **self.prov(
                    ticker + ":SNAPSHOT", received, bar.t, delayed=data.get("status") == "DELAYED"
                ),
                ticker=ticker,
                price=bar.c,
                open=bar.o,
                high=bar.h,
                low=bar.l,
                close=bar.c,
                volume=bar.v,
                kind="SNAPSHOT",
                interval="1minute",
            )
        return EquityObservation(
            **self.prov(ticker + ":SNAPSHOT", received), ticker=ticker, kind="SNAPSHOT"
        )

    def get_latest_quote(self, ticker):
        ticker = ticker_path(ticker)
        data, received, _ = self.client.read("GET", "/v2/last/nbbo/" + ticker)
        row = validate(LatestQuote, data.get("results"))
        if row.T != ticker:
            raise ProviderError("MASSIVE", "CONFLICTING_TICKER")
        with localcontext() as ctx:
            ctx.prec = 80
            midpoint = (row.p + row.P) / 2
        return EquityObservation(
            **self.prov(
                ticker + ":QUOTE",
                received,
                row.y or row.t,
                "ns",
                delayed=data.get("status") == "DELAYED",
            ),
            ticker=ticker,
            price=midpoint,
            bid=row.p,
            ask=row.P,
            kind="QUOTE",
        )

    def pages(self, path, params, *, max_pages=3):
        if not 1 <= max_pages <= 10:
            raise ValueError("Bounded pages required")
        seen = set()
        resource = path
        self.last_page_complete = True
        for _ in range(max_pages):
            data, received, _ = self.client.read("GET", path, params, ttl=30)
            yield data, received
            url = data.get("next_url")
            if not url:
                return
            if url in seen:
                raise ProviderError("MASSIVE", "PAGINATION_LOOP")
            seen.add(url)
            path, params = self.client.page(url, resource)
        self.last_page_complete = False

    def get_historical_bars(
        self, ticker, start, end, *, multiplier=1, timespan="minute", max_pages=3
    ):
        ticker = ticker_path(ticker)
        if not 1 <= multiplier <= 60 or timespan not in {
            "minute",
            "hour",
            "day",
            "week",
            "month",
            "quarter",
            "year",
        }:
            raise ValueError("Invalid bar interval")
        for value in [start, end]:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("ISO date bounds required")
            datetime.fromisoformat(value)
        if start > end:
            raise ValueError("Invalid historical range")
        path = f"/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{start}/{end}"
        records = []
        for data, received in self.pages(
            path, {"adjusted": "true", "sort": "asc", "limit": 5000}, max_pages=max_pages
        ):
            if data.get("ticker") != ticker or data.get("adjusted") is not True:
                raise ProviderError("MASSIVE", "CONFLICTING_BAR_CONTEXT")
            for bar in validate(list[Bar], data.get("results")):
                records.append(
                    EquityObservation(
                        **self.prov(ticker + ":BAR", received, bar.t, historical=True),
                        ticker=ticker,
                        price=bar.c,
                        open=bar.o,
                        high=bar.h,
                        low=bar.l,
                        close=bar.c,
                        volume=bar.v,
                        kind="BAR",
                        interval=f"{multiplier}{timespan}",
                        adjusted=True,
                    )
                )
        return records

    def get_market_status(self):
        data, received, _ = self.client.read("GET", "/v1/marketstatus/now", ttl=30)
        row = validate(StockStatus, data)
        if row.market not in {"open", "closed", "extended-hours"}:
            raise ProviderError("MASSIVE", "UNKNOWN_MARKET_STATUS")
        try:
            observed = utc(datetime.fromisoformat(row.serverTime.replace("Z", "+00:00")))
        except ValueError:
            raise ProviderError("MASSIVE", "INVALID_TIMESTAMP") from None
        quality = "DEMO" if self.mode == "DEMO" else quality_at(self.mode, observed, received)
        return MarketStatus(
            source="DEMO_EQUITY" if self.mode == "DEMO" else "MASSIVE",
            provider_identifier="US_MARKET",
            source_timestamp=observed,
            raw_source_timestamp=row.serverTime,
            timestamp_unit="RFC3339",
            ingestion_timestamp=received,
            data_mode=self.mode,
            data_quality=quality,
            state=row.market,
            provider_metadata=row.model_dump(mode="json"),
        )

    def get_market_holidays(self):
        data, _, _ = self.client.read("GET", "/v1/marketstatus/upcoming", ttl=3600)
        rows = validate(list[Holiday], data)
        for row in rows:
            datetime.fromisoformat(row.date)
            if row.status not in {"closed", "early-close"}:
                raise ProviderError("MASSIVE", "UNKNOWN_HOLIDAY_STATUS")
            if row.status == "early-close":
                if not row.open or not row.close:
                    raise ProviderError("MASSIVE", "MISSING_HOLIDAY_TIMES")
                utc(datetime.fromisoformat(row.open.replace("Z", "+00:00")))
                utc(datetime.fromisoformat(row.close.replace("Z", "+00:00")))
        return rows

    def get_news(self, ticker, *, before=None, max_pages=3):
        # A truncated descending prefix can cover a decision window without covering
        # full history. Never reuse a previous call's coverage after a failed read.
        self.news_prefix_start = None
        ticker = ticker_path(ticker)
        params = {"ticker": ticker, "limit": 100, "order": "desc", "sort": "published_utc"}
        if before:
            params["published_utc.lte"] = utc(before).isoformat()
        records = []
        for data, received in self.pages("/v2/reference/news", params, max_pages=max_pages):
            for row in validate(list[Article], data.get("results")):
                if ticker not in row.tickers:
                    raise ProviderError("MASSIVE", "CONFLICTING_NEWS_TICKER")
                try:
                    published = utc(
                        datetime.fromisoformat(row.published_utc.replace("Z", "+00:00"))
                    )
                except ValueError:
                    raise ProviderError("MASSIVE", "INVALID_TIMESTAMP") from None
                if (
                    published > received + timedelta(seconds=5)
                    or before
                    and published > utc(before)
                ):
                    raise ProviderError("MASSIVE", "FUTURE_NEWS")
                publisher = validate(StrictStr, row.publisher.get("name"))
                records.append(
                    NewsEvent(
                        source="DEMO_NEWS" if self.mode == "DEMO" else "MASSIVE_NEWS",
                        provider_identifier=row.id,
                        source_timestamp=published,
                        raw_source_timestamp=row.published_utc,
                        timestamp_unit="RFC3339",
                        ingestion_timestamp=received,
                        data_mode=self.mode,
                        data_quality="DEMO" if self.mode == "DEMO" else "HISTORICAL",
                        ticker=ticker,
                        headline=row.title,
                        publisher=publisher,
                        url=row.article_url,
                        published_timestamp=published,
                        categories=tuple(row.keywords),
                    )
                )
        if (
            before is None
            and records
            and all(
                a.published_timestamp >= b.published_timestamp
                for a, b in zip(records, records[1:], strict=False)
            )
        ):
            self.news_prefix_start = records[-1].published_timestamp
        return records

    def get_previous_regular_close(self, ticker, at, calendar):
        session = calendar.previous_session(at)
        bars = self.get_historical_bars(
            ticker, session[0].date().isoformat(), session[1].date().isoformat()
        )
        eligible = [
            b
            for b in bars
            if b.source_timestamp >= session[0]
            and b.source_timestamp + timedelta(minutes=1) <= session[1]
        ]
        if not eligible:
            raise ProviderError("MASSIVE", "REGULAR_CLOSE_UNAVAILABLE")
        last = max(eligible, key=lambda b: b.source_timestamp)
        # Require the last completed minute ending at the actual session close.
        if last.source_timestamp + timedelta(minutes=1) != session[1]:
            raise ProviderError("MASSIVE", "REGULAR_CLOSE_INCOMPLETE")
        return EquityObservation.model_validate(
            dict(
                last.model_dump(),
                kind="REGULAR_CLOSE",
                provider_identifier=ticker + ":REGULAR_CLOSE",
            )
        )

    def get_corporate_actions(self, ticker):
        ticker = ticker_path(ticker)
        actions = []
        for kind in ["splits", "dividends"]:
            for data, received in self.pages(
                "/stocks/v1/" + kind, {"ticker": ticker, "limit": 100}
            ):
                if not isinstance(data.get("results"), list):
                    raise ProviderError("MASSIVE", "PAYLOAD_SCHEMA_INVALID")
                for row in data["results"]:
                    if not isinstance(row, dict) or row.get("ticker") != ticker:
                        raise ProviderError("MASSIVE", "CONFLICTING_ACTION_TICKER")
                    if kind == "splits":
                        validate(Positive, row.get("split_from"))
                        validate(Positive, row.get("split_to"))
                        datetime.fromisoformat(row["execution_date"])
                    else:
                        validate(Nonnegative, row.get("cash_amount"))
                        datetime.fromisoformat(row["ex_dividend_date"])
                    actions.append(
                        {
                            "kind": kind,
                            "data": row,
                            "ingestion_timestamp": received.isoformat(),
                            "data_mode": self.mode,
                            "source": "MASSIVE",
                        }
                    )
        return actions
