from app.clients.alpaca import AlpacaClient
from app.clients.binance_web3 import BinanceWeb3Client
from app.clients.common import ProviderError
from app.clients.finnhub import FinnhubClient
from app.clients.massive import MassiveClient
from app.providers.alpaca import AlpacaProvider
from app.providers.binance import BinanceMarketProvider, BinanceRWAProvider
from app.providers.demo import DemoEquityProvider, DemoRWAProvider, load_data_fixture
from app.providers.finnhub import FinnhubEventProvider
from app.providers.massive import MassiveProvider
from app.repositories.data import DataRepository
from app.services.asset_discovery import AssetDiscoveryService
from app.services.calendar import USEquityCalendar


class DataLayer:
    def __init__(self, settings, database):
        self.repository = DataRepository(database)
        self.clients = []
        self.events = None  # Explicit research reads only; never replaces self.news/calendar.
        self.mode = "DEMO" if settings.data_mode == "DEMO" else "LIVE"
        if self.mode == "DEMO":
            records = load_data_fixture()
            self.repository.save([r for rows in records.values() for r in rows])
            self.rwa, self.equity = DemoRWAProvider(records), DemoEquityProvider(records)
            self.market = None
            self.news = self.equity
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
            self.news = self.equity
            if settings.equity_provider == "ALPACA":
                alpaca = AlpacaClient(settings.alpaca_api_key, settings.alpaca_secret_key)
                self.clients.append(alpaca)
                self.equity = AlpacaProvider(
                    alpaca, feed=settings.alpaca_feed, freshness=settings.alpaca_data_quality
                )
            if settings.finnhub_api_key:
                events = FinnhubClient(settings.finnhub_api_key)
                self.clients.append(events)
                self.events = FinnhubEventProvider(events)
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
            ("news", lambda: self.news.get_news(asset.ticker, max_pages=1)),
        ]:
            try:
                rows = fetch()
                self.repository.save(rows)
                if capability == "equity":
                    equities = rows
                else:
                    news = rows
                    if getattr(self.news, "last_page_complete", True) is False:
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
