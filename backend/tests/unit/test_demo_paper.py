"""Paper accounting and actual server-derived Trust/Risk/simulation proof, never transport."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, localcontext
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.demo_paper import PaperFill, PaperPosition
from app.services.demo_opportunity import DemoOpportunityFlow
from app.services.demo_paper import DemoPaperLedger, pnl
from app.services.demo_preparation import DemoPreparationFlow
from app.services.demo_sandbox import DemoTrustSandbox


def altered(model, **values):
    return type(model).model_validate({**model.model_dump(), **values})


@pytest.fixture
def pipeline():
    elapsed = [0]
    core = DemoOpportunityFlow(DemoTrustSandbox(), clock=lambda: elapsed[0])
    d = DemoPreparationFlow(core)
    t = core.remember(
        core.sandbox.assess(
            "supported-move",
            run_id="paper",
            request_id="paper",
            correlation_id="paper",
        )
    )
    o = core.opportunity(t.assessment.assessment_id)
    r = core.risk(o.opportunity.opportunity_id)
    q = d.quote(r.risk.risk_id)
    p = d.prepare(q.quote.quote_id)
    s = d.simulate(p.transaction.transaction_id)
    ledger = DemoPaperLedger(d)
    return core, d, ledger, elapsed, q, p, s


def filled(pipeline):
    _, _, ledger, _, _, p, s = pipeline
    return ledger.fill(p.transaction.transaction_id, s.simulation.simulation_id)


def test_valid_information_creates_exactly_one_bound_fill_and_open_position(pipeline):
    _, _, ledger, _, q, p, s = pipeline
    row = filled(pipeline)
    assert len(ledger.rows) == len(ledger.transactions) == 1
    assert row.position.state == "OPEN" and row.exit is row.pnl is None
    assert row.fill.quantity == q.quote.output_token_quantity
    assert row.fill.price_usd == q.quote.execution_price_usd
    assert row.fill.notional_usd == q.quote.input_amount_usd
    assert row.position.entry_costs_usd == Decimal(".15")
    assert row.order.transaction_id == p.transaction.transaction_id
    assert row.order.simulation_id == s.simulation.simulation_id
    assert row.order.risk_id == row.risk.risk_id and row.risk.status == "PASS"
    assert row.fill_revalidation.status == "SIMULATION_PASS"
    assert row.events[0].reference_id == row.fill.fill_id
    for record in [row, row.order, row.fill, row.position, *row.events]:
        assert record.source == "DEMO" and record.execution_mode == "PAPER"
        assert not record.production_eligible and not record.funds_moved


def test_concurrent_and_expired_retries_are_idempotent_without_eviction(pipeline):
    _, _, ledger, elapsed, _, p, s = pipeline
    args = (p.transaction.transaction_id, s.simulation.simulation_id)
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(lambda _: ledger.fill(*args), range(16)))
    assert all(r == rows[0] for r in rows) and len(ledger.rows) == 1
    elapsed[0] = 1000
    assert ledger.fill(*args) == rows[0]
    assert len(ledger.get(rows[0].position.position_id).events) == 1
    with pytest.raises(ValueError):
        ledger.fill(args[0], uuid4())


def test_snapshot_mutation_does_not_modify_ledger(pipeline):
    row = filled(pipeline)
    row.events.clear()
    row.risk.reason_codes.clear()
    saved = pipeline[2].get(row.position.position_id)
    assert len(saved.events) == 1 and saved.risk.reason_codes


@pytest.mark.parametrize(
    "change", ["expired", "risk", "simulation", "context", "unknown", "binding"]
)
def test_invalid_or_stale_proof_and_failed_current_risk_create_nothing(pipeline, change):
    core, d, ledger, elapsed, _, p, s = pipeline
    proof = s.simulation.simulation_id
    if change == "expired":
        elapsed[0] = 30
    elif change == "risk":
        core.fixture = altered(
            core.fixture, risk_inputs=altered(core.fixture.risk_inputs, wallet_available_usd="1")
        )
    elif change == "simulation":
        elapsed[0] = 30
        failed = d.simulate(p.transaction.transaction_id)
        proof = failed.simulation.simulation_id
    elif change == "context":
        core.fixture = altered(
            core.fixture, economics=altered(core.fixture.economics, fees_usd=".20")
        )
    elif change == "unknown":
        proof = uuid4()
    elif change == "binding":
        p = altered(p, transaction=altered(p.transaction, transaction_id=uuid4()))
        core._save(d.transactions, p.transaction.transaction_id, p)
    with pytest.raises((LookupError, ValueError)):
        ledger.fill(p.transaction.transaction_id, proof)
    assert not ledger.rows and not ledger.transactions


@pytest.mark.parametrize("scenario", ["steady", "thin-move"])
def test_non_information_never_creates_paper_records(pipeline, scenario):
    core, d, ledger, _, _, _, _ = pipeline
    t = core.remember(
        core.sandbox.assess(scenario, run_id="paper", request_id="paper", correlation_id="paper")
    )
    o = core.opportunity(t.assessment.assessment_id)
    r = core.risk(o.opportunity.opportunity_id)
    assert r.risk.status == "FAIL" and d.quote(r.risk.risk_id).quote is None
    with pytest.raises(LookupError):
        ledger.fill(uuid4(), uuid4())
    assert not ledger.rows


def test_ledger_financial_state_enforces_cooldown_and_no_second_entry(pipeline):
    core, d, ledger, _, _, _, _ = pipeline
    row = filled(pipeline)
    inputs = ledger._mandate(row.fill.filled_at)
    with localcontext() as ctx:
        ctx.prec = 256
        assert inputs.wallet_available_usd == Decimal(100) - row.quote.total_cash_required_usd
    assert inputs.existing_exposure_usd == row.quote.base_notional_usd
    assert inputs.trades_today == 1 and inputs.last_trade_at == row.fill.filled_at
    t = core.remember(
        core.sandbox.assess(
            "supported-move", run_id="again", request_id="again", correlation_id="again"
        )
    )
    o = core.opportunity(t.assessment.assessment_id)
    r = core.risk(o.opportunity.opportunity_id)
    q = d.quote(r.risk.risk_id)
    p = d.prepare(q.quote.quote_id)
    s = d.simulate(p.transaction.transaction_id)
    with pytest.raises(ValueError):
        ledger.fill(p.transaction.transaction_id, s.simulation.simulation_id)
    assert len(ledger.rows) == 1


def test_monitor_exit_calculated_pnl_scorecard_and_invalid_transitions(pipeline):
    row = filled(pipeline)
    ledger = pipeline[2]
    key = row.position.position_id
    with pytest.raises(ValueError):
        ledger.scorecard(key)
    with pytest.raises(ValueError):
        ledger.exit(key, uuid4())
    marked = ledger.monitor(key)
    assert ledger.monitor(key) == marked and len(marked.events) == 2
    assert marked.observation.token_mark_price_usd == Decimal(53)
    assert marked.observation.sell_price_usd == Decimal("52.894")
    exited = ledger.exit(key, marked.observation.observation_id)
    assert exited.position.state == "EXITED" and len(exited.events) == 3
    assert exited.pnl.gross_pnl_usd == Decimal("1.75335603303197526425600")
    assert exited.pnl.costs_usd == Decimal(".30")
    assert exited.pnl.net_pnl_usd == Decimal("1.45335603303197526425600")
    assert exited.pnl.return_pct == Decimal("2.898018012027866929")
    score = ledger.scorecard(key)
    assert score.entry == exited.fill and score.exit == exited.exit and score.pnl == exited.pnl
    assert score.event_ids == [e.event_id for e in exited.events]
    assert score.trust_classification == "LIKELY_INFORMATION"
    assert score.quote_id == exited.quote.quote_id and score.risk_id == exited.risk.risk_id
    assert score.reason_codes[: len(exited.trust_reason_codes)] == exited.trust_reason_codes
    for method, args in [
        (ledger.monitor, (key,)),
        (ledger.exit, (key, marked.observation.observation_id)),
    ]:
        with pytest.raises(ValueError):
            method(*args)
    assert len(ledger.get(key).events) == 3
    assert ledger.fill(row.order.transaction_id, row.order.simulation_id) == exited
    with localcontext() as ctx:
        ctx.prec = 256
        assert (
            ledger._mandate(exited.exit.exited_at).wallet_available_usd
            == Decimal(100) + exited.pnl.net_pnl_usd
        )


@pytest.mark.parametrize(
    "entry,exit_price,quantity",
    [("50", "55", "2"), ("50", "45", "2"), ("51", "55", "2"), ("50", "55", "3"), ("50", "50", "2")],
)
def test_pnl_is_derived_from_variable_prices_quantity_and_costs(
    pipeline, entry, exit_price, quantity
):
    row = filled(pipeline)
    ledger = pipeline[2]
    marked = ledger.monitor(row.position.position_id)
    exited = ledger.exit(row.position.position_id, marked.observation.observation_id)
    e, x, q = map(Decimal, (entry, exit_price, quantity))
    position = altered(
        row.position, quantity=q, entry_price_usd=e, entry_notional_usd=e * q, entry_costs_usd=".20"
    )
    exit = altered(
        exited.exit, quantity=q, price_usd=x, notional_usd=x * q, fees_usd=".10", gas_usd=".05"
    )
    result = pnl(position, exit)
    assert result.gross_pnl_usd == (x - e) * q
    assert result.net_pnl_usd == (x - e) * q - Decimal(".35")


def test_losing_exit_updates_stateful_daily_loss_and_releases_reserve(pipeline):
    ledger = pipeline[2]
    ledger.exit_fixture = altered(ledger.exit_fixture, token_mark_price_usd="40")
    row = filled(pipeline)
    m = ledger.monitor(row.position.position_id)
    e = ledger.exit(row.position.position_id, m.observation.observation_id)
    assert e.pnl.net_pnl_usd < 0 and e.exit.released_reserve_usd == Decimal(".10")
    state = ledger._mandate(e.exit.exited_at)
    assert state.daily_loss_usd == -e.pnl.net_pnl_usd
    assert state.existing_exposure_usd == 0


def test_capacity_refuses_new_fills_and_records_reject_live_flags(pipeline):
    ledger = pipeline[2]
    ledger.capacity = 0
    with pytest.raises(ValueError):
        filled(pipeline)
    ledger.capacity = 64
    row = filled(pipeline)
    for field, value in [
        ("execution_mode", "LIVE"),
        ("source", "LIVE"),
        ("signed", True),
        ("funds_moved", True),
        ("quantity", 1.0),
    ]:
        with pytest.raises(ValidationError):
            PaperFill.model_validate({**row.fill.model_dump(), field: value})
    with pytest.raises(ValidationError):
        PaperPosition.model_validate({**row.position.model_dump(), "token": "0x123"})
