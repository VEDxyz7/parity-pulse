"""Alpaca market-data host only. Trading, accounts and wallet paths are absent."""

from app.clients.common import ProviderError, ReadTransport

PATHS = {"/v2/stocks/quotes/latest", "/v2/stocks/bars"}


class AlpacaClient(ReadTransport):
    def __init__(self, api_key, secret_key, **kwargs):
        kwargs.setdefault("min_interval", 0.31)  # Below documented Basic 200 requests/minute.
        super().__init__("ALPACA", **kwargs)
        self.api_key, self.secret_key = api_key, secret_key

    def authorize(self, method, path):
        if method != "GET" or path not in PATHS:
            raise ProviderError(self.provider, "READ_ONLY_OPERATION_REQUIRED")
        if not self.api_key or not self.secret_key:
            raise ProviderError(self.provider, "NOT_CONFIGURED")

    def build_request(self, method, path, params, body):
        self.authorize(method, path)
        if body is not None:
            raise ProviderError(self.provider, "READ_ONLY_OPERATION_REQUIRED")
        return self.http.build_request(
            method,
            "https://data.alpaca.markets" + path,
            params=params,
            headers={
                **self.context_headers(),
                "APCA-API-KEY-ID": self.api_key.get_secret_value(),
                "APCA-API-SECRET-KEY": self.secret_key.get_secret_value(),
            },
            timeout=self.timeout,
        )

    def sensitive_values(self, request):
        return (self.api_key.get_secret_value(), self.secret_key.get_secret_value())

    def validate(self, raw):
        if not isinstance(raw, dict):
            raise ValueError("Invalid Alpaca envelope")
        if "code" in raw or "message" in raw:
            # Do not echo provider messages, even on HTTP 200.
            raise ProviderError(self.provider, "BUSINESS_FAILURE", 200, "PROVIDER_ERROR")
        return raw, "OK"
