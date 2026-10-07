"""The sole Binance signer. Only explicitly reviewed market read operations exist."""

import base64
import hashlib
import hmac
import json
from uuid import uuid4

from pydantic import SecretStr

from app.clients.common import OCResult, ProviderError, ReadTransport

READ_OPERATIONS = {
    "GET": {
        "supported/chain",
        "token/search",
        "candles",
        "trades",
        "rwa/platforms",
        "rwa/search",
        "rwa/price",
        "rwa/underlying-profile",
        "rwa/tokens",
        "rwa/underlying-market",
    },
    "POST": {"price", "price-info", "token/basic-info"},
}
PREFIX = "/api/v1/dex/market/"


def sign_request(
    secret: SecretStr, timestamp: str, method: str, wire_path: str, body: bytes
) -> str:
    if not wire_path.startswith("/build/api/v1/dex/market/"):
        raise ValueError("Signing requires the exact /build market path")
    message = (timestamp + method.upper() + wire_path).encode() + body
    return base64.b64encode(
        hmac.new(secret.get_secret_value().encode(), message, hashlib.sha256).digest()
    ).decode()


class BinanceWeb3Client(ReadTransport):
    def __init__(
        self,
        api_key: SecretStr | None,
        secret_key: SecretStr | None,
        *,
        recv_window: int = 5000,
        nonce: bool = True,
        **kwargs,
    ):
        if not 1 <= recv_window <= 60000:
            raise ValueError("Invalid receive window")
        super().__init__("BINANCE_WEB3", **kwargs)
        self.api_key, self.secret_key, self.recv_window, self.nonce = (
            api_key,
            secret_key,
            recv_window,
            nonce,
        )

    def authorize(self, method, path):
        if not path.startswith(PREFIX) or path[len(PREFIX) :] not in READ_OPERATIONS.get(
            method, set()
        ):
            raise ProviderError(self.provider, "READ_ONLY_OPERATION_REQUIRED")
        if not self.api_key or not self.secret_key:
            raise ProviderError(self.provider, "NOT_CONFIGURED")

    def build_request(self, method, path, params, body):
        raw = (
            b""
            if body is None
            else json.dumps(
                body, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ).encode()
        )
        request = self.http.build_request(
            method,
            "https://web3.binance.com/build" + path,
            params=params,
            content=raw,
            timeout=self.timeout,
        )
        timestamp = self.clock().isoformat(timespec="milliseconds").replace("+00:00", "Z")
        request.headers.update(self.context_headers())
        request.headers.update(
            {
                "X-OC-APIKEY": self.api_key.get_secret_value(),
                "X-OC-TIMESTAMP": timestamp,
                "X-OC-SIGN": sign_request(
                    self.secret_key, timestamp, method, request.url.raw_path.decode(), raw
                ),
                "X-OC-RECV-WINDOW": str(self.recv_window),
                "Content-Type": "application/json",
            }
        )
        if self.nonce:
            request.headers["X-OC-NONCE"] = str(uuid4())
        return request

    def sensitive_values(self, request):
        return (
            self.api_key.get_secret_value(),
            self.secret_key.get_secret_value(),
            request.headers["X-OC-SIGN"],
        )

    def validate(self, raw):
        value = OCResult.model_validate(raw)
        if value.code != 0 or value.success is not True:
            raise ProviderError(self.provider, "BUSINESS_FAILURE", 200, value.code)
        if value.timestamp <= 0:
            raise ValueError("Invalid envelope timestamp")
        return value.data, value.code
