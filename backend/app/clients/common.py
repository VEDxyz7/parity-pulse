"""Bounded read-only HTTP transport. No provider response/header/URL logging."""

import json
import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, StrictStr, ValidationError

from app.utils.logging import correlation_id_context, request_id_context

logger = logging.getLogger("parity.providers")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


class ProviderError(Exception):
    def __init__(
        self,
        provider: str,
        kind: str,
        http_status: int | None = None,
        business_status: int | str | None = None,
    ):
        self.provider, self.kind = provider, kind
        self.http_status, self.business_status = http_status, business_status
        super().__init__(f"{provider}: {kind}")


class OCResult(BaseModel):
    model_config = ConfigDict(extra="allow", hide_input_in_errors=True)
    code: StrictInt
    msg: StrictStr
    data: object
    timestamp: StrictInt
    success: StrictBool


class ReadTransport:
    def __init__(
        self,
        provider: str,
        *,
        http: httpx.Client | None = None,
        timeout: float = 10,
        attempts: int = 3,
        min_interval: float = 0.25,
        cache_ttl: float = 5,
        sleep: Callable = time.sleep,
        monotonic: Callable = time.monotonic,
        clock: Callable = lambda: datetime.now(UTC),
    ):
        if not 1 <= attempts <= 3 or not 0 < timeout <= 30 or min_interval < 0 or cache_ttl < 0:
            raise ValueError("Invalid bounded transport configuration")
        self.provider, self.http = (
            provider,
            http or httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False),
        )
        self.timeout, self.attempts, self.min_interval, self.cache_ttl = (
            timeout,
            attempts,
            min_interval,
            cache_ttl,
        )
        self.sleep, self.monotonic, self.clock = sleep, monotonic, clock
        self.lock, self.cache = threading.RLock(), {}
        self.last_request, self.cooldown, self.failures = -float("inf"), 0.0, 0
        self.evidence = []
        self.run_id = str(uuid4())
        self.trace = {}
        # Third-party request logs can contain credentials in query URLs. Log only our whitelist.
        logging.getLogger("httpx").disabled = True
        logging.getLogger("httpcore").disabled = True

    def close(self):
        self.http.close()

    def _retry_delay(self, response, attempt):
        raw = response.headers.get("Retry-After") if response is not None else None
        try:
            delay = max(0, float(raw)) if raw else min(2**attempt, 8)
        except ValueError:
            try:
                delay = max(0, (parsedate_to_datetime(raw) - self.clock()).total_seconds())
            except (ValueError, TypeError):
                delay = 8
        if delay > 8:
            self.cooldown = self.monotonic() + delay
            return None
        return delay

    def read(self, method, path, params=None, body=None, *, ttl=None):
        self.authorize(method, path)
        attempts = self.request_attempts(method, path)
        cacheable = self.cache_request(method, path)
        key = (
            method,
            path,
            json.dumps(params or {}, sort_keys=True),
            json.dumps(body, sort_keys=True),
        )
        with self.lock:  # Single-flight and bounded request deduplication; one local owner.
            cached = self.cache.get(key) if cacheable else None
            if cached and self.monotonic() < cached[0]:
                return cached[1]
            if self.monotonic() < self.cooldown:
                raise ProviderError(self.provider, "RATE_LIMIT_OR_CIRCUIT_OPEN")
            for attempt in range(attempts):
                self.sleep(max(0, self.min_interval - (self.monotonic() - self.last_request)))
                request = self.build_request(method, path, params, body)
                self.trace = {
                    "request_id": request.headers.get("X-Request-ID"),
                    "correlation_id": request.headers.get("X-Correlation-ID"),
                }
                self.last_request = self.monotonic()
                start = self.monotonic()
                response = None
                error = None
                try:
                    response = self.http.send(request)
                    if response.status_code >= 400:
                        kind = (
                            "UNAUTHORIZED"
                            if response.status_code == 401
                            else "FORBIDDEN"
                            if response.status_code == 403
                            else "RATE_LIMITED"
                            if response.status_code == 429
                            else "HTTP_FAILURE"
                        )
                        error = ProviderError(self.provider, kind, response.status_code)
                    elif not 200 <= response.status_code < 300:
                        error = ProviderError(
                            self.provider, "REDIRECT_OR_UNEXPECTED_STATUS", response.status_code
                        )
                    else:
                        text = response.text
                        if len(response.content) > 8_000_000 or any(
                            value and value in text for value in self.sensitive_values(request)
                        ):
                            raise ProviderError(
                                self.provider, "UNSAFE_RESPONSE", response.status_code
                            )
                        try:
                            raw = json.loads(
                                text,
                                parse_float=Decimal,
                                object_pairs_hook=unique_object,
                                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
                            )
                            data, business = self.validate(raw)
                        except (ValueError, ValidationError, KeyError, TypeError):
                            raise ProviderError(
                                self.provider, "SCHEMA_INVALID", response.status_code
                            ) from None
                        result = (data, self.clock(), raw)
                        self.record(path, method, response.status_code, business, "PASS", start)
                        self.failures = 0
                        if response.headers.get("X-OC-RateLimit-Remaining") == "0":
                            self.cooldown = self.monotonic() + 60
                        lifetime = self.cache_ttl if ttl is None else ttl
                        if cacheable:
                            if len(self.cache) >= 256:
                                self.cache.pop(next(iter(self.cache)))
                            self.cache[key] = (self.monotonic() + lifetime, result)
                        return result
                except httpx.RequestError:
                    error = ProviderError(self.provider, "TRANSPORT_UNAVAILABLE")
                except ProviderError as exc:
                    error = exc
                self.record(
                    path, method, error.http_status, error.business_status, error.kind, start
                )
                transient = error.kind == "TRANSPORT_UNAVAILABLE" or error.http_status in {
                    408,
                    429,
                    500,
                    502,
                    503,
                    504,
                }
                delay = self._retry_delay(response, attempt) if transient else None
                if error.http_status == 429 and delay is not None:
                    self.cooldown = max(self.cooldown, self.monotonic() + delay)
                if transient and attempt + 1 < attempts:
                    if delay is not None:
                        self.sleep(delay)
                        continue
                self.failures += 1
                if self.failures >= 3:
                    self.cooldown = max(self.cooldown, self.monotonic() + 30)
                raise error from None

    def request_attempts(self, method, path):
        return self.attempts

    def cache_request(self, method, path):
        return True

    def record(self, path, method, status, business, capability, start):
        item = {
            "endpoint": method + " " + path,
            "http_status": status,
            "business_status": business,
            "schema_validation": "ENVELOPE_PASS" if capability == "PASS" else "NOT_VALIDATED",
            "capability_result": capability,
            "timestamp": self.clock().isoformat(),
            "response_ms": round((self.monotonic() - start) * 1000, 2),
        }
        self.evidence.append(item)
        self.evidence = self.evidence[-256:]
        logger.info(
            "DATA_FETCH",
            extra={
                "event_fields": {
                    "provider": self.provider,
                    "endpoint": path,
                    "status_code": status,
                    "duration_ms": item["response_ms"],
                    "run_id": self.run_id,
                    **self.trace,
                }
            },
        )

    def sensitive_values(self, request):
        return ()

    def context_headers(self):
        return {
            "X-Request-ID": request_id_context.get() or str(uuid4()),
            "X-Correlation-ID": correlation_id_context.get() or str(uuid4()),
        }
