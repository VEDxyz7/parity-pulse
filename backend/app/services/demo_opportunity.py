"""Bounded in-memory orchestration of exact server-derived Trust → Opportunity → Risk."""

import hashlib
import time
from collections import OrderedDict
from datetime import timedelta
from threading import Lock

from app.config import ROOT_DIR
from app.models.demo_opportunity import (
    DemoOpportunityFixture,
    DemoOpportunityResult,
    DemoRiskResult,
)
from app.services.demo_sandbox import MARKER
from app.services.opportunity import OpportunityEngine
from app.services.risk import RiskEngine


class DemoOpportunityFlow:
    capacity = 64

    def __init__(self, sandbox, *, clock=time.monotonic):
        self.sandbox = sandbox
        self.clock = clock
        content = (ROOT_DIR / "data/demo/opportunity/inputs.json").read_bytes()
        self.fixture = DemoOpportunityFixture.model_validate_json(content)
        self.fixture_hash = hashlib.sha256(content).hexdigest()
        self.opportunity_engine = OpportunityEngine()
        self.risk_engine = RiskEngine()
        self.trust_results = OrderedDict()
        self.opportunities = OrderedDict()
        self.lock = Lock()

    def _save(self, cache, key, value):
        with self.lock:
            cache[key] = (value, self.clock())
            while len(cache) > self.capacity:
                cache.popitem(last=False)

    def _read(self, cache, key):
        with self.lock:
            entry = cache.get(key)
        if entry is None:
            raise LookupError("Unknown or evicted DEMO analysis; run the selected scenario again")
        value, created = entry
        elapsed = self.clock() - created
        if not 0 <= elapsed < 120:
            raise LookupError("Expired DEMO analysis; run the selected scenario again")
        return value, timedelta(seconds=elapsed)

    def remember(self, result):
        self._save(self.trust_results, result.assessment.assessment_id, result)
        return result

    def opportunity(self, assessment_id):
        trust, elapsed = self._read(self.trust_results, assessment_id)
        dataset = self.sandbox.datasets[trust.scenario_id]
        if len(trust.assessment.representations) != 1:
            raise ValueError("This DEMO adapter requires exactly one supplied representation")
        decision = self.opportunity_engine.evaluate(
            trust.assessment,
            trust.assessment.representations[0],
            dataset.token.record,
            self.fixture.economics,
            now=trust.assessment.evaluated_at + elapsed,
        )
        result = DemoOpportunityResult(
            **MARKER,
            scenario_id=trust.scenario_id,
            trust_fixture_sha256=trust.fixture_sha256,
            inputs_fixture_sha256=self.fixture_hash,
            opportunity=decision,
        )
        self._save(self.opportunities, decision.opportunity_id, result)
        return result

    def risk(self, opportunity_id):
        result, elapsed = self._read(self.opportunities, opportunity_id)
        decision = self.risk_engine.evaluate(
            result.opportunity,
            self.fixture.risk_inputs,
            self.fixture.risk_policy,
            now=result.opportunity.evaluated_at + elapsed,
        )
        return DemoRiskResult(
            **MARKER,
            scenario_id=result.scenario_id,
            inputs_fixture_sha256=self.fixture_hash,
            risk=decision,
        )
