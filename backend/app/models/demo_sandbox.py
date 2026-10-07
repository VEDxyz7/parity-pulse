"""Synthetic fixture envelopes; production data and Trust contracts remain unchanged."""

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.models.data import (
    DataModel,
    EquityObservation,
    Issuer,
    NewsEvent,
    TokenMetadata,
    TokenObservation,
    TrackedAsset,
    utc,
)
from app.models.trust import TrustAssessment, TrustEpisode, TrustSample

ScenarioId = Literal["steady", "thin-move", "supported-move"]


class DemoMarker(DataModel):
    dataset_type: Literal["DEMO_FIXTURE"]
    synthetic: Literal[True]
    production_eligible: Literal[False]


class FixtureRecord[T](DemoMarker):
    record: T


class DemoScenarioSummary(DemoMarker):
    scenario_id: ScenarioId
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=300)


class DemoTrustDataset(DemoScenarioSummary):
    fixture_version: Literal["demo-trust-1"]
    decision_at: datetime
    asset: FixtureRecord[TrackedAsset]
    issuer: FixtureRecord[Issuer]
    token: FixtureRecord[TokenMetadata]
    price: FixtureRecord[TokenObservation]
    equity: FixtureRecord[EquityObservation]
    news: list[FixtureRecord[NewsEvent]] = Field(max_length=10)
    baseline_episodes: list[FixtureRecord[TrustEpisode]] = Field(max_length=60)
    preceding_samples: list[FixtureRecord[TrustSample]] = Field(max_length=32)

    @field_validator("decision_at")
    @classmethod
    def aware(cls, value):
        return utc(value)

    @model_validator(mode="after")
    def isolated(self):
        records = [
            self.asset.record,
            self.issuer.record,
            self.token.record,
            self.price.record,
            self.equity.record,
            *(r.record for r in self.news),
        ]
        if any(r.data_mode != "DEMO" or r.data_quality != "DEMO" for r in records):
            raise ValueError("Sandbox fixtures must be synthetic DEMO records")
        if self.token.record.chain_id != "DEMO" or not self.token.record.contract.startswith(
            "demo:"
        ):
            raise ValueError("Sandbox requires a synthetic token identity")
        for wrapped in self.baseline_episodes:
            if wrapped.record.evidence_kind != "SYNTHETIC_TEST":
                raise ValueError("Sandbox episode must explicitly be synthetic")
        points = [r.record for r in self.preceding_samples] + [
            r.record.sample for r in self.baseline_episodes
        ]
        token = self.token.record
        expected = ("DEMO", token.ticker, token.platform_id, token.chain_id, token.contract)
        if any(s.scope[:5] != expected or s.ratio != token.token_to_share_ratio for s in points):
            raise ValueError("Sandbox history identity/ratio must match its synthetic token")
        return self


class DemoCatalog(DemoMarker):
    runtime_mode: Literal["DEMO"]
    scenarios: list[DemoScenarioSummary]


class DemoProductionGates(DataModel):
    DATA_GATE: Literal["PASS"] = "PASS"
    DRY_RUN_GATE: Literal["PASS"] = "PASS"
    TRUST_GATE: Literal["BLOCKED"] = "BLOCKED"
    OPPORTUNITY_GATE: Literal["BLOCKED_BY_TRUST"] = "BLOCKED_BY_TRUST"
    SWAP_LIVE_GATE: Literal["BLOCKED"] = "BLOCKED"
    RFQ_LIVE_GATE: Literal["BLOCKED"] = "BLOCKED"
    AGENTIC_WALLET_LIVE_GATE: Literal["BLOCKED"] = "BLOCKED"


class DemoTrustResult(DemoScenarioSummary):
    runtime_mode: Literal["DEMO"]
    fixture_version: Literal["demo-trust-1"]
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fixture_episode_count: int
    fixture_preceding_sample_count: int
    news_inputs: list[FixtureRecord[NewsEvent]]
    assessment: TrustAssessment
    production_gates: DemoProductionGates = DemoProductionGates()

    @model_validator(mode="after")
    def demo_assessment(self):
        if self.assessment.data_mode != "DEMO":
            raise ValueError("Sandbox cannot return a production assessment")
        return self
