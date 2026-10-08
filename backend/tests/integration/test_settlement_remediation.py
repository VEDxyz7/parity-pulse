"""Regression probes across reconciliation, state, model and durable journal boundaries."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.execution import ExecutionAttempt, RFQStatus, SettlementEvidence
from app.repositories.execution import ExecutionStore
from app.services.execution_confirmation import settlement_identity
from app.services.execution_state_machine import ExecutionStateMachine
from app.services.execution_status import ExecutionStatusTracker
from app.services.wallet_reconciliation import WalletReconciler
from backend.tests.fixtures.execution_fixtures import NOW, TXHASH, mutate
from backend.tests.fixtures.wallet_fixtures import WalletWire
from backend.tests.unit.test_agentic_wallet import adapter, prepared

OTHER_HASH = "0x" + "6" * 64


def existing(*, known=TXHASH, state="EXECUTION_PENDING"):
    service, a = prepared(execution_mode="RFQ")
    a = mutate(
        a,
        external_tracking_only=True,
        state=state,
        order_id="platform-order",
        tx_hash=known,
        version=0,
    )
    store = ExecutionStore()
    store.save(a)
    return service.provider, store, a


def filled(a, **changes):
    return RFQStatus.model_validate(
        {
            "orderId": a.order_id,
            "status": "FILLED",
            "txHash": TXHASH,
            "fromAmount": a.quote.request.amount,
            "toAmount": a.quote.route.toTokenAmount,
            "createdAt": int(NOW.timestamp() * 1000),
            "filledAt": int(NOW.timestamp() * 1000),
            **changes,
        }
    )


def observe(p, store, a, record, **kwargs):
    p.order_status = lambda _: (record, NOW)
    return ExecutionStatusTracker(p, store).reconcile(a, now=NOW, **kwargs)


def test_known_hash_complete_success_confirms_and_journal_retains_bound_proof():
    p, store, a = existing()
    result = observe(p, store, a, filled(a))
    assert result.state == "EXECUTION_CONFIRMED" and result.tx_hash == TXHASH
    assert result.settlement_evidence.identity == settlement_identity(a)
    assert result.filled_quantity_base_units == a.quote.route.toTokenAmount
    assert store.get(a.execution_id, mode="DEMO") == result
    assert not result.broadcast and not result.funds_moved
    # Terminal evidence is monotonic: no further reads or rewritten journal entries.
    p.order_status = lambda _: pytest.fail("terminal attempt must not be reinterpreted")
    assert ExecutionStatusTracker(p, store).reconcile(result, now=NOW) == result
    with pytest.raises(ValueError):
        store.save(mutate(result, version=result.version + 1))
    store.close()


@pytest.mark.parametrize("status", ["FILLED", "PENDING_ONCHAIN", "FAILED"])
def test_different_hash_never_replaces_known_identity_even_on_non_success(status):
    p, store, a = existing()
    result = observe(p, store, a, filled(a, txHash=OTHER_HASH, status=status))
    assert result.state == "EXECUTION_UNKNOWN" and result.tx_hash == TXHASH
    assert result.conflicting_tx_hashes == (OTHER_HASH,)
    assert result.request_id == a.request_id and result.order_id == a.order_id
    again = observe(p, store, result, filled(a))
    assert again.state == "EXECUTION_UNKNOWN" and again.tx_hash == TXHASH
    assert again.conflicting_tx_hashes == (OTHER_HASH,)
    store.close()


def test_wallet_hash_corroboration_cannot_be_rebound_to_another_tracker_hash():
    p, store, a = existing(known=None)
    p.order_status = lambda _: (filled(a, txHash=OTHER_HASH), NOW)
    w = WalletWire()
    result = WalletReconciler(
        adapter(w), store, execution_tracker=ExecutionStatusTracker(p, store)
    ).reconcile(a, now=NOW, wallet_order_id="wallet-order")
    saved = store.get(a.execution_id, mode="DEMO")
    assert result.execution_state == "EXECUTION_UNKNOWN"
    assert saved.tx_hash == TXHASH and saved.conflicting_tx_hashes == (OTHER_HASH,)
    assert not result.new_order_created
    store.close()


def test_wallet_order_hash_conflict_is_preserved_without_reaching_tracker():
    p, store, a = existing()
    p.order_status = lambda _: pytest.fail("contradictory wallet evidence must stop reconciliation")
    w = WalletWire()
    w.values["orders"]["list"][0]["txHash"] = OTHER_HASH
    result = WalletReconciler(
        adapter(w), store, execution_tracker=ExecutionStatusTracker(p, store)
    ).reconcile(a, now=NOW, wallet_order_id="wallet-order")
    saved = store.get(a.execution_id, mode="DEMO")
    assert result.execution_state == "EXECUTION_UNKNOWN"
    assert saved.tx_hash == TXHASH and saved.conflicting_tx_hashes == (OTHER_HASH,)
    store.close()


def test_terminal_corroboration_conflict_survives_later_standalone_tracker_success():
    p, store, a = existing()
    conflict = observe(p, store, a, filled(a), expected_terminal="FAILED")
    assert conflict.state == "EXECUTION_UNKNOWN" and conflict.settlement_conflict
    later = observe(p, store, conflict, filled(a))
    assert later.state == "EXECUTION_UNKNOWN" and later.settlement_conflict
    for target in ("EXECUTION_CONFIRMED", "EXECUTION_FAILED"):
        with pytest.raises(ValueError):
            ExecutionStateMachine().transition(
                later,
                target,
                now=NOW,
                external_status="FILLED" if target == "EXECUTION_CONFIRMED" else "FAILED",
                settlement_conflict=False,
            )
    with pytest.raises(ValueError):
        store.save(
            mutate(later, settlement_conflict=False, version=later.version + 1),
            expected_version=later.version,
        )
    store.close()


def test_conflicting_hash_beyond_bounded_list_is_still_retained_in_journal():
    p, store, a = existing()
    hashes = tuple("0x" + format(n, "064x") for n in range(10, 22))
    for h in hashes:
        a = observe(p, store, a, filled(a, txHash=h))
        assert a.state == "EXECUTION_UNKNOWN" and a.tx_hash == TXHASH
        assert a.last_conflicting_tx_hash == h
    assert a.conflicting_tx_hashes == hashes[:10]
    assert store.get(a.execution_id, mode="DEMO") == a
    with store.engine.connect() as db:
        payloads = (
            db.execute(select(store.events.c.payload).order_by(store.events.c.version))
            .scalars()
            .all()
        )
    assert len(payloads) == len(hashes) + 1
    assert (
        tuple(
            ExecutionAttempt.model_validate_json(p).last_conflicting_tx_hash for p in payloads[1:]
        )
        == hashes
    )
    store.close()


@pytest.mark.parametrize("state", ["EXECUTION_PENDING", "EXECUTION_SUBMITTED", "EXECUTION_UNKNOWN"])
def test_direct_confirmation_without_proof_rejected_at_all_boundaries(state):
    _, store, a = existing(state=state)
    fields = dict(
        external_status="FILLED",
        tx_hash=TXHASH,
        settled_at=NOW,
        filled_quantity_base_units="400000",
    )
    with pytest.raises(ValueError):
        ExecutionStateMachine().transition(a, "EXECUTION_CONFIRMED", now=NOW, **fields)
    with pytest.raises(ValueError):
        mutate(a, state="EXECUTION_CONFIRMED", **fields)
    # Even a host that bypasses Pydantic construction cannot write this journal entry.
    forged = a.model_copy(update={"state": "EXECUTION_CONFIRMED", **fields})
    with pytest.raises(ValueError):
        store.save(forged, expected_version=a.version)
    assert store.get(a.execution_id, mode="DEMO").state == state
    store.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("execution_id", uuid4()),
        ("request_id", uuid4()),
        ("decision_id", "different"),
        ("quote_id", "other-quote"),
        ("vendor", "OtherVendor"),
        ("wallet", "0x" + "7" * 40),
        ("execution_mode", "SWAP"),
        ("order_id", "other-order"),
        ("route_fingerprint", "f" * 64),
    ],
)
def test_complete_terminal_evidence_with_wrong_identity_never_confirms(field, value):
    _, store, a = existing()
    identity = settlement_identity(a).model_copy(update={field: value})
    evidence = SettlementEvidence.model_construct(
        identity=identity, received_at=NOW, corroborated_tx_hash=None, rfq=filled(a), swap=None
    )
    with pytest.raises(ValueError):
        ExecutionStateMachine().transition(
            a,
            "EXECUTION_CONFIRMED",
            now=NOW,
            external_status="FILLED",
            settled_at=NOW,
            filled_quantity_base_units="400000",
            settlement_evidence=evidence,
        )
    store.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"orderId": "other-order"},
        {"toAmount": None},
        {"filledAt": None},
        {"fromAmount": "1"},
        {"toAmount": "1"},
        {"txHash": None},
        {"filledAt": int((NOW + timedelta(seconds=1)).timestamp() * 1000)},
        {
            "createdAt": int((NOW - timedelta(days=2)).timestamp() * 1000),
            "filledAt": int((NOW - timedelta(days=2)).timestamp() * 1000),
        },
    ],
)
def test_missing_mismatched_or_future_settlement_fails_closed(changes):
    p, store, a = existing()
    result = observe(p, store, a, filled(a, **changes))
    assert result.state == "EXECUTION_UNKNOWN" and result.tx_hash == TXHASH
    store.close()


@pytest.mark.parametrize("field", ["order_id", "quote", "route", "external_tracking_only"])
def test_existing_external_bindings_cannot_change_through_state_or_store(field):
    _, store, a = existing()
    if field == "order_id":
        value = "another-order"
    elif field == "external_tracking_only":
        value = False
    elif field == "quote":
        value = mutate(
            a.quote, route=mutate(a.quote.route, vendorName="OtherVendor", quoteId="other")
        )
    else:
        value = mutate(a.route, prepared_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError):
        ExecutionStateMachine().transition(a, "EXECUTION_UNKNOWN", now=NOW, **{field: value})
    with pytest.raises(ValueError):
        store.save(
            a.model_copy(update={field: value, "version": a.version + 1}),
            expected_version=a.version,
        )
    store.close()


def test_conflict_evidence_cannot_be_erased_and_known_hash_cannot_be_cleared():
    _, store, a = existing()
    for update in ({"tx_hash": None}, {"tx_hash": OTHER_HASH}):
        with pytest.raises(ValueError):
            ExecutionStateMachine().transition(a, "EXECUTION_UNKNOWN", now=NOW, **update)
        with pytest.raises(ValueError):
            store.save(a.model_copy(update={**update, "version": 1}), expected_version=0)
    conflicting = mutate(a, conflicting_tx_hashes=(OTHER_HASH,), version=1)
    store.save(conflicting, expected_version=0)
    with pytest.raises(ValueError):
        ExecutionStateMachine().transition(
            conflicting, "EXECUTION_UNKNOWN", now=NOW, conflicting_tx_hashes=()
        )
    with pytest.raises(ValueError):
        store.save(mutate(conflicting, conflicting_tx_hashes=(), version=2), expected_version=1)
    assert ExecutionAttempt.model_validate_json(conflicting.model_dump_json()) == conflicting
    store.close()
