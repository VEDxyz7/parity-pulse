"""Separate SQLite/SQLAlchemy audit and structured memory; no production-table access."""

import hashlib
from pathlib import Path
from threading import Lock

from sqlalchemy import Column, MetaData, String, Table, create_engine, insert, select
from sqlalchemy.pool import StaticPool

from app.agents.schemas import AgentRun, MemoryEpisode


class AgentStore:
    def __init__(self, directory=None):
        if directory is None:
            url = "sqlite:///:memory:"
        else:
            folder = Path(directory).resolve()
            if folder.suffix or folder.is_file() or list(folder.glob("*.db")):
                raise ValueError(
                    "Use a separate agent-store directory without application databases"
                )
            folder.mkdir(parents=True, exist_ok=True)
            url = f"sqlite:///{folder / 'agent-memory.sqlite'}"
        self._lock = Lock()
        self._engine = create_engine(
            url, connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        schema = MetaData()
        self._tables = {}
        for name in ("agent_runs", "agent_evidence", "decisions", "agent_memory"):
            self._tables[name] = Table(
                name,
                schema,
                Column("id", String, primary_key=True),
                Column("mode", String, nullable=False),
                Column("stock", String, nullable=False),
                Column("regime", String, nullable=False),
                Column("timestamp", String, nullable=False),
                Column("available_at", String, nullable=False),
                Column("payload", String, nullable=False),
                Column("digest", String, nullable=False),
            )
        schema.create_all(self._engine)

    @staticmethod
    def _row(identifier, mode, at, payload, *, stock="", regime="", available=None):
        return dict(
            id=identifier,
            mode=mode,
            stock=stock,
            regime=regime,
            timestamp=at.isoformat(),
            available_at=(available or at).isoformat(),
            payload=payload,
            digest=hashlib.sha256(payload.encode()).hexdigest(),
        )

    def _write(self, connection, table, row):
        previous = (
            connection.execute(select(table).where(table.c.id == row["id"])).mappings().first()
        )
        if previous:
            if dict(previous) != row:
                raise ValueError("Immutable agent record conflict")
            return
        connection.execute(insert(table).values(**row))

    def save_run(self, run):
        run = AgentRun.model_validate_json(run.model_dump_json())
        with self._lock, self._engine.begin() as connection:
            self._write(
                connection,
                self._tables["agent_runs"],
                self._row(run.run_id, run.data_mode, run.timestamp, run.model_dump_json()),
            )
            self._write(
                connection,
                self._tables["decisions"],
                self._row(
                    run.decision_id, run.data_mode, run.timestamp, run.decision.model_dump_json()
                ),
            )
            for evidence in run.evidence:
                self._write(
                    connection,
                    self._tables["agent_evidence"],
                    self._row(
                        f"{run.run_id}:{evidence.evidence_id}",
                        run.data_mode,
                        run.timestamp,
                        evidence.model_dump_json(),
                    ),
                )
            for response in run.responses:
                self._write(
                    connection,
                    self._tables["agent_evidence"],
                    self._row(
                        f"{run.run_id}:{response.agent}",
                        run.data_mode,
                        run.timestamp,
                        response.model_dump_json(),
                    ),
                )

    def load_run(self, identifier, mode):
        table = self._tables["agent_runs"]
        with self._lock, self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(table).where(table.c.id == identifier, table.c.mode == mode)
                )
                .mappings()
                .first()
            )
        if row is None:
            raise LookupError("No mode-scoped agent run")
        if hashlib.sha256(row["payload"].encode()).hexdigest() != row["digest"]:
            raise ValueError("Corrupt agent audit record")
        run = AgentRun.model_validate_json(row["payload"])
        if run.data_mode != mode or run.run_id != identifier:
            raise ValueError("Corrupt agent mode/identity binding")
        return run

    def remember(self, episode):
        episode = MemoryEpisode.model_validate_json(episode.model_dump_json())
        with self._lock, self._engine.begin() as connection:
            self._write(
                connection,
                self._tables["agent_memory"],
                self._row(
                    episode.memory_id,
                    episode.data_mode,
                    episode.timestamp,
                    episode.model_dump_json(),
                    stock=episode.stock,
                    regime=episode.regime,
                    available=episode.available_at,
                ),
            )

    def recent(self, stock, mode, regime, at, *, k=4):
        if type(k) is not int or not 1 <= k <= 10:
            raise ValueError("Bounded memory K required")
        table = self._tables["agent_memory"]
        with self._lock, self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(table)
                    .where(
                        table.c.mode == mode,
                        table.c.stock == stock,
                        table.c.regime == regime,
                        table.c.timestamp < at.isoformat(),
                        table.c.available_at <= at.isoformat(),
                    )
                    .order_by(table.c.timestamp.desc(), table.c.id.asc())
                    .limit(k)
                )
                .mappings()
                .all()
            )
        result = []
        for row in rows:
            if hashlib.sha256(row["payload"].encode()).hexdigest() != row["digest"]:
                raise ValueError("Corrupt agent memory")
            m = MemoryEpisode.model_validate_json(row["payload"])
            if (
                m.data_mode != mode
                or m.stock != stock
                or m.regime != regime
                or m.timestamp >= at
                or m.available_at > at
            ):
                raise ValueError("Corrupt agent memory scope")
            # Outcomes and scorecards are independently projected at query T, not just episode T.
            updates = {}
            if m.outcome_available_at is None or m.outcome_available_at > at:
                updates.update(eventual_outcome="UNAVAILABLE", outcome_available_at=None)
            if m.scorecard_available_at is None or m.scorecard_available_at > at:
                updates.update(scorecard_reference=None, scorecard_available_at=None)
            result.append(MemoryEpisode.model_validate({**m.model_dump(), **updates}))
        return tuple(result)

    def close(self):
        self._engine.dispose()

    def list_runs(self, mode, at, *, limit=100, offset=0):
        """Inspection only: no orchestration, provider calls or memory updates."""
        if (
            mode not in {"DEMO", "LIVE_READ_ONLY"}
            or not 1 <= limit <= 101
            or not 0 <= offset <= 10000
        ):
            raise ValueError("Bounded mode-scoped agent inspection required")
        table = self._tables["agent_runs"]
        with self._lock, self._engine.connect() as connection:
            ids = (
                connection.execute(
                    select(table.c.id)
                    .where(table.c.mode == mode, table.c.timestamp <= at.isoformat())
                    .order_by(table.c.timestamp.desc(), table.c.id)
                    .offset(offset)
                    .limit(limit)
                )
                .scalars()
                .all()
            )
        return tuple(self.load_run(identifier, mode) for identifier in ids)
