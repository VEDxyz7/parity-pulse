"""Finnhub event reads only; no equity quote, candle or execution capability."""

from app.clients.common import ProviderError, ReadTransport

EVENT_PATHS = frozenset(
    {"/company-news", "/calendar/earnings", "/stock/market-status", "/stock/market-holiday"}
)


class FinnhubClient(ReadTransport):
    paths = EVENT_PATHS

    def __init__(self, api_key, **kwargs):
        kwargs.setdefault("min_interval", 1.1)
        super().__init__("FINNHUB", **kwargs)
        self.api_key = api_key

    def authorize(self, method, path):
        if method != "GET" or path not in self.paths:
            raise ProviderError(self.provider, "READ_ONLY_OPERATION_REQUIRED")
        if not self.api_key or not self.api_key.get_secret_value():
            raise ProviderError(self.provider, "NOT_CONFIGURED")

    def build_request(self, method, path, params, body):
        self.authorize(method, path)
        if body is not None or any(
            name.lower() in {"token", "apikey", "api_key"} for name in (params or {})
        ):
            raise ProviderError(self.provider, "READ_ONLY_OPERATION_REQUIRED")
        return self.http.build_request(
            method,
            "https://finnhub.io/api/v1" + path,
            params=params,
            headers={**self.context_headers(), "X-Finnhub-Token": self.api_key.get_secret_value()},
            timeout=self.timeout,
        )

    def sensitive_values(self, request):
        return (self.api_key.get_secret_value(),)

    def validate(self, raw):
        if isinstance(raw, dict) and ("error" in raw or "message" in raw):
            raise ProviderError(self.provider, "BUSINESS_FAILURE", 200, "ERROR_BODY_SUPPRESSED")
        if not isinstance(raw, (dict, list)):
            raise ValueError("Expected Finnhub market-data JSON")
        return raw, "OK"
