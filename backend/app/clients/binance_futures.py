"""Public, keyless Binance index reads for non-authoritative index corroboration only.

Binance USD-M "TRADIFI_PERPETUAL" contracts publish a multi-vendor equity index
(databento, dxfeed, kaiko, massive, pyth) with a millisecond source timestamp. Only the
index and the USDC/USDT conversion are read; no account, order or signed endpoint exists here.
"""

import re

from app.clients.common import ProviderError, ReadTransport

FUTURES = "https://fapi.binance.com"
SPOT = "https://api.binance.com"
PATHS = {
    "/fapi/v1/premiumIndex": FUTURES,
    "/fapi/v1/constituents": FUTURES,
    "/api/v3/ticker/price": SPOT,
}
SYMBOL = re.compile(r"^[A-Z0-9]{2,20}$")


class BinanceIndexClient(ReadTransport):
    def __init__(self, **kwargs):
        kwargs.setdefault("cache_ttl", 2)
        super().__init__("BINANCE_INDEX", **kwargs)

    def authorize(self, method, path):
        if method != "GET" or path not in PATHS:
            raise ProviderError(self.provider, "READ_ONLY_OPERATION_REQUIRED")

    def build_request(self, method, path, params, body):
        params = dict(params or {})
        if body is not None or set(params) != {"symbol"} or not SYMBOL.match(params["symbol"]):
            raise ProviderError(self.provider, "READ_ONLY_OPERATION_REQUIRED")
        return self.http.build_request(
            method,
            PATHS[path] + path,
            params=params,
            headers=self.context_headers(),
            timeout=self.timeout,
        )

    def validate(self, raw):
        if not isinstance(raw, dict) or not isinstance(raw.get("symbol"), str):
            raise ValueError("Invalid Binance index response")
        return raw, "OK"
