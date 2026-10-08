"""Wallet corroboration of existing execution attempts; never creates an order or position."""

from app.clients.baw_cli import human_base_units
from app.models.execution import ExecutionAttempt
from app.models.wallet import WalletReconciliation
from app.services.execution_state_machine import EXTERNAL, TERMINAL, ExecutionStateMachine


class WalletReconciler:
    def __init__(self, adapter, store, *, execution_tracker=None):
        self.adapter, self.store, self.execution_tracker = adapter, store, execution_tracker

    def reconcile(self, attempt, *, now, wallet_order_id=None):
        current = self.store.get(attempt.execution_id, mode=attempt.data_mode)
        if current.version != attempt.version:
            raise ValueError("STALE_RECONCILIATION_ATTEMPT")
        if current.state in TERMINAL:
            return self._result(
                current, now, "NOT_VERIFIED", "UNKNOWN", ("EXISTING_TERMINAL_RECORD",)
            )
        if current.state not in EXTERNAL or not current.external_tracking_only:
            raise ValueError("EXISTING_EXTERNAL_EXECUTION_REQUIRED")
        snapshot = self.adapter.snapshot()
        now = max(now, self.adapter.clock())
        reasons = []
        wallet_state = "UNKNOWN"
        if (
            snapshot.capability_status not in {"VERIFIED_READ", "FIXTURE_VERIFIED"}
            or snapshot.connection != "CONNECTED"
            or snapshot.data_mode != current.data_mode
            or not 0 <= (now - snapshot.received_at).total_seconds() <= 120
            or "56" not in snapshot.supported_chains
            or current.quote is None
            or snapshot.bsc_address != current.quote.request.userWalletAddress
            or snapshot.settings is None
            or min(snapshot.settings.session_expires_at, snapshot.settings.inactive_signout_at)
            <= now
        ):
            reasons.append("WALLET_RECONCILIATION_UNAVAILABLE")
        else:
            if wallet_order_id is not None:
                result = self.adapter.read_records("orders", order_id=wallet_order_id)
                if (
                    result.capability_status in {"VERIFIED_READ", "FIXTURE_VERIFIED"}
                    and len(result.orders) == 1
                ):
                    order = result.orders[0]
                    q = current.quote
                    try:
                        amount = human_base_units(
                            order.sell_quantity, int(q.route.fromToken.decimal)
                        )
                    except ValueError:
                        amount = None
                    if (
                        order.sell_token == q.request.fromTokenAddress
                        and order.buy_token == q.request.toTokenAddress
                        and amount == q.request.amount
                        and (
                            current.tx_hash is None
                            or current.tx_hash.lower() == (order.tx_hash or "").lower()
                        )
                    ):
                        wallet_state = order.status
                    else:
                        reasons.append("WALLET_ORDER_BINDING_UNVERIFIED")
                else:
                    reasons.append("WALLET_ORDER_UNKNOWN_NO_NEW_ORDER")
            if current.tx_hash:
                result = self.adapter.read_records("history", tx_hash=current.tx_hash)
                if (
                    result.capability_status not in {"VERIFIED_READ", "FIXTURE_VERIFIED"}
                    or len(result.transactions) != 1
                    or result.transactions[0].status == "UNKNOWN"
                ):
                    reasons.append("WALLET_HISTORY_UNKNOWN_NO_NEW_ORDER")
                elif wallet_state == "FINISHED" and result.transactions[0].status != "confirmed":
                    reasons.append("WALLET_TERMINAL_EVIDENCE_CONFLICT")
                elif wallet_state == "FAILED" and result.transactions[0].status != "failed":
                    reasons.append("WALLET_TERMINAL_EVIDENCE_CONFLICT")
            if wallet_state in {"PENDING", "UNKNOWN"} and wallet_order_id is not None:
                reasons.append("WALLET_ORDER_NOT_TERMINAL_SUCCESS")
        if not reasons and self.execution_tracker is not None:
            # Only Phase 8's exact settlement tracker confirms execution.
            expected = {"FINISHED": "SUCCESS", "FAILED": "FAILED"}.get(wallet_state)
            current = self.execution_tracker.reconcile(
                current, now=max(now, self.adapter.clock()), expected_terminal=expected
            )
            reasons.append("PHASE8_EXACT_SETTLEMENT_RECONCILIATION")
        else:
            reasons.append("EXACT_SETTLEMENT_UNVERIFIED_NO_NEW_ORDER")
            if current.state != "EXECUTION_UNKNOWN":
                updated = ExecutionStateMachine().transition(
                    current, "EXECUTION_UNKNOWN", now=now, reason_codes=tuple(reasons)
                )
            else:
                updated = ExecutionAttempt.model_validate(
                    {
                        **current.model_dump(),
                        "version": current.version + 1,
                        "updated_at": now,
                        "reason_codes": tuple(reasons),
                    }
                )
            self.store.save(updated, expected_version=current.version)
            current = updated
        return self._result(current, now, snapshot.capability_status, wallet_state, tuple(reasons))

    @staticmethod
    def _result(attempt, now, capability, state, reasons):
        return WalletReconciliation(
            execution_id=attempt.execution_id,
            request_id=attempt.request_id,
            decision_id=attempt.decision_id,
            data_mode=attempt.data_mode,
            evaluated_at=now,
            wallet_capability=capability,
            wallet_order_state=state,
            execution_state=attempt.state,
            reasons=reasons,
        )

    def recover(self, *, mode, now):
        pending = self.store.pending(mode=mode)
        if len(pending) > 10:
            raise ValueError("BOUNDED_MANUAL_RECONCILIATION_REQUIRED")
        return tuple(self.reconcile(attempt, now=now) for attempt in pending)
