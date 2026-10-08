"""Unified immutable evaluation and audit projections over existing source journals."""

import hashlib
from pathlib import Path
from threading import RLock

from sqlalchemy import Column, MetaData, String, Table, Text, create_engine, select
from sqlalchemy.pool import StaticPool

from app.models.portfolio import portfolio_fingerprint
from app.models.scorecard import AuditEvent, Scorecard


def identity(record):
    return portfolio_fingerprint(record.model_dump(exclude={"recorded_at"}))


class ScorecardStore:
    def __init__(self, directory=None):
        self.lock = RLock()
        if directory is None:
            self.engine = create_engine(
                "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
            )
        else:
            folder = Path(directory)
            folder.mkdir(parents=True, exist_ok=True)
            self.engine = create_engine(f"sqlite:///{folder / 'scorecard-audit.sqlite'}")
        schema = MetaData()
        self.tables = {}
        for name in ("scorecards", "audit_events"):
            self.tables[name] = Table(
                name,
                schema,
                Column("id", String, primary_key=True),
                Column("mode", String, nullable=False),
                Column("decision", String, nullable=False),
                Column("payload", Text, nullable=False),
                Column("digest", String, nullable=False),
            )
        schema.create_all(self.engine)

    @staticmethod
    def decode(row, model):
        if hashlib.sha256(row["payload"].encode()).hexdigest() != row["digest"]:
            raise ValueError("Evaluation journal checksum mismatch")
        value = model.model_validate_json(row["payload"])
        identifier = value.evaluation_id if model is Scorecard else value.event_id
        if (identifier, value.data_mode, value.decision_id) != (
            row["id"],
            row["mode"],
            row["decision"],
        ):
            raise ValueError("Evaluation journal identity mismatch")
        key = "evaluation_id" if model is Scorecard else "event_id"
        if identifier != portfolio_fingerprint(value.model_dump(exclude={key, "recorded_at"})):
            raise ValueError("Evaluation semantic identity mismatch")
        return value

    def append(self, cards, events):
        # One transaction prevents an evaluation from losing its audit references.
        with self.lock, self.engine.begin() as db:
            for values, name, model in (
                (events, "audit_events", AuditEvent),
                (cards, "scorecards", Scorecard),
            ):
                table = self.tables[name]
                for value in values:
                    value = model.model_validate_json(value.model_dump_json())
                    ident = value.evaluation_id if model is Scorecard else value.event_id
                    old = db.execute(select(table).where(table.c.id == ident)).mappings().first()
                    if old:
                        if identity(self.decode(old, model)) != identity(value):
                            raise ValueError("Immutable evaluation journal conflict")
                        continue
                    payload = value.model_dump_json()
                    db.execute(
                        table.insert()
                        .prefix_with("OR IGNORE")
                        .values(
                            id=ident,
                            mode=value.data_mode,
                            decision=value.decision_id,
                            payload=payload,
                            digest=hashlib.sha256(payload.encode()).hexdigest(),
                        )
                    )
                    saved = db.execute(select(table).where(table.c.id == ident)).mappings().one()
                    if identity(self.decode(saved, model)) != identity(value):
                        raise ValueError("Concurrent immutable evaluation conflict")
            for card in cards:
                table = self.tables["scorecards"]
                previous = (
                    db.execute(
                        select(table)
                        .where(table.c.mode == card.data_mode, table.c.decision == card.decision_id)
                        .limit(20001)
                    )
                    .mappings()
                    .all()
                )
                if len(previous) > 20000:
                    raise ValueError("Decision evaluation inspection bound exceeded")
                for row in previous:
                    known = self.decode(row, Scorecard)
                    if (known.origin, known.origin_id) == (
                        card.origin,
                        card.origin_id,
                    ) and known.input_digest != card.input_digest:
                        raise ValueError("Original decision inputs cannot be replaced")
                for event_id in card.event_ids:
                    row = (
                        db.execute(
                            select(self.tables["audit_events"]).where(
                                self.tables["audit_events"].c.id == event_id
                            )
                        )
                        .mappings()
                        .first()
                    )
                    if row is None:
                        raise ValueError("Missing atomic audit reference")
                    event = self.decode(row, AuditEvent)
                    if (event.data_mode, event.decision_id) != (card.data_mode, card.decision_id):
                        raise ValueError("Cross-decision audit reference")

    def list(self, model, *, mode):
        if mode not in {"DEMO", "LIVE_READ_ONLY"}:
            raise ValueError("Explicit evaluation mode required")
        table = self.tables["scorecards" if model is Scorecard else "audit_events"]
        with self.lock, self.engine.connect() as db:
            rows = (
                db.execute(select(table).where(table.c.mode == mode).limit(20001)).mappings().all()
            )
        if len(rows) > 20000:
            raise ValueError("Evaluation journal inspection bound exceeded")
        return tuple(self.decode(row, model) for row in rows)

    def close(self):
        self.engine.dispose()
