"""Event context is separate from equity observations and production Trust history."""

from datetime import date, datetime
from typing import Literal

from pydantic import StrictBool, StrictInt, StrictStr, field_validator

from app.models.data import DataModel, Provenance, utc

EventEndpoint = Literal[
    "/company-news", "/calendar/earnings", "/stock/market-status", "/stock/market-holiday"
]


class EventObservation(Provenance):
    source: Literal["FINNHUB_EVENTS"] = "FINNHUB_EVENTS"
    timestamp_unit: Literal["s", "UNKNOWN"] = "UNKNOWN"
    data_mode: Literal["LIVE"] = "LIVE"
    endpoint: EventEndpoint
    quality_flags: tuple[StrictStr, ...] = ()


class CompanyNewsEvent(EventObservation):
    endpoint: Literal["/company-news"] = "/company-news"
    ticker: StrictStr
    related_tickers: tuple[StrictStr, ...]
    ticker_mapping: Literal["PROVIDER_CONFIRMED", "REQUEST_SCOPE_ONLY"]
    headline: StrictStr | None
    publisher: StrictStr | None
    url: StrictStr | None
    published_timestamp: datetime | None
    event_date: date | None
    event_date_timezone: Literal["UTC"] = "UTC"
    categories: tuple[StrictStr, ...] = ()

    @field_validator("published_timestamp")
    @classmethod
    def publication_utc(cls, value):
        return utc(value) if value is not None else None


class EarningsCalendarEvent(EventObservation):
    endpoint: Literal["/calendar/earnings"] = "/calendar/earnings"
    ticker: StrictStr
    event_date: date
    event_date_timezone: Literal["America/New_York"] = "America/New_York"
    published_timestamp: datetime | None = None
    fiscal_year: StrictInt | None
    fiscal_quarter: StrictInt | None
    timing: Literal["BEFORE_OPEN", "AFTER_CLOSE", "DURING_SESSION", "UNKNOWN"]
    provider_hour: StrictStr | None


class USMarketStatus(EventObservation):
    endpoint: Literal["/stock/market-status"] = "/stock/market-status"
    exchange: Literal["US"] = "US"
    market_timezone: Literal["America/New_York"] = "America/New_York"
    is_open: StrictBool
    session: Literal["PREMARKET", "REGULAR", "POSTMARKET", "UNKNOWN"]
    provider_session: StrictStr | None
    holiday: StrictStr | None


class MarketHoliday(EventObservation):
    endpoint: Literal["/stock/market-holiday"] = "/stock/market-holiday"
    exchange: Literal["US"] = "US"
    event_date: date
    event_date_timezone: Literal["America/New_York"] = "America/New_York"
    name: StrictStr | None
    published_timestamp: datetime | None = None
    kind: Literal["CLOSED", "EARLY_CLOSE", "SPECIAL_SESSION", "UNKNOWN"]
    regular_open: datetime | None
    regular_close: datetime | None
    postmarket_open: datetime | None
    postmarket_close: datetime | None
    raw_trading_hours: StrictStr | None
    raw_postmarket_hours: StrictStr | None

    @field_validator("regular_open", "regular_close", "postmarket_open", "postmarket_close")
    @classmethod
    def session_utc(cls, value):
        return utc(value) if value is not None else None


class EventRejection(DataModel):
    row: StrictInt
    reason: Literal["INVALID_EVENT", "CONFLICTING_EVENT_ID"]


class EventBatch[EventType: EventObservation](DataModel):
    source: Literal["FINNHUB_EVENTS"] = "FINNHUB_EVENTS"
    endpoint: EventEndpoint
    ticker: StrictStr | None = None
    requested_start: date | None = None
    requested_end: date | None = None
    ingestion_timestamp: datetime
    data_mode: Literal["LIVE"] = "LIVE"
    status: Literal["PASS", "PARTIAL", "UNAVAILABLE"]
    # These endpoints have no verified exhaustive pagination/point-in-time ledger.
    coverage_complete: Literal[False] = False
    coverage_flags: tuple[StrictStr, ...] = ("EXHAUSTIVE_COVERAGE_NOT_VERIFIED",)
    received_count: StrictInt
    duplicate_count: StrictInt
    records: tuple[EventType, ...]
    rejections: tuple[EventRejection, ...]

    @field_validator("ingestion_timestamp")
    @classmethod
    def timezone(cls, value):
        return utc(value)
