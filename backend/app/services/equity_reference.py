"""Independent current equity reference from the Binance multi-vendor equity index.

The index is published in USDT; it is converted to USD with the live USDC/USDT spot rate
(USDC treated as the USD proxy). `observed_at` is Binance's index publication time, not an
underlying exchange trade time: outside US sessions the index can be fresh while the stock
itself is closed, so callers must combine it with market status.
"""

from datetime import UTC, datetime
from decimal import Decimal, localcontext

from pydantic import BaseModel, ConfigDict

from app.clients.common import ProviderError

MAX_AGE_SECONDS = 120
MAX_USDT_DEPEG = Decimal("0.02")


class EquityReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    symbol: str
    price_usd: Decimal
    index_price_usdt: Decimal
    usdt_per_usd: Decimal
    observed_at: datetime
    received_at: datetime
    source: str = "BINANCE_USDM_EQUITY_INDEX"
    timestamp_semantics: str = "INDEX_PUBLICATION_TIME_NOT_LAST_TRADE"


class EquityReferenceService:
    def __init__(self, client, *, clock=lambda: datetime.now(UTC)):
        self.client, self.clock = client, clock

    def reference(self, ticker):
        symbol = ticker.upper().replace(".", "") + "USDT"
        index, received, _ = self.client.read("GET", "/fapi/v1/premiumIndex", {"symbol": symbol})
        usdc, _, _ = self.client.read("GET", "/api/v3/ticker/price", {"symbol": "USDCUSDT"})
        try:
            price = Decimal(str(index["indexPrice"]))
            usdt_per_usd = Decimal(str(usdc["price"]))
            observed = datetime.fromtimestamp(int(index["time"]) / 1000, UTC)
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise ProviderError("BINANCE_INDEX", "SCHEMA_INVALID") from None
        if index.get("symbol") != symbol or price <= 0 or usdt_per_usd <= 0:
            raise ProviderError("BINANCE_INDEX", "SCHEMA_INVALID")
        if abs(usdt_per_usd - 1) > MAX_USDT_DEPEG:
            raise ProviderError("BINANCE_INDEX", "USDT_USD_CONVERSION_OUT_OF_RANGE")
        age = (self.clock() - observed).total_seconds()
        if not -5 <= age <= MAX_AGE_SECONDS:
            raise ProviderError("BINANCE_INDEX", "STALE")
        with localcontext() as ctx:
            ctx.prec = 34
            usd = price / usdt_per_usd
        return EquityReference(
            ticker=ticker.upper(),
            symbol=symbol,
            price_usd=usd,
            index_price_usdt=price,
            usdt_per_usd=usdt_per_usd,
            observed_at=observed,
            received_at=received,
        )
