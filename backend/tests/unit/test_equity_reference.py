from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.clients.binance_futures import BinanceIndexClient
from app.clients.common import ProviderError
from app.services.equity_reference import EquityReferenceService

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)


class FakeClient:
    def __init__(self, index_time=NOW, usdc="1.0005", price="235.00", symbol="NVDAUSDT"):
        self.rows = {
            "/fapi/v1/premiumIndex": {
                "symbol": symbol,
                "indexPrice": price,
                "time": int(index_time.timestamp() * 1000),
            },
            "/api/v3/ticker/price": {"symbol": "USDCUSDT", "price": usdc},
        }

    def read(self, method, path, params=None):
        return self.rows[path], NOW, self.rows[path]


def test_converts_usdt_index_to_usd_with_source_time():
    ref = EquityReferenceService(FakeClient(), clock=lambda: NOW).reference("NVDA")
    assert ref.symbol == "NVDAUSDT" and ref.observed_at == NOW
    assert abs(ref.price_usd - Decimal("235.00") / Decimal("1.0005")) < Decimal("1e-20")
    assert ref.timestamp_semantics == "INDEX_PUBLICATION_TIME_NOT_LAST_TRADE"


@pytest.mark.parametrize(
    "client",
    [
        FakeClient(index_time=NOW - timedelta(seconds=121)),
        FakeClient(usdc="1.05"),
        FakeClient(price="0"),
        FakeClient(symbol="AAPLUSDT"),
    ],
)
def test_stale_depegged_invalid_or_mismatched_index_fails_closed(client):
    with pytest.raises(ProviderError):
        EquityReferenceService(client, clock=lambda: NOW).reference("NVDA")


@pytest.mark.parametrize(
    "path,params",
    [
        ("/fapi/v1/order", {"symbol": "NVDAUSDT"}),
        ("/fapi/v1/premiumIndex", {"symbol": "NVDA&x=1"}),
        ("/fapi/v1/premiumIndex", {"symbol": "NVDAUSDT", "extra": "1"}),
    ],
)
def test_client_is_read_only_closed_grammar(path, params):
    client = BinanceIndexClient()
    with pytest.raises(ProviderError):
        client.authorize("GET", path)
        client.build_request("GET", path, params, None)
    with pytest.raises(ProviderError):
        client.authorize("POST", "/fapi/v1/premiumIndex")
