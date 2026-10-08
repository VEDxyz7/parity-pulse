"""Atomic lifecycle + job persistence, CAS updates and append-only position history."""

import hashlib
import threading
from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, String, Table, Text, create_engine, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from app.models.execution import ExecutionAttempt
from app.models.position import TRANSITIONS, Position


class PositionStore:
    def __init__(self, executions, directory=None):
        self.executions = executions
        self.lock = threading.RLock()
        if directory is None:
            self.engine = create_engine(
                "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
            )
        else:
            directory = Path(directory)
            directory.mkdir(parents=True, exist_ok=True)
            self.engine = create_engine(f"sqlite:///{directory / 'positions.sqlite'}")
        metadata = MetaData()
        self.positions = Table(
            "positions",
            metadata,
            Column("position_id", String, primary_key=True),
            Column("execution_id", String, nullable=False, unique=True),
            Column("mode", String, nullable=False),
            Column("state", String, nullable=False),
            Column("version", Integer, nullable=False),
            Column("payload", Text, nullable=False),
            Column("digest", String, nullable=False),
        )
        self.events = Table(
            "position_events",
            metadata,
            Column("position_id", String, primary_key=True),
            Column("version", Integer, primary_key=True),
            Column("payload", Text, nullable=False),
            Column("digest", String, nullable=False),
        )
        metadata.create_all(self.engine)

    def _validate_journal(self, position):
        attempts = [position.entry_execution, *position.applied_exit_executions]
        if position.exit_intent and position.exit_intent.execution:
            attempts.append(position.exit_intent.execution)
        for a in attempts:
            saved = self.executions.get(a.execution_id, mode=position.data_mode)
            if saved == a:
                continue
            # A stale monitor snapshot must itself be an authentic historical journal entry.
            # The complete journal chain is validated by get() above before this lookup.
            with self.executions.lock, self.executions.engine.connect() as db:
                payload = db.execute(
                    select(self.executions.events.c.payload).where(
                        self.executions.events.c.attempt == str(a.execution_id),
                        self.executions.events.c.version == a.version,
                    )
                ).scalar_one_or_none()
            if payload is None or ExecutionAttempt.model_validate_json(payload) != a:
                raise ValueError("Position snapshot is not validated execution journal evidence")

    def save(self, position, *, expected_version=None):
        position = Position.model_validate_json(position.payload())
        self._validate_journal(position)
        payload = position.payload()
        digest = hashlib.sha256(payload.encode()).hexdigest()
        row = dict(
            position_id=str(position.position_id),
            execution_id=str(position.entry_execution.execution_id),
            mode=position.data_mode,
            state=position.state,
            version=position.version,
            payload=payload,
            digest=digest,
        )
        try:
            with self.lock, self.engine.begin() as db:
                if expected_version is None:
                    if position.version != 0:
                        raise ValueError("New positions start at version zero")
                    db.execute(self.positions.insert().values(**row))
                else:
                    old_row = (
                        db.execute(
                            select(self.positions).where(
                                self.positions.c.position_id == row["position_id"]
                            )
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if old_row is None:
                        raise ValueError("Unknown immutable position identifier")
                    old = self._decode(old_row)
                    self._validate_update(old, position, expected_version)
                    result = db.execute(
                        update(self.positions)
                        .where(
                            self.positions.c.position_id == row["position_id"],
                            self.positions.c.version == expected_version,
                        )
                        .values(**row)
                    )
                    if result.rowcount != 1:
                        raise ValueError("Concurrent position update")
                db.execute(
                    self.events.insert().values(
                        position_id=row["position_id"],
                        version=position.version,
                        payload=payload,
                        digest=digest,
                    )
                )
        except IntegrityError:
            raise ValueError("Duplicate position/execution or stale lifecycle version") from None
        return position

    @staticmethod
    def _validate_update(old, new, expected):
        if old.version != expected or new.version != expected + 1:
            raise ValueError("Stale position version")
        for field in (
            "position_id",
            "account_scope",
            "data_mode",
            "instrument",
            "created_at",
            "requested_quantity_base_units",
            "postopen_exit_minutes",
            "exit_rule",
        ):
            if getattr(old, field) != getattr(new, field):
                raise ValueError("Immutable position identity/holding policy")
        if old.entry_execution.execution_id != new.entry_execution.execution_id:
            raise ValueError("Immutable entry execution")
        if (
            any(
                getattr(old.entry_execution, f) != getattr(new.entry_execution, f)
                for f in (
                    "request_id",
                    "decision_id",
                    "source",
                    "quote",
                    "route",
                )
            )
            or new.entry_execution.version < old.entry_execution.version
        ):
            raise ValueError("Immutable position entry binding and monotonic execution evidence")
        if old.entry_execution.state == "EXECUTION_CONFIRMED" and (
            old.entry_execution != new.entry_execution
        ):
            raise ValueError("Immutable confirmed entry evidence")
        if (
            old.entry_execution.tx_hash
            and old.entry_execution.tx_hash != new.entry_execution.tx_hash
        ):
            raise ValueError("Known transaction identity cannot be replaced")
        if new.state != old.state and new.state not in TRANSITIONS[old.state]:
            raise ValueError("Invalid position transition")
        if old.state in {"CLOSED", "FAILED", "RECONCILIATION_REQUIRED"} and old.state != new.state:
            raise ValueError("Terminal lifecycle cannot be reopened")
        if tuple(new.applied_exit_executions[: len(old.applied_exit_executions)]) != (
            old.applied_exit_executions
        ):
            raise ValueError("Confirmed exits are append-only")
        if new.valuations[: len(old.valuations)] != old.valuations:
            raise ValueError("As-of settlement valuations are append-only")
        if old.entry_at is not None and any(
            getattr(old, f) != getattr(new, f)
            for f in ("entry_at", "market_open_at", "exit_due_at", "calendar_version")
        ):
            raise ValueError("Established entry and schedule cannot change")
        if old.exit_intent:
            intent = new.exit_intent
            applied = {a.execution_id for a in new.applied_exit_executions}
            old_a = old.exit_intent.execution
            if intent is None or intent.ordinal != old.exit_intent.ordinal:
                if old_a is None or old_a.execution_id not in applied:
                    raise ValueError("Unresolved exit intent cannot be discarded or replaced")
            else:
                if intent.model_dump(exclude={"execution"}) != old.exit_intent.model_dump(
                    exclude={"execution"}
                ):
                    raise ValueError("Immutable exit intent")
                if old_a and (
                    intent.execution is None or intent.execution.execution_id != old_a.execution_id
                ):
                    raise ValueError("Immutable exit execution")
                if old_a and old_a.tx_hash and intent.execution.tx_hash != old_a.tx_hash:
                    raise ValueError("Exit transaction identity cannot change")
                if old_a and (
                    any(
                        getattr(old_a, f) != getattr(intent.execution, f)
                        for f in (
                            "request_id",
                            "decision_id",
                            "source",
                            "quote",
                            "route",
                        )
                    )
                    or intent.execution.version < old_a.version
                ):
                    raise ValueError("Immutable exit binding and monotonic execution evidence")
        if new.updated_at < old.updated_at or new.job.job_id != old.job.job_id:
            raise ValueError("Immutable job identity and monotonic timestamps required")

    @staticmethod
    def _decode(row):
        if hashlib.sha256(row["payload"].encode()).hexdigest() != row["digest"]:
            raise ValueError("Corrupt position payload")
        result = Position.model_validate_json(row["payload"])
        if (
            str(result.position_id),
            result.version,
            result.data_mode,
            str(result.entry_execution.execution_id),
            result.state,
        ) != (row["position_id"], row["version"], row["mode"], row["execution_id"], row["state"]):
            raise ValueError("Position row binding mismatch")
        return result

    def get(self, position_id, *, mode):
        with self.lock, self.engine.connect() as db:
            row = (
                db.execute(
                    select(self.positions).where(
                        self.positions.c.position_id == str(position_id),
                        self.positions.c.mode == mode,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError("Position not found in this mode")
            result = self._decode(row)
            history = (
                db.execute(
                    select(self.events)
                    .where(self.events.c.position_id == str(position_id))
                    .order_by(self.events.c.version)
                )
                .mappings()
                .all()
            )
            if len(history) != result.version + 1:
                raise ValueError("Incomplete position event history")
            previous = None
            for version, event in enumerate(history):
                if (
                    event["version"] != version
                    or hashlib.sha256(event["payload"].encode()).hexdigest() != event["digest"]
                ):
                    raise ValueError("Corrupt position history")
                current = Position.model_validate_json(event["payload"])
                if previous:
                    self._validate_update(previous, current, version - 1)
                previous = current
            if previous != result:
                raise ValueError("Position event head mismatch")
            return result

    def list(self, *, mode, limit=100, active=False):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Bounded position listing required")
        with self.lock, self.engine.connect() as db:
            conditions = [self.positions.c.mode == mode]
            if active:
                conditions.append(self.positions.c.state.not_in(("CLOSED", "FAILED")))
            ids = (
                db.execute(
                    select(self.positions.c.position_id)
                    .where(*conditions)
                    .order_by(self.positions.c.position_id)
                    .limit(limit)
                )
                .scalars()
                .all()
            )
        return [self.get(i, mode=mode) for i in ids]

    def for_execution(self, execution_id, *, mode):
        with self.lock, self.engine.connect() as db:
            identifier = db.execute(
                select(self.positions.c.position_id).where(
                    self.positions.c.execution_id == str(execution_id),
                    self.positions.c.mode == mode,
                )
            ).scalar_one_or_none()
        return self.get(identifier, mode=mode) if identifier else None

    def count(self, *, mode, active=False):
        from sqlalchemy import func

        with self.lock, self.engine.connect() as db:
            conditions = [self.positions.c.mode == mode]
            if active:
                conditions.append(self.positions.c.state.not_in(("CLOSED", "FAILED")))
            return db.execute(
                select(func.count()).select_from(self.positions).where(*conditions)
            ).scalar_one()

    def close(self):
        self.engine.dispose()
