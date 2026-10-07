"""Actual deterministic DEMO service composition and adversarial economic/parameter checks."""

from datetime import timedelta
from decimal import Decimal, localcontext
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.demo_execution import DemoQuote, artifact_digest, artifact_id
from app.services.demo_opportunity import DemoOpportunityFlow
from app.services.demo_preparation import DemoPreparationFlow
from app.services.demo_sandbox import DemoTrustSandbox


def altered(model, **values):
    return type(model).model_validate({**model.model_dump(), **values})


@pytest.fixture
def pipeline():
    elapsed = [0]
    core = DemoOpportunityFlow(DemoTrustSandbox(), clock=lambda: elapsed[0])
    downstream = DemoPreparationFlow(core)
    trust = core.remember(
        core.sandbox.assess(
            "supported-move",
            run_id="stage3b",
            request_id="stage3b",
            correlation_id="stage3b",
        )
    )
    o = core.opportunity(trust.assessment.assessment_id)
    risk = core.risk(o.opportunity.opportunity_id)
    q = downstream.quote(risk.risk.risk_id)
    p = downstream.prepare(q.quote.quote_id)
    return core, downstream, elapsed, risk, q, p


def test_quote_determinism_arithmetic_expiry_and_exact_revalidation(pipeline):
    core, d, _, risk, q, _ = pipeline
    first = d.quote_service.create(
        q.opportunity,
        q.risk_before_quote,
        source_risk_id=risk.risk.risk_id,
        context_sha256=d.context("supported-move"),
        market_observation_kind="PRICE_INFO",
        now=q.quote.quoted_at,
    )
    second = d.quote_service.create(
        q.opportunity,
        q.risk_before_quote,
        source_risk_id=risk.risk.risk_id,
        context_sha256=d.context("supported-move"),
        market_observation_kind="PRICE_INFO",
        now=q.quote.quoted_at,
    )
    assert first == second == q.quote
    assert q.quote.execution_price_usd == Decimal("51.102")
    assert q.quote.output_token_quantity == Decimal("0.978435286290164768")
    with localcontext() as context:
        context.prec = 256
        assert (
            q.quote.input_amount_usd == q.quote.output_token_quantity * q.quote.execution_price_usd
        )
        assert q.quote.input_amount_usd <= 50
        assert q.quote.total_cash_required_usd == q.quote.input_amount_usd + Decimal("0.25")
        assert q.quote.estimated_slippage_usd == q.quote.base_notional_usd * Decimal("0.002")
    assert q.quote.net_hypothetical_edge_usd == Decimal("1.607070173378732729")
    assert q.quote.valid_until - q.quote.quoted_at == timedelta(seconds=30)
    assert q.risk_before_quote.status == q.risk_revalidation.status == "PASS"
    assert q.quoted_opportunity.inputs.requested_notional_usd == q.quote.base_notional_usd
    assert q.risk_revalidation.proposed_token_quantity == q.quote.output_token_quantity
    assert q.quote.fingerprint == artifact_digest(q.quote, "quote_id")
    assert q.quote.quote_id == artifact_id("quote", q.quote.fingerprint)
    assert core.fixture.economics.requested_notional_usd == 50  # No fixture mutation.


def test_transaction_parameters_smallest_units_and_fingerprint(pipeline):
    _, d, _, _, q, prepared = pipeline
    t = prepared.transaction
    assert t == d.transaction_builder.prepare(
        q.quote, prepared.risk_revalidation, now=t.prepared_at
    )
    assert t.parameters.quantity == q.quote.output_token_quantity
    assert t.parameters.token_base_units == "978435286290164768"
    assert t.parameters.maximum_input_usd == q.quote.input_amount_usd
    assert t.parameters.target_token == "demo:NVDA" and t.parameters.chain_id == "DEMO"
    assert t.quote_id == t.parameters.quote_id == q.quote.quote_id
    assert t.quote_fingerprint == q.quote.fingerprint and t.fingerprint == artifact_digest(
        t, "transaction_id"
    )
    assert t.calldata is t.signature is None and t.broadcastable is t.signed is False


def test_valid_simulation_is_deterministic_and_passes_every_constraint(pipeline):
    core, d, _, _, q, prepared = pipeline
    first = d.simulate(prepared.transaction.transaction_id).simulation
    second = d.simulate(prepared.transaction.transaction_id).simulation
    assert first.model_dump(exclude={"risk_revalidation"}) == second.model_dump(
        exclude={"risk_revalidation"}
    )
    assert first.status == "SIMULATION_PASS" and len(first.checks) == 18
    assert all(c.passed for c in first.checks)
    assert first.method == "LOCAL_DEMO_CONSTRAINT_EVALUATION" and first.chain_simulation is False
    assert first.execution_ready is first.funds_moved is first.transaction_broadcast is False
    assert first.transaction_fingerprint == prepared.transaction.fingerprint
    assert first.quote_fingerprint == q.quote.fingerprint
    assert core.fixture.risk_policy.max_timestamp_skew_seconds == 30


@pytest.mark.parametrize("scenario", ["steady", "thin-move"])
def test_non_information_scenarios_stop_before_quote_or_other_services(monkeypatch, scenario):
    core = DemoOpportunityFlow(DemoTrustSandbox(), clock=lambda: 0)
    d = DemoPreparationFlow(core)

    def forbidden(*args, **kwargs):
        raise AssertionError("Ineligible scenario cannot reach quote/build/simulate")

    monkeypatch.setattr(d.quote_service, "create", forbidden)
    monkeypatch.setattr(d.transaction_builder, "prepare", forbidden)
    monkeypatch.setattr(d.simulation_service, "simulate", forbidden)
    trust = core.remember(
        core.sandbox.assess(scenario, run_id="test", request_id="test", correlation_id="test")
    )
    o = core.opportunity(trust.assessment.assessment_id)
    r = core.risk(o.opportunity.opportunity_id)
    result = d.quote(r.risk.risk_id)
    assert result.status == "BLOCKED" and result.quote is result.quoted_opportunity is None
    assert not d.quotes and not d.transactions


@pytest.mark.parametrize("offset", [30, 31, 60])
def test_expiry_blocks_preparation_and_actual_simulation_fails(pipeline, offset):
    _, d, elapsed, _, q, prepared = pipeline
    elapsed[0] = offset
    failed = d.prepare(q.quote.quote_id)
    assert failed.status == "BLOCKED" and failed.transaction is None
    assert "QUOTE_EXPIRED_OR_FUTURE" in failed.reason_codes
    simulation = d.simulate(prepared.transaction.transaction_id).simulation
    assert simulation.status == "SIMULATION_FAIL" and "QUOTE_VALID" in simulation.reason_codes
    assert "REQUEST_VALID" in simulation.reason_codes


@pytest.mark.parametrize(
    "kind,values,risk_reason",
    [
        ("risk_inputs", {"wallet_available_usd": "40"}, "WALLET_LIMIT"),
        ("risk_inputs", {"risk_budget_usd": "0.5"}, "STRESS_RISK_BUDGET"),
        ("risk_policy", {"max_position_usd": "40"}, "POSITION_CAP"),
        ("risk_policy", {"max_slippage_bps": "19"}, "SLIPPAGE_LIMIT"),
        ("risk_policy", {"min_liquidity_usd": "6000"}, "LIQUIDITY_MINIMUM"),
        ("economics", {"fees_usd": "2"}, "NET_EDGE_MINIMUM"),
        ("economics", {"gas_usd": "2"}, "NET_EDGE_MINIMUM"),
        ("economics", {"slippage_bps": "500"}, "NET_EDGE_MINIMUM"),
        ("economics", {"target_share_price_usd": "100"}, "OPPORTUNITY_ACTIONABLE"),
    ],
)
def test_changed_economics_or_risk_inputs_revalidated_and_fail_closed(
    pipeline, kind, values, risk_reason
):
    core, d, _, risk, q, prepared = pipeline
    updated = altered(getattr(core.fixture, kind), **values)
    core.fixture = altered(core.fixture, **{kind: updated})
    before = d.quote(risk.risk.risk_id)
    assert before.status == "BLOCKED" and before.quote is None
    p = d.prepare(q.quote.quote_id)
    assert p.status == "BLOCKED" and p.transaction is None
    assert "CURRENT_INPUTS_CHANGED_REQUOTE_REQUIRED" in p.reason_codes
    assert p.risk_revalidation.status == "FAIL" and risk_reason in p.risk_revalidation.reason_codes
    simulation = d.simulate(prepared.transaction.transaction_id).simulation
    assert simulation.status == "SIMULATION_FAIL"
    assert (
        "CURRENT_INPUTS_UNCHANGED" in simulation.reason_codes
        and "RISK_REVALIDATION" in simulation.reason_codes
    )


def test_fresh_quote_uses_changed_still_eligible_costs_but_old_quote_is_invalid(pipeline):
    core, d, _, risk, old, _ = pipeline
    core.fixture = altered(core.fixture, economics=altered(core.fixture.economics, fees_usd="0.20"))
    new = d.quote(risk.risk.risk_id)
    assert new.status == "QUOTED" and new.quote.fees_usd == Decimal("0.20")
    assert new.quote.context_sha256 != old.quote.context_sha256
    assert new.quote.net_hypothetical_edge_usd == old.quote.net_hypothetical_edge_usd - Decimal(
        "0.10"
    )
    assert d.prepare(old.quote.quote_id).status == "BLOCKED"
    p = d.prepare(new.quote.quote_id)
    assert d.simulate(p.transaction.transaction_id).simulation.status == "SIMULATION_PASS"


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("quantity", "2", "ALLOWED_SIZE"),
        ("maximum_input_usd", "60", "AMOUNT_EQUIVALENCE"),
        ("minimum_output_tokens", "0.9", "AMOUNT_EQUIVALENCE"),
        ("maximum_slippage_bps", "51", "SLIPPAGE_LIMIT"),
        ("token_base_units", "1", "BASE_UNITS"),
        ("target_token", "demo:OTHER", "REPRESENTATION_VALID"),
        ("fees_usd", "1", "EXPECTED_COSTS"),
        ("quote_id", uuid4(), "QUOTE_BINDING"),
    ],
)
def test_simulation_rejects_tampered_parameters_even_if_request_fingerprint_recomputed(
    pipeline, field, value, reason
):
    core, d, _, _, q, prepared = pipeline
    t = altered(
        prepared.transaction, parameters=altered(prepared.transaction.parameters, **{field: value})
    )
    fingerprint = artifact_digest(t, "transaction_id")
    t = altered(t, fingerprint=fingerprint, transaction_id=artifact_id("request", fingerprint))
    result = d.simulation_service.simulate(
        t,
        q.quote,
        prepared.risk_revalidation,
        core.sandbox.datasets["supported-move"].token.record,
        context_sha256=d.context("supported-move"),
        now=t.prepared_at,
    )
    assert result.status == "SIMULATION_FAIL" and reason in result.reason_codes
    assert next(c for c in result.checks if c.code == "TRANSACTION_FINGERPRINT").passed


def test_quote_fingerprint_tampering_and_fabricated_edge_are_rejected(pipeline):
    core, d, _, _, q, prepared = pipeline
    bad = altered(q.quote, net_hypothetical_edge_usd="100")
    s = d.simulation_service.simulate(
        prepared.transaction,
        bad,
        prepared.risk_revalidation,
        core.sandbox.datasets["supported-move"].token.record,
        context_sha256=d.context("supported-move"),
        now=bad.quoted_at,
    )
    assert s.status == "SIMULATION_FAIL"
    assert "QUOTE_FINGERPRINT" in s.reason_codes and "QUOTED_NET_EDGE" in s.reason_codes
    with pytest.raises(ValueError):
        d.transaction_builder.prepare(bad, prepared.risk_revalidation, now=bad.quoted_at)


def test_market_metadata_changes_do_not_reuse_old_trust_or_quote(pipeline):
    core, d, _, risk, q, prepared = pipeline
    original = core.sandbox.datasets["supported-move"]
    token = altered(original.token.record, open_state=False, market_state="pause")
    core.sandbox.datasets["supported-move"] = altered(
        original, token=altered(original.token, record=token)
    )
    assert d.quote(risk.risk.risk_id).status == "BLOCKED"
    assert d.prepare(q.quote.quote_id).transaction is None
    s = d.simulate(prepared.transaction.transaction_id).simulation
    assert s.status == "SIMULATION_FAIL" and "REPRESENTATION_VALID" in s.reason_codes


def test_contracts_reject_real_chain_broadcast_signature_and_float_inputs(pipeline):
    quote = pipeline[4].quote
    for field, value in (
        ("chain_id", "56"),
        ("source", "LIVE"),
        ("signed", True),
        ("transaction_broadcast", True),
        ("execution_price_usd", 51.102),
        ("mark_price_usd", "NaN"),
        ("market_observation_kind", "CANDLE"),
    ):
        with pytest.raises(ValidationError):
            DemoQuote.model_validate({**quote.model_dump(), field: value})
