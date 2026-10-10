"""Merge-specific regressions; synthetic fixtures, no provider/wallet network calls."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from app.services.live_portfolio_source import USDT, LiveLimits, LivePortfolioSource

NOW = datetime(2026, 10, 11, tzinfo=UTC)
TOKEN = "0x" + "b" * 40
WALLET = "0x" + "a" * 40


def test_read_only_wallet_capture_never_fabricates_risk_liquidity_or_costs():
    calls = []

    class Rpc:
        def native_balance(self, wallet):
            calls.append(("native_balance", wallet))
            return 10**18

        def erc20_balance(self, token, wallet):
            calls.append(("erc20_balance", token, wallet))
            return 10**18

    class Rwa:
        def tokens(self, chain):
            assert chain == "56"
            return [
                NS(
                    ticker="NVDA",
                    chain_id="56",
                    asset_type=1,
                    contract=TOKEN,
                    decimals=18,
                    platform_id="BStock",
                    token_symbol="NVDAB",
                    reason_code="TRADING",
                    market_state="offhours",
                    open_state=True,
                    token_to_share_ratio=Decimal("1"),
                    source="BINANCE",
                    source_timestamp=NOW,
                    ingestion_timestamp=NOW,
                )
            ]

        def prices(self, tokens):
            assert len(tokens) == 1
            return [
                NS(
                    contract=TOKEN,
                    token_price=Decimal("235"),
                    source="BINANCE",
                    source_timestamp=NOW,
                    data_quality="LIVE",
                )
            ]

    class NoOtherReads:
        def __getattr__(self, name):
            raise AssertionError(f"Unexpected reference/quote/capture operation: {name}")

    source = LivePortfolioSource(
        rwa=Rwa(),
        trading=NoOtherReads(),
        market=NoOtherReads(),
        equity=NoOtherReads(),
        rpc=Rpc(),
        wallet=WALLET,
        limits=LiveLimits(max_notional_usd="25", max_slippage_bps="100"),
        clock=lambda: NOW,
        capture_rfq=lambda *_: pytest.fail("automatic signing-payload capture forbidden"),
    )
    inputs = source.capture(NS(targets=[NS(asset="NVDA", kind="TOKENIZED_STOCK")]))
    assert inputs.blockers == (
        "TRUST_EVIDENCE_UNAVAILABLE",
        "AUTHORITATIVE_LIQUIDITY_UNAVAILABLE",
        "INDEPENDENT_EQUITY_REFERENCE_REQUIRED",
        "VERIFIED_QUOTE_COST_UNITS_REQUIRED",
    )
    assert inputs.data_mode == "LIVE_READ_ONLY" and not inputs.inventory_complete
    assert inputs.funding is None and not inputs.token_funding and not inputs.risks
    (route,) = inputs.routes
    assert route.market_state == "offhours" and route.trust_state == "INSUFFICIENT_EVIDENCE"
    assert route.liquidity_usd is None and route.liquidity_status == "UNAVAILABLE"
    assert (
        route.fees_usd is None and route.slippage_bps is None and route.cost_status == "UNAVAILABLE"
    )
    assert route.route_available is None and route.route_support == "INDICATIVE_ONLY"
    assert source.last_capture["balances_base_units"] == {USDT: str(10**18), TOKEN: str(10**18)}
    assert len(calls) == 3 and source.decimals(TOKEN) == 18


def test_wallet_capture_cannot_disable_trust():
    with pytest.raises(ValueError, match="Trust cannot be disabled"):
        LiveLimits(max_notional_usd="25", max_slippage_bps="100", trust_required=False)


def test_quote_informational_fields_do_not_change_route_fingerprint():
    from app.models.execution import QuoteRoute, SegmentToken, fingerprint
    from backend.tests.fixtures.execution_fixtures import quote
    from backend.tests.unit.test_execution_safety import request

    # Existing canonical fixture is augmented with descriptive fields only.
    raw = quote(request()).route
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump(mode="json")
    before = QuoteRoute.model_validate(raw)
    after = QuoteRoute.model_validate({**raw, "isBest": True})
    assert fingerprint(before) == fingerprint(after)
    segment = SegmentToken(
        tokenContractAddress=TOKEN,
        tokenSymbol="NVDA",
        tokenUnitPrice="235",
        decimal="18",
        isHoneyPot=False,
        taxRate="0",
    )
    assert segment.model_dump() == {"tokenContractAddress": TOKEN, "tokenSymbol": "NVDA"}
