"""Cached discovery boundary. Missing host inventory/funding is never replaced by fixtures."""

from app.models.data import TokenMetadata, TokenObservation
from app.models.portfolio import PortfolioInputs
from app.models.routing import RouteIdentity, RouteInput


class CachedPortfolioSource:
    """Read stored provider observations only; no endpoint calls, estimates or balance guesses.

    A verified host adapter can supply PortfolioInputs through create_app(portfolio_source=...).
    It must bind fresh inventory, prices, independent equity, costs and Trust evidence. The
    default adapter explicitly blocks until that assembly exists (Phase 7 remains PARTIAL).
    """

    def __init__(self, data_layer, *, clock):
        self.data = data_layer
        self.clock = clock
        self._decimals = {}

    def capture(self, config):
        mode = "DEMO" if config.data_mode == "DEMO" else "LIVE"
        routes = []
        self._decimals = {}
        blockers = [
            "CURRENT_FUNDING_UNAVAILABLE",
            "CURRENT_COMPLETE_INVENTORY_UNAVAILABLE",
            "HOST_RISK_TRUST_COST_ASSEMBLY_UNAVAILABLE",
        ]
        for target in sorted(config.targets, key=lambda t: t.asset):
            if target.kind != "TOKENIZED_STOCK":
                continue
            metadata = self.data.repository.list(TokenMetadata, mode=mode, ticker=target.asset)
            prices = self.data.repository.list(TokenObservation, mode=mode, ticker=target.asset)
            if len(metadata) == 1000 or len(prices) == 1000:
                blockers.append("CACHE_COVERAGE_BOUND_EXCEEDED")
            seen = set()
            for token in metadata:
                key = (token.chain_id, token.contract)
                if key in seen:
                    continue
                seen.add(key)
                price = next(
                    (
                        p
                        for p in prices
                        if (
                            p.chain_id,
                            p.contract,
                            p.issuer,
                            p.token_symbol,
                            p.token_to_share_ratio,
                        )
                        == (*key, token.platform_id, token.token_symbol, token.token_to_share_ratio)
                        and p.kind in {"PRICE", "PRICE_INFO"}
                    ),
                    None,
                )
                if token.chain_id == "56":
                    self._decimals[token.contract] = token.decimals
                routes.append(
                    RouteInput(
                        identity=RouteIdentity(
                            underlying=token.ticker,
                            issuer=token.platform_id,
                            chain_id=token.chain_id,
                            contract=token.contract,
                            token=token.token_symbol,
                        ),
                        data_mode=mode,
                        token_price_usd=price.token_price if price else None,
                        token_to_share_ratio=token.token_to_share_ratio,
                        price_source=price.source if price else token.source,
                        price_timestamp=price.source_timestamp if price else None,
                        price_quality=price.data_quality if price else "MISSING",
                        ratio_source=token.source,
                        ratio_observed_at=token.ingestion_timestamp,
                        ratio_source_timestamp=token.source_timestamp,
                        supported=token.asset_type == 1
                        and token.reason_code
                        not in {
                            "ASSET_PAUSED",
                            "ASSET_LIMITED",
                            "UNSUPPORTED",
                            "MARKET_MAINTENANCE",
                        },
                        market_state=token.market_state,
                        tradable=token.open_state,
                    )
                )
        return PortfolioInputs(
            data_mode=config.data_mode,
            captured_at=self.clock(),
            position_verified_at=None,
            inventory_complete=False,
            funding=None,
            routes=tuple(routes),
            source="MODE_SCOPED_PROVIDER_CACHE",
            blockers=tuple(dict.fromkeys(blockers)),
        )

    def decimals(self, contract):
        return self._decimals.get(contract)
