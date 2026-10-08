"""Synthetic lifecycle evidence, never real fills or LIVE gate evidence."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import update

from app.clients.common import ProviderError
from app.models.execution import ExecutionControls, ProviderQuote, QuoteRoute
from app.models.position import PositionInstrument, SettlementValuation
from app.repositories.execution import ExecutionStore
from app.repositories.position import PositionStore
from app.services.execution import SafetyExecutionService
from app.services.position import PositionService, change
from backend.tests.fixtures.execution_fixtures import (
    BUY,
    NOW,
    SELL,
    TXHASH,
    FixtureProvider,
    allowance,
    build,
    evidence,
    funding,
    mutate,
    route_data,
)
from backend.tests.integration.test_settlement_remediation import existing, filled, observe


def instrument(**changes):
    return mutate(
        PositionInstrument(
            ticker="NVDA",
            company="Nvidia synthetic fixture",
            representation="nvda_fixture",
            token="NVDA",
            contract=BUY,
            issuer="FIXTURE",
            platform="FIXTURE",
            decimals=6,
            shares_per_token="0.01",
            ratio_observed_at=NOW,
            ratio_available_at=NOW,
            source="TEST_FIXTURE",
            data_mode="DEMO",
        ),
        **changes,
    )


class ReverseProvider(FixtureProvider):
    def quote(self, request, *, mode):
        assert mode == "DEMO"
        self.calls.append(("quote", request.model_dump()))
        self.count += 1
        raw = route_data(request, execution_mode=self.execution_mode, quote_id=f"exit{self.count}")
        raw.update(router=BUY + "--" + SELL, toTokenAmount=str(int(request.amount) * 100))
        raw["fromToken"].update(tokenContractAddress=BUY, tokenSymbol="NVDA", tokenUnitPrice="100")
        raw["toToken"].update(tokenContractAddress=SELL, tokenSymbol="USDT", tokenUnitPrice="1")
        return [
            ProviderQuote(
                request=request,
                route=QuoteRoute(**raw),
                data_mode="DEMO",
                source="TEST_FIXTURE",
                requested_at=self.clock(),
                received_at=self.clock(),
                expires_at=self.clock() + timedelta(seconds=30),
            )
        ]

    def build(self, q, *, slippage_bps):
        self.calls.append(("build", q.route.quoteId))
        result = build(q, slippage_bps=slippage_bps)
        if result.tx:
            result = mutate(
                result,
                tx=mutate(
                    result.tx, minReceiveAmount=str(int(q.route.toTokenAmount) * 995 // 1000)
                ),
            )
        return result


def runtime(tmp_path=None, *, confirmed=True, amount=None, pending="EXECUTION_PENDING"):
    provider, memory, a = existing(state=pending)
    if tmp_path:
        store = ExecutionStore(tmp_path / "execution")
        store.save(a)
        memory.close()
    else:
        store = memory
    if confirmed:
        a = observe(provider, store, a, filled(a, **({"toAmount": amount} if amount else {})))
    time = [NOW]
    service = SafetyExecutionService(
        provider, store, ExecutionControls(data_mode="DEMO"), clock=lambda: time[0]
    )
    positions = PositionStore(store, tmp_path / "positions" if tmp_path else None)
    manager = PositionService(positions, service, clock=lambda: time[0])
    manager.recover()
    service.position_guard = manager.has_unresolved
    p = manager.create(a.execution_id, instrument())
    return manager, p, time


def reopen(manager, tmp_path, time, provider=None):
    manager.store.close()
    manager.execution.store.close()
    executions = ExecutionStore(tmp_path / "execution")
    service = SafetyExecutionService(
        provider, executions, ExecutionControls(data_mode="DEMO"), clock=lambda: time[0]
    )
    manager = PositionService(
        PositionStore(executions, tmp_path / "positions"), service, clock=lambda: time[0]
    )
    service.position_guard = manager.has_unresolved
    return manager


def exit_inputs(manager, p, time, amount=None):
    amount = amount or p.remaining_quantity_base_units
    at = time[0]
    f = funding(
        asset=mutate(funding().asset, contract=BUY, symbol="NVDA", observed_at=at),
        unit_price_usd="100",
        price_observed_at=at,
        native_price_observed_at=at,
        balance_base_units=p.remaining_quantity_base_units,
        balance_observed_at=at,
        conversion_cost_observed_at=at,
    )
    e = evidence(
        decision_id=manager.exit_decision_id(p.position_id, amount),
        notional_usd=Decimal(amount) / Decimal(10000),
        token_observed_at=at,
        equity_observed_at=at,
        evidence_observed_at=at,
        context=mutate(evidence().context, observed_at=at, existing_exposure_usd="40"),
    )
    return dict(
        evidence=e,
        funding_state=f,
        allowance=allowance(token=BUY, observed_at=at),
        correlation_id="position_exit",
        quantity_base_units=amount,
    )


def prepare_exit(manager, p, time, *, amount=None, execution_mode="SWAP"):
    time[0] = p.exit_due_at
    provider = ReverseProvider(clock=lambda: time[0], execution_mode=execution_mode)
    manager.execution.provider = provider
    manager.execution.quotes.provider = provider
    manager.execution.simulator.provider = provider
    return manager.prepare_exit(p.position_id, **exit_inputs(manager, p, time, amount)), provider


def settle_exit(manager, p, time, provider, *, unknown=False):
    a = p.exit_intent.execution
    imported = mutate(
        a,
        state="EXECUTION_PENDING",
        external_tracking_only=True,
        order_id="exit_order_" + str(p.exit_intent.ordinal),
        tx_hash=TXHASH,
        version=a.version + 1,
        updated_at=time[0],
    )
    manager.execution.store.save(imported, expected_version=a.version)
    status = filled(
        imported,
        createdAt=int(time[0].timestamp() * 1000),
        filledAt=int(time[0].timestamp() * 1000),
    )
    provider.order_status = lambda _: (
        mutate(status, status="PENDING_VENDOR") if unknown else status,
        time[0],
    )
    return manager.reconcile(p.position_id)


def test_confirmed_creation_retains_identity_ratio_schedule_and_exact_quantities():
    manager, p, _ = runtime(amount="398000")
    assert p.state == "OPEN" and p.synthetic and not p.broadcast
    assert p.requested_quantity_base_units == "400000"
    assert p.filled_quantity_base_units == p.remaining_quantity_base_units == "398000"
    assert p.unfilled_quoted_quantity_base_units == "2000"
    assert p.normalized_share_exposure == Decimal("0.00398")
    assert p.entry_notional_usd == Decimal("40.0000004004")
    assert p.average_execution_price_usd.quantize(Decimal("0.00000001")) == (
        p.entry_notional_usd / p.filled_quantity
    ).quantize(Decimal("0.00000001"))
    assert p.effective_cost_per_share_usd > p.average_execution_price_usd
    assert p.exit_due_at == datetime(2026, 10, 9, 13, 40, tzinfo=UTC)
    assert p.gas_native_base_units == (None,)
    assert p.net_pnl_usd is None and p.fees_usd is None
    assert manager.create(p.entry_execution.execution_id, instrument()) == p
    assert manager.store.count(mode="DEMO") == 1


@pytest.mark.parametrize("state", ["EXECUTION_PENDING", "EXECUTION_SUBMITTED", "EXECUTION_UNKNOWN"])
def test_pending_unknown_cannot_establish_open(state):
    manager, p, _ = runtime(confirmed=False, pending=state)
    assert p.state == ("UNKNOWN" if state == "EXECUTION_UNKNOWN" else "OPENING")
    assert p.remaining_quantity_base_units == "0"
    with pytest.raises(ValueError):
        change(p, state="OPEN")
    assert manager.has_unresolved()


def test_quote_and_simulation_are_only_proposed():
    from backend.tests.unit.test_agentic_wallet import prepared

    service, a = prepared()
    manager = PositionService(PositionStore(service.store), service, clock=lambda: NOW)
    p = manager.create(a.execution_id, instrument())
    assert a.simulation.status == "PASS" and p.state == "PROPOSED"
    assert p.entry_at is None and p.filled_quantity_base_units == "0"


@pytest.mark.parametrize("target", ["PROPOSED", "OPENING", "FAILED", "CLOSED", "EXITING"])
def test_invalid_open_transitions_rejected(target):
    manager, p, _ = runtime()
    with pytest.raises(ValueError):
        manager.store.save(
            change(p, state=target, version=p.version + 1), expected_version=p.version
        )


def test_pending_becomes_open_only_via_existing_confirmation():
    manager, p, _ = runtime(confirmed=False)
    a = p.entry_execution
    manager.execution.provider.order_status = lambda _: (filled(a), NOW)
    result = manager.reconcile(p.position_id)
    assert result.state == "OPEN" and result.entry_execution.settlement_evidence is not None
    assert not result.funds_moved and not result.entry_execution.broadcast


def test_terminal_failed_pending_becomes_failed_without_quantity():
    manager, p, _ = runtime(confirmed=False)
    manager.execution.provider.order_status = lambda _: (
        mutate(filled(p.entry_execution), status="FAILED"),
        NOW,
    )
    assert manager.reconcile(p.position_id).state == "FAILED"


def test_hash_conflict_is_sticky_and_blocks_dependent_execution():
    manager, p, _ = runtime(confirmed=False)
    provider = manager.execution.provider
    provider.order_status = lambda _: (filled(p.entry_execution, txHash="0x" + "6" * 64), NOW)
    result = manager.reconcile(p.position_id)
    assert result.state == "RECONCILIATION_REQUIRED"
    assert result.entry_execution.tx_hash == TXHASH
    assert result.entry_execution.conflicting_tx_hashes == ("0x" + "6" * 64,)
    provider.quote = lambda *_args, **_kwargs: pytest.fail("Unresolved position must block quote")
    a = manager.execution.prepare(
        evidence(decision_id="dependent"),
        funding(),
        target_contract=BUY,
        allowance=allowance(),
        correlation_id="dependent",
    )
    assert a.reason_codes == ("POSITION_STATE_UNRESOLVED",)


@pytest.mark.parametrize(
    "field,value",
    [("data_mode", "LIVE_READ_ONLY"), ("position_id", uuid4()), ("postopen_exit_minutes", 11)],
)
def test_immutable_identity_and_mode_cannot_change(field, value):
    manager, p, _ = runtime()
    with pytest.raises((ValueError, KeyError)):
        manager.store.save(
            change(p, **{field: value}, version=p.version + 1), expected_version=p.version
        )
    with pytest.raises(KeyError):
        manager.store.get(p.position_id, mode="LIVE_READ_ONLY")


def test_ratio_cannot_be_backfilled_from_after_entry():
    manager, p, _ = runtime()
    with pytest.raises(ValueError):
        manager.create(
            p.entry_execution.execution_id,
            instrument(ratio_available_at=NOW + timedelta(seconds=1)),
        )
    with pytest.raises(ValueError):
        change(p, instrument=instrument(shares_per_token=0.01))


def test_store_rejects_model_construct_confirmation_forgery():
    manager, p, _ = runtime(confirmed=False)
    forged = p.model_copy(update={"state": "OPEN", "filled_quantity_base_units": "400000"})
    with pytest.raises(ValueError):
        manager.store.save(forged, expected_version=0)


def test_event_or_payload_corruption_fails_closed():
    manager, p, _ = runtime()
    with manager.store.engine.begin() as db:
        db.execute(update(manager.store.events).values(payload="{}"))
    with pytest.raises(ValueError):
        manager.store.get(p.position_id, mode="DEMO")
    assert manager.has_unresolved()


@pytest.mark.parametrize(
    "at,opening",
    [
        (datetime(2026, 10, 10, 12, tzinfo=UTC), datetime(2026, 10, 12, 13, 30, tzinfo=UTC)),
        (datetime(2026, 11, 2, 12, tzinfo=UTC), datetime(2026, 11, 2, 14, 30, tzinfo=UTC)),
        (datetime(2026, 11, 26, 12, tzinfo=UTC), datetime(2026, 11, 27, 14, 30, tzinfo=UTC)),
    ],
)
def test_calendar_holidays_dst_weekend_and_early_close(at, opening):
    manager, _, _ = runtime()
    schedule = manager.schedule(at)
    assert schedule["market_open_at"] == opening
    assert schedule["exit_due_at"] == opening + timedelta(minutes=10)


def test_custom_exit_minutes_and_out_of_calendar_fail_closed():
    manager, _, _ = runtime()
    custom = PositionService(
        manager.store, manager.execution, clock=manager.clock, postopen_exit_minutes=17
    )
    assert custom.schedule(NOW)["exit_due_at"].minute == 47
    with pytest.raises(ProviderError):
        manager.schedule(datetime(2030, 1, 1, tzinfo=UTC))
    for value in (0, 121, True, 10.5):
        with pytest.raises(ValueError):
            PositionService(
                manager.store, manager.execution, clock=manager.clock, postopen_exit_minutes=value
            )


def test_premature_exit_rejected_without_provider_calls():
    manager, p, time = runtime()
    before = len(manager.execution.provider.calls)
    with pytest.raises(ValueError, match="NOT_SAFE_OR_NOT_DUE"):
        manager.prepare_exit(p.position_id, **exit_inputs(manager, p, time))
    assert len(manager.execution.provider.calls) == before


def test_due_exit_uses_existing_risk_funding_quote_build_simulation_gateway():
    manager, p, time = runtime()
    p, provider = prepare_exit(manager, p, time)
    a = p.exit_intent.execution
    assert p.state == "EXIT_PENDING" and a.risk.status == a.funding.status == "PASS"
    assert a.simulation.status == "PASS" and a.route.fingerprint == a.simulation.fingerprint
    assert {v[0] for v in provider.calls} == {"quote", "build", "simulate"}
    assert a.quote.request.fromTokenAddress == BUY and a.quote.request.toTokenAddress == SELL
    assert a.quote.request.amount == p.remaining_quantity_base_units
    assert a.reason_codes and not a.broadcast and not a.signed
    assert p.remaining_quantity_base_units == "400000" and p.closed_at is None
    count = len(provider.calls)
    assert manager.prepare_exit(p.position_id, **exit_inputs(manager, p, time)) == p
    assert len(provider.calls) == count


def test_bad_exit_risk_blocks_without_quote():
    manager, p, time = runtime()
    time[0] = p.exit_due_at
    inputs = exit_inputs(manager, p, time)
    inputs["evidence"] = mutate(inputs["evidence"], required_evidence_valid=False)
    manager.execution.provider.quote = lambda *_a, **_kw: pytest.fail("Failed risk cannot quote")
    result = manager.prepare_exit(p.position_id, **inputs)
    assert result.state == "EXIT_PENDING" and result.exit_intent.execution is None
    assert (
        manager.execution.store.for_decision(result.exit_intent.decision_id, mode="DEMO").state
        == "BLOCKED"
    )


@pytest.mark.parametrize("amount", ["0", "400001", "-1", "1.2"])
def test_exit_cannot_oversell_or_use_ambiguous_units(amount):
    manager, p, time = runtime()
    time[0] = p.exit_due_at
    inputs = exit_inputs(manager, p, time)
    inputs["quantity_base_units"] = amount
    with pytest.raises(ValueError):
        manager.prepare_exit(p.position_id, **inputs)


def test_partial_exit_and_second_exit_preserve_remaining_exposure_and_idempotency():
    manager, p, time = runtime()
    p, provider = prepare_exit(manager, p, time, amount="200000", execution_mode="RFQ")
    p = settle_exit(manager, p, time, provider)
    assert p.state == "OPEN" and p.remaining_quantity_base_units == "200000"
    assert len(p.applied_exit_executions) == 1
    p = manager.reconcile(p.position_id)
    assert p.remaining_quantity_base_units == "200000" and len(p.applied_exit_executions) == 1
    p, provider = prepare_exit(manager, p, time, amount="200000", execution_mode="RFQ")
    assert p.exit_intent.ordinal == 2
    p = settle_exit(manager, p, time, provider)
    assert p.state == "CLOSED" and p.remaining_quantity_base_units == "0"
    assert len(p.applied_exit_executions) == 2
    assert p.holding_duration_seconds == int((p.exit_due_at - NOW).total_seconds())
    assert manager.reconcile(p.position_id) == p


def test_actual_pnl_inputs_require_asof_cash_reference_and_actual_cost_receipts():
    manager, p, time = runtime()
    p, provider = prepare_exit(manager, p, time, execution_mode="RFQ")
    p = settle_exit(manager, p, time, provider)
    assert p.exit_notional_usd is None and p.net_pnl_usd is None
    valuations = tuple(
        SettlementValuation(
            execution_id=a.execution_id,
            cash_contract=SELL,
            cash_unit_price_usd="1",
            price_observed_at=a.settled_at,
            price_available_at=a.settled_at,
            source="TEST_FIXTURE",
            data_mode="DEMO",
            actual_fees_usd="0.12",
            actual_gas_usd="0",
            cost_source="TEST_FIXTURE",
        )
        for a in (p.entry_execution, *p.applied_exit_executions)
    )
    result = manager.store.save(
        change(p, valuations=valuations, version=p.version + 1), expected_version=p.version
    )
    assert result.exit_notional_usd == Decimal("40")
    assert result.gross_pnl_usd == Decimal("40") - result.entry_notional_usd
    assert result.net_pnl_usd == result.gross_pnl_usd - Decimal("0.24")
    with pytest.raises(ValueError):
        change(
            result,
            valuations=(mutate(valuations[0], price_available_at=NOW + timedelta(seconds=1)),),
        )


@pytest.mark.parametrize("state", ["OPENING", "OPEN", "EXIT_PENDING", "EXITING", "UNKNOWN"])
def test_restart_restores_links_jobs_and_does_not_duplicate_entry_or_exit(tmp_path, state):
    manager, p, time = runtime(
        tmp_path,
        confirmed=state not in {"OPENING", "UNKNOWN"},
        pending="EXECUTION_UNKNOWN" if state == "UNKNOWN" else "EXECUTION_PENDING",
    )
    provider = manager.execution.provider
    if state in {"OPENING", "UNKNOWN"}:
        provider.order_status = lambda _: (
            mutate(filled(p.entry_execution), status="PENDING_VENDOR"),
            time[0],
        )
    elif state == "EXIT_PENDING":
        time[0] = p.exit_due_at
        p = manager.reconcile(p.position_id)
    elif state == "EXITING":
        p, provider = prepare_exit(manager, p, time, execution_mode="RFQ")
        p = settle_exit(manager, p, time, provider, unknown=True)
    assert p.state == state
    job_id, entry_id = p.job.job_id, p.entry_execution.execution_id
    manager = reopen(manager, tmp_path, time, provider)
    assert not manager.recovery_complete
    manager.recover()
    p = manager.store.get(p.position_id, mode="DEMO")
    assert p.state == ("OPENING" if state == "UNKNOWN" else state)
    assert p.job.job_id == job_id and p.entry_execution.execution_id == entry_id
    assert manager.store.count(mode="DEMO") == 1
    assert manager.create(entry_id, instrument()).position_id == p.position_id
    if state == "EXITING":
        with pytest.raises(ValueError):
            manager.prepare_exit(p.position_id, **exit_inputs(manager, p, time))


def test_scheduler_interruption_lease_is_durable_and_reclaimed_once(tmp_path):
    manager, p, time = runtime(tmp_path)
    p = manager._save(
        p,
        job=change(
            p.job, status="RUNNING", lease_id=uuid4(), lease_until=time[0] + timedelta(seconds=30)
        ),
    )
    manager = reopen(manager, tmp_path, time)
    assert manager.recover() == []
    assert manager.store.get(p.position_id, mode="DEMO").job.status == "RUNNING"
    time[0] += timedelta(seconds=31)
    result = manager.tick()
    assert len(result) == 1 and result[0].job.status == "WAITING"
    assert manager.tick() == []
    assert result[0].job.job_id == p.job.job_id


def test_unknown_provider_monitor_has_bounded_retries_and_no_order_retry(tmp_path):
    manager, p, time = runtime(tmp_path, confirmed=False)
    manager = reopen(manager, tmp_path, time)
    for i in range(3):
        time[0] = NOW + timedelta(seconds=i * 60)
        manager.recover() if i == 0 else manager.tick()
    p = manager.store.get(p.position_id, mode="DEMO")
    assert p.state == "UNKNOWN" and p.job.attempts == 3 and p.job.status == "BLOCKED"
    time[0] += timedelta(hours=1)
    assert manager.tick() == [] and manager.has_unresolved()


def test_monitor_crash_after_execution_poll_recovers_without_second_order(tmp_path, monkeypatch):
    manager, p, time = runtime(tmp_path, confirmed=False)
    provider = manager.execution.provider
    provider.order_status = lambda _: (filled(p.entry_execution), time[0])
    original = manager._save

    def crash(old, **updates):
        if updates.get("state") == "OPEN":
            raise SystemExit("simulated crash after persisted terminal poll")
        return original(old, **updates)

    monkeypatch.setattr(manager, "_save", crash)
    with pytest.raises(SystemExit):
        manager.tick()
    assert (
        manager.execution.store.get(p.entry_execution.execution_id, mode="DEMO").state
        == "EXECUTION_CONFIRMED"
    )
    manager = reopen(manager, tmp_path, time, provider)
    time[0] += timedelta(seconds=31)
    manager.recover()
    result = manager.store.get(p.position_id, mode="DEMO")
    assert result.state == "OPEN" and result.filled_quantity_base_units == "400000"
    assert manager.store.count(mode="DEMO") == 1
