"""Memory-only DEMO downstream adapter. All services are deterministic and have no transport."""

from collections import OrderedDict

from app.models.demo_execution import (
    DemoPreparationResult,
    DemoQuoteResult,
    DemoSimulationResult,
    artifact_digest,
    digest,
)
from app.models.opportunity import OpportunityDecision
from app.services.demo_sandbox import MARKER
from app.services.quote import QuoteService
from app.services.simulation import SimulationService
from app.services.transaction import TransactionBuilder


class DemoPreparationFlow:
    def __init__(self, flow):
        self.flow = flow
        self.quote_service = QuoteService()
        self.transaction_builder = TransactionBuilder()
        self.simulation_service = SimulationService()
        self.quotes = OrderedDict()
        self.transactions = OrderedDict()
        self.simulations = OrderedDict()
        self.market_snapshots = {k: digest(v) for k, v in flow.sandbox.datasets.items()}

    def context(self, scenario):
        return digest(
            {
                "market_dataset": self.flow.sandbox.datasets[scenario].model_dump(mode="json"),
                "economic_and_risk_fixture": self.flow.fixture.model_dump(mode="json"),
            }
        )

    def _risk(self, opportunity, now):
        return self.flow.risk_engine.evaluate(
            opportunity, self.flow.fixture.risk_inputs, self.flow.fixture.risk_policy, now=now
        )

    def _quoted_risk(self, result, now):
        current = self.quote_service.quoted_opportunity(
            result.opportunity,
            result.quote,
            current_inputs=self.flow.fixture.economics,
        )
        return self._risk(current, now)

    def quote(self, risk_id):
        previous, _ = self.flow._read(self.flow.risks, risk_id)
        source, elapsed = self.flow._read(self.flow.opportunities, previous.risk.opportunity_id)
        trust, _ = self.flow._read(self.flow.trust_results, source.opportunity.trust_assessment_id)
        scenario = source.scenario_id
        dataset = self.flow.sandbox.datasets[scenario]
        now = source.opportunity.evaluated_at + elapsed
        refreshed = self.flow.opportunity_engine.evaluate(
            trust.assessment,
            trust.assessment.representations[0],
            dataset.token.record,
            self.flow.fixture.economics,
            now=now,
        )
        refreshed = OpportunityDecision.model_validate(
            {
                **refreshed.model_dump(),
                "opportunity_id": source.opportunity.opportunity_id,
                "valid_until": min(refreshed.valid_until, source.opportunity.valid_until),
            }
        )
        before = self._risk(refreshed, now)
        reasons = []
        if previous.risk.status != "PASS":
            reasons.append("SOURCE_RISK_NOT_APPROVED")
        if digest(dataset) != self.market_snapshots[scenario]:
            reasons.append("DEMO_MARKET_INPUTS_CHANGED_REASSESS_REQUIRED")
        if before.status != "PASS":
            reasons.extend(before.reason_codes)
        quote = quoted = revalidated = None
        if not reasons:
            quote = self.quote_service.create(
                refreshed,
                before,
                source_risk_id=risk_id,
                context_sha256=self.context(scenario),
                market_observation_kind=dataset.price.record.kind,
                now=now,
            )
            quoted = self.quote_service.quoted_opportunity(refreshed, quote)
            revalidated = self._risk(quoted, now)
            if revalidated.status != "PASS":
                reasons.extend(revalidated.reason_codes)
        result = DemoQuoteResult(
            **MARKER,
            inputs_fixture_sha256=self.flow.fixture_hash,
            scenario_id=scenario,
            status="BLOCKED" if reasons else "QUOTED",
            quote=quote,
            opportunity=refreshed,
            risk_before_quote=before,
            quoted_opportunity=quoted,
            risk_revalidation=revalidated,
            reason_codes=reasons or ["DEMO_QUOTE_AND_REVALIDATED_RISK_PASS"],
        )
        if result.status == "QUOTED":
            self.flow._save(self.quotes, quote.quote_id, result)
        return result

    def prepare(self, quote_id):
        result, elapsed = self.flow._read(self.quotes, quote_id)
        quote = result.quote
        now = quote.quoted_at + elapsed
        risk = self._quoted_risk(result, now)
        reasons = []
        if not quote.quoted_at <= now < quote.valid_until:
            reasons.append("QUOTE_EXPIRED_OR_FUTURE")
        if self.context(result.scenario_id) != quote.context_sha256:
            reasons.append("CURRENT_INPUTS_CHANGED_REQUOTE_REQUIRED")
        if artifact_digest(quote, "quote_id") != quote.fingerprint:
            reasons.append("QUOTE_FINGERPRINT_MISMATCH")
        if risk.status != "PASS":
            reasons.extend(risk.reason_codes)
        transaction = None
        if not reasons:
            transaction = self.transaction_builder.prepare(quote, risk, now=now)
        prepared = DemoPreparationResult(
            **MARKER,
            inputs_fixture_sha256=self.flow.fixture_hash,
            scenario_id=result.scenario_id,
            status="BLOCKED" if reasons else "PREPARED",
            transaction=transaction,
            risk_revalidation=risk,
            reason_codes=reasons or ["UNSIGNED_DEMO_REQUEST_PREPARED"],
        )
        if transaction is not None:
            self.flow._save(self.transactions, transaction.transaction_id, prepared)
        return prepared

    def simulate(self, transaction_id):
        prepared, elapsed = self.flow._read(self.transactions, transaction_id)
        transaction = prepared.transaction
        result, _ = self.flow._read(self.quotes, transaction.quote_id)
        now = transaction.prepared_at + elapsed
        risk = self._quoted_risk(result, now)
        simulation = self.simulation_service.simulate(
            transaction,
            result.quote,
            risk,
            self.flow.sandbox.datasets[result.scenario_id].token.record,
            context_sha256=self.context(result.scenario_id),
            now=now,
        )
        result = DemoSimulationResult(
            **MARKER,
            inputs_fixture_sha256=self.flow.fixture_hash,
            scenario_id=result.scenario_id,
            simulation=simulation,
            reason_codes=simulation.reason_codes,
        )

        self.flow._save(self.simulations, simulation.simulation_id, result)
        return result
