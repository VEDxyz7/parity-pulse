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
from app.models.opportunity import OpportunityDecision
from app.services.demo_sandbox import MARKER
from app.services.opportunity import OpportunityEngine
from app.services.risk import RiskEngine
from app.services.route_inputs import opportunity_input, opportunity_policy
from app.services.routing import RoutingService


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
        self.router = RoutingService()
        self.trust_results = OrderedDict()
        self.opportunities = OrderedDict()
        self.risks = OrderedDict()
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

    def snapshots(self):
        """Read bounded historical analyses without treating expired proposals as live."""
        with self.lock:
            return tuple(value for value, _ in self.opportunities.values())

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
        route = self.route(trust, decision, dataset, now=decision.evaluated_at)
        if route.status != "ROUTE_SELECTED" and decision.status == "ACTIONABLE":
            decision = OpportunityDecision.model_validate(
                {
                    **decision.model_dump(),
                    "status": "REJECTED",
                    "action": "NONE",
                    "reason_codes": [*decision.reason_codes, "NO_ELIGIBLE_ROUTE"],
                }
            )
        result = DemoOpportunityResult(
            route_decision=route,
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
        result = DemoRiskResult(
            **MARKER,
            scenario_id=result.scenario_id,
            inputs_fixture_sha256=self.fixture_hash,
            risk=decision,
        )
        self._save(self.risks, decision.risk_id, result)
        return result

    def route(self, trust, decision, dataset, *, now):
        risk = self.risk_engine.evaluate(
            decision, self.fixture.risk_inputs, self.fixture.risk_policy, now=now
        )
        candidate = opportunity_input(
            dataset.token.record,
            dataset.price.record,
            trust.assessment,
            decision,
            risk,
            self.fixture.economics,
        )
        return self.router.decide(
            decision.ticker,
            self.fixture.economics.requested_notional_usd,
            [candidate],
            mode="DEMO",
            now=now,
            policy=opportunity_policy(self.fixture.risk_policy),
        )
