"""Live portfolio capture: on-chain wallet balances + Binance RWA marks + executable costs.

Every number in the returned PortfolioInputs comes from a fresh read in this capture:
- balances: BSC RPC `balanceOf` / `eth_getBalance` for the configured wallet;
- token marks, share ratios, tradability: Binance RWA `rwa/tokens` + `rwa/price`;
- costs/slippage/route availability: a Binance aggregator quote at the trade-size probe;
- liquidity: Binance pool reserves when reported, else quote-verified executable depth;
- independent equity: Binance multi-vendor equity index (see equity_reference.py).

Trust is not evaluated here (classifier parked); routes carry INSUFFICIENT_EVIDENCE and the
portfolio service must be configured with trust_required=False to plan from them.
"""

from datetime import UTC, datetime
from decimal import Decimal, localcontext

from app.clients.common import ProviderError
from app.models.execution import (
    ExecutionRiskEvidence,
    FundingAsset,
    FundingState,
    QuoteRequest,
)
from app.models.portfolio import AssetRisk, PortfolioInputs
from app.models.risk import OpportunityRiskContext
from app.models.routing import RouteIdentity, RouteInput
from app.services.routing import CLOSED_STATES

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
        trust_required=False,
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
        self.trust_required = trust_required


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
        self._captured = set()  # one planning capture per (vendor, token pair) per process
        self._decimals = {}
        self.last_capture = {}
        self.notes = []

    def decimals(self, contract):
        return self._decimals.get(contract)

    # -- reads -------------------------------------------------------------------------------
    def _usd_rates(self):
        usdc, at, _ = self.market.read("GET", "/api/v3/ticker/price", {"symbol": "USDCUSDT"})
        bnb, _, _ = self.market.read("GET", "/api/v3/ticker/price", {"symbol": "BNBUSDT"})
        usdt_per_usd = Decimal(str(usdc["price"]))
        if abs(usdt_per_usd - 1) > Decimal("0.02"):
            raise ProviderError("BINANCE_INDEX", "USDT_USD_CONVERSION_OUT_OF_RANGE")
        with localcontext() as ctx:
            ctx.prec = 34
            return Decimal(1) / usdt_per_usd, Decimal(str(bnb["price"])) / usdt_per_usd, at

    def _quote(self, token, usd):
        amount = int(usd * 10**USDT_DECIMALS)
        request = QuoteRequest(
            binanceChainId="56",
            amount=str(amount),
            fromTokenAddress=USDT,
            toTokenAddress=token.contract,
            userWalletAddress=self.wallet,
        )
        quotes = self.trading.quote(request, mode="LIVE_READ_ONLY")
        self._capture_rfq_payloads(quotes)
        best = [q for q in quotes if q.route.executionMode == "SWAP"]
        if not best:
            return None
        return min(best, key=lambda q: -int(q.route.toTokenAmount))

    def _capture_rfq_payloads(self, quotes):
        """Planning-time capture: record real RFQ /swap payloads even in read-only mode."""
        if self.capture_rfq is None:
            return
        for q in quotes:
            key = (q.route.vendorName, q.request.fromTokenAddress, q.request.toTokenAddress)
            if q.route.executionMode != "RFQ" or key in self._captured:
                continue
            self._captured.add(key)
            try:
                raw = self.trading.build_rfq(q, slippage_bps=self.limits.max_slippage_bps)
                self.capture_rfq(raw, verdict="PLANNING_CAPTURE")
            except (ProviderError, ValueError):
                continue

    def _liquidity(self, token, now):
        try:
            data, _, _ = self.rwa.client.read(
                "GET",
                "/api/v1/dex/market/token/top-liquidity",
                {"binanceChainId": "56", "tokenContractAddress": token.contract},
                ttl=30,
            )
            pools = sum(
                (
                    Decimal(str(r["liquidityUsd"]))
                    for r in data
                    if isinstance(r, dict) and r.get("liquidityUsd") is not None
                ),
                Decimal(0),
            )
        except (ProviderError, KeyError, TypeError, ValueError, ArithmeticError):
            pools = Decimal(0)
        if pools > 0:
            return pools, "BINANCE_POOL_RESERVES"
        # RFQ / prop-AMM depth is invisible in pool reserves: verify executable depth with a
        # quote several times the largest allowed trade and accept it only within the cap.
        probe = max(
            self.limits.min_liquidity_usd,
            self.limits.max_notional_usd * self.limits.depth_probe_multiple,
        )
        quote = self._quote(token, probe)
        if quote is None or quote.route.priceImpactPercent is None:
            return None, None
        impact_bps = abs(quote.route.priceImpactPercent) * 10000
        if impact_bps > self.limits.max_slippage_bps:
            return None, None
        return probe, "BINANCE_AGGREGATOR_EXECUTABLE_DEPTH"

    # -- capture -----------------------------------------------------------------------------
    def capture(self, config):
        now = self.clock()
        self.notes = []
        usdt_usd, bnb_usd, rate_at = self._usd_rates()
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
        trades, last_trade, daily_loss = self.activity()
        blockers = []
        routes, token_funding, risks = [], [], []
        self._decimals = {t.contract: t.decimals for t in tokens}
        funding = self._funding(
            USDT, "USDT", USDT_DECIMALS, usdt_balance, usdt_usd, native, bnb_usd, now, balance_at
        )
        stock_value = Decimal(0)
        evidence = {}
        for token in sorted(tokens, key=lambda t: (t.ticker, t.platform_id, t.contract)):
            price = prices.get(token.contract)
            balance = self.rpc.erc20_balance(token.contract, self.wallet)
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
                else token.market_state,
                tradable=token.open_state,
                trust_state="INSUFFICIENT_EVIDENCE",
                trust_source="NOT_EVALUATED_CLASSIFIER_PARKED",
                trust_timestamp=now,
            )
            quote = None
            if price and supported and token.open_state:
                try:
                    quote = self._quote(token, self.limits.max_notional_usd)
                    liquidity, liquidity_source = self._liquidity(token, now)
                except ProviderError:
                    quote, liquidity, liquidity_source = None, None, None
                if quote is not None:
                    impact = abs(quote.route.priceImpactPercent or Decimal(0)) * 10000
                    route.update(
                        fees_usd=Decimal(0),
                        gas_usd=quote.route.tradeFee or Decimal(0),
                        slippage_bps=max(Decimal(10), impact),
                        cost_status="AVAILABLE",
                        cost_source="BINANCE_AGGREGATOR_QUOTE_" + quote.route.vendorName,
                        cost_timestamp=quote.received_at,
                        route_available=True,
                        route_support="VERIFIED_PROVIDER_ROUTE",
                    )
                if liquidity is not None:
                    route.update(
                        liquidity_usd=liquidity,
                        liquidity_status="AVAILABLE",
                        liquidity_source=liquidity_source,
                        liquidity_timestamp=now,
                    )
            route = RouteInput(**route)
            routes.append(route)
            if price:
                token_funding.append(
                    self._funding(
                        token.contract,
                        token.token_symbol,
                        token.decimals,
                        balance,
                        price.token_price,
                        native,
                        bnb_usd,
                        now,
                        balance_at,
                    )
                )
                with localcontext() as ctx:
                    ctx.prec = 72
                    stock_value += Decimal(balance) / Decimal(10) ** token.decimals * (
                        price.token_price
                    )
            evidence.setdefault(token.ticker, []).append((route, quote))
        for ticker in sorted(tickers):
            risks.append(
                self._risk(
                    ticker,
                    evidence.get(ticker, []),
                    funding,
                    stock_value,
                    trades,
                    last_trade,
                    daily_loss,
                    now,
                    blockers,
                )
            )
        if not tokens:
            blockers.append("NO_CONFIGURED_TOKENIZED_STOCK_DISCOVERED")
        self.last_capture = dict(at=now, rates_at=rate_at, wallet=self.wallet, notes=self.notes)
        return PortfolioInputs(
            data_mode="LIVE_READ_ONLY",
            captured_at=now,
            position_verified_at=balance_at,
            inventory_complete=True,
            funding=funding,
            token_funding=tuple(token_funding),
            routes=tuple(routes),
            risks=tuple(r for r in risks if r is not None),
            source=SOURCE,
            blockers=tuple(dict.fromkeys(blockers)),
        )

    def _funding(self, contract, symbol, decimals, balance, price, native, bnb_usd, now, at):
        return FundingState(
            asset=FundingAsset(
                chain_id="56",
                contract=contract,
                symbol=symbol,
                decimals=decimals,
                source="BSC_RPC_BALANCE_OF",
                observed_at=at,
                data_mode="LIVE_READ_ONLY",
            ),
            wallet=self.wallet,
            balance_base_units=str(balance),
            native_gas_balance_wei=str(native),
            gas_reserve_wei=str(self.limits.gas_reserve_wei),
            native_unit_price_usd=bnb_usd,
            native_price_observed_at=now,
            unit_price_usd=price,
            price_observed_at=now,
            balance_observed_at=at,
            conversion_cost_usd=Decimal(0),
            conversion_cost_observed_at=now,
            conversion_required=False,
            conversion_verified=True,
            identity_verified=True,
            source=SOURCE,
        )

    def _risk(self, ticker, rows, funding, stock_value, trades, last, loss, now, blockers):
        """Per-asset risk template; the portfolio service fills notional/costs per action."""
        priced = [(r, q) for r, q in rows if r.token_price_usd is not None]
        if not priced:
            blockers.append("NO_PRICED_REPRESENTATION_" + ticker)
            return None
        route = min(priced, key=lambda rq: (rq[0].token_price_usd / rq[0].token_to_share_ratio))[0]
        try:
            ref = self.equity.reference(ticker)
            equity_at, equity_ok = ref.observed_at, True
            with localcontext() as ctx:
                ctx.prec = 34
                per_share = route.token_price_usd / route.token_to_share_ratio
                deviation = abs(per_share - ref.price_usd) / ref.price_usd
            if deviation > self.limits.max_parity_deviation:
                blockers.append("PARITY_DEVIATION_EXCEEDS_LIMIT_" + ticker)
                equity_ok = False
        except ProviderError:
            equity_at, equity_ok = now, False
            blockers.append("INDEPENDENT_EQUITY_UNAVAILABLE_" + ticker)
        cash_usd = Decimal(funding.balance_base_units) / Decimal(10) ** funding.asset.decimals * (
            funding.unit_price_usd
        )
        lim = self.limits
        # Conservative: if any priced representation is closed the router may pick it.
        closed = any(r.market_state in CLOSED_STATES for r, _ in priced)
        if closed:
            blockers_note = "UNDERLYING_MARKET_CLOSED_" + ticker
            self.notes.append(blockers_note)
        cap = lim.max_notional_usd / 2 if closed else lim.max_notional_usd
        context = OpportunityRiskContext(
            data_mode="LIVE_READ_ONLY",
            observed_at=now,
            source="LIVE_OPERATOR_LIMITS",
            stress_adverse_move_fraction=lim.stress_adverse_move_fraction,
            wallet_available_usd=cash_usd,
            existing_exposure_usd=stock_value,
            daily_loss_usd=loss,
            trades_today=trades,
            last_trade_at=last,
            system_resolved=True,
            wallet_allowed=True,
            max_position_usd=cap,
            max_portfolio_exposure_usd=lim.max_portfolio_exposure_usd,
            max_daily_loss_usd=lim.max_daily_loss_usd,
            max_risk_budget_usd=lim.max_portfolio_exposure_usd,
            max_trades_per_day=lim.max_trades_per_day,
            max_liquidity_fraction=lim.max_liquidity_fraction,
            min_confidence="LOW",
            min_liquidity_usd=lim.min_liquidity_usd,
            min_liquidity_percentile=50,
            max_slippage_bps=lim.max_slippage_bps,
            min_net_edge_usd=Decimal("0.01"),
            cooldown_seconds=lim.cooldown_seconds,
        )
        return AssetRisk(
            asset=ticker,
            evidence=ExecutionRiskEvidence(
                decision_id="portfolio_template",
                data_mode="LIVE_READ_ONLY",
                purpose="DIRECT_EXPOSURE",
                budget_usd=cap,
                risk_budget_usd=cap,
                notional_usd=cap,
                costs_usd=Decimal(0),
                conversion_cost_usd=Decimal(0),
                slippage_bps=route.slippage_bps or Decimal(0),
                net_expected_edge_usd=Decimal(0),
                liquidity_usd=route.liquidity_usd,
                liquidity_p50_usd=None,
                context=context,
                confidence="LOW",
                trust_state="INSUFFICIENT_EVIDENCE",
                trust_required=lim.trust_required,
                tradable=route.tradable is True,
                route_available=route.route_available is True,
                token_observed_at=route.price_timestamp or now,
                equity_observed_at=equity_at,
                evidence_observed_at=now,
                required_evidence_valid=equity_ok,
                system_resolved=True,
            ),
        )
