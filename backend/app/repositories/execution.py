"""Separate mode-scoped durable execution journal; atomic CAS and unique decision ownership."""

import threading
from pathlib import Path

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from app.models.execution import ExecutionAttempt, fingerprint


class ExecutionStore:
    def __init__(self, directory=None):
        self.lock = threading.RLock()
        if directory is None:
            self.engine = create_engine(
                "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
            )
        else:
            path = Path(directory).resolve()
            if path.suffix or any(path.glob("*.db")):
                raise ValueError("Separate execution audit directory required")
            path.mkdir(parents=True, exist_ok=True)
            self.engine = create_engine(
                "sqlite:///" + str(path / "execution.sqlite"), connect_args={"timeout": 5}
            )
        meta = MetaData()
        self.table = Table(
            "execution_attempts",
            meta,
            Column("id", String, primary_key=True),
            Column("mode", String, nullable=False),
            Column("decision", String, nullable=False),
            Column("version", Integer, nullable=False),
            Column("digest", String, nullable=False),
            Column("payload", String, nullable=False),
            UniqueConstraint("mode", "decision"),
        )
        self.events = Table(
            "execution_events",
            meta,
            Column("id", String, primary_key=True),
            Column("attempt", String, nullable=False),
            Column("version", Integer, nullable=False),
            Column("previous_digest", String, nullable=False),
            Column("digest", String, nullable=False),
            Column("payload", String, nullable=False),
            UniqueConstraint("attempt", "version"),
        )
        meta.create_all(self.engine)

    def claim(self, attempt):
        """Unique durable decision ownership across workers; losers never call providers."""
        try:
            self.save(attempt)
            return attempt, True
        except IntegrityError:
            existing = self.for_decision(attempt.decision_id, mode=attempt.data_mode)
            if existing is None or fingerprint(existing.evidence) != fingerprint(attempt.evidence):
                raise ValueError("DECISION_ALREADY_OWNED_DIFFERENT_EVIDENCE") from None
            return existing, False

    def save(self, attempt, *, expected_version=None):
        attempt = ExecutionAttempt.model_validate_json(attempt.model_dump_json())
        payload = attempt.model_dump_json()
        checksum = fingerprint(attempt)
        ident = str(attempt.execution_id)
        with self.lock, self.engine.begin() as db:
            old = db.execute(select(self.table).where(self.table.c.id == ident)).mappings().first()
            if old:
                if (
                    expected_version is None
                    or old["version"] != expected_version
                    or attempt.version != expected_version + 1
                ):
                    raise ValueError("EXECUTION_CONCURRENT_OR_DUPLICATE_WRITE")
                previous = self._validate(old)
                if (previous.settlement_conflict and not attempt.settlement_conflict) or (
                    previous.last_conflicting_tx_hash and attempt.last_conflicting_tx_hash is None
                ):
                    raise ValueError("IMMUTABLE_SETTLEMENT_CONFLICT")
                if (
                    previous.state
                    in {
                        "EXECUTION_CONFIRMED",
                        "EXECUTION_FAILED",
                        "EXECUTION_CANCELLED",
                        "EXECUTION_EXPIRED",
                        "BLOCKED",
                    }
                    and previous.external_tracking_only
                ):
                    raise ValueError("IMMUTABLE_EXTERNAL_TERMINAL_RECORD")
                if previous.tx_hash is not None and (
                    attempt.tx_hash is None or previous.tx_hash.lower() != attempt.tx_hash.lower()
                ):
                    raise ValueError("IMMUTABLE_KNOWN_TRANSACTION_HASH")
                if not set(previous.conflicting_tx_hashes).issubset(attempt.conflicting_tx_hashes):
                    raise ValueError("IMMUTABLE_CONTRADICTORY_EVIDENCE")
                if previous.external_tracking_only and any(
                    getattr(previous, key) != getattr(attempt, key)
                    for key in (
                        "quote",
                        "route",
                        "order_id",
                        "evidence",
                        "rfq_request_digest",
                        "external_tracking_only",
                        "generation",
                    )
                ):
                    raise ValueError("IMMUTABLE_EXTERNAL_EXECUTION_BINDING")
                if (
                    previous.decision_id,
                    previous.data_mode,
                    previous.request_id,
                    previous.source,
                    previous.created_at,
                    previous.correlation_id,
                ) != (
                    attempt.decision_id,
                    attempt.data_mode,
                    attempt.request_id,
                    attempt.source,
                    attempt.created_at,
                    attempt.correlation_id,
                ):
                    raise ValueError("EXECUTION_IDENTITY_MUTATION")
                result = db.execute(
                    self.table.update()
                    .where(self.table.c.id == ident, self.table.c.version == expected_version)
                    .values(version=attempt.version, digest=checksum, payload=payload)
                )
                if result.rowcount != 1:
                    raise ValueError("EXECUTION_CONCURRENT_WRITE")
                prior = old["digest"]
            else:
                if expected_version is not None or attempt.version != 0:
                    raise ValueError("INITIAL_EXECUTION_VERSION_REQUIRED")
                db.execute(
                    self.table.insert().values(
                        id=ident,
                        mode=attempt.data_mode,
                        decision=attempt.decision_id,
                        version=0,
                        digest=checksum,
                        payload=payload,
                    )
                )
                prior = "0" * 64
            db.execute(
                self.events.insert().values(
                    id=f"{ident}:{attempt.version}",
                    attempt=ident,
                    version=attempt.version,
                    previous_digest=prior,
                    digest=checksum,
                    payload=payload,
                )
            )

    def _validate(self, row):
        value = ExecutionAttempt.model_validate_json(row["payload"])
        if (
            fingerprint(value) != row["digest"]
            or value.version != row["version"]
            or str(value.execution_id) != row["id"]
            or value.data_mode != row["mode"]
            or value.decision_id != row["decision"]
        ):
            raise ValueError("EXECUTION_AUDIT_CORRUPT")
        return value

    def get(self, execution_id, *, mode):
        with self.lock, self.engine.connect() as db:
            row = (
                db.execute(
                    select(self.table).where(
                        self.table.c.id == str(execution_id), self.table.c.mode == mode
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise LookupError("Unknown mode-scoped execution")
            attempt = self._validate(row)
            events = (
                db.execute(
                    select(self.events)
                    .where(
                        self.events.c.attempt == str(execution_id),
                        self.events.c.version <= attempt.version,
                    )
                    .order_by(self.events.c.version)
                )
                .mappings()
                .all()
            )
        previous = "0" * 64
        if len(events) != attempt.version + 1:
            raise ValueError("EXECUTION_JOURNAL_INCOMPLETE")
        for i, e in enumerate(events):
            if (
                e["version"] != i
                or e["previous_digest"] != previous
                or fingerprint(ExecutionAttempt.model_validate_json(e["payload"])) != e["digest"]
            ):
                raise ValueError("EXECUTION_JOURNAL_CORRUPT")
            previous = e["digest"]
        if previous != row["digest"]:
            raise ValueError("EXECUTION_JOURNAL_DIVERGED")
        return attempt

    def for_decision(self, decision_id, *, mode):
        with self.lock, self.engine.connect() as db:
            row = db.execute(
                select(self.table.c.id).where(
                    self.table.c.mode == mode, self.table.c.decision == decision_id
                )
            ).first()
        return self.get(row[0], mode=mode) if row else None

    def pending(self, *, mode):
        with self.lock, self.engine.connect() as db:
            ids = (
                db.execute(select(self.table.c.id).where(self.table.c.mode == mode)).scalars().all()
            )
        return [
            a
            for key in ids
            if (a := self.get(key, mode=mode)).state
            in {"EXECUTION_SUBMITTED", "EXECUTION_PENDING", "EXECUTION_UNKNOWN"}
        ]

    def close(self):
        self.engine.dispose()
