"""Assemble wallet-inventory planning and (optionally) live execution from settings."""

from decimal import Decimal
from pathlib import Path

from app.clients.binance_futures import BinanceIndexClient
from app.clients.binance_trading import BinanceSafetyClient, LiveTradingClient
from app.clients.bsc_rpc import BscRpcClient
from app.repositories.live_fills import LiveFillStore
from app.services.equity_reference import EquityReferenceService
from app.services.live_portfolio_source import LiveLimits, LivePortfolioSource
from app.services.rfq_orders import parse_allowlist


class LiveRuntime:
    """Holds the live clients so the app lifespan can close them."""

    def __init__(self, configured, data_layer, directory):
        self.settings = configured
        self.index = BinanceIndexClient()
        # Only the full live opt-in gets the client that can submit RFQ orders.
        client = LiveTradingClient if configured.live_execution else BinanceSafetyClient
        self.trading = client(
            configured.binance_web3_api_key,
            configured.binance_web3_secret_key,
            cache_ttl=0,
            min_interval=1.2,
        )
        self.rpc = BscRpcClient(configured.bsc_rpc_url, allow_send=configured.live_execution)
        self.journal = LiveFillStore(
            None if directory is None else Path(directory) / "live_fills.sqlite"
        )
        self.signer = self._signer() if configured.live_execution else None
        wallet = self.signer.address if self.signer else configured.live_wallet_address
        if wallet is None:
            raise ValueError("Wallet inventory requires LIVE_WALLET_ADDRESS or a live signer")
        self.wallet = wallet.lower()
        cap = configured.live_max_notional_usd or 25
        self.limits = LiveLimits(
            max_notional_usd=cap,
            max_slippage_bps=configured.live_max_slippage_bps,
            trust_required=configured.trust_required_for_rebalance,
        )
        self.equity = EquityReferenceService(self.index)
        self.source = LivePortfolioSource(
            rwa=data_layer.rwa,
            trading=self.trading,
            market=self.index,
            equity=self.equity,
            rpc=self.rpc,
            wallet=self.wallet,
            limits=self.limits,
            activity=self.journal.activity,
            capture_rfq=self.journal.capture_rfq,
        )
        self.executor = None

    def _signer(self):
        if self.settings.live_signer == "LOCAL_KEY":
            from app.services.live_signer import LocalKeySigner

            return LocalKeySigner(self.settings.live_signer_private_key, self.rpc)
        if self.settings.live_signer == "ALTANA":
            from app.services.live_signer import AltanaSigner

            return AltanaSigner(self.settings.altana_sidecar_url, self.settings.sidecar_token)
        from app.services.agentic_wallet_signer import AgenticWalletSigner

        return AgenticWalletSigner(self.rpc)

    def attach(self, portfolio):
        if self.signer is None:
            return None
        from app.services.live_execution import LiveRebalanceExecutor

        self.executor = LiveRebalanceExecutor(
            portfolio,
            self.trading,
            self.rpc,
            self.signer,
            self.journal,
            max_notional_usd=self.limits.max_notional_usd,
            max_slippage_bps=self.limits.max_slippage_bps,
            gas_reserve_wei=self.limits.gas_reserve_wei,
            rfq_allowlist=parse_allowlist(self.settings.rfq_settlement_allowlist)
            if self.settings.rfq_enabled
            else None,
        )
        portfolio.live_execution = True
        return self.executor

    def status(self):
        return dict(
            wallet=self.wallet,
            signer=self.signer.kind if self.signer else None,
            live_execution=self.settings.live_execution,
            max_notional_usd=str(self.limits.max_notional_usd),
            max_slippage_bps=str(self.limits.max_slippage_bps),
            trust_required=self.limits.trust_required,
            equity_reference="BINANCE_USDM_EQUITY_INDEX",
            chain_id=56,
            rfq_enabled=bool(self.executor and self.executor.rfq_enabled),
            rfq_settlements={
                k: sorted(v)
                for k, v in parse_allowlist(self.settings.rfq_settlement_allowlist).items()
            },
            closed_market_swap=self.settings.closed_market_swap,
        )

    def close(self):
        for client in (self.index, self.trading, self.rpc, self.journal):
            client.close()


def parity(live, ticker):
    """Per-representation token price per share vs the independent equity index."""
    from decimal import localcontext

    ticker = ticker.upper()
    reference = live.equity.reference(ticker)
    tokens = [t for t in live.source.rwa.tokens("56") if t.ticker == ticker and t.asset_type == 1]
    rows = []
    for observation in live.source.rwa.prices(tokens) if tokens else []:
        token = next(t for t in tokens if t.contract == observation.contract)
        with localcontext() as ctx:
            ctx.prec = 34
            per_share = observation.token_price / token.token_to_share_ratio
            deviation_bps = (per_share - reference.price_usd) / reference.price_usd * 10000
        rows.append(
            dict(
                issuer=token.platform_id,
                token=token.token_symbol,
                contract=token.contract,
                token_price_usd=str(observation.token_price),
                shares_per_token=str(token.token_to_share_ratio),
                price_per_share_usd=str(per_share.quantize(Decimal("0.0001"))),
                deviation_bps=str(deviation_bps.quantize(Decimal("0.01"))),
                token_observed_at=observation.source_timestamp.isoformat(),
                market_state=token.market_state,
            )
        )
    return dict(
        ticker=ticker,
        equity_reference_usd=str(reference.price_usd.quantize(Decimal("0.0001"))),
        equity_source=reference.source,
        equity_observed_at=reference.observed_at.isoformat(),
        timestamp_semantics=reference.timestamp_semantics,
        representations=rows,
        trust="NOT_EVALUATED",
    )
