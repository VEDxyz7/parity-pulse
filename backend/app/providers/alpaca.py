"""Independent quotes and bounded historical bars; no inferred feed entitlements."""

import re
from datetime import datetime, timedelta
from decimal import localcontext

from pydantic import Field, StrictStr

from app.clients.common import ProviderError
from app.models.data import EquityObservation, Nonnegative, Positive, quality_at, utc
from app.providers.binance import WireModel, validate
from app.providers.massive import ticker_path


class Quote(WireModel):
    t: StrictStr
    bp: Positive
    ap: Positive
    bs: Positive
    # Alpaca's ask-size field is literally "as".
    as_: Positive = Field(alias="as")


class Bar(WireModel):
    t: StrictStr
    o: Positive
    h: Positive
    l: Positive  # noqa: E741 -- provider wire name
    c: Positive
    v: Nonnegative


def observed_at(raw):
    if not isinstance(raw, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})", raw
    ):
        raise ProviderError("ALPACA", "INVALID_TIMESTAMP")
    try:
        value = utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))
        if not 2000 <= value.year <= 2100:
            raise ValueError()
        return value
    except ValueError:
        raise ProviderError("ALPACA", "INVALID_TIMESTAMP") from None


class AlpacaProvider:
    def __init__(self, client, *, feed="iex", freshness="UNKNOWN"):
        if feed not in {"iex", "sip", "delayed_sip", "boats", "overnight"} or freshness not in {
            "UNKNOWN",
            "DELAYED",
            "REALTIME",
        }:
            raise ValueError("Invalid feed/entitlement policy")
        self.client, self.feed, self.freshness, self.mode = client, feed, freshness, "LIVE"
        self.last_page_complete = False

    def prov(self, ticker, kind, raw, received, *, historical=False, interval=None):
        observed = observed_at(raw)
        delayed = self.feed == "delayed_sip" or self.freshness == "DELAYED"
        base = (
            "HISTORICAL"
            if historical
            else "DELAYED"
            if delayed
            else ("LIVE" if self.freshness == "REALTIME" else "UNKNOWN")
        )
        flags = ["ACCOUNT_PLAN_NOT_INFERRED", "FEED_REQUESTED_NOT_INDEPENDENTLY_CERTIFIED"]
        if self.feed == "iex":
            flags.append("SINGLE_EXCHANGE_NOT_NBBO")
        if self.feed in {"boats", "overnight"}:
            flags.append("OVERNIGHT_NOT_OFFICIAL_REGULAR_REFERENCE")
        if delayed:
            flags.append("DELAYED_FEED")
        if historical:
            flags.extend(["BAR_START_TIMESTAMP", "HISTORICAL_REVISION_ASOF_UNVERIFIED"])
        quality = quality_at("LIVE", observed, received, base=base)
        if observed > received:
            quality = "INVALID"
        return dict(
            source="ALPACA",
            provider_identifier=f"{ticker}:{kind}:{self.feed}:{interval or '-'}:raw",
            source_timestamp=observed,
            raw_source_timestamp=raw,
            timestamp_unit="RFC3339",
            ingestion_timestamp=received,
            data_mode="LIVE",
            data_quality=quality,
            feed=self.feed,
            is_delayed=delayed if self.freshness != "UNKNOWN" or delayed else None,
            quality_flags=tuple(flags),
        )

    def get_latest_quote(self, ticker):
        ticker = ticker_path(ticker)
        data, received, _ = self.client.read(
            "GET",
            "/v2/stocks/quotes/latest",
            {"symbols": ticker, "feed": self.feed, "currency": "USD"},
        )
        if not isinstance(data.get("quotes"), dict) or set(data["quotes"]) != {ticker}:
            raise ProviderError("ALPACA", "MISSING_OR_CONFLICTING_QUOTE")
        row = validate(Quote, data["quotes"][ticker], provider="ALPACA")
        with localcontext() as ctx:
            ctx.prec = 80
            midpoint = (row.bp + row.ap) / 2
        try:
            return EquityObservation(
                **self.prov(ticker, "QUOTE", row.t, received),
                ticker=ticker,
                price=midpoint,
                bid=row.bp,
                ask=row.ap,
                kind="QUOTE",
            )
        except ValueError:
            raise ProviderError("ALPACA", "PAYLOAD_SCHEMA_INVALID") from None

    def get_snapshot(self, ticker):
        # The existing consumer accepts QUOTE or SNAPSHOT. Preserve the true quote kind.
        return self.get_latest_quote(ticker)

    def get_historical_bars(
        self, ticker, start, end, *, multiplier=1, timespan="minute", max_pages=3
    ):
        self.last_page_complete = False
        ticker = ticker_path(ticker)
        if type(multiplier) is not int or multiplier not in {1, 5} or timespan != "minute":
            raise ValueError("Only verified 1/5-minute intervals are supported")
        if type(max_pages) is not int or not 1 <= max_pages <= 10:
            raise ValueError("Bounded pages required")
        if self.feed not in {"iex", "sip", "boats"}:
            raise ProviderError("ALPACA", "HISTORICAL_FEED_NOT_SUPPORTED")
        begin, finish = observed_at(start), observed_at(end)
        if begin >= finish:
            raise ValueError("Explicit ascending RFC3339 bounds required")
        params = dict(
            symbols=ticker,
            start=start,
            end=end,
            timeframe=f"{multiplier}Min",
            feed=self.feed,
            currency="USD",
            adjustment="raw",
            asof="-",
            limit=1000,
            sort="asc",
        )
        records, seen, previous = [], set(), None
        for _ in range(max_pages):
            data, received, _ = self.client.read("GET", "/v2/stocks/bars", params, ttl=30)
            bars = data.get("bars")
            if not isinstance(bars, dict) or set(bars) - {ticker}:
                raise ProviderError("ALPACA", "CONFLICTING_BAR_CONTEXT")
            for row in validate(list[Bar], bars.get(ticker, []), provider="ALPACA"):
                timestamp = observed_at(row.t)
                if not begin <= timestamp <= finish or previous and timestamp <= previous:
                    raise ProviderError("ALPACA", "BAR_BOUNDS_OR_ORDER_INVALID")
                if timestamp + timedelta(minutes=multiplier) > received:
                    raise ProviderError("ALPACA", "INCOMPLETE_OR_FUTURE_BAR")
                try:
                    records.append(
                        EquityObservation(
                            **self.prov(
                                ticker,
                                "BAR",
                                row.t,
                                received,
                                historical=True,
                                interval=f"{multiplier}minute",
                            ),
                            ticker=ticker,
                            kind="BAR",
                            interval=f"{multiplier}minute",
                            price=row.c,
                            open=row.o,
                            high=row.h,
                            low=row.l,
                            close=row.c,
                            volume=row.v,
                            adjusted=False,
                        )
                    )
                except ValueError:
                    raise ProviderError("ALPACA", "PAYLOAD_SCHEMA_INVALID") from None
                previous = timestamp
            token = data.get("next_page_token")
            if token is None:
                self.last_page_complete = True
                return records
            if not isinstance(token, str) or not token or len(token) > 2048 or token in seen:
                raise ProviderError("ALPACA", "PAGINATION_INVALID")
            seen.add(token)
            params = dict(params, page_token=token)
        return records

    def get_previous_regular_close(self, ticker, at, calendar):
        # A single-venue last bar is not an official consolidated closing reference.
        raise ProviderError("ALPACA", "OFFICIAL_REGULAR_CLOSE_NOT_VERIFIED")

    def get_market_status(self):
        raise ProviderError("ALPACA", "MARKET_STATUS_NOT_IMPLEMENTED")

    def get_market_holidays(self):
        raise ProviderError("ALPACA", "MARKET_HOLIDAYS_NOT_IMPLEMENTED")

    def get_corporate_actions(self, ticker):
        ticker_path(ticker)
        raise ProviderError("ALPACA", "CORPORATE_ACTIONS_NOT_IMPLEMENTED")
