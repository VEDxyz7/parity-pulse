"""Evidence-driven lifecycle and leased, bounded monitoring. Never submits an order."""

import hashlib
import logging
import threading
from datetime import timedelta
from decimal import localcontext
from uuid import uuid4

from app.clients.common import ProviderError
from app.models.execution import ExecutionRiskEvidence, FundingState
from app.models.position import ExitIntent, Position, PositionInstrument, PositionJob, quantity
from app.services.calendar import USEquityCalendar
from app.services.execution_status import ExecutionStatusTracker

logger = logging.getLogger("parity.positions")
FINAL = {"CLOSED", "FAILED", "RECONCILIATION_REQUIRED"}
UNRESOLVED = {"OPENING", "EXITING", "UNKNOWN", "RECONCILIATION_REQUIRED"}
PENDING = {"EXECUTION_SUBMITTED", "EXECUTION_PENDING", "EXECUTION_UNKNOWN"}
FAILURES = {"EXECUTION_FAILED", "EXECUTION_EXPIRED", "EXECUTION_CANCELLED"}


def change(model, **updates):
    return type(model).model_validate(
        {
            **model.model_dump(exclude_computed_fields=True),
            **updates,
        }
    )


class PositionService:
    """Host-only evidence ingestion/preparation; public position APIs are read-only.

    A fresh host-supplied risk/funding/allowance bundle is mandatory for exit preparation.
    The scheduler only reconciles existing identifiers and records due exit intents.
    """

    def __init__(self, store, execution, *, clock, postopen_exit_minutes=10, calendar=None):
        if type(postopen_exit_minutes) is not int or not 1 <= postopen_exit_minutes <= 120:
            raise ValueError("Bounded post-open exit minutes required")
        self.store, self.execution, self.clock = store, execution, clock
        self.mode = execution.controls.data_mode
        self.calendar = calendar or USEquityCalendar()
        self.minutes = postopen_exit_minutes
        self.lock = threading.RLock()
        self.recovery_complete = False

    def has_unresolved(self, decision_id=None):
        if not self.recovery_complete or self.store.count(mode=self.mode, active=True) > 1000:
            return True
        try:
            positions = self.store.list(mode=self.mode, limit=1000, active=True)
            for p in positions:
                self.store._validate_journal(p)
            return any(
                p.state in UNRESOLVED
                or p.job.status == "RUNNING"
                or (
                    p.exit_intent is not None
                    and p.exit_intent.execution is None
                    and p.exit_intent.decision_id != decision_id
                )
                for p in positions
            )
        except (ValueError, LookupError):
            return True

    def _save(self, old, **updates):
        if updates.get("state") in FINAL:
            updates["job"] = change(old.job, status="FINISHED", lease_id=None, lease_until=None)
        result = self.store.save(
            change(old, version=old.version + 1, updated_at=self.clock(), **updates),
            expected_version=old.version,
        )
        logger.info(
            "POSITION_LIFECYCLE",
            extra={
                "event_fields": {
                    "position_id": str(result.position_id),
                    "execution_id": str(result.entry_execution.execution_id),
                    "state": result.state,
                    "data_mode": result.data_mode,
                }
            },
        )
        return result

    def schedule(self, at, *, minutes=None):
        day = at.astimezone(self.calendar.zone).date()
        for offset in range(15):
            session = self.calendar.session(day + timedelta(days=offset))
            if session and session[0] >= at:
                due = session[0] + timedelta(minutes=self.minutes if minutes is None else minutes)
                if due >= session[1]:
                    raise ValueError("Exit window lies outside the verified regular session")
                return dict(
                    market_open_at=session[0],
                    exit_due_at=due,
                    calendar_version=self.calendar.data["version"],
                )
        raise ValueError("Next regular opening unavailable")

    def create(self, execution_id, instrument):
        with self.lock:
            instrument = PositionInstrument.model_validate_json(instrument.model_dump_json())
            old = self.store.for_execution(execution_id, mode=self.mode)
            if old:
                if old.instrument != instrument:
                    raise ValueError(
                        "Existing position has different representation/as-of metadata"
                    )
                return old
            a = self.execution.store.get(execution_id, mode=self.mode)
            now = self.clock()
            fields = self._entry_fields(None, a)
            p = Position(
                position_id=uuid4(),
                data_mode=self.mode,
                instrument=instrument,
                state=fields.pop("state", "PROPOSED"),
                version=0,
                requested_quantity_base_units=a.quote.route.toTokenAmount if a.quote else "0",
                postopen_exit_minutes=self.minutes,
                created_at=now,
                updated_at=now,
                job=PositionJob(job_id=uuid4(), next_check_at=now),
                **fields,
            )
            try:
                return self.store.save(p)
            except ValueError:
                winner = self.store.for_execution(execution_id, mode=self.mode)
                if winner and winner.instrument == instrument:
                    return winner
                raise

    def _entry_fields(self, p, a):
        fields = dict(entry_execution=a)
        if a.settlement_conflict or a.conflicting_tx_hashes or a.last_conflicting_tx_hash:
            return {
                **fields,
                "state": "RECONCILIATION_REQUIRED",
                "reasons": ("CONTRADICTORY_SETTLEMENT_IDENTITY",),
            }
        if a.state == "EXECUTION_CONFIRMED":
            fields.update(
                entry_at=a.settled_at,
                filled_quantity_base_units=a.filled_quantity_base_units,
                remaining_quantity_base_units=a.filled_quantity_base_units,
                state="OPEN",
                reasons=(),
            )
            try:
                fields.update(
                    self.schedule(
                        a.settled_at, minutes=p.postopen_exit_minutes if p else self.minutes
                    )
                )
            except (ValueError, ProviderError):
                fields.update(
                    state="RECONCILIATION_REQUIRED", reasons=("EXIT_CALENDAR_UNAVAILABLE",)
                )
        elif a.state in FAILURES:
            fields.update(state="FAILED", reasons=("ENTRY_TERMINAL_FAILURE",))
        elif a.state == "EXECUTION_UNKNOWN":
            fields.update(state="UNKNOWN", reasons=("ENTRY_STATUS_UNRESOLVED",))
        elif a.state in PENDING:
            fields.update(state="OPENING", reasons=())
        return fields

    def _observe(self, snapshot, now):
        a = self.execution.store.get(snapshot.execution_id, mode=self.mode)
        if a.state in PENDING and a.external_tracking_only and self.execution.provider is not None:
            a = ExecutionStatusTracker(self.execution.provider, self.execution.store).reconcile(
                a, now=now
            )
        return a

    def _calendar_matches(self, p):
        if not p.market_open_at or not p.exit_due_at:
            return False
        try:
            session = self.calendar.session(p.market_open_at.astimezone(self.calendar.zone).date())
            return (
                session is not None
                and session[0] == p.market_open_at
                and p.calendar_version == self.calendar.data["version"]
                and p.exit_due_at == p.market_open_at + timedelta(minutes=p.postopen_exit_minutes)
                and p.exit_due_at < session[1]
            )
        except ProviderError:
            return False

    def _exit_window_open(self, p, now):
        if not self._calendar_matches(p):
            return False
        session = self.calendar.session(p.market_open_at.astimezone(self.calendar.zone).date())
        return p.exit_due_at <= now < session[1]

    def _reconcile(self, p, now):
        if p.state in FINAL:
            return p
        a = self._observe(p.entry_execution, now)
        if p.entry_at is None:
            fields = self._entry_fields(p, a)
            if fields.get("state", p.state) == "OPENING" and self.execution.provider is None:
                fields.update(state="UNKNOWN", reasons=("STATUS_PROVIDER_UNAVAILABLE",))
            p = self._save(p, **fields)
        elif a != p.entry_execution:
            return self._save(
                p, state="RECONCILIATION_REQUIRED", reasons=("CONFIRMED_ENTRY_JOURNAL_CONFLICT",)
            )
        if p.state in FINAL or p.entry_at is None:
            return p
        if not self._calendar_matches(p):
            return self._save(
                p, state="RECONCILIATION_REQUIRED", reasons=("PERSISTED_EXIT_CALENDAR_MISMATCH",)
            )
        intent = p.exit_intent
        if intent:
            exit_a = intent.execution or self.execution.store.for_decision(
                intent.decision_id, mode=self.mode
            )
            if exit_a:
                # A blocked preparation with no route is preserved as a reason, never a fill.
                if exit_a.quote is None or exit_a.route is None:
                    return self._save(
                        p, state="EXIT_PENDING", reasons=("EXIT_PREPARATION_BLOCKED",)
                    )
                exit_a = self._observe(exit_a, now)
                p.validate_exit(exit_a)
                intent = change(intent, execution=exit_a)
                if (
                    exit_a.settlement_conflict
                    or exit_a.conflicting_tx_hashes
                    or exit_a.last_conflicting_tx_hash
                ):
                    return self._save(
                        p,
                        exit_intent=intent,
                        state="RECONCILIATION_REQUIRED",
                        reasons=("EXIT_SETTLEMENT_IDENTITY_CONFLICT",),
                    )
                if exit_a.state == "EXECUTION_CONFIRMED":
                    if exit_a.execution_id not in {
                        e.execution_id for e in p.applied_exit_executions
                    }:
                        remaining = int(p.remaining_quantity_base_units) - int(
                            exit_a.quote.request.amount
                        )
                        if remaining < 0:
                            return self._save(
                                p,
                                state="RECONCILIATION_REQUIRED",
                                reasons=("CONFIRMED_EXIT_EXCEEDS_HOLDING",),
                            )
                        return self._save(
                            p,
                            state="CLOSED" if remaining == 0 else "OPEN",
                            exit_intent=intent,
                            remaining_quantity_base_units=str(remaining),
                            applied_exit_executions=(*p.applied_exit_executions, exit_a),
                            closed_at=exit_a.settled_at if remaining == 0 else None,
                            reasons=() if remaining == 0 else ("PARTIAL_EXIT_EXPOSURE_REMAINS",),
                        )
                elif exit_a.state == "EXECUTION_UNKNOWN" or exit_a.state in FAILURES:
                    return self._save(
                        p,
                        exit_intent=intent,
                        state="UNKNOWN",
                        reasons=("EXIT_UNRESOLVED_NO_NEW_ORDER",),
                    )
                elif exit_a.state in PENDING:
                    return self._save(
                        p,
                        exit_intent=intent,
                        state="EXITING" if self.execution.provider else "UNKNOWN",
                        reasons=() if self.execution.provider else ("STATUS_PROVIDER_UNAVAILABLE",),
                    )
                else:
                    return self._save(
                        p,
                        exit_intent=intent,
                        state="EXIT_PENDING",
                        reasons=("DRY_RUN_EXIT_NOT_EXECUTED",),
                    )
        if p.state in {"OPEN", "UNKNOWN"} and now >= p.exit_due_at:
            return self._save(p, state="EXIT_PENDING", reasons=("DETERMINISTIC_EXIT_DUE",))
        return p

    def tick(self, *, limit=100, recovery=False):
        """One bounded pass; one status read per pending leg; no sleep or order retry."""
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Bounded monitoring required")
        results = []
        for p in self.store.list(mode=self.mode, limit=limit, active=True):
            now = self.clock()
            if p.state in FINAL or (
                p.job.status == "BLOCKED" and (not recovery or p.job.attempts >= 3)
            ):
                continue
            if p.job.status == "RUNNING" and now < p.job.lease_until:
                continue
            if not recovery and now < p.job.next_check_at:
                continue
            lease = change(
                p.job, status="RUNNING", lease_id=uuid4(), lease_until=now + timedelta(seconds=30)
            )
            try:
                p = self._save(p, job=lease)
            except ValueError:
                continue  # Another worker won the persisted CAS lease.
            try:
                p = self._reconcile(p, now)
            except (ValueError, LookupError, ProviderError, TypeError):
                p = self.store.get(p.position_id, mode=self.mode)
                p = self._save(
                    p,
                    state="RECONCILIATION_REQUIRED",
                    reasons=("POSITION_EVIDENCE_RECONCILIATION_REQUIRED",),
                )
            attempts = min(3, p.job.attempts + 1) if p.state in UNRESOLVED else 0
            if attempts >= 3 and p.state in {"OPENING", "EXITING"}:
                p = self._save(
                    p, state="UNKNOWN", reasons=("STATUS_RETRY_LIMIT_REACHED_NO_NEW_ORDER",)
                )
            blocked = attempts >= 3 or p.state == "EXIT_PENDING"
            status = "FINISHED" if p.state in FINAL else "BLOCKED" if blocked else "WAITING"
            next_at = now + timedelta(seconds=60)
            if p.state == "OPEN" and p.exit_due_at:
                next_at = p.exit_due_at
            p = self._save(
                p,
                job=change(
                    p.job,
                    status=status,
                    attempts=attempts,
                    next_check_at=next_at,
                    lease_id=None,
                    lease_until=None,
                ),
            )
            results.append(p)
        return results

    def recover(self, *, limit=100):
        result = self.tick(limit=limit, recovery=True)
        self.recovery_complete = self.store.count(mode=self.mode, active=True) <= limit
        return result

    def reconcile(self, position_id):
        # Explicit host inspection can restart exhausted read-only monitoring, never order retries.
        with self.lock:
            p = self.store.get(position_id, mode=self.mode)
            if p.job.status == "RUNNING" and self.clock() < p.job.lease_until:
                raise ValueError("Position monitor already leased")
            try:
                return self._reconcile(p, self.clock())
            except (ValueError, LookupError, ProviderError, TypeError):
                p = self.store.get(position_id, mode=self.mode)
                return self._save(
                    p,
                    state="RECONCILIATION_REQUIRED",
                    reasons=("POSITION_EVIDENCE_RECONCILIATION_REQUIRED",),
                )

    def prepare_exit(
        self,
        position_id,
        *,
        evidence,
        funding_state,
        allowance,
        correlation_id,
        quantity_base_units=None,
    ):
        """Prepare through Phase 8; LIVE gates remain blocked. No direct wallet path."""
        with self.lock:
            p = self.store.get(position_id, mode=self.mode)
            now = self.clock()
            if (
                p.state not in {"OPEN", "EXIT_PENDING"}
                or p.entry_at is None
                or not p.entry_execution.tx_hash
                or not self._calendar_matches(p)
                or now < p.exit_due_at
                or not self._exit_window_open(p, now)
                or self.has_unresolved(p.exit_intent.decision_id if p.exit_intent else None)
            ):
                raise ValueError("POSITION_EXIT_NOT_SAFE_OR_NOT_DUE")
            applied = {a.execution_id for a in p.applied_exit_executions}
            pending_intent = p.exit_intent and (
                p.exit_intent.execution is None
                or p.exit_intent.execution.execution_id not in applied
            )
            if pending_intent and p.exit_intent.execution:
                return p  # Never regenerate quote/order for an existing exit attempt.
            evidence = ExecutionRiskEvidence.model_validate_json(evidence.model_dump_json())
            funding_state = FundingState.model_validate_json(funding_state.model_dump_json())
            amount = (
                p.remaining_quantity_base_units
                if quantity_base_units is None
                else quantity_base_units
            )
            from app.models.execution import units

            amount = units(amount)
            if not 0 < int(amount) <= int(p.remaining_quantity_base_units):
                raise ValueError("Exit quantity exceeds known remaining holding")
            ordinal = len(p.applied_exit_executions) + 1
            decision = (
                "exit_" + hashlib.sha256(f"{p.position_id}:{ordinal}:{amount}".encode()).hexdigest()
            )
            if pending_intent and (
                p.exit_intent.decision_id != decision or p.exit_intent.quantity_base_units != amount
            ):
                raise ValueError("Unresolved exit intent cannot be changed")
            with localcontext() as ctx:
                ctx.prec = 160
                notional = quantity(amount, p.instrument.decimals) * funding_state.unit_price_usd
            if (
                evidence.data_mode != self.mode
                or evidence.purpose != "OPPORTUNITY"
                or evidence.decision_id != decision
                or evidence.notional_usd != notional
                or funding_state.asset.contract != p.instrument.contract
                or funding_state.asset.decimals != p.instrument.decimals
                or funding_state.wallet != p.entry_execution.quote.request.userWalletAddress
            ):
                raise ValueError(
                    "Exit risk/funding facts must match the deterministic intent and quantity"
                )
            if not pending_intent:
                p = self._save(
                    p,
                    state="EXIT_PENDING",
                    exit_intent=ExitIntent(
                        ordinal=ordinal,
                        decision_id=decision,
                        quantity_base_units=amount,
                        created_at=now,
                    ),
                )
            # The intent is durable BEFORE Phase 8 claims its unique decision. Crash recovery
            # finds that exact decision in the execution journal; it never submits a new order.
            a = self.execution.prepare(
                evidence,
                funding_state,
                target_contract=p.entry_execution.quote.request.fromTokenAddress,
                allowance=allowance,
                correlation_id=correlation_id,
            )
            if a.quote is None or a.route is None:
                return self._save(p, reasons=("EXIT_PREPARATION_BLOCKED",))
            p.validate_exit(a)
            return self._save(
                p,
                exit_intent=change(p.exit_intent, execution=a),
                reasons=("DRY_RUN_EXIT_NOT_EXECUTED",),
            )

    def exit_decision_id(self, position_id, quantity_base_units=None):
        p = self.store.get(position_id, mode=self.mode)
        amount = (
            p.remaining_quantity_base_units if quantity_base_units is None else quantity_base_units
        )
        return (
            "exit_"
            + hashlib.sha256(
                f"{p.position_id}:{len(p.applied_exit_executions) + 1}:{amount}".encode()
            ).hexdigest()
        )
