"""Offline safety/measurement tests for the isolated diagnostic, not provider evidence."""

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app.clients.common import ProviderError


@pytest.fixture
def diagnostic():
    path = Path(__file__).parents[3] / "scripts/diagnose-multi-provider.py"
    spec = importlib.util.spec_from_file_location("multi_provider_diagnostic", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "url,enabled,reason",
    [
        ("https://api.hyperliquid.xyz/info/info", True, "UNVERIFIED_INFO_URL"),
        ("https://api.hyperliquid.xyz", True, "UNVERIFIED_INFO_URL"),
        ("https://evil.invalid/info", True, "UNVERIFIED_INFO_URL"),
        ("https://api.hyperliquid.xyz/info", False, "DISABLED"),
    ],
)
def test_hyperliquid_configuration_never_reaches_wrong_host(diagnostic, url, enabled, reason):
    calls = []
    client = diagnostic.PublicProbe(
        "HYPERLIQUID",
        url=url,
        enabled=enabled,
        http=httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(r))),
    )
    with pytest.raises(ProviderError, match=reason):
        client.read("POST", "/info", body={"type": "perpDexs"})
    assert not calls


@pytest.mark.parametrize(
    "body",
    [
        {"type": "order"},
        {"type": "clearinghouseState", "user": "anything"},
        {"type": "perpDexs", "signature": "anything"},
    ],
)
def test_info_allowlist_cannot_read_wallet_or_submit_orders(diagnostic, body):
    calls = []
    client = diagnostic.PublicProbe(
        "HYPERLIQUID", http=httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(r)))
    )
    with pytest.raises(ProviderError, match="READ_ONLY"):
        client.read("POST", "/info", body=body)
    assert not calls


def test_finnhub_key_header_only_and_evidence_has_no_secret(diagnostic):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"c": 200, "t": 1791572400})

    client = diagnostic.PublicProbe(
        "FINNHUB",
        key=SecretStr("synthetic-finnhub-credential"),
        http=httpx.Client(transport=httpx.MockTransport(handle)),
    )
    data, _, _ = client.read("GET", "/quote", {"symbol": "NVDA"})
    assert (
        data["c"] == 200 and calls[0].headers["X-Finnhub-Token"] == "synthetic-finnhub-credential"
    )
    assert "synthetic" not in str(calls[0].url) + str(client.evidence)
    assert client.evidence[0]["parameters"] == {"symbol": "NVDA"}
    assert "authorization" not in str(client.evidence).lower()
    with pytest.raises(ProviderError, match="READ_ONLY"):
        client.read("POST", "/quote", body={})


def test_echo_and_error_messages_suppressed(diagnostic):
    for status, body in [
        (200, {"echo": "synthetic-finnhub-credential"}),
        (403, {"error": "synthetic-finnhub-credential"}),
    ]:
        client = diagnostic.PublicProbe(
            "FINNHUB",
            key=SecretStr("synthetic-finnhub-credential"),
            http=httpx.Client(
                transport=httpx.MockTransport(
                    lambda _, status=status, body=body: httpx.Response(status, json=body)
                )
            ),
        )
        result = diagnostic.attempt(
            client, "quote", lambda client=client: client.read("GET", "/quote", {"symbol": "NVDA"})
        )
        assert result["status"] == "UNAVAILABLE" and "synthetic" not in str(result)


def test_429_is_bounded_and_does_not_force_retries(diagnostic):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"})

    client = diagnostic.PublicProbe(
        "FINNHUB",
        key=SecretStr("synthetic-finnhub-credential"),
        http=httpx.Client(transport=httpx.MockTransport(handle)),
    )
    for _ in range(2):
        with pytest.raises(ProviderError):
            client.read("GET", "/quote", {"symbol": "NVDA"})
    assert len(calls) == 1


@pytest.mark.parametrize(
    "timestamp,expected",
    [
        ("2026-10-09T13:30:00Z", "REGULAR"),
        ("2026-10-10T07:30:00Z", "WEEKEND"),
        ("2026-11-27T18:00:00Z", "POSTMARKET"),
        ("2026-11-26T15:00:00Z", "HOLIDAY"),
        ("2026-03-06T14:30:00Z", "REGULAR"),
        ("2026-03-09T13:30:00Z", "REGULAR"),
        ("2026-10-09T01:00:00Z", "WEEKDAY_OVERNIGHT"),
    ],
)
def test_calendar_sessions_dst_and_cross_date_overnight(diagnostic, timestamp, expected):
    assert diagnostic.regime(diagnostic.observed_at(timestamp)) == expected


def test_coverage_counts_missing_slots_and_duplicates_without_filling(diagnostic):
    at = datetime(2026, 10, 9, 14, tzinfo=UTC)
    row = SimpleNamespace(source_timestamp=at, model_dump=lambda **_: {"t": at.isoformat()})
    result = diagnostic.history_summary(
        [row, row], 1, "2026-10-09T14:00:00Z", "2026-10-09T14:02:00Z"
    )
    assert result["duplicates"] == 1 and result["potential_calendar_slots"]["REGULAR"] == 3
    assert result["unobserved_slots_not_necessarily_provider_loss"]["REGULAR"] == 2
    assert result["historical_revision_asof_verified"] is False


def test_missing_finnhub_key_does_not_fetch(diagnostic):
    client = diagnostic.PublicProbe("FINNHUB")
    result = diagnostic.attempt(
        client, "quote", lambda client=client: client.read("GET", "/quote", {"symbol": "NVDA"})
    )
    assert result["status"] == "NOT_CONFIGURED" and result["requests"] == []


def test_explicit_authorization_required(diagnostic, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "sys.argv", ["diagnose-multi-provider.py", "--output", str(tmp_path / "no.json")]
    )
    with pytest.raises(SystemExit):
        diagnostic.main()
    assert not (tmp_path / "no.json").exists()


def test_catalog_audit_preserves_rejection_without_returning_validation_inputs(
    diagnostic, monkeypatch
):
    path = Path(__file__).parents[1] / "fixtures/binance/rwa_tokens.json"
    rows = json.loads(path.read_text())["data"]
    rows[0]["statusInfo"]["marketStatus"] = "UNEXPECTED"
    received = datetime(2026, 10, 10, tzinfo=UTC)

    class Client:
        evidence = []

        def read(self, method, path, params):
            assert (method, path, params) == (
                "GET",
                "/api/v1/dex/market/rwa/tokens",
                {"binanceChainId": "56"},
            )
            self.evidence.append({"http_status": 200})
            return rows, received, 0

        def close(self):
            pass

    monkeypatch.setattr(diagnostic, "BinanceWeb3Client", lambda *a, **kw: Client())
    result = diagnostic.catalog_audit(
        SimpleNamespace(binance_web3_api_key=None, binance_web3_secret_key=None)
    )
    audited = result["checks"][0]["result"]["target_rows"]
    assert audited[0]["status"] == "UNAVAILABLE" and audited[1]["status"] == "PASS"
    assert audited[0]["rejected_fields"] == [
        {"field": ["statusInfo", "marketStatus"], "type": "literal_error"}
    ]
    assert "UNEXPECTED" not in json.dumps(result) and result["request_count"] == 1
