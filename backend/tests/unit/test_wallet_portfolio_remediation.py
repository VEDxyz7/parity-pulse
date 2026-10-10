"""Reuse portfolio planning with wallet holdings; synthetic only, no admission bypass."""

from datetime import timedelta
from decimal import Decimal

import pytest

from app.repositories.live_fills import LiveFillStore
from app.services.portfolio import PortfolioService
from app.services.position import change
from backend.tests.unit.test_live_execution import claimed
from backend.tests.unit.test_portfolio import evaluate, setup


@pytest.mark.parametrize("weight,side", [("0.5", "BUY"), ("0.1", "SELL")])
def test_wallet_planning_reuses_routing_risk_normalization(weight, side):
    service, _, _ = setup(weight=weight)
    service.inventory = "WALLET"
    plan = evaluate(service)
    assert plan.status == "REBALANCE_REQUIRED"
    assert plan.total_value_usd == Decimal("140.0200")  # holdings counted once
    action = plan.actions[0]
    assert action.side == side and action.inventory_source == "WALLET_BALANCE"
    assert action.position_id is None and action.risk.status == "PASS"
    assert action.route.status == "ROUTE_SELECTED"
    assert plan.execution_mode == "DRY_RUN" and not plan.live_trading_enabled


@pytest.mark.parametrize("defect", ["stale", "identity", "unknown", "duplicate", "price"])
def test_wallet_balance_authority_requires_fresh_verified_marks(defect):
    s, _, _ = setup()
    s.inventory = "WALLET"
    h = s.source.inputs.token_funding[0]
    if defect == "stale":
        h = change(h, balance_observed_at=h.balance_observed_at - timedelta(seconds=121))
    elif defect == "identity":
        h = change(h, identity_verified=False)
    elif defect == "unknown":
        h = change(h, asset=change(h.asset, contract="0x" + "9" * 40))
    elif defect == "price":
        h = change(h, unit_price_usd="101")
    elif defect == "duplicate":
        with pytest.raises(ValueError, match="Ambiguous duplicate token funding"):
            change(s.source.inputs, token_funding=(h, h))
        return
    s.source.inputs = change(
        s.source.inputs, token_funding=(h, h) if defect == "duplicate" else (h,)
    )
    plan = evaluate(s)
    assert plan.status == "BLOCKED" and not plan.actions
    assert any("WALLET_HOLDING" in r for r in plan.reasons)


def test_no_trust_disable_and_unresolved_guard_cannot_be_bypassed_internally():
    s, _, _ = setup()
    with pytest.raises(ValueError, match="Trust cannot be disabled"):
        PortfolioService(s.store, s.positions, s.source, clock=s.clock, trust_required=False)
    plan = evaluate(s)
    s.live_journal = LiveFillStore()
    claimed(s.live_journal)
    s.live_journal.db.execute(
        "UPDATE fills SET plan_id=? WHERE action_id=?", (str(plan.plan_id), "action")
    )
    s.live_journal.db.commit()
    s.live_journal.upsert("action", status="RECONCILIATION_REQUIRED")
    for operation in (
        lambda: s.retire(plan.plan_id),
        lambda: evaluate(s),
        lambda: s.prepare(plan.plan_id, plan.actions[0].action_id, allowance=None),
    ):
        with pytest.raises(ValueError, match="UNRESOLVED"):
            operation()
