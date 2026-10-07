"""Supply synthetic inputs to the unchanged TrustService in disposable memory databases."""

import hashlib
from pathlib import Path
from types import SimpleNamespace

from app.config import ROOT_DIR
from app.database import Database
from app.models.demo_sandbox import DemoCatalog, DemoTrustDataset, DemoTrustResult
from app.providers.demo import DemoEquityProvider, DemoRWAProvider
from app.repositories.data import DataRepository
from app.repositories.trust import TrustRepository
from app.services.asset_discovery import AssetDiscoveryService
from app.services.calendar import USEquityCalendar
from app.services.trust import TrustService

MARKER = {"dataset_type": "DEMO_FIXTURE", "synthetic": True, "production_eligible": False}
FIXTURES = ("steady", "thin-move", "supported-move")


class DemoMarketProvider:
    def __init__(self, price):
        self.price = price

    def chains(self):
        return [SimpleNamespace(binanceChainId="DEMO")]

    def prices(self, tokens, *, info=False):
        return [self.price]


class DemoTrustSandbox:
    def __init__(self, fixture_dir: Path = ROOT_DIR / "data/demo/trust-sandbox"):
        self.datasets = {}
        self.hashes = {}
        for identifier in FIXTURES:
            content = (fixture_dir / (identifier + ".json")).read_bytes()
            dataset = DemoTrustDataset.model_validate_json(content)
            if dataset.scenario_id != identifier:
                raise ValueError("Sandbox fixture identity conflict")
            self.datasets[identifier] = dataset
            self.hashes[identifier] = hashlib.sha256(content).hexdigest()

    @staticmethod
    def summary(dataset):
        return {k: getattr(dataset, k) for k in (*MARKER, "scenario_id", "title", "description")}

    def catalog(self):
        return DemoCatalog(
            **MARKER,
            runtime_mode="DEMO",
            scenarios=[self.summary(dataset) for dataset in self.datasets.values()],
        )

    def assess(self, identifier, *, run_id, request_id, correlation_id):
        dataset = self.datasets[identifier]
        # No configured database URL, live client, or production repository is accepted here.
        database = Database("sqlite:///:memory:")
        try:
            database.initialize()
            history = TrustRepository(database)
            for wrapped in [*dataset.baseline_episodes, *dataset.preceding_samples]:
                history.save(wrapped.record)
            records = {
                "assets": [dataset.asset.record],
                "issuers": [dataset.issuer.record],
                "metadata": [dataset.token.record],
                "tokens": [dataset.price.record],
                "equities": [dataset.equity.record],
                "news": [r.record for r in dataset.news],
            }
            rwa = DemoRWAProvider(records)
            market = DemoMarketProvider(dataset.price.record)
            layer = SimpleNamespace(
                mode="DEMO",
                repository=DataRepository(database),
                rwa=rwa,
                equity=DemoEquityProvider(records),
                market=market,
                discovery=AssetDiscoveryService(rwa, market, mode="DEMO", chain="DEMO"),
                calendar=USEquityCalendar(mode="DEMO"),
                catalog_limitations=lambda: {},
            )
            assessment = TrustService(layer, database, clock=lambda: dataset.decision_at).assess(
                dataset.asset.record.ticker,
                run_id=run_id,
                request_id=request_id,
                correlation_id=correlation_id,
            )
            return DemoTrustResult(
                **self.summary(dataset),
                runtime_mode="DEMO",
                fixture_version=dataset.fixture_version,
                fixture_sha256=self.hashes[identifier],
                fixture_episode_count=len(dataset.baseline_episodes),
                fixture_preceding_sample_count=len(dataset.preceding_samples),
                news_inputs=dataset.news,
                assessment=assessment,
            )
        finally:
            database.close()
