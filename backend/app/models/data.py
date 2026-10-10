"""Provider-independent Phase 2 data. All money is Decimal, never binary float."""

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

DataMode = Literal["DEMO", "LIVE"]
Quality = Literal[
    "LIVE", "DELAYED", "HISTORICAL", "DEMO", "STALE", "MISSING", "INVALID", "CONFLICTING", "UNKNOWN"
]


def financial(value):
    if isinstance(value, (float, bool)) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("Financial value must be an exact numeric lexeme")
    if isinstance(value, str) and not re.fullmatch(
        r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value
    ):
        raise ValueError("Invalid numeric lexeme")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError("Invalid decimal") from None
    if not result.is_finite():
        raise ValueError("Financial value must be finite")
    return result


Positive = Annotated[Decimal, BeforeValidator(financial), Field(gt=0)]
Nonnegative = Annotated[Decimal, BeforeValidator(financial), Field(ge=0)]


def asset_type(value):
    if type(value) is not int:
        raise ValueError("Asset type must be a verified integer enum")
    return value


AssetType = Annotated[Literal[1, 2, 3], BeforeValidator(asset_type)]


def utc(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return value.astimezone(UTC)


def source_time(raw, unit="ms"):
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise ValueError("Invalid source timestamp")
    divisor = {"ms": 1000, "ns": 1_000_000_000}[unit]
    seconds, remainder = divmod(raw, divisor)
    try:
        result = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
            seconds=seconds, microseconds=remainder * 1_000_000 // divisor
        )
    except (OverflowError, ValueError):
        raise ValueError("Invalid source timestamp") from None
    if not 2000 <= result.year <= 2100:
        raise ValueError("Source timestamp outside supported bounds")
    return result


def quality_at(mode, observed, received, *, max_age=120, base="LIVE"):
    if mode == "DEMO":
        return "DEMO"
    if observed is None:
        return "MISSING"
    age = (utc(received) - utc(observed)).total_seconds()
    if age < -5:
        return "INVALID"
    if base == "HISTORICAL":
        return base
    if age > max_age:
        return "STALE"
    return base


class DataModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, frozen=True)


class Provenance(DataModel):
    source: StrictStr
    provider_identifier: StrictStr
    source_timestamp: datetime | None = None
    raw_source_timestamp: StrictStr | None = None
    timestamp_unit: Literal["ms", "ns", "RFC3339", "SCHEDULE", "UNKNOWN"] = "UNKNOWN"
    ingestion_timestamp: datetime
    data_mode: DataMode
    data_quality: Quality
    schema_version: Literal["2"] = "2"

    @field_validator("source_timestamp", "ingestion_timestamp")
    @classmethod
    def timezone(cls, value):
        return utc(value) if value is not None else None

    @model_validator(mode="after")
    def isolated(self):
        if (self.data_mode == "DEMO") != (self.data_quality == "DEMO"):
            raise ValueError("DEMO data and quality must agree")
        if self.source.startswith("BINANCE") and type(self).__name__ == "EquityObservation":
            raise ValueError("Independent equity may not originate from Binance")
        return self


class TrackedAsset(Provenance):
    ticker: StrictStr
    company_name: StrictStr
    supported: StrictBool
    status: Literal["VERIFIED", "UNAVAILABLE", "NOT_VERIFIED", "DEMO"]

    @field_validator("ticker")
    @classmethod
    def valid_ticker(cls, value):
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,14}", value):
            raise ValueError("Invalid ticker")
        return value


class Issuer(Provenance):
    platform_id: StrictStr
    website: StrictStr | None = None
    chains: tuple[StrictStr, ...]


class TokenMetadata(Provenance):
    ticker: StrictStr
    company_name: StrictStr
    platform_id: StrictStr
    chain_id: StrictStr
    contract: StrictStr
    token_symbol: StrictStr
    asset_type: AssetType
    token_to_share_ratio: Positive
    decimals: StrictInt | None = Field(default=None, ge=0, le=255)
    market_state: Literal[
        "premarket", "regular", "postmarket", "overnight", "offhours", "closed", "pause", "UNKNOWN"
    ]
    open_state: StrictBool | None = None
    next_open: datetime | None = None
    next_close: datetime | None = None
    reason_code: StrictStr | None = None
    reason_message: StrictStr | None = None
    protections: dict = Field(default_factory=dict)
    provider_metadata: dict = Field(default_factory=dict)

    @field_validator("next_open", "next_close")
    @classmethod
    def timezone(cls, value):
        return utc(value) if value is not None else None


class TokenObservation(Provenance):
    ticker: StrictStr
    issuer: StrictStr
    chain_id: StrictStr
    contract: StrictStr
    token_symbol: StrictStr
    token_to_share_ratio: Positive
    token_price: Positive | None
    binance_reference_price: Positive | None = None
    volume: Nonnegative | None = None
    volume_unit: Literal["USD", "TOKEN", "UNKNOWN"] = "UNKNOWN"
    trade_count: StrictInt | None = Field(default=None, ge=0)
    market_state: Literal[
        "premarket", "regular", "postmarket", "overnight", "offhours", "closed", "pause", "UNKNOWN"
    ] = "UNKNOWN"
    next_open: datetime | None = None
    next_close: datetime | None = None
    kind: Literal["PRICE", "PRICE_INFO", "CANDLE", "TRADE"] = "PRICE"
    interval: StrictStr | None = None
    open: Positive | None = None
    high: Positive | None = None
    low: Positive | None = None
    close: Positive | None = None
    provider_metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def missing(self):
        if self.token_price is None and self.data_quality not in {"MISSING", "DEMO", "CONFLICTING"}:
            raise ValueError("Missing price must be marked")
        validate_ohlc(self)
        return self


class EquityObservation(Provenance):
    ticker: StrictStr
    price: Positive | None = None
    open: Positive | None = None
    high: Positive | None = None
    low: Positive | None = None
    close: Positive | None = None
    volume: Nonnegative | None = None
    bid: Positive | None = None
    ask: Positive | None = None
    market_status: StrictStr = "UNKNOWN"
    kind: Literal["SNAPSHOT", "QUOTE", "BAR", "REGULAR_CLOSE"]
    interval: StrictStr | None = None
    adjusted: StrictBool | None = None

    @model_validator(mode="after")
    def prices(self):
        validate_ohlc(self)
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("Conflicting bid/ask")
        return self


class NewsEvent(Provenance):
    ticker: StrictStr
    headline: StrictStr
    publisher: StrictStr
    url: StrictStr
    published_timestamp: datetime
    categories: tuple[StrictStr, ...] = ()

    @field_validator("url")
    @classmethod
    def safe_url(cls, value):
        if not value.startswith(("https://", "http://")):
            raise ValueError("Invalid article URL")
        return value

    @field_validator("published_timestamp")
    @classmethod
    def timezone(cls, value):
        return utc(value)


class MarketStatus(Provenance):
    ticker: StrictStr = "US_EQUITY"
    state: StrictStr
    next_open: datetime | None = None
    next_close: datetime | None = None
    early_close: StrictBool = False
    multi_day_closure: StrictBool = False
    reopening: StrictBool = False
    provider_metadata: dict = Field(default_factory=dict)


def validate_ohlc(value):
    if all(getattr(value, key) is not None for key in ("open", "high", "low", "close")):
        if (
            value.low > min(value.open, value.close)
            or value.high < max(value.open, value.close)
            or value.high < value.low
        ):
            raise ValueError("Conflicting OHLC")
