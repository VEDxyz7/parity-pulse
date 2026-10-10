"""Unwired read-only wallet capture prototype, not execution-ready evidence.

Preserves wallet balances/discovery/marks, with explicit admission blockers.
Quotes are not liquidity reserves; Binance's index is not independent equity.
No live worker uses this prototype, and no default cost or risk is invented.
"""

from datetime import UTC, datetime
from decimal import Decimal

from app.models.portfolio import PortfolioInputs
from app.models.routing import RouteIdentity, RouteInput

USDT = "0x55d398326f99059ff775485246999027b3197955"
USDT_DECIMALS = 18
SOURCE = "LIVE_WALLET_AND_BINANCE"


class LiveLimits:
    """Operator limits for live rebalancing; all are hard caps checked by RiskEngine."""

    def __init__(
        self,
        *,
        max_notional_usd,
        max_slippage_bps,
        max_portfolio_exposure_usd=Decimal("1000"),
        max_daily_loss_usd=Decimal("50"),
        max_trades_per_day=20,
        min_liquidity_usd=Decimal("1000"),
        max_liquidity_fraction=Decimal("0.25"),
        stress_adverse_move_fraction=Decimal("0.10"),
        cooldown_seconds=15,
        gas_reserve_wei=2 * 10**15,
        max_parity_deviation=Decimal("0.03"),
        depth_probe_multiple=8,
        trust_required=True,
    ):
        self.max_notional_usd = Decimal(str(max_notional_usd))
        self.max_slippage_bps = Decimal(str(max_slippage_bps))
        self.max_portfolio_exposure_usd = Decimal(str(max_portfolio_exposure_usd))
        self.max_daily_loss_usd = Decimal(str(max_daily_loss_usd))
        self.max_trades_per_day = max_trades_per_day
        self.min_liquidity_usd = Decimal(str(min_liquidity_usd))
        self.max_liquidity_fraction = Decimal(str(max_liquidity_fraction))
        self.stress_adverse_move_fraction = Decimal(str(stress_adverse_move_fraction))
        self.cooldown_seconds = cooldown_seconds
        self.gas_reserve_wei = gas_reserve_wei
        self.max_parity_deviation = Decimal(str(max_parity_deviation))
        self.depth_probe_multiple = depth_probe_multiple
        if trust_required is not True:
            raise ValueError("Trust cannot be disabled")
        self.trust_required = True


def no_activity():
    return 0, None, Decimal(0)


class LivePortfolioSource:
    def __init__(
        self,
        *,
        rwa,
        trading,
        market,
        equity,
        rpc,
        wallet,
        limits,
        activity=no_activity,
        clock=lambda: datetime.now(UTC),
        capture_rfq=None,
    ):
        self.rwa, self.trading, self.market, self.equity = rwa, trading, market, equity
        self.rpc, self.wallet, self.limits = rpc, wallet.lower(), limits
        self.activity, self.clock = activity, clock
        self.capture_rfq = capture_rfq
        self._decimals = {}
        self.last_capture = {}
        self.notes = []

    def decimals(self, contract):
        return self._decimals.get(contract)

    # -- capture -----------------------------------------------------------------------------
    def capture(self, config):
        now = self.clock()
        self.notes = []
        native = self.rpc.native_balance(self.wallet)
        usdt_balance = self.rpc.erc20_balance(USDT, self.wallet)
        balance_at = self.clock()
        tickers = {t.asset for t in config.targets if t.kind == "TOKENIZED_STOCK"}
        tokens = [
            t
            for t in self.rwa.tokens("56")
            if t.ticker in tickers and t.chain_id == "56" and t.asset_type == 1
        ]
        prices = {o.contract: o for o in self.rwa.prices(tokens)} if tokens else {}
        blockers = [
            "TRUST_EVIDENCE_UNAVAILABLE",
            "AUTHORITATIVE_LIQUIDITY_UNAVAILABLE",
            "INDEPENDENT_EQUITY_REFERENCE_REQUIRED",
            "VERIFIED_QUOTE_COST_UNITS_REQUIRED",
        ]
        routes = []
        balances = {USDT: str(usdt_balance)}
        self._decimals = {t.contract: t.decimals for t in tokens}
        for token in sorted(tokens, key=lambda t: (t.ticker, t.platform_id, t.contract)):
            price = prices.get(token.contract)
            balances[token.contract] = str(self.rpc.erc20_balance(token.contract, self.wallet))
            supported = token.reason_code not in {
                "ASSET_PAUSED",
                "ASSET_LIMITED",
                "UNSUPPORTED",
                "MARKET_MAINTENANCE",
            }
            route = dict(
                identity=RouteIdentity(
                    underlying=token.ticker,
                    issuer=token.platform_id,
                    chain_id="56",
                    contract=token.contract,
                    token=token.token_symbol,
                ),
                data_mode="LIVE",
                token_price_usd=price.token_price if price else None,
                token_to_share_ratio=token.token_to_share_ratio,
                price_source=price.source if price else token.source,
                price_timestamp=price.source_timestamp if price else None,
                price_quality=price.data_quality if price else "MISSING",
                ratio_source=token.source,
                ratio_observed_at=token.ingestion_timestamp,
                ratio_source_timestamp=token.source_timestamp,
                supported=supported,
                market_state="open"
                if token.market_state in {None, "UNKNOWN"}
                and token.open_state is True
                and token.reason_code == "TRADING"
                else token.market_state or "UNKNOWN",
                tradable=token.open_state,
                trust_state="INSUFFICIENT_EVIDENCE",
                trust_source="TRUST_EVIDENCE_UNAVAILABLE",
                trust_timestamp=now,
            )
            # Preserve mark/discovery only. Do not infer fees, slippage, liquidity,
            # route availability or successful Trust from an aggregator quote.
            route = RouteInput(**route)
            routes.append(route)
        if not tokens:
            blockers.append("NO_CONFIGURED_TOKENIZED_STOCK_DISCOVERED")
        self.last_capture = dict(
            at=now,
            balance_received_at=balance_at,
            wallet=self.wallet,
            balances_base_units=balances,
            native_balance_wei=str(native),
            notes=self.notes,
        )
        return PortfolioInputs(
            data_mode="LIVE_READ_ONLY",
            captured_at=now,
            position_verified_at=balance_at,
            # Raw balances are retained in last_capture, not promoted to verified
            # USD funding with fabricated zero costs/conversion timestamps.
            inventory_complete=False,
            funding=None,
            token_funding=(),
            routes=tuple(routes),
            risks=(),
            source=SOURCE,
            blockers=tuple(dict.fromkeys(blockers)),
        )
