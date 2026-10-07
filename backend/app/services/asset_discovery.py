from app.clients.common import ProviderError
from app.models.data import TrackedAsset


class AssetDiscoveryService:
    def __init__(self, rwa, market=None, *, mode="LIVE", chain="56"):
        self.rwa, self.market, self.mode, self.chain = rwa, market, mode, chain

    def universe(self):
        if self.market and self.chain not in {c.binanceChainId for c in self.market.chains()}:
            raise ProviderError("DISCOVERY", "CHAIN_NOT_SUPPORTED")
        issuers = self.rwa.platforms()
        platforms = {p.platform_id: p for p in issuers}
        tokens = self.rwa.tokens(self.chain)
        for t in tokens:
            if t.platform_id not in platforms or t.chain_id not in platforms[t.platform_id].chains:
                raise ProviderError("DISCOVERY", "ISSUER_CHAIN_NOT_VERIFIED")
        assets = {}
        for token in tokens:
            if token.asset_type != 1:
                continue
            assets[token.ticker] = TrackedAsset(
                source="DEMO_DISCOVERY" if self.mode == "DEMO" else "BINANCE_RWA",
                provider_identifier=token.ticker,
                ingestion_timestamp=token.ingestion_timestamp,
                data_mode=self.mode,
                data_quality="DEMO" if self.mode == "DEMO" else "UNKNOWN",
                ticker=token.ticker,
                company_name=token.company_name,
                supported=True,
                status="DEMO" if self.mode == "DEMO" else "VERIFIED",
            )
        return sorted(assets.values(), key=lambda a: a.ticker), issuers, tokens

    def resolve(self, query):
        matches = self.rwa.search(query)
        exact = [
            m
            for m in matches
            if m.ticker.casefold() == query.casefold()
            or m.companyName.casefold() == query.casefold()
        ]
        candidates = exact or matches
        if len(candidates) != 1:
            return {
                "status": "UNAVAILABLE" if not candidates else "NOT_VERIFIED",
                "reason": "NO_VERIFIED_MATCH" if not candidates else "AMBIGUOUS_MATCH",
                "assets": [],
            }
        match = candidates[0]
        assets, issuers, universe = self.universe()
        expected = {
            (a.platformId, a.binanceChainId, a.tokenContractAddress)
            for a in match.assets
            if a.assetType == 1 and a.binanceChainId == self.chain
        }
        tokens = [
            t
            for t in universe
            if t.ticker == match.ticker and (t.platform_id, t.chain_id, t.contract) in expected
        ]
        if not tokens:
            return {"status": "UNAVAILABLE", "reason": "NO_VERIFIED_REPRESENTATION", "assets": []}
        if len(tokens) > 10:
            raise ProviderError("DISCOVERY", "REPRESENTATION_BOUND_EXCEEDED")
        return {
            "status": "DEMO" if self.mode == "DEMO" else "VERIFIED",
            "asset": next(a for a in assets if a.ticker == match.ticker),
            "issuers": issuers,
            "tokens": tokens,
        }
