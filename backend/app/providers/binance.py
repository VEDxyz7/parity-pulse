import re
from datetime import timedelta
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    StrictInt,
    StrictStr,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from app.clients.binance_web3 import PREFIX
from app.clients.common import ProviderError
from app.models.data import (
    AssetType,
    Issuer,
    MarketStatus,
    Nonnegative,
    Positive,
    TokenMetadata,
    TokenObservation,
    financial,
    quality_at,
    source_time,
)


class WireModel(BaseModel):
    model_config = ConfigDict(extra="allow", hide_input_in_errors=True)


class TokenKey(WireModel):
    binanceChainId: StrictStr
    tokenContractAddress: StrictStr

    @field_validator("binanceChainId")
    @classmethod
    def chain(cls, value):
        if not re.fullmatch(r"[a-zA-Z0-9_]{1,20}", value):
            raise ValueError("Invalid chain identifier")
        return value

    @field_validator("tokenContractAddress")
    @classmethod
    def contract(cls, value):
        if value.startswith("0x"):
            if not re.fullmatch(r"0x[a-fA-F0-9]{40}", value):
                raise ValueError("Invalid contract")
            return value.lower()
        if not re.fullmatch(r"[A-Za-z0-9]{20,64}", value):
            raise ValueError("Invalid contract")
        return value


class Platform(WireModel):
    platformId: StrictStr
    tickerCount: StrictInt
    chainDistribution: list[dict]
    website: StrictStr | None = None


class Chain(WireModel):
    binanceChainId: StrictStr
    name: StrictStr
    nativeTokenDecimals: StrictInt


class AssetKey(TokenKey):
    platformId: StrictStr
    tokenSymbol: StrictStr
    assetType: AssetType


class SearchResult(WireModel):
    ticker: StrictStr
    companyName: StrictStr
    assets: list[AssetKey]


class Status(WireModel):
    openState: StrictBool
    marketStatus: (
        Literal["premarket", "regular", "postmarket", "overnight", "closed", "pause"] | None
    )
    reasonCode: (
        Literal[
            "TRADING",
            "MARKET_CLOSED",
            "MARKET_PAUSED",
            "MARKET_MAINTENANCE",
            "ASSET_PAUSED",
            "ASSET_LIMITED",
            "UNSUPPORTED",
        ]
        | None
    ) = None
    reasonMsg: StrictStr | None = None
    nextOpenTime: StrictInt | None = None
    nextCloseTime: StrictInt | None = None


class RWAToken(AssetKey):
    underlyingTicker: StrictStr
    underlyingName: StrictStr
    tokenToShareRatio: Positive
    statusInfo: Status
    decimals: int | None = None
    tokenPrice: Positive | None = None
    referencePrice: Positive | None = None
    volume24H: Nonnegative | None = None

    @field_validator("decimals", mode="before")
    @classmethod
    def measured_decimals(cls, value):
        if value is None:
            return None
        if isinstance(value, bool) or not (
            isinstance(value, int) or isinstance(value, str) and re.fullmatch(r"[0-9]{1,3}", value)
        ):
            raise ValueError("Invalid decimals")
        result = int(value)
        if not 0 <= result <= 255:
            raise ValueError("Invalid decimals")
        return result


class Profile(TokenKey):
    platformId: StrictStr
    underlyingTicker: StrictStr
    underlyingFullName: StrictStr
    assetType: AssetType
    tokenToShareRatio: Positive
    protections: dict
    companyInfo: dict = {}


class UnderlyingMarket(TokenKey):
    platformId: StrictStr
    assetType: AssetType
    statusInfo: Status
    marketData: dict


class RWAPrice(TokenKey):
    platformId: StrictStr
    tokenPrice: Positive | None
    referencePrice: Positive | None = None
    tokenPriceUpdatedAt: StrictInt | None


class Price(TokenKey):
    price: Positive | None
    time: StrictInt | None


class PriceInfo(Price):
    volume24H: Nonnegative | None
    txs24H: StrictInt | None

    @field_validator("txs24H")
    @classmethod
    def count(cls, v):
        if v is not None and v < 0:
            raise ValueError("Invalid trade count")
        return v

    @model_validator(mode="after")
    def validate_metrics(self):
        for name, value in (self.model_extra or {}).items():
            if value is None:
                continue
            if re.fullmatch(
                r"(?:bn)?(?:buyVolume|sellVolume|volume|Volume|BuyVolume|SellVolume)(?:5M|1H|4H|24H)",
                name,
            ) or name in {"liquidity", "marketCap", "circSupply"}:
                if financial(value) < 0:
                    raise ValueError("Invalid nonnegative metric")
            elif name.startswith("priceChange"):
                financial(value)
            elif (
                re.fullmatch(
                    r"(?:buyTxs|sellTxs|txs|bnTxs|bnBuyTxs|bnSellTxs)(?:5M|1H|4H|24H)", name
                )
                or name == "holders"
            ):
                if type(value) is not int or value < 0:
                    raise ValueError("Invalid count")
        return self


class BasicInfo(TokenKey):
    tokenName: StrictStr
    tokenSymbol: StrictStr
    decimals: StrictInt


class GenericSearch(TokenKey):
    tokenName: StrictStr
    tokenSymbol: StrictStr
    decimals: StrictStr | StrictInt


class Trade(TokenKey):
    txHash: StrictStr
    type: Literal["buy", "sell"]
    price: Positive
    volume: Nonnegative
    time: StrictInt
    changedTokenInfo: list[dict]


class Trades(WireModel):
    cursor: StrictStr
    trades: list[Trade]


def validate(schema, data, *, provider="BINANCE_WEB3"):
    try:
        return TypeAdapter(schema).validate_python(data)
    except (ValidationError, ValueError, TypeError):
        raise ProviderError(provider, "PAYLOAD_SCHEMA_INVALID") from None


def provenance(source, identifier, received, raw=None, *, mode="LIVE", max_age=120, base="LIVE"):
    observed = source_time(raw) if raw is not None else None
    return dict(
        source=source,
        provider_identifier=identifier,
        source_timestamp=observed,
        raw_source_timestamp=str(raw) if raw is not None else None,
        timestamp_unit="ms" if raw is not None else "UNKNOWN",
        ingestion_timestamp=received,
        data_mode=mode,
        data_quality=(
            "UNKNOWN"
            if observed is None
            else quality_at(mode, observed, received, max_age=max_age, base=base)
        ),
    )


def next_time(raw):
    return source_time(raw) if raw is not None else None


def metadata(row, received):
    status = row.statusInfo
    return TokenMetadata(
        **provenance("BINANCE_RWA", row.binanceChainId + ":" + row.tokenContractAddress, received),
        ticker=row.underlyingTicker,
        company_name=row.underlyingName,
        platform_id=row.platformId,
        chain_id=row.binanceChainId,
        contract=row.tokenContractAddress,
        token_symbol=row.tokenSymbol,
        asset_type=row.assetType,
        token_to_share_ratio=row.tokenToShareRatio,
        decimals=row.decimals,
        market_state=status.marketStatus or "UNKNOWN",
        open_state=status.openState,
        next_open=next_time(status.nextOpenTime),
        next_close=next_time(status.nextCloseTime),
        reason_code=status.reasonCode,
        reason_message=status.reasonMsg,
        provider_metadata=row.model_dump(mode="json"),
    )


def matching(row, token):
    if row.binanceChainId != token.chain_id or row.tokenContractAddress != token.contract:
        raise ProviderError("BINANCE_WEB3", "CONFLICTING_TOKEN_IDENTITY")
    if hasattr(row, "platformId") and row.platformId != token.platform_id:
        raise ProviderError("BINANCE_WEB3", "CONFLICTING_ISSUER")


def observation(
    token,
    row,
    received,
    *,
    kind="PRICE",
    source="BINANCE_MARKET",
    identifier=None,
    historical=False,
):
    matching(row, token)
    is_rwa = isinstance(row, RWAPrice)
    raw = row.tokenPriceUpdatedAt if is_rwa else row.time
    price = row.tokenPrice if is_rwa else row.price
    prov = provenance(
        source,
        identifier or token.chain_id + ":" + token.contract,
        received,
        raw,
        base="HISTORICAL" if historical else "LIVE",
    )
    if price is None or raw is None:
        prov["data_quality"] = "MISSING"
    return TokenObservation(
        **prov,
        ticker=token.ticker,
        issuer=token.platform_id,
        chain_id=token.chain_id,
        contract=token.contract,
        token_symbol=token.token_symbol,
        token_to_share_ratio=token.token_to_share_ratio,
        token_price=price,
        binance_reference_price=row.referencePrice if is_rwa else None,
        volume=row.volume24H if isinstance(row, PriceInfo) else None,
        volume_unit="USD" if isinstance(row, PriceInfo) else "UNKNOWN",
        trade_count=row.txs24H if isinstance(row, PriceInfo) else None,
        market_state=token.market_state,
        next_open=token.next_open,
        next_close=token.next_close,
        kind=kind,
        provider_metadata=row.model_dump(mode="json"),
    )


class BinanceRWAProvider:
    def __init__(self, client):
        self.client = client
        self.catalog_rejections = []

    def platforms(self):
        data, received, _ = self.client.read("GET", PREFIX + "rwa/platforms", ttl=300)
        rows = validate(list[Platform], data)
        return [
            Issuer(
                **provenance("BINANCE_RWA", r.platformId, received),
                platform_id=r.platformId,
                website=r.website,
                chains=tuple(
                    validate(list[StrictStr], [d["binanceChainId"] for d in r.chainDistribution])
                ),
            )
            for r in rows
        ]

    def search(self, keyword):
        if not isinstance(keyword, str) or not 1 <= len(keyword.strip()) <= 100:
            raise ValueError("Invalid search keyword")
        data, _, _ = self.client.read(
            "GET", PREFIX + "rwa/search", {"keyword": keyword.strip()}, ttl=60
        )
        return validate(list[SearchResult], data)

    def tokens(self, chain="56"):
        if not isinstance(chain, str):
            raise ValueError("Chain ID must be a string")
        data, received, _ = self.client.read(
            "GET", PREFIX + "rwa/tokens", {"binanceChainId": chain}, ttl=30
        )
        if not isinstance(data, list):
            raise ProviderError("BINANCE_WEB3", "PAYLOAD_SCHEMA_INVALID")
        self.catalog_rejections = []
        records = []
        for index, raw in enumerate(data):
            try:
                records.append(metadata(RWAToken.model_validate(raw), received))
            except (ValidationError, ValueError, TypeError):
                # Reject the entire representation. Never repair an undocumented enum or price.
                self.catalog_rejections.append({"row": index, "reason": "PAYLOAD_SCHEMA_INVALID"})
        if data and not records:
            raise ProviderError("BINANCE_WEB3", "PAYLOAD_SCHEMA_INVALID")
        return records

    def profile(self, token):
        data, received, _ = self.client.read(
            "GET", PREFIX + "rwa/underlying-profile", self.params(token), ttl=60
        )
        row = validate(Profile, data)
        matching(row, token)
        if row.underlyingTicker != token.ticker or row.assetType != token.asset_type:
            raise ProviderError("BINANCE_RWA", "CONFLICTING_UNDERLYING")
        return TokenMetadata.model_validate(
            dict(
                token.model_dump(),
                company_name=row.underlyingFullName,
                token_to_share_ratio=row.tokenToShareRatio,
                protections=row.protections,
                provider_metadata={
                    **token.provider_metadata,
                    "underlying_profile": row.model_dump(mode="json"),
                },
                ingestion_timestamp=received,
            )
        )

    def market(self, token):
        data, received, _ = self.client.read(
            "GET", PREFIX + "rwa/underlying-market", self.params(token), ttl=15
        )
        row = validate(UnderlyingMarket, data)
        matching(row, token)
        s = row.statusInfo
        return MarketStatus(
            **provenance("BINANCE_RWA", token.chain_id + ":" + token.contract, received),
            ticker=token.ticker,
            state=s.marketStatus or "UNKNOWN",
            next_open=next_time(s.nextOpenTime),
            next_close=next_time(s.nextCloseTime),
            provider_metadata=row.model_dump(mode="json"),
        )

    def prices(self, tokens):
        if not tokens:
            return []
        if len(tokens) > 100 or len({t.chain_id for t in tokens}) != 1:
            raise ValueError("RWA price batch must contain at most100 tokens on one chain")
        data, received, _ = self.client.read(
            "GET",
            PREFIX + "rwa/price",
            {
                "binanceChainId": tokens[0].chain_id,
                "tokenContractAddresses": ",".join(t.contract for t in tokens),
            },
        )
        rows = validate(list[RWAPrice], data)
        index = {(r.binanceChainId, r.tokenContractAddress): r for r in rows}
        if len(index) != len(rows) or set(index) != {(t.chain_id, t.contract) for t in tokens}:
            raise ProviderError("BINANCE_RWA", "INCOMPLETE_OR_CONFLICTING_BATCH")
        return [
            observation(t, index[(t.chain_id, t.contract)], received, source="BINANCE_RWA")
            for t in tokens
        ]

    def observation(self, token):
        return self.prices([token])[0]

    @staticmethod
    def params(token):
        return {"binanceChainId": token.chain_id, "tokenContractAddress": token.contract}


BARS = {
    "1s": 1,
    "5s": 5,
    "30s": 30,
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "3d": 259200,
    "1w": 604800,
    "1M": None,
}


class BinanceMarketProvider:
    def __init__(self, client):
        self.client = client
        self.candle_rejections = []

    def chains(self):
        data, _, _ = self.client.read("GET", PREFIX + "supported/chain", ttl=300)
        return validate(list[Chain], data)

    def search(self, chain, keyword):
        data, _, _ = self.client.read(
            "GET", PREFIX + "token/search", {"chains": chain, "search": keyword}, ttl=60
        )
        return validate(list[GenericSearch], data)

    def basic_info(self, token):
        data, _, _ = self.client.read(
            "POST", PREFIX + "token/basic-info", BinanceRWAProvider.params(token), ttl=300
        )
        row = validate(BasicInfo, data)
        matching(row, token)
        if not 0 <= row.decimals <= 255:
            raise ProviderError("BINANCE_MARKET", "INVALID_DECIMALS")
        return row

    def prices(self, tokens, info=False):
        result = []
        for start in range(0, len(tokens), 100):
            chunk = tokens[start : start + 100]
            data, received, _ = self.client.read(
                "POST",
                PREFIX + ("price-info" if info else "price"),
                body=[BinanceRWAProvider.params(t) for t in chunk],
            )
            rows = validate(list[PriceInfo] if info else list[Price], data)
            index = {(r.binanceChainId, r.tokenContractAddress): r for r in rows}
            if len(index) != len(rows) or set(index) != {(t.chain_id, t.contract) for t in chunk}:
                raise ProviderError("BINANCE_MARKET", "INCOMPLETE_OR_CONFLICTING_BATCH")
            result.extend(
                observation(
                    t,
                    index[(t.chain_id, t.contract)],
                    received,
                    kind="PRICE_INFO" if info else "PRICE",
                )
                for t in chunk
            )
        return result

    def candles(self, token, *, bar="1m", after=None, before=None, limit=100):
        if (
            bar not in BARS
            or not 1 <= limit <= 100
            or any(
                v is not None and (isinstance(v, bool) or not isinstance(v, int))
                for v in [after, before]
            )
        ):
            raise ValueError("Invalid candle query")
        params = dict(BinanceRWAProvider.params(token), bar=bar, limit=limit)
        if after is not None:
            params["after"] = after
        if before is not None:
            params["before"] = before
        data, received, _ = self.client.read("GET", PREFIX + "candles", params, ttl=30)
        if not isinstance(data, list):
            raise ProviderError("BINANCE_MARKET", "PAYLOAD_SCHEMA_INVALID")
        rows = []
        self.candle_rejections = []
        for row in data:
            if not isinstance(row, list) or len(row) != 7:
                raise ProviderError("BINANCE_MARKET", "PAYLOAD_SCHEMA_INVALID")
            o, h, low_value, c, v, t, n = validate(
                tuple[Positive, Positive, Positive, Positive, Nonnegative, StrictInt, StrictInt],
                row,
            )
            observed = source_time(t)
            # Exclude unfinished bars; monthly completion lacks a verified fixed duration here.
            if BARS[bar] is None:
                raise ProviderError("BINANCE_MARKET", "MONTHLY_COMPLETION_NOT_VERIFIED")
            if observed + timedelta(seconds=BARS[bar]) > received:
                continue
            if after is not None and t > after:
                raise ProviderError("BINANCE_MARKET", "CANDLE_OUTSIDE_REQUEST_BOUND")
            if after is not None and t == after or before is not None and t <= before:
                # Runtime returns the inclusive end and ignores the lower bound. Quarantine
                # these rows; the persisted window still obeys the documented exclusive bounds.
                self.candle_rejections.append({"timestamp": t, "reason": "OUTSIDE_EXCLUSIVE_BOUND"})
                continue
            rows.append(
                TokenObservation(
                    **provenance(
                        "BINANCE_MARKET",
                        token.chain_id + ":" + token.contract,
                        received,
                        t,
                        base="HISTORICAL",
                    ),
                    ticker=token.ticker,
                    issuer=token.platform_id,
                    chain_id=token.chain_id,
                    contract=token.contract,
                    token_symbol=token.token_symbol,
                    token_to_share_ratio=token.token_to_share_ratio,
                    token_price=c,
                    volume=v,
                    volume_unit="UNKNOWN",
                    trade_count=n,
                    market_state="UNKNOWN",
                    kind="CANDLE",
                    interval=bar,
                    open=o,
                    high=h,
                    low=low_value,
                    close=c,
                )
            )
        return rows

    def trades(self, token, *, cursor=None, limit=100):
        if not 1 <= limit <= 500:
            raise ValueError("Invalid trade limit")
        params = dict(BinanceRWAProvider.params(token), limit=limit)
        if cursor:
            params["cursor"] = cursor
        data, received, _ = self.client.read("GET", PREFIX + "trades", params, ttl=15)
        value = validate(Trades, data)
        records = []
        for row in value.trades:
            matching(row, token)
            # Real NVDA/NVDAB trades reported price near1 against USD token price near241.
            # Preserve the reported field; do not silently classify an unverified pair price as USD.
            prov = provenance(
                "BINANCE_MARKET",
                row.txHash + ":" + token.contract,
                received,
                row.time,
                base="HISTORICAL",
            )
            prov["data_quality"] = "CONFLICTING"
            records.append(
                TokenObservation(
                    **prov,
                    ticker=token.ticker,
                    issuer=token.platform_id,
                    chain_id=token.chain_id,
                    contract=token.contract,
                    token_symbol=token.token_symbol,
                    token_to_share_ratio=token.token_to_share_ratio,
                    token_price=None,
                    volume=row.volume,
                    volume_unit="USD",
                    kind="TRADE",
                    provider_metadata={
                        "reported_price": str(row.price),
                        "price_unit": "NOT_VERIFIED",
                        "direction": row.type,
                        "changedTokenInfo": row.changedTokenInfo,
                        "txHash": row.txHash,
                    },
                )
            )
        return records, value.cursor
