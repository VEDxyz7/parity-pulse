import re
from urllib.parse import parse_qsl, urlsplit

from app.clients.common import ProviderError, ReadTransport

PATHS = [
    r"/v2/last/nbbo/[A-Z0-9.\-]{1,15}",
    r"/v2/snapshot/locale/us/markets/stocks/tickers(?:/[A-Z0-9.\-]{1,15})?",
    r"/v2/aggs/ticker/[A-Z0-9.\-]{1,15}/range/[1-9][0-9]*/(?:minute|hour|day|week|month|quarter|year)/[0-9\-]+/[0-9\-]+",
    r"/v1/marketstatus/(?:now|upcoming)",
    r"/v2/reference/news",
    r"/stocks/v1/(?:splits|dividends)",
]


class MassiveClient(ReadTransport):
    def __init__(self, api_key, **kwargs):
        kwargs.setdefault("min_interval", 12.1)  # Safe for the documented Basic5/minute plan.
        super().__init__("MASSIVE", **kwargs)
        self.api_key = api_key

    def authorize(self, method, path):
        if method != "GET" or not any(re.fullmatch(pattern, path) for pattern in PATHS):
            raise ProviderError(self.provider, "READ_ONLY_OPERATION_REQUIRED")
        if not self.api_key:
            raise ProviderError(self.provider, "NOT_CONFIGURED")

    def build_request(self, method, path, params, body):
        if body is not None:
            raise ProviderError(self.provider, "READ_ONLY_OPERATION_REQUIRED")
        params = {k: v for k, v in (params or {}).items() if k.lower() != "apikey"}
        params["apiKey"] = self.api_key.get_secret_value()
        return self.http.build_request(
            method,
            "https://api.massive.com" + path,
            params=params,
            headers=self.context_headers(),
            timeout=self.timeout,
        )

    def sensitive_values(self, request):
        return (self.api_key.get_secret_value(),)

    def validate(self, raw):
        if isinstance(raw, list):
            return raw, "HOLIDAYS_ARRAY"
        if not isinstance(raw, dict):
            raise ValueError("Invalid Massive response")
        # Market status is a standalone response without the common status envelope.
        if "serverTime" in raw and "market" in raw:
            return raw, "MARKET_STATUS"
        if raw.get("status") not in {"OK", "DELAYED"}:
            raise ProviderError(self.provider, "BUSINESS_FAILURE", 200, "UNEXPECTED_STATUS")
        return raw, raw["status"]

    def page(self, next_url, resource):
        parts = urlsplit(next_url)
        if (
            parts.scheme != "https"
            or parts.netloc != "api.massive.com"
            or not (
                parts.path == resource
                or resource.startswith("/v2/aggs/ticker/")
                and "/".join(parts.path.split("/")[:8]) == "/".join(resource.split("/")[:8])
                and parts.path.split("/")[-1] == resource.split("/")[-1]
            )
            or parts.fragment
        ):
            raise ProviderError(self.provider, "UNSAFE_PAGINATION_URL")
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        if len({k for k, _ in pairs}) != len(pairs):
            raise ProviderError(self.provider, "UNSAFE_PAGINATION_URL")
        self.authorize("GET", parts.path)
        return parts.path, {k: v for k, v in pairs if k.lower() != "apikey"}
