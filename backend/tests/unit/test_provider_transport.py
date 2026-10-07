from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from app.clients.binance_web3 import PREFIX, BinanceWeb3Client, sign_request
from app.clients.common import ProviderError
from app.clients.massive import MassiveClient

NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)
GOOD = {"code": 0, "msg": "success", "data": [], "timestamp": 1791288000000, "success": True}


class Timer:
    def __init__(self):
        self.value = 0
        self.sleeps = []

    def now(self):
        return self.value

    def clock(self):
        return NOW + timedelta(seconds=self.value)

    def sleep(self, value):
        self.sleeps.append(value)
        self.value += value


def client(handler, **kwargs):
    timer = Timer()
    return BinanceWeb3Client(
        SecretStr("synthetic-key"),
        SecretStr("synthetic-signing-secret"),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=timer.sleep,
        monotonic=timer.now,
        clock=timer.clock,
        **kwargs,
    ), timer


def test_known_signature_vector_and_wire_bytes():
    assert (
        sign_request(
            SecretStr("synthetic-signing-secret"),
            "2026-10-06T12:00:00.123Z",
            "GET",
            "/build/api/v1/dex/market/rwa/search?keyword=Nvidia%20Corp",
            b"",
        )
        == "Bb7GWeRlA3ijzQy+n5UPY0X5Wc7POk+Ab4D2FfWSmIY="
    )
    c, _ = client(lambda r: httpx.Response(200, json=GOOD))
    request = c.build_request("GET", PREFIX + "rwa/search", {"keyword": "Nvidia Corp & Co"}, None)
    assert request.url.raw_path == b"/build/api/v1/dex/market/rwa/search?keyword=Nvidia+Corp+%26+Co"
    assert request.content == b""
    assert request.headers["X-OC-SIGN"] == sign_request(
        c.secret_key,
        request.headers["X-OC-TIMESTAMP"],
        "GET",
        request.url.raw_path.decode(),
        request.content,
    )
    request = c.build_request(
        "POST",
        PREFIX + "price",
        None,
        [{"binanceChainId": "56", "tokenContractAddress": "0x" + "a" * 40}],
    )
    assert request.content == (
        b'[{"binanceChainId":"56",'
        b'"tokenContractAddress":"0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}]'
    )
    assert request.headers["X-OC-SIGN"] == sign_request(
        c.secret_key,
        request.headers["X-OC-TIMESTAMP"],
        "POST",
        request.url.raw_path.decode(),
        request.content,
    )
    assert request.headers["X-OC-RECV-WINDOW"] == "5000"
    assert "X-Correlation-ID" in request.headers and "X-OC-NONCE" in request.headers


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/v1/dex/aggregator/order/submit", "POST"),
        ("/api/v1/dex/pre-transaction/broadcast-transaction", "POST"),
        ("/api/v1/dex/balance/supported/chain", "GET"),
        (PREFIX + "price", "GET"),
        ("https://evil.invalid", "GET"),
    ],
)
def test_write_unknown_wallet_operations_never_reach_transport(path, method):
    calls = []
    c, _ = client(lambda r: calls.append(r))
    with pytest.raises(ProviderError, match="READ_ONLY"):
        c.read(method, path)
    assert calls == []


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409])
def test_nontransient_errors_do_not_retry_or_echo_body(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"msg": "synthetic-key synthetic-signing-secret"})

    c, _ = client(handler)
    with pytest.raises(ProviderError) as exc:
        c.read("GET", PREFIX + "supported/chain")
    assert len(calls) == 1 and "synthetic" not in str(exc.value)


@pytest.mark.parametrize("status", [408, 500, 502, 503, 504])
def test_transient_errors_bounded(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status)

    c, timer = client(handler)
    with pytest.raises(ProviderError):
        c.read("GET", PREFIX + "supported/chain")
    assert len(calls) == 3 and sum(timer.sleeps) <= 8
    assert len({r.headers["X-OC-NONCE"] for r in calls}) == 3


def test_429_honors_retry_after_and_resigns():
    calls = []

    def handler(request):
        calls.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "2"})
            if len(calls) == 1
            else httpx.Response(200, json=GOOD)
        )

    c, timer = client(handler)
    c.read("GET", PREFIX + "supported/chain")
    assert len(calls) == 2 and 2 in timer.sleeps
    assert calls[0].headers["X-OC-SIGN"] != calls[1].headers["X-OC-SIGN"]


def test_long_retry_after_blocks_followup_without_early_retry():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"})

    c, _ = client(handler)
    for _ in range(2):
        with pytest.raises(ProviderError):
            c.read("GET", PREFIX + "supported/chain")
    assert len(calls) == 1


def test_rate_headers_and_singleflight_cache():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=GOOD, headers={"X-OC-RateLimit-Remaining": "0"})

    c, _ = client(handler)
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(lambda _: c.read("GET", PREFIX + "supported/chain"), range(4)))
    assert len(calls) == 1 and len(values) == 4
    with pytest.raises(ProviderError):
        c.read("GET", PREFIX + "rwa/platforms")


@pytest.mark.parametrize(
    "patch",
    [
        {"code": "0"},
        {"success": "true"},
        {"timestamp": None},
        {"data": None, "success": False},
        {"code": True},
    ],
)
def test_envelope_schema_fails_safely(patch):
    c, _ = client(lambda r: httpx.Response(200, json=dict(GOOD, **patch)))
    with pytest.raises(ProviderError):
        c.read("GET", PREFIX + "supported/chain")


def test_timeout_circuit_and_json_decimal_precision():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectTimeout("synthetic-secret detail", request=request)

    c, _ = client(handler)
    for _ in range(4):
        with pytest.raises(ProviderError) as exc:
            c.read("GET", PREFIX + "supported/chain")
        assert "synthetic-secret" not in str(exc.value)
    assert len(calls) == 9
    c, _ = client(
        lambda r: httpx.Response(
            200,
            text='{"code":0,"msg":"success","data":[0.123456789012345678901],"timestamp":1791288000000,"success":true}',
        )
    )
    assert c.read("GET", PREFIX + "supported/chain")[0][0] == Decimal("0.123456789012345678901")


def test_credentials_and_signature_echo_are_rejected_and_not_logged(capsys):
    c, _ = client(
        lambda r: httpx.Response(200, json=dict(GOOD, data={"echo": r.headers["X-OC-SIGN"]}))
    )
    with pytest.raises(ProviderError, match="UNSAFE_RESPONSE"):
        c.read("GET", PREFIX + "supported/chain")
    assert "synthetic-key" not in capsys.readouterr().out


def test_massive_pagination_allowlist_removes_key_and_blocks_exfiltration():
    c = MassiveClient(
        SecretStr("synthetic-massive"),
        http=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"status": "OK", "results": []})
            )
        ),
        min_interval=0,
    )
    path = "/v2/aggs/ticker/NVDA/range/1/minute/2026-10-05/2026-10-05"
    new, params = c.page(
        "https://api.massive.com/v2/aggs/ticker/NVDA/range/1/minute/1791244800000/2026-10-05?cursor=a&apiKey=not-retained",
        path,
    )
    assert params == {"cursor": "a"} and new.endswith("/1791244800000/2026-10-05")
    for url in [
        "https://evil.invalid/v2/reference/news?apiKey=anything",
        "https://api.massive.com@evil.invalid/v2/reference/news",
        "https://api.massive.com/v2/reference/news?cursor=a&cursor=b",
        "https://api.massive.com/stocks/v1/splits",
    ]:
        with pytest.raises(ProviderError):
            c.page(url, "/v2/reference/news")


def test_final_rate_limited_attempt_honors_cooldown():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"})

    c, _ = client(handler, attempts=1)
    for _ in range(2):
        with pytest.raises(ProviderError):
            c.read("GET", PREFIX + "supported/chain")
    assert len(calls) == 1


def test_duplicate_json_fields_are_rejected():
    c, _ = client(
        lambda r: httpx.Response(
            200,
            text='{"code":1,"code":0,"msg":"success","data":[],"timestamp":1791288000000,"success":true}',
        )
    )
    with pytest.raises(ProviderError, match="SCHEMA_INVALID"):
        c.read("GET", PREFIX + "supported/chain")
