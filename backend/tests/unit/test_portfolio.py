"""Synthetic portfolio acceptance evidence; never production coverage or live gate evidence."""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.execution import ExecutionControls
from app.models.portfolio import Allocation, AssetRisk, PortfolioInputs, PortfolioRules
from app.models.routing import RouteIdentity, RouteInput
from app.repositories.portfolio import PortfolioStore
from app.repositories.position import PositionStore
from app.services.execution import SafetyExecutionService
from app.services.portfolio import PortfolioService
from app.services.position import change
from backend.tests.fixtures.execution_fixtures import (
    BUY,
    NOW,
    FixtureProvider,
    allowance,
    evidence,
    funding,
)
from backend.tests.unit.test_position import ReverseProvider, instrument, runtime

D = Decimal


def rules(weight="0.5", band="0.05", **updates):
    return change(
        PortfolioRules(
            targets=(
                Allocation(asset="NVDA", kind="TOKENIZED_STOCK", weight=weight, drift_band=band),
                Allocation(asset="CASH", kind="CASH", weight=1 - D(weight), drift_band=band),
            ),
            max_rebalance_notional_usd="50",
            risk_budget_usd="2",
            max_stock_exposure_usd="100",
        ),
        **updates,
    )


def route(**updates):
    return change(
        RouteInput(
            identity=RouteIdentity(
                underlying="NVDA", issuer="FIXTURE", chain_id="56", contract=BUY, token="NVDA"
            ),
            data_mode="DEMO",
            token_price_usd="100",
            token_to_share_ratio="0.01",
            price_source="TEST_FIXTURE",
            price_timestamp=NOW,
            price_quality="DEMO",
            ratio_source="TEST_FIXTURE",
            ratio_observed_at=NOW,
            market_state="regular",
            tradable=True,
            liquidity_usd="100000",
            liquidity_status="AVAILABLE",
            liquidity_source="TEST_FIXTURE",
            liquidity_timestamp=NOW,
            fees_usd="0.12",
            gas_usd="0.1",
            slippage_bps="50",
            cost_status="AVAILABLE",
            cost_source="TEST_FIXTURE",
            cost_timestamp=NOW,
            trust_state="NORMAL",
            trust_source="TEST_FIXTURE",
            trust_timestamp=NOW,
            trust_assessment_id=uuid4(),
            route_available=True,
            route_support="SYNTHETIC_DEMO_PREPARATION",
        ),
        **updates,
    )


class Source:
    def __init__(self):
        f = funding()
        token = change(
            f,
            asset=change(f.asset, contract=BUY, symbol="NVDA"),
            balance_base_units="400000",
            unit_price_usd="100",
        )
        self.inputs = PortfolioInputs(
            data_mode="DEMO",
            captured_at=NOW,
            position_verified_at=NOW,
            inventory_complete=True,
            funding=f,
            token_funding=(token,),
            routes=(route(),),
            risks=(AssetRisk(asset="NVDA", evidence=evidence()),),
            source="TEST_FIXTURE",
        )

    def capture(self, config):
        return self.inputs

    def decimals(self, contract):
        return 6


def setup(tmp_path=None, *, weight="0.5", policy="PORTFOLIO_DRIFT", confirmed=True):
    manager, previous, time = runtime(tmp_path, confirmed=confirmed)
    # Use a separate Phase 10 store to create the immutable holding policy at entry.
    manager.store.close()
    manager.store = PositionStore(
        manager.execution.store, tmp_path / "portfolio_positions" if tmp_path else None
    )
    manager.recover()
    p = manager.create(previous.entry_execution.execution_id, instrument(), exit_rule=policy)
    manager.execution = SafetyExecutionService(
        FixtureProvider(clock=lambda: time[0]),
        manager.execution.store,
        ExecutionControls(data_mode="DEMO"),
        clock=lambda: time[0],
    )
    manager.execution.position_guard = manager.has_unresolved
    source = Source()
    store = PortfolioStore(tmp_path / "portfolio" if tmp_path else None)
    service = PortfolioService(store, manager, source, clock=lambda: time[0])
    service.recover()
    manager.portfolio_exit_guard = service.can_reduce
    service.configure(rules(weight), expected_version=0, request_id=uuid4(), correlation_id=uuid4())
    return service, p, time


def evaluate(service, key=None, **kw):
    return service.evaluate(
        idempotency_key=key or uuid4(), request_id=uuid4(), correlation_id=uuid4(), **kw
    )


def test_exact_stock_cash_drift_and_conservative_units():
    s, p, _ = setup()
    plan = evaluate(s)
    assert plan.status == "REBALANCE_REQUIRED"
    assert plan.total_value_usd == D("140.0200")
    nvda = next(r for r in plan.rows if r.asset == "NVDA")
    assert nvda.current_value_usd == D("40")
    assert nvda.target_value_usd == D("70.01")
    assert nvda.required_delta_usd == D("30.01")
    assert nvda.current_share_exposure == D("0.004")
    a = plan.actions[0]
    assert a.quantity_base_units == "300100"
    assert a.estimated_share_delta == D("0.003001")
    assert a.risk.status == "PASS" and not a.execution_ready
    assert a.route.selected_representation.contract == BUY
    assert p.remaining_quantity_base_units == "400000"
    assert not s.positions.execution.provider.calls


def test_band_boundary_is_inclusive():
    s, _, _ = setup(weight="0.3")
    s.configure(
        rules("0.3", "0.02"), expected_version=1, request_id=uuid4(), correlation_id=uuid4()
    )
    assert evaluate(s).status == "NO_ACTION"


@pytest.mark.parametrize("weights", [("0.4", "0.5"), ("0.9", "0.2"), ("-0.1", "1.1")])
def test_invalid_allocation_sum_or_negative_rejected(weights):
    with pytest.raises(ValueError):
        change(
            rules(),
            targets=(
                Allocation(asset="NVDA", kind="TOKENIZED_STOCK", weight=weights[0]),
                Allocation(asset="CASH", kind="CASH", weight=weights[1]),
            ),
        )


def test_float_financial_input_rejected():
    with pytest.raises(ValueError):
        rules(0.5)


def test_duplicate_assets_rejected():
    r = rules()
    with pytest.raises(ValueError):
        change(r, targets=(*r.targets, r.targets[0]))


def test_optional_crypto_is_explicit_disabled_never_forced():
    s, _, _ = setup()
    cfg = rules()
    crypto = Allocation(asset="BTC", kind="CRYPTO", weight="0")
    s.configure(
        change(cfg, targets=(*cfg.targets, crypto)),
        expected_version=1,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    plan = evaluate(s)
    assert next(r for r in plan.rows if r.asset == "BTC").state == "DISABLED"
    assert all(a.asset != "BTC" for a in plan.actions)
    with pytest.raises(ValueError):
        change(
            cfg,
            targets=(
                cfg.targets[0],
                change(cfg.targets[1], weight="0.4"),
                change(crypto, weight="0.1"),
            ),
        )


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("inventory_complete", False, "INVENTORY_NOT_VERIFIED_COMPLETE"),
        ("funding", None, "CURRENT_FUNDING_UNAVAILABLE"),
        ("position_verified_at", None, "POSITION_STATE_STALE_OR_MISSING"),
        ("position_verified_at", NOW - timedelta(seconds=121), "POSITION_STATE_STALE_OR_MISSING"),
        ("routes", (), "UNSUPPORTED_OR_UNRESOLVED_ASSET"),
    ],
)
def test_missing_inputs_never_become_zero(field, value, reason):
    s, _, _ = setup()
    s.source.inputs = change(s.source.inputs, **{field: value})
    plan = evaluate(s)
    assert plan.status == "BLOCKED" and reason in plan.reasons
    assert plan.total_value_usd is None
    assert all(r.current_value_usd is None for r in plan.rows)
    assert not plan.actions


@pytest.mark.parametrize(
    "updates",
    [
        {"token_price_usd": None},
        {"price_timestamp": NOW - timedelta(seconds=121)},
        {"ratio_observed_at": NOW - timedelta(seconds=121)},
        {"price_quality": "LIVE"},
        {"token_to_share_ratio": "0.02"},
    ],
)
def test_missing_stale_or_mismatched_marks_fail_closed(updates):
    s, _, _ = setup()
    s.source.inputs = change(
        s.source.inputs, routes=(change(s.source.inputs.routes[0], **updates),)
    )
    assert evaluate(s).status == "BLOCKED"


@pytest.mark.parametrize(
    "updates",
    [
        {"trust_state": "INSUFFICIENT_EVIDENCE"},
        {"trust_state": "LIKELY_NOISE"},
        {"tradable": False},
        {"market_state": "pause"},
        {"liquidity_usd": "1"},
        {"cost_status": "UNAVAILABLE"},
        {"route_available": False},
    ],
)
def test_router_rejects_unqualified_candidate(updates):
    s, _, _ = setup()
    s.source.inputs = change(
        s.source.inputs, routes=(change(s.source.inputs.routes[0], **updates),)
    )
    plan = evaluate(s)
    assert plan.status == "BLOCKED" and not plan.actions
    assert plan.route_decisions[0].status == "NO_ROUTE"


@pytest.mark.parametrize("state", ["UNKNOWN", "RECONCILIATION_REQUIRED"])
def test_uncertain_positions_are_not_treated_as_cash_or_zero(state):
    s, p, _ = setup()
    s.positions._save(p, state=state)
    assert evaluate(s).total_value_usd is None


def test_pending_entry_is_not_owned_and_blocks_plan():
    s, _, _ = setup(confirmed=False)
    plan = evaluate(s)
    assert plan.status == "BLOCKED" and plan.total_value_usd is None


def test_stale_position_blocks():
    s, _, time = setup()
    time[0] += timedelta(seconds=121)
    assert evaluate(s).status == "BLOCKED"


def test_excessive_drift_and_notional_caps():
    s, _, _ = setup()
    s.configure(
        change(rules(), max_drift="0.1"),
        expected_version=1,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert "EXCESSIVE_DRIFT" in evaluate(s).reasons


def test_no_risk_context_blocks():
    s, _, _ = setup()
    s.source.inputs = change(s.source.inputs, risks=())
    assert evaluate(s).status == "BLOCKED"


def test_insufficient_funding_and_gas_blocks():
    s, _, _ = setup()
    s.source.inputs = change(s.source.inputs, funding=change(funding(), native_gas_balance_wei="0"))
    assert evaluate(s).status == "BLOCKED"


def test_stale_independent_equity_does_not_use_token_reference():
    s, _, _ = setup()
    s.source.inputs = change(
        s.source.inputs,
        risks=(
            AssetRisk(
                asset="NVDA", evidence=evidence(equity_observed_at=NOW - timedelta(seconds=121))
            ),
        ),
    )
    assert evaluate(s).status == "BLOCKED"


def test_pending_unique_and_config_cas():
    s, _, _ = setup()
    key = uuid4()
    a = evaluate(s, key)
    assert evaluate(s, key) == a
    assert evaluate(s).plan_id == a.plan_id
    with pytest.raises(ValueError):
        s.configure(rules(), expected_version=1, request_id=uuid4(), correlation_id=uuid4())
    retired = s.retire(a.plan_id)
    assert retired.status == "RETIRED"
    assert s.store.pending(mode="DEMO") is None
    # Exact historical request identity stays retired, never resurrected.
    assert evaluate(s, key).status == "RETIRED"


def test_restart_and_two_store_duplicate_prevention(tmp_path):
    s, _, _ = setup(tmp_path)
    a = evaluate(s)
    second = PortfolioService(
        PortfolioStore(tmp_path / "portfolio"), s.positions, s.source, clock=s.clock
    )
    second.recover()
    assert second.store.config(mode="DEMO") == s.store.config(mode="DEMO")
    assert evaluate(second).plan_id == a.plan_id
    assert second.store.pending(mode="LIVE_READ_ONLY") is None
    assert len(second.store.audit(mode="DEMO")) == 3


def test_buy_handoff_uses_existing_phase8_and_does_not_own_quote():
    s, p, _ = setup()
    plan = evaluate(s)
    result = s.prepare(plan.plan_id, plan.actions[0].action_id, allowance=allowance())
    assert result.preparations[0].status == "DRY_RUN_PREPARED"
    attempt = s.positions.execution.store.get(result.preparations[0].execution_id, mode="DEMO")
    assert attempt.simulation.status == "PASS" and not attempt.execution_ready
    assert attempt.route.build.tx is not None
    assert (
        s.positions.store.get(p.position_id, mode="DEMO").remaining_quantity_base_units == "400000"
    )
    count = len(s.positions.execution.provider.calls)
    assert s.prepare(plan.plan_id, plan.actions[0].action_id, allowance=allowance()) == result
    assert len(s.positions.execution.provider.calls) == count


def test_changed_inputs_block_prepare_without_quote():
    s, _, _ = setup()
    plan = evaluate(s)
    s.source.inputs = change(
        s.source.inputs, funding=change(funding(), balance_base_units="99000000")
    )
    with pytest.raises(ValueError):
        s.prepare(plan.plan_id, plan.actions[0].action_id, allowance=allowance())
    assert not s.positions.execution.provider.calls


def test_crash_after_execution_journal_recovers_receipt(tmp_path):
    s, _, _ = setup(tmp_path)
    plan = evaluate(s)
    a = plan.actions[0]
    attempt = s.positions.execution.prepare(
        a.risk_inputs,
        s.source.inputs.funding,
        target_contract=BUY,
        allowance=allowance(),
        correlation_id=str(plan.correlation_id),
    )
    s.recover()
    restored = s.store.pending(mode="DEMO")
    assert restored.preparations[0].execution_id == attempt.execution_id
    calls = len(s.positions.execution.provider.calls)
    s.prepare(plan.plan_id, a.action_id, allowance=allowance())
    assert len(s.positions.execution.provider.calls) == calls


def test_sell_only_through_existing_lifecycle_and_drift_guard():
    s, p, _ = setup(weight="0.1")
    s.positions.execution = SafetyExecutionService(
        ReverseProvider(),
        s.positions.execution.store,
        ExecutionControls(data_mode="DEMO"),
        clock=s.clock,
    )
    s.positions.execution.position_guard = s.positions.has_unresolved
    plan = evaluate(s)
    assert plan.status == "REBALANCE_REQUIRED" and plan.actions[0].side == "SELL"
    action = plan.actions[0]
    assert action.quantity_base_units == "259980"
    result = s.prepare(plan.plan_id, action.action_id, allowance=change(allowance(), token=BUY))
    assert result.preparations[0].status == "DRY_RUN_PREPARED"
    held = s.positions.store.get(p.position_id, mode="DEMO")
    assert held.remaining_quantity_base_units == "400000"
    assert held.exit_intent.execution.decision_id == action.execution_decision_id
    with pytest.raises(ValueError):
        s.retire(plan.plan_id)


def test_opportunity_exit_policy_cannot_be_overridden():
    s, _, _ = setup(weight="0.1", policy="FIRST_REGULAR_OPEN_PLUS_MINUTES")
    plan = evaluate(s)
    assert plan.status == "BLOCKED"
    assert "EXISTING_POSITION_EXIT_POLICY_HAS_PRIORITY" in plan.reasons


def test_drift_holdings_do_not_exit_on_timer():
    s, p, time = setup()
    time[0] += timedelta(days=1)
    assert s.positions.reconcile(p.position_id).state == "OPEN"
    assert s.positions.store.get(p.position_id, mode="DEMO").exit_due_at is None


def test_drift_guard_missing_cannot_prepare_exit():
    s, p, _ = setup(weight="0.1")
    s.positions.portfolio_exit_guard = None
    plan = evaluate(s)
    a = plan.actions[0]
    with pytest.raises(ValueError, match="NOT_AUTHORIZED"):
        s.positions.prepare_exit(
            p.position_id,
            evidence=a.risk_inputs,
            funding_state=s.source.inputs.token_funding[0],
            allowance=change(allowance(), token=BUY),
            correlation_id=str(plan.correlation_id),
            quantity_base_units=a.quantity_base_units,
        )


def test_mode_mixing_and_synthetic_relabel_rejected():
    s, _, _ = setup()
    with pytest.raises(ValueError):
        change(s.source.inputs, data_mode="LIVE_READ_ONLY")
    assert s.store.config(mode="LIVE_READ_ONLY") is None


def test_decision_math_is_repeatable_for_same_snapshot():
    s, _, _ = setup()
    a, b = evaluate(s, persist=False), evaluate(s, persist=False)
    assert a.actions == b.actions and a.rows == b.rows and a.plan_id == b.plan_id


def test_cash_target_only_drift_repairs_explicit_stock():
    s, _, _ = setup(weight="0.3")
    cfg = rules("0.3")
    s.configure(
        change(
            cfg,
            targets=(
                change(cfg.targets[0], drift_band="0.9"),
                change(cfg.targets[1], drift_band="0.001"),
            ),
        ),
        expected_version=1,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    plan = evaluate(s)
    assert plan.status == "REBALANCE_REQUIRED" and plan.actions[0].asset == "NVDA"


def test_exact_band_boundary_not_decimal_rounding():
    s, _, _ = setup(weight="0.3", confirmed=True)
    s.source.inputs = change(s.source.inputs, funding=change(funding(), unit_price_usd="1"))
    # 40/140 - .3 is repeating, choose a terminating exact boundary by making total=200.
    s.source.inputs = change(
        s.source.inputs,
        funding=change(funding(), unit_price_usd="1", balance_base_units="160000000"),
    )
    cfg = rules("0.25", "0.05")
    s.configure(cfg, expected_version=1, request_id=uuid4(), correlation_id=uuid4())
    assert evaluate(s).status == "NO_ACTION"


def test_cas_corruption_and_immutable_plan_evidence(tmp_path):
    from sqlalchemy import update

    s, _, _ = setup(tmp_path)
    a = evaluate(s)
    with pytest.raises(ValueError):
        s.store.save(change(a, version=1, reasons=("REWRITTEN",)), expected_version=5)
    with s.store.engine.begin() as db:
        db.execute(update(s.store.plans).values(digest="0" * 64))
    with pytest.raises(ValueError, match="Corrupt"):
        s.recover()


def test_concurrent_workers_claim_one_pending_plan(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    s, _, _ = setup(tmp_path)
    workers = [
        PortfolioService(
            PortfolioStore(tmp_path / "portfolio"), s.positions, s.source, clock=s.clock
        )
        for _ in range(4)
    ]
    for worker in workers:
        worker.recover()
    with ThreadPoolExecutor(max_workers=4) as pool:
        plans = list(pool.map(evaluate, workers))
    assert len({p.plan_id for p in plans}) == 1
    assert len({p.idempotency_key for p in plans}) == 1
    for worker in workers:
        worker.store.close()


def test_recovery_incomplete_prevents_financial_calculation():
    s, _, _ = setup()
    s.recovery_complete = False
    assert "RECOVERY_INCOMPLETE" in evaluate(s).reasons


def test_reconciliation_change_blocks_existing_plan_without_provider_calls():
    s, p, _ = setup()
    plan = evaluate(s)
    s.positions._save(p, state="RECONCILIATION_REQUIRED")
    with pytest.raises(ValueError):
        s.prepare(plan.plan_id, plan.actions[0].action_id, allowance=allowance())
    assert s.positions.execution.provider.calls == []


def test_exit_pending_retains_exposure_but_suppresses_reduction():
    s, p, _ = setup(weight="0.1")
    s.positions._save(p, state="EXIT_PENDING")
    plan = evaluate(s)
    assert next(r for r in plan.rows if r.asset == "NVDA").current_value_usd == D("40")
    assert plan.status == "BLOCKED"


def test_current_funding_contract_and_historical_quote_are_not_interchangeable():
    s, _, _ = setup()
    s.source.inputs = change(
        s.source.inputs,
        funding=change(funding(), asset=change(funding().asset, contract="0x" + "9" * 40)),
    )
    assert "POSITION_CASH_ASSET_MISMATCH" in evaluate(s).reasons


def test_sell_funding_price_must_match_selected_held_mark():
    s, _, _ = setup(weight="0.1")
    f = s.source.inputs.token_funding[0]
    s.source.inputs = change(s.source.inputs, token_funding=(change(f, unit_price_usd="99"),))
    assert "REDUCTION_FUNDING_MARK_QUANTITY_MISMATCH" in evaluate(s).reasons


def test_changed_route_order_does_not_change_economics():
    s, _, _ = setup()
    original = s.source.inputs.routes[0]
    expensive = change(
        original,
        identity=change(original.identity, contract="0x" + "7" * 40, issuer="OTHER"),
        token_price_usd="120",
    )
    s.source.inputs = change(s.source.inputs, routes=(original, expensive))
    a = evaluate(s, persist=False)
    s.source.inputs = change(s.source.inputs, routes=(expensive, original))
    b = evaluate(s, persist=False)
    assert a.actions[0].route.selected_representation == b.actions[0].route.selected_representation
    assert a.actions[0].notional_usd == b.actions[0].notional_usd


def test_notional_cap_suppresses_entire_plan():
    s, _, _ = setup()
    s.configure(
        change(rules(), max_stock_exposure_usd="50"),
        expected_version=1,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    plan = evaluate(s)
    assert plan.status == "BLOCKED" and "PORTFOLIO_STOCK_EXPOSURE_CAP" in plan.reasons
    assert not any(a.eligible_for_preparation for a in plan.actions)


def test_baseunit_rounding_never_exceeds_delta():
    s, _, _ = setup()
    s.source.inputs = change(
        s.source.inputs, routes=(change(s.source.inputs.routes[0], token_price_usd="101.1234567"),)
    )
    plan = evaluate(s)
    a = plan.actions[0]
    row = next(r for r in plan.rows if r.asset == "NVDA")
    assert a.notional_usd <= row.required_delta_usd
    assert row.required_delta_usd - a.notional_usd < D("101.1234567") / 10**6
    assert int(a.target_representation_base_units) - int(
        a.current_representation_base_units
    ) == int(a.quantity_base_units)


def test_existing_holding_policy_is_immutable():
    s, p, _ = setup()
    with pytest.raises(ValueError):
        s.positions.create(
            p.entry_execution.execution_id,
            p.instrument,
            exit_rule="FIRST_REGULAR_OPEN_PLUS_MINUTES",
        )


def test_bounded_universe_no_truncation():
    with pytest.raises(ValueError):
        change(
            rules(),
            targets=tuple(
                Allocation(asset=f"S{i}", kind="TOKENIZED_STOCK", weight="0") for i in range(24)
            )
            + rules().targets,
        )


def test_fresh_process_recovers_configuration_drift_and_pending_plan(tmp_path):
    import json
    import os
    import subprocess
    import sys

    s, _, _ = setup(tmp_path)
    plan = evaluate(s)
    s.store.close()
    s.positions.store.close()
    s.positions.execution.store.close()
    code = """
import json,sys
from pathlib import Path
from app.models.execution import ExecutionControls
from app.repositories.execution import ExecutionStore
from app.repositories.position import PositionStore
from app.repositories.portfolio import PortfolioStore
from app.services.execution import SafetyExecutionService
from app.services.position import PositionService
from app.services.portfolio import PortfolioService
from backend.tests.unit.test_portfolio import Source, evaluate
from backend.tests.fixtures.execution_fixtures import NOW
p=Path(sys.argv[1])
e=SafetyExecutionService(None,ExecutionStore(p/'execution'),ExecutionControls(data_mode='DEMO'),clock=lambda:NOW)
m=PositionService(PositionStore(e.store,p/'portfolio_positions'),e,clock=lambda:NOW)
m.recover()
s=PortfolioService(PortfolioStore(p/'portfolio'),m,Source(),clock=lambda:NOW)
s.recover()
a=evaluate(s)
print(json.dumps({'plan':a.plan_id,'total':str(a.total_value_usd),'config_version':s.state()['config'].version,'positions':len(s.state()['active_positions'])}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        env={"PATH": os.defpath, "PYTHONPATH": "backend"},
        text=True,
        capture_output=True,
        check=True,
    )
    recovered = json.loads(result.stdout.splitlines()[-1])
    assert recovered == {
        "plan": plan.plan_id,
        "total": str(plan.total_value_usd),
        "config_version": 1,
        "positions": 1,
    }


def test_agent_mandate_cannot_replace_explicit_targets_or_limits():
    from app.agents.schemas import Mandate

    s, _, _ = setup()
    mandate = Mandate(
        mode="AUTOPILOT",
        strategy="TOKENIZED_AI_AND_CASH",
        allocation_stock_percent="50",
        allocation_cash_percent="50",
    )
    assert (
        s.configure_from_mandate(
            mandate, rules(), expected_version=1, request_id=uuid4(), correlation_id=uuid4()
        ).version
        == 2
    )
    with pytest.raises(ValueError):
        s.configure_from_mandate(
            mandate, rules("0.6"), expected_version=2, request_id=uuid4(), correlation_id=uuid4()
        )


def test_wallet_gate_still_blocks_prepared_portfolio_action():
    s, _, _ = setup()
    plan = evaluate(s)
    result = s.prepare(plan.plan_id, plan.actions[0].action_id, allowance=allowance())
    attempt = s.positions.execution.store.get(result.preparations[0].execution_id, mode="DEMO")
    assert attempt.simulation.status == "PASS"
    assert not attempt.execution_ready
    assert any("DRY_RUN" in reason or "WALLET" in reason for reason in attempt.reason_codes)


def test_failed_simulation_does_not_change_holdings_or_resubmit():
    s, p, _ = setup()
    s.positions.execution.provider.simulation_status = "FAILED"
    plan = evaluate(s)
    result = s.prepare(plan.plan_id, plan.actions[0].action_id, allowance=allowance())
    assert result.preparations[0].status == "BLOCKED"
    assert (
        s.positions.store.get(p.position_id, mode="DEMO").remaining_quantity_base_units == "400000"
    )
    before = len(s.positions.execution.provider.calls)
    s.prepare(plan.plan_id, plan.actions[0].action_id, allowance=allowance())
    assert len(s.positions.execution.provider.calls) == before


def test_direct_exit_cannot_override_portfolio_risk_inputs():
    s, p, _ = setup(weight="0.1")
    plan = evaluate(s)
    a = plan.actions[0]
    with pytest.raises(ValueError, match="NOT_AUTHORIZED"):
        s.positions.prepare_exit(
            p.position_id,
            evidence=change(a.risk_inputs, risk_budget_usd="3"),
            funding_state=s.source.inputs.token_funding[0],
            allowance=change(allowance(), token=BUY),
            correlation_id=str(plan.correlation_id),
            quantity_base_units=a.quantity_base_units,
        )
    assert not s.positions.execution.provider.calls


def test_configuration_compare_and_swap_after_restart(tmp_path):
    s, _, _ = setup(tmp_path)
    other = PortfolioService(
        PortfolioStore(tmp_path / "portfolio"), s.positions, s.source, clock=s.clock
    )
    other.recover()
    s.configure(rules("0.4"), expected_version=1, request_id=uuid4(), correlation_id=uuid4())
    with pytest.raises(ValueError, match="version"):
        other.configure(
            rules("0.3"), expected_version=1, request_id=uuid4(), correlation_id=uuid4()
        )
    assert other.store.config(mode="DEMO").version == 2


def test_outside_band_missing_risk_cannot_create_an_executable_plan():
    s, _, _ = setup()
    s.source.inputs = change(
        s.source.inputs,
        risks=(
            AssetRisk(asset="NVDA", evidence=change(evidence(), required_evidence_valid=False)),
        ),
    )
    assert evaluate(s).status == "BLOCKED"


def test_token_equity_alignment_and_stale_trust_still_enforced():
    s, _, _ = setup()
    s.source.inputs = change(
        s.source.inputs,
        risks=(
            AssetRisk(
                asset="NVDA",
                evidence=change(evidence(), equity_observed_at=NOW - timedelta(seconds=31)),
            ),
        ),
    )
    assert evaluate(s).status == "BLOCKED"


def test_plan_stale_cannot_prepare_or_reduce():
    s, _, time = setup()
    plan = evaluate(s)
    time[0] += timedelta(seconds=121)
    with pytest.raises(ValueError):
        s.prepare(plan.plan_id, plan.actions[0].action_id, allowance=allowance())
    assert not s.positions.execution.provider.calls


@pytest.mark.parametrize("weight,expected", [("0", "CLOSED"), ("0.1", "OPEN")])
def test_confirmed_disposition_is_valued_only_from_phase10(weight, expected):
    from backend.tests.unit.test_position import settle_exit

    s, p, time = setup(weight=weight)
    provider = ReverseProvider(execution_mode="RFQ")
    s.positions.execution = SafetyExecutionService(
        provider, s.positions.execution.store, ExecutionControls(data_mode="DEMO"), clock=s.clock
    )
    s.positions.execution.position_guard = s.positions.has_unresolved
    plan = evaluate(s)
    action = plan.actions[0]
    s.prepare(plan.plan_id, action.action_id, allowance=change(allowance(), token=BUY))
    prepared = s.positions.store.get(p.position_id, mode="DEMO")
    # Import documented synthetic settlement proof through existing Phase 8/10 machinery.
    result = settle_exit(s.positions, prepared, time, provider)
    assert result.state == expected
    current = evaluate(s, persist=False)
    row = next(r for r in current.rows if r.asset == "NVDA")
    assert row.current_value_usd == D(result.remaining_quantity_base_units) / 10**6 * 100
    assert row.current_share_exposure == result.normalized_share_exposure
    assert not result.broadcast
    if expected == "CLOSED":
        assert current.status == "NO_ACTION" and row.current_value_usd == 0
    else:
        assert result.remaining_quantity_base_units == "140020"


def test_pending_disposition_blocks_whole_portfolio_without_erasing_holdings():
    from backend.tests.unit.test_position import settle_exit

    s, p, time = setup(weight="0.1")
    provider = ReverseProvider(execution_mode="RFQ")
    s.positions.execution = SafetyExecutionService(
        provider, s.positions.execution.store, ExecutionControls(data_mode="DEMO"), clock=s.clock
    )
    s.positions.execution.position_guard = s.positions.has_unresolved
    plan = evaluate(s)
    s.prepare(plan.plan_id, plan.actions[0].action_id, allowance=change(allowance(), token=BUY))
    p = s.positions.store.get(p.position_id, mode="DEMO")
    pending = settle_exit(s.positions, p, time, provider, unknown=True)
    assert pending.state == "EXITING" and pending.remaining_quantity_base_units == "400000"
    assessment = evaluate(s, persist=False)
    assert assessment.status == "BLOCKED" and assessment.total_value_usd is None
    assert not assessment.actions
    with pytest.raises(ValueError):
        s.retire(plan.plan_id)


def test_live_readonly_uses_shared_router_and_remains_blocked_before_provider_call(tmp_path):
    """Offline LIVE contract probe, not real provider/Trust evidence or synthetic gate bypass."""
    from app.repositories.execution import ExecutionStore
    from app.services.position import PositionService
    from app.services.routing import RoutingService

    provider = FixtureProvider()
    execution = SafetyExecutionService(
        provider,
        ExecutionStore(tmp_path / "probe_execution"),
        ExecutionControls(data_mode="LIVE_READ_ONLY"),
        clock=lambda: NOW,
    )
    manager = PositionService(
        PositionStore(execution.store, tmp_path / "probe_positions"), execution, clock=lambda: NOW
    )
    manager.recover()
    execution.position_guard = manager.has_unresolved
    source = Source()
    offline = "OFFLINE_SCHEMA_PROBE"
    f = change(
        source.inputs.funding,
        source=offline,
        asset=change(source.inputs.funding.asset, data_mode="LIVE_READ_ONLY", source=offline),
    )
    r = change(
        source.inputs.routes[0],
        data_mode="LIVE",
        price_quality="LIVE",
        price_source=offline,
        ratio_source=offline,
        liquidity_source=offline,
        cost_source=offline,
        trust_source=offline,
        route_support="VERIFIED_PROVIDER_ROUTE",
    )
    e = change(
        evidence(),
        data_mode="LIVE_READ_ONLY",
        context=change(evidence().context, data_mode="LIVE_READ_ONLY", source=offline),
    )
    source.inputs = PortfolioInputs(
        data_mode="LIVE_READ_ONLY",
        captured_at=NOW,
        position_verified_at=NOW,
        inventory_complete=True,
        funding=f,
        routes=(r,),
        risks=(AssetRisk(asset="NVDA", evidence=e),),
        source=offline,
    )
    s = PortfolioService(
        PortfolioStore(tmp_path / "probe_portfolio"), manager, source, clock=lambda: NOW
    )
    s.recover()
    s.configure(rules(), expected_version=0, request_id=uuid4(), correlation_id=uuid4())
    result = evaluate(s)
    assert type(s.router) is RoutingService
    assert result.data_mode == "LIVE_READ_ONLY" and result.status == "BLOCKED"
    assert result.route_decisions[0].data_mode == "LIVE"
    assert (
        "PRODUCTION_TRUST_GATE" in result.route_decisions[0].candidates[0].inputs.risk_reason_codes
    )
    assert result.route_decisions[0].candidates[0].inputs.route_support == "VERIFIED_PROVIDER_ROUTE"
    assert not provider.calls and not result.actions


def test_handoff_reuses_actual_provider_quote_route_selection_and_binding():
    class MultipleRoutes(FixtureProvider):
        def quote(self, request, *, mode):
            q = super().quote(request, mode=mode)[0]
            best = change(
                q,
                route=change(
                    q.route,
                    quoteId="better_provider_quote",
                    vendorName="AlternateDex",
                    toTokenAmount="450000",
                ),
            )
            return [q, best]

        def build(self, q, *, slippage_bps):
            result = super().build(q, slippage_bps=slippage_bps)
            return change(
                result,
                tx=change(
                    result.tx, minReceiveAmount=str(int(q.route.toTokenAmount) * 995 // 1000)
                ),
            )

    s, _, _ = setup()
    provider = MultipleRoutes()
    s.positions.execution = SafetyExecutionService(
        provider, s.positions.execution.store, ExecutionControls(data_mode="DEMO"), clock=s.clock
    )
    s.positions.execution.position_guard = s.positions.has_unresolved
    plan = evaluate(s)
    result = s.prepare(plan.plan_id, plan.actions[0].action_id, allowance=allowance())
    attempt = s.positions.execution.store.get(result.preparations[0].execution_id, mode="DEMO")
    assert attempt.quote.route.quoteId == "better_provider_quote"
    assert attempt.quote.route.vendorName == "AlternateDex"
    assert attempt.quote.source == "TEST_FIXTURE"
    assert attempt.route.quote == attempt.quote and attempt.simulation.status == "PASS"
    assert attempt.route.fingerprint == attempt.simulation.fingerprint
    assert not attempt.execution_ready


@pytest.mark.parametrize(
    "identity",
    [
        {"chain_id": "1", "contract": "0x" + "7" * 40},
        {"chain_id": "56", "contract": "demo:unverified_contract"},
    ],
)
def test_unsupported_execution_chain_or_address_never_becomes_quote(identity):
    s, _, _ = setup()
    base = s.source.inputs.routes[0]
    unsupported = change(base, identity=change(base.identity, **identity), token_price_usd="80")
    s.source.inputs = change(s.source.inputs, routes=(unsupported, base))
    plan = evaluate(s)
    assert plan.actions[0].route.selected_representation.contract == BUY
    rejected = next(
        c
        for c in plan.route_decisions[0].candidates
        if c.inputs.identity.contract == identity["contract"]
    )
    assert "UNSUPPORTED_EXECUTION_CHAIN_OR_CONTRACT" in rejected.rejection_reasons
    assert not s.positions.execution.provider.calls


def test_coalesced_request_keeps_auditable_current_capture():
    s, _, _ = setup()
    first = evaluate(s)
    s.source.inputs = change(
        s.source.inputs, funding=change(funding(), balance_base_units="95000000")
    )
    assert evaluate(s).plan_id == first.plan_id
    event = s.store.audit(mode="DEMO")[0]
    assert event["event"] == "PENDING_PLAN_REUSED"
    assert event["captured_inputs"]["inputs"]["funding"]["balance_base_units"] == "95000000"
    assert event["input_snapshot"] != first.snapshot.snapshot_id


def test_new_execution_evidence_cannot_hide_behind_authentic_old_position_snapshot():
    from backend.tests.fixtures.execution_fixtures import TXHASH

    s, p, _ = setup(weight="0.1")
    provider = ReverseProvider(execution_mode="RFQ")
    s.positions.execution = SafetyExecutionService(
        provider, s.positions.execution.store, ExecutionControls(data_mode="DEMO"), clock=s.clock
    )
    s.positions.execution.position_guard = s.positions.has_unresolved
    plan = evaluate(s)
    s.prepare(plan.plan_id, plan.actions[0].action_id, allowance=change(allowance(), token=BUY))
    p = s.positions.store.get(p.position_id, mode="DEMO")
    old = p.exit_intent.execution
    pending = change(
        old,
        state="EXECUTION_PENDING",
        external_tracking_only=True,
        order_id="fixture_existing_exit",
        tx_hash=TXHASH,
        version=old.version + 1,
        updated_at=NOW,
    )
    s.positions.execution.store.save(pending, expected_version=old.version)
    assessment = evaluate(s, persist=False)
    assert assessment.status == "BLOCKED" and assessment.total_value_usd is None
    assert "CURRENT_EXECUTION_REQUIRES_POSITION_RECONCILIATION" in assessment.reasons


def test_portfolio_handoff_runs_existing_wallet_quota_checks_without_writes():
    from backend.tests.fixtures.wallet_fixtures import WalletWire
    from backend.tests.unit.test_agentic_wallet import adapter

    s, _, _ = setup()
    wire = WalletWire()
    wire.values["settings"]["quotaUsed"] = "100"
    wire.values["settings"]["quotaLeft"] = "0"
    s.positions.execution = SafetyExecutionService(
        FixtureProvider(),
        s.positions.execution.store,
        ExecutionControls(data_mode="DEMO"),
        clock=s.clock,
        wallet_adapter=adapter(wire),
    )
    s.positions.execution.position_guard = s.positions.has_unresolved
    plan = evaluate(s)
    result = s.prepare(plan.plan_id, plan.actions[0].action_id, allowance=allowance())
    attempt = s.positions.execution.store.get(result.preparations[0].execution_id, mode="DEMO")
    assert attempt.simulation.status == "PASS" and not attempt.execution_ready
    assert any("QUOTA" in code for code in attempt.reason_codes)
    assert "WALLET_EXECUTION_DISABLED" in attempt.reason_codes
    assert any("settings" in args for args in wire.calls)
    assert not any(
        command in args for args in wire.calls for command in ("swap", "send", "sign", "broadcast")
    )


def test_preparation_or_missing_settlement_cannot_complete_or_establish_ownership():
    s, _, _ = setup()
    plan = evaluate(s)
    a = plan.actions[0]
    s.prepare(plan.plan_id, a.action_id, allowance=allowance())
    with pytest.raises(ValueError, match="CONFIRMED"):
        s.register_confirmed_entry(plan.plan_id, a.action_id, instrument())
    with pytest.raises(ValueError, match="CONFIRMED"):
        s.complete(plan.plan_id)
    assert s.store.pending(mode="DEMO") is not None


def test_verified_reduction_completes_plan_but_never_cancels_external_execution():
    from backend.tests.unit.test_position import settle_exit

    s, p, time = setup(weight="0.1")
    provider = ReverseProvider(execution_mode="RFQ")
    s.positions.execution = SafetyExecutionService(
        provider, s.positions.execution.store, ExecutionControls(data_mode="DEMO"), clock=s.clock
    )
    s.positions.execution.position_guard = s.positions.has_unresolved
    plan = evaluate(s)
    s.prepare(plan.plan_id, plan.actions[0].action_id, allowance=change(allowance(), token=BUY))
    p = s.positions.store.get(p.position_id, mode="DEMO")
    settled = settle_exit(s.positions, p, time, provider)
    s.source.inputs = change(
        s.source.inputs,
        token_funding=(
            change(
                s.source.inputs.token_funding[0],
                balance_base_units=settled.remaining_quantity_base_units,
            ),
        ),
    )
    completed = s.complete(plan.plan_id)
    assert completed.status == "COMPLETED" and s.store.pending(mode="DEMO") is None
    assert completed.completion_snapshot is not None
    assert completed.settled_execution_ids == (settled.applied_exit_executions[-1].execution_id,)
    event = s.store.audit(mode="DEMO")[0]
    assert event["completion_snapshot"]["snapshot_id"] == completed.completion_snapshot.snapshot_id
    assert s.complete(plan.plan_id) == completed
    assert evaluate(s, plan.idempotency_key).status == "COMPLETED"
    assert settled.remaining_quantity_base_units == "140020"


def test_confirmed_buy_uses_phase10_filled_units_and_immutable_drift_policy():
    from backend.tests.fixtures.execution_fixtures import TXHASH
    from backend.tests.integration.test_settlement_remediation import filled, observe

    s, _, _ = setup()
    provider = FixtureProvider(execution_mode="RFQ")
    s.positions.execution = SafetyExecutionService(
        provider, s.positions.execution.store, ExecutionControls(data_mode="DEMO"), clock=s.clock
    )
    s.positions.execution.position_guard = s.positions.has_unresolved
    plan = evaluate(s)
    action = plan.actions[0]
    prepared = s.prepare(plan.plan_id, action.action_id, allowance=allowance())
    a = s.positions.execution.store.get(prepared.preparations[0].execution_id, mode="DEMO")
    pending = change(
        a,
        state="EXECUTION_PENDING",
        external_tracking_only=True,
        order_id="synthetic_portfolio_buy",
        tx_hash=TXHASH,
        version=a.version + 1,
        updated_at=NOW,
    )
    s.positions.execution.store.save(pending, expected_version=a.version)
    confirmed = observe(provider, s.positions.execution.store, pending, filled(pending))
    with pytest.raises(ValueError, match="POSITION_LINK"):
        s.complete(plan.plan_id)
    owned = s.register_confirmed_entry(plan.plan_id, action.action_id, instrument())
    assert owned.remaining_quantity_base_units == confirmed.filled_quantity_base_units
    assert owned.exit_rule == "PORTFOLIO_DRIFT" and owned.exit_due_at is None
    assert s.register_confirmed_entry(plan.plan_id, action.action_id, instrument()) == owned
    assert s.complete(plan.plan_id).status == "COMPLETED"
    assert s.positions.store.count(mode="DEMO") == 2
