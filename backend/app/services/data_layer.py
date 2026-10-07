from app.clients.binance_web3 import BinanceWeb3Client
from app.clients.common import ProviderError
from app.clients.massive import MassiveClient
from app.providers.binance import BinanceMarketProvider, BinanceRWAProvider
from app.providers.demo import DemoEquityProvider, DemoRWAProvider, load_data_fixture
from app.providers.massive import MassiveProvider
from app.repositories.data import DataRepository
from app.services.asset_discovery import AssetDiscoveryService
from app.services.calendar import USEquityCalendar


class DataLayer:
    def __init__(self, settings, database):
        self.repository = DataRepository(database)
        self.clients = []
        self.mode = "DEMO" if settings.data_mode == "DEMO" else "LIVE"
        if self.mode == "DEMO":
            records = load_data_fixture()
            self.repository.save([r for rows in records.values() for r in rows])
            self.rwa, self.equity = DemoRWAProvider(records), DemoEquityProvider(records)
            self.market = None
        else:
            client = BinanceWeb3Client(
                settings.binance_web3_api_key, settings.binance_web3_secret_key
            )
            independent = MassiveClient(settings.massive_api_key)
            self.clients = [client, independent]
            self.rwa, self.market, self.equity = (
                BinanceRWAProvider(client),
                BinanceMarketProvider(client),
                MassiveProvider(independent, freshness=settings.massive_data_quality),
            )
        self.discovery = AssetDiscoveryService(
            self.rwa, self.market, mode=self.mode, chain="DEMO" if self.mode == "DEMO" else "56"
        )
        self.calendar = USEquityCalendar(mode=self.mode)

    def close(self):
        for client in self.clients:
            client.close()

    def assets(self):
        assets, issuers, tokens = self.discovery.universe()
        self.repository.save([*assets, *issuers, *tokens])
        return {
            "data_mode": self.mode,
            "assets": assets,
            "representations": tokens,
            "limitations": self.catalog_limitations(),
        }

    def catalog_limitations(self):
        count = len(getattr(self.rwa, "catalog_rejections", []))
        return (
            {"rwa_catalog": f"PARTIAL: {count} invalid representations excluded"} if count else {}
        )

    def asset(self, query):
        found = self.discovery.resolve(query)
        if found["status"] in {"UNAVAILABLE", "NOT_VERIFIED"}:
            return dict(found, data_mode=self.mode, limitations=self.catalog_limitations())
        asset = found["asset"]
        tokens = []
        observations = []
        states = []
        for token in found["tokens"]:
            detail = self.rwa.profile(token)
            tokens.append(detail)
            observations.append(self.rwa.observation(detail))
            if self.mode == "LIVE":
                states.append(self.rwa.market(detail))
        self.repository.save([asset, *found["issuers"], *tokens, *observations, *states])
        limitations = self.catalog_limitations()
        equities = []
        news = []
        for capability, fetch in [
            ("equity", lambda: [self.equity.get_snapshot(asset.ticker)]),
            ("news", lambda: self.equity.get_news(asset.ticker, max_pages=1)),
        ]:
            try:
                rows = fetch()
                self.repository.save(rows)
                if capability == "equity":
                    equities = rows
                else:
                    news = rows
                    if getattr(self.equity, "last_page_complete", True) is False:
                        limitations["news_history"] = "PAGINATION_BOUND_REACHED"
            except ProviderError as error:
                limitations[capability] = error.kind
        return {
            "status": found["status"],
            "data_mode": self.mode,
            "asset": asset,
            "tokens": tokens,
            "token_observations": observations,
            "market_status": states,
            "equity_observations": equities,
            "news": news,
            "limitations": limitations,
        }
