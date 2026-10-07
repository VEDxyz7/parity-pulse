import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.clients.binance_web3 import PREFIX, BinanceWeb3Client
from app.clients.common import ProviderError
from app.models.data import financial, quality_at, source_time
from app.providers.binance import BinanceMarketProvider, BinanceRWAProvider
from app.services.asset_discovery import AssetDiscoveryService

FIXTURES = Path(__file__).parents[1] / "fixtures"
NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)


def fixture(name, provider="binance"):
    return json.loads((FIXTURES / provider / (name + ".json")).read_text(), parse_float=Decimal)


def providers(patch=None):
    calls = []

    def handler(request):
        calls.append(request)
        name = request.url.path.removeprefix("/build" + PREFIX).replace("/", "_")
        data = fixture(name)
        if patch:
            data = patch(name, data)
        return httpx.Response(200, text=json.dumps(data, default=str))

    c = BinanceWeb3Client(
        SecretStr("test-key"),
        SecretStr("test-secret"),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: NOW,
        min_interval=0,
        sleep=lambda _: None,
    )
    return BinanceRWAProvider(c), BinanceMarketProvider(c), calls


def test_rwa_discovery_profile_price_status_independent_separation():
    rwa, market, calls = providers()
    result = AssetDiscoveryService(rwa, market).resolve("Nvidia")
    assert result["asset"].ticker == "NVDA"
    assert {t.platform_id for t in result["tokens"]} == {"ondo", "bstock"}
    token = next(t for t in result["tokens"] if t.platform_id == "ondo")
    profile = rwa.profile(token)
    obs = rwa.observation(profile)
    state = rwa.market(profile)
    assert profile.token_to_share_ratio == Decimal(
        fixture("rwa_underlying-profile")["data"]["tokenToShareRatio"]
    )
    assert obs.token_price == Decimal(fixture("rwa_price")["data"][0]["tokenPrice"])
    assert obs.raw_source_timestamp == str(fixture("rwa_price")["data"][0]["tokenPriceUpdatedAt"])
    assert obs.binance_reference_price is not None and obs.source == "BINANCE_RWA"
    assert state.state == "premarket" and profile.protections
    assert calls[0].url.params["keyword"] == "Nvidia"
    assert all("ticker" not in r.url.params and "company" not in r.url.params for r in calls)
    assert any(r.url.params.get("tokenContractAddresses") == token.contract for r in calls)
    bstock = next(t for t in result["tokens"] if t.platform_id == "bstock")
    assert bstock.market_state == "UNKNOWN"


@pytest.mark.parametrize(
    "field,value",
    [
        ("tokenPrice", "0"),
        ("tokenPrice", "-1"),
        ("tokenPrice", "NaN"),
        ("tokenToShareRatio", "0"),
        ("volume24H", "bad"),
        ("decimals", True),
        ("statusInfo", {"openState": True, "marketStatus": "UNEXPECTED"}),
    ],
)
def test_invalid_rwa_financial_schema_is_rejected(field, value):
    def patch(name, data):
        if name == "rwa_tokens":
            data["data"][0][field] = value
        return data

    rwa, _, _ = providers(patch)
    accepted = rwa.tokens()
    assert len(accepted) == 1 and accepted[0].platform_id == "bstock"
    assert rwa.catalog_rejections == [{"row": 0, "reason": "PAYLOAD_SCHEMA_INVALID"}]


def test_missing_rwa_fields_and_unknown_issuer_fail():
    def missing(name, data):
        if name == "rwa_tokens":
            del data["data"][0]["tokenToShareRatio"]
        return data

    rwa, _, _ = providers(missing)
    accepted = rwa.tokens()
    assert len(accepted) == 1 and accepted[0].platform_id == "bstock"
    assert rwa.catalog_rejections == [{"row": 0, "reason": "PAYLOAD_SCHEMA_INVALID"}]

    def unknown(name, data):
        if name == "rwa_tokens":
            data["data"][0]["platformId"] = "unverified-xstocks"
        return data

    rwa, market, _ = providers(unknown)
    with pytest.raises(ProviderError, match="ISSUER"):
        AssetDiscoveryService(rwa, market).universe()
    rwa, market, _ = providers(lambda n, d: dict(d, data=[]) if n == "rwa_search" else d)
    assert AssetDiscoveryService(rwa, market).resolve("xstocks")["status"] == "UNAVAILABLE"


def test_market_methods_batches_candles_trades_and_units():
    rwa, market, calls = providers()
    token = rwa.tokens()[0]
    assert "56" in {c.binanceChainId for c in market.chains()}
    assert market.search("56", "NVDA")
    assert market.basic_info(token).decimals == 18
    prices = market.prices([token])
    metrics = market.prices([token], info=True)
    candles = market.candles(token, bar="1h", limit=10)
    trades, cursor = market.trades(token, limit=5)
    assert prices[0].token_price > 0 and metrics[0].trade_count >= 0
    assert len(candles) == 10 and candles[0].open == Decimal(fixture("candles")["data"][0][0])
    assert candles[0].raw_source_timestamp == str(fixture("candles")["data"][0][5])
    assert candles[0].volume_unit == "UNKNOWN"
    assert (
        trades
        and cursor
        and all(t.token_price is None and t.data_quality == "CONFLICTING" for t in trades)
    )
    assert (
        trades[0].provider_metadata["reported_price"]
        == fixture("trades")["data"]["trades"][0]["price"]
    )
    for path in ["price", "price-info"]:
        request = next(r for r in calls if r.url.path.endswith("/" + path))
        assert request.method == "POST" and isinstance(json.loads(request.content), list)
        assert json.loads(request.content)[0]["binanceChainId"] == "56"
    assert next(r for r in calls if r.url.path.endswith("/candles")).url.params["bar"] == "1h"
    assert next(r for r in calls if r.url.path.endswith("/trades")).method == "GET"


def test_price_schema_identity_null_staleness_extra_fields():
    def wrong(name, data):
        if name == "price":
            data["data"][0]["binanceChainId"] = "1"
        return data

    rwa, market, _ = providers(wrong)
    with pytest.raises(ProviderError, match="BATCH"):
        market.prices([rwa.tokens()[0]])

    def missing(name, data):
        if name == "price":
            data["data"][0].update(price=None, extraFutureField="kept")
        return data

    rwa, market, _ = providers(missing)
    observation = market.prices([rwa.tokens()[0]])[0]
    assert observation.token_price is None and observation.data_quality == "MISSING"
    assert observation.provider_metadata["extraFutureField"] == "kept"
    assert quality_at("LIVE", NOW - timedelta(seconds=121), NOW) == "STALE"
    assert quality_at("LIVE", NOW + timedelta(seconds=10), NOW) == "INVALID"
    assert quality_at("DEMO", NOW - timedelta(days=1), NOW) == "DEMO"


@pytest.mark.parametrize("value", [0, -1, "Infinity", "NaN", True, 0.1, "not-money"])
def test_precision_invalid_money(value):
    if value in [0, -1] and type(value) is int:
        from pydantic import TypeAdapter

        from app.models.data import Positive

        with pytest.raises(ValidationError):
            TypeAdapter(Positive).validate_python(value)
    else:
        with pytest.raises(ValueError):
            financial(value)


def test_source_timestamp_units_and_ns_precision():
    assert source_time(1791288000000) == NOW
    assert source_time(1791288000123456789, "ns").microsecond == 123456
    for value in [0, True, "1791288000000", -1, 99999999999999999999999]:
        with pytest.raises(ValueError):
            source_time(value)


def test_measured_full_catalog_quarantines_undocumented_rows():
    rwa, _, _ = providers(lambda n, d: fixture("rwa_catalog") if n == "rwa_tokens" else d)
    tokens = rwa.tokens()
    assert len(tokens) == 451 and len(rwa.catalog_rejections) == 37
    assert {t.platform_id for t in tokens if t.ticker == "NVDA"} == {"ondo", "bstock"}
    assert all(t.market_state != "paused" for t in tokens)


def test_measured_candle_bounds_are_enforced_locally():
    rwa, market, _ = providers(lambda n, d: fixture("candles_bounded") if n == "candles" else d)
    # Exact request times recorded with this sanitized fixture, independent of mutable docs.
    before, after = 1791272680000, 1791287080000
    rows = market.candles(rwa.tokens()[0], bar="1h", before=before, after=after)
    assert rows and all(before < int(r.raw_source_timestamp) < after for r in rows)
    assert market.candle_rejections
    rwa, market, _ = providers(lambda n, d: fixture("candles_page") if n == "candles" else d)
    rows = market.candles(rwa.tokens()[0], bar="1h", after=1791273600000, limit=4)
    assert len(rows) == 3 and market.candle_rejections == [
        {"timestamp": 1791273600000, "reason": "OUTSIDE_EXCLUSIVE_BOUND"}
    ]


@pytest.mark.parametrize("name", ["rwa_tokens", "rwa_underlying-profile", "rwa_underlying-market"])
def test_critical_asset_type_never_coerces_boolean(name):
    from app.providers.binance import Profile, RWAToken, UnderlyingMarket, validate

    raw = fixture(name)["data"]
    if isinstance(raw, list):
        raw = raw[0]
    raw["assetType"] = True
    schema = {
        "rwa_tokens": RWAToken,
        "rwa_underlying-profile": Profile,
        "rwa_underlying-market": UnderlyingMarket,
    }[name]
    with pytest.raises(ProviderError, match="PAYLOAD_SCHEMA_INVALID"):
        validate(schema, raw)
