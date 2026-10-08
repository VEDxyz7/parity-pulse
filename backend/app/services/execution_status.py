"""Bounded read-only reconciliation. No timeout can create or retry an order."""

import time
from datetime import UTC, datetime

from app.clients.common import ProviderError
from app.models.execution import ExecutionAttempt, RFQStatus, SettlementEvidence, SwapStatus
from app.services.execution_confirmation import settlement_identity, settlement_values
from app.services.execution_state_machine import TERMINAL, ExecutionStateMachine


class ExecutionStatusTracker:
    def __init__(self, provider, store, *, sleep=time.sleep):
        self.provider, self.store, self.sleep = provider, store, sleep
        self.machine = ExecutionStateMachine()

    def reconcile(self, attempt, *, now, expected_terminal=None, corroborated_tx_hash=None):
        if expected_terminal not in {None, "SUCCESS", "FAILED"}:
            raise ValueError("Invalid independent terminal corroboration")
        attempt = ExecutionAttempt.model_validate_json(attempt.model_dump_json())
        if attempt.state in TERMINAL:
            return attempt
        if not attempt.external_tracking_only or attempt.quote is None or attempt.route is None:
            raise ValueError("EXISTING_EXTERNAL_ATTEMPT_REQUIRED")
        q = attempt.quote
        if (q.source == "TEST_FIXTURE") != (getattr(self.provider, "fixture_only", False) is True):
            raise ValueError("STATUS_PROVIDER_MODE_MISMATCH")
        target = "EXECUTION_UNKNOWN"
        fields = {}
        observed_conflict = None
        try:
            if q.route.executionMode == "RFQ":
                if attempt.order_id is None:
                    raise ValueError("Platform order ID required")
                status, received = self.provider.order_status(attempt.order_id)
                if status.orderId != attempt.order_id:
                    raise ValueError("Order binding mismatch")
                fields = {"external_status": status.status}
                target = {
                    "PENDING_VENDOR": "EXECUTION_PENDING",
                    "PENDING_ONCHAIN": "EXECUTION_PENDING",
                    "FAILED": "EXECUTION_FAILED",
                    "EXPIRED": "EXECUTION_EXPIRED",
                    "CANCELLED": "EXECUTION_CANCELLED",
                }.get(status.status, "EXECUTION_UNKNOWN")
                status = RFQStatus.model_validate_json(status.model_dump_json())
                expected_hash = attempt.tx_hash or corroborated_tx_hash
                if (
                    status.txHash
                    and expected_hash
                    and status.txHash.lower() != expected_hash.lower()
                ):
                    observed_conflict = status.txHash
                    raise ValueError("Known transaction hash conflict")
                if status.status == "FILLED":
                    evidence = SettlementEvidence(
                        identity=settlement_identity(attempt),
                        received_at=received,
                        corroborated_tx_hash=corroborated_tx_hash,
                        rfq=status,
                    )
                    fields.update(
                        settlement_values(attempt, evidence), settlement_evidence=evidence
                    )
                    target = "EXECUTION_CONFIRMED"
            else:
                if attempt.tx_hash is None:
                    raise ValueError("Transaction hash required")
                status, received = self.provider.swap_status(attempt.tx_hash)
                if status is not None:
                    status = SwapStatus.model_validate_json(status.model_dump_json())
                    if status.txHash.lower() != attempt.tx_hash.lower():
                        observed_conflict = status.txHash
                        raise ValueError("Transaction identity mismatch")
                    fields = {"external_status": status.status}
                    if status.status == "failed":
                        target = "EXECUTION_FAILED"
                    elif status.status == "success":
                        evidence = SettlementEvidence(
                            identity=settlement_identity(attempt),
                            received_at=received,
                            corroborated_tx_hash=corroborated_tx_hash,
                            swap=status,
                        )
                        fields.update(
                            settlement_values(attempt, evidence), settlement_evidence=evidence
                        )
                        target = "EXECUTION_CONFIRMED"
            if not 0 <= (received - now).total_seconds() <= 30:
                raise ValueError("Invalid receipt time")
        except (ProviderError, ValueError, TypeError, KeyError):
            target = "EXECUTION_UNKNOWN"
            fields = {"reason_codes": ("STATUS_UNRESOLVED_NO_NEW_ORDER",)}
            if observed_conflict is not None:
                conflicts = tuple(
                    dict.fromkeys((*attempt.conflicting_tx_hashes, observed_conflict))
                )
                fields = {
                    "reason_codes": ("CONTRADICTORY_TRANSACTION_HASH_RECONCILIATION_REQUIRED",),
                    "conflicting_tx_hashes": conflicts[:10],
                    "last_conflicting_tx_hash": observed_conflict,
                    "settlement_conflict": True,
                }
                if attempt.tx_hash is None and corroborated_tx_hash is not None:
                    fields["tx_hash"] = corroborated_tx_hash
        if (
            expected_terminal is not None
            and target in TERMINAL
            and target
            != ("EXECUTION_CONFIRMED" if expected_terminal == "SUCCESS" else "EXECUTION_FAILED")
        ):
            target = "EXECUTION_UNKNOWN"
            fields = {
                "reason_codes": ("CONFLICTING_EXTERNAL_TERMINAL_EVIDENCE",),
                "settlement_conflict": True,
            }
        if target in TERMINAL and (
            attempt.settlement_conflict
            or attempt.conflicting_tx_hashes
            or attempt.last_conflicting_tx_hash
        ):
            target = "EXECUTION_UNKNOWN"
            fields = {"reason_codes": ("CONTRADICTORY_SETTLEMENT_RECONCILIATION_REQUIRED",)}
        if target == attempt.state:
            # Repeated pending/unknown reads remain recorded, not illegal duplicate transitions.
            result = ExecutionAttempt.model_validate(
                {
                    **attempt.model_dump(),
                    **fields,
                    "version": attempt.version + 1,
                    "updated_at": now,
                }
            )
        else:
            result = self.machine.transition(attempt, target, now=now, **fields)
        self.store.save(result, expected_version=attempt.version)
        return result

    def poll(self, attempt, *, max_polls=3, spacing_seconds=1, clock=lambda: datetime.now(UTC)):
        if type(max_polls) is not int or not 1 <= max_polls <= 10 or not 0 <= spacing_seconds <= 5:
            raise ValueError("Bounded polling required")
        for i in range(max_polls):
            attempt = self.reconcile(attempt, now=clock())
            if attempt.state in TERMINAL:
                break
            if i + 1 < max_polls:
                self.sleep(spacing_seconds)
        return attempt

    def recover(self, *, mode, now):
        # No new preparation while imported pending attempts remain unresolved.
        return [self.reconcile(a, now=now) for a in self.store.pending(mode=mode)]
