import json
from types import SimpleNamespace

from app.config import ROOT_DIR
from app.models.data import (
    EquityObservation,
    Issuer,
    NewsEvent,
    TokenMetadata,
    TokenObservation,
    TrackedAsset,
)

TYPES = {
    "assets": TrackedAsset,
    "issuers": Issuer,
    "metadata": TokenMetadata,
    "tokens": TokenObservation,
    "equities": EquityObservation,
    "news": NewsEvent,
}


def load_data_fixture(path=ROOT_DIR / "data/demo/data-layer.json"):
    raw = json.loads(path.read_text())
    records = {}
    if raw["data_mode"] != "DEMO" or raw["execution_allowed"] is not False:
        raise ValueError("Invalid DEMO boundary")
    for key, model in TYPES.items():
        records[key] = [model.model_validate(row) for row in raw[key]]
        if any(r.data_mode != "DEMO" for r in records[key]):
            raise ValueError("Fixture contaminated by real data")
    return records


class DemoRWAProvider:
    def __init__(self, records):
        self.records = records

    def platforms(self):
        return self.records["issuers"]

    def tokens(self, chain=None):
        return self.records["metadata"]

    def search(self, query):
        found = [
            a
            for a in self.records["assets"]
            if query.casefold() in a.ticker.casefold()
            or query.casefold() in a.company_name.casefold()
        ]
        return [
            SimpleNamespace(
                ticker=a.ticker,
                companyName=a.company_name,
                assets=[
                    SimpleNamespace(
                        platformId=t.platform_id,
                        binanceChainId=t.chain_id,
                        tokenContractAddress=t.contract,
                        assetType=t.asset_type,
                    )
                    for t in self.records["metadata"]
                    if t.ticker == a.ticker
                ],
            )
            for a in found
        ]

    def profile(self, token):
        return token

    def observation(self, token):
        return next(r for r in self.records["tokens"] if r.contract == token.contract)


class DemoEquityProvider:
    def __init__(self, records):
        self.records = records

    def get_snapshot(self, ticker):
        return next(r for r in self.records["equities"] if r.ticker == ticker)

    def get_news(self, ticker, **kwargs):
        return [r for r in self.records["news"] if r.ticker == ticker]
