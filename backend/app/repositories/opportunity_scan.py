"""Immutable mode-scoped scan audit. Dedicated SQLite store; no production table access."""

from pathlib import Path
from threading import RLock

from sqlalchemy import Column, MetaData, String, Table, create_engine, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.pool import StaticPool

from app.models.opportunity_scan import OpportunityScan
from app.services.research_episodes import fingerprint


class OpportunityScanStore:
    def __init__(self, directory=None):
        self.lock = RLock()
        if directory is None:
            self.engine = create_engine(
                "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
            )
        else:
            path = Path(directory).resolve()
            if path.suffix or any(path.glob("*.db")):
                raise ValueError("A separate audit directory is required")
            path.mkdir(parents=True, exist_ok=True)
            self.engine = create_engine("sqlite:///" + str(path / "opportunity-scans.sqlite"))
        metadata = MetaData()
        self.table = Table(
            "opportunity_scans",
            metadata,
            Column("id", String, primary_key=True),
            Column("mode", String, nullable=False),
            Column("digest", String, nullable=False),
            Column("payload", String, nullable=False),
        )
        metadata.create_all(self.engine)

    def save(self, scan):
        scan = OpportunityScan.model_validate_json(scan.model_dump_json())
        payload = scan.model_dump_json()
        checksum = fingerprint(scan)
        with self.lock, self.engine.begin() as db:
            # The unique key arbitrates across separate workers/processes too.
            db.execute(
                insert(self.table)
                .values(id=scan.run_id, mode=scan.data_mode, digest=checksum, payload=payload)
                .on_conflict_do_nothing(index_elements=["id"])
            )
            old = (
                db.execute(select(self.table).where(self.table.c.id == scan.run_id))
                .mappings()
                .first()
            )
            if old:
                if (
                    old["digest"] != checksum
                    or fingerprint(OpportunityScan.model_validate_json(old["payload"])) != checksum
                    or old["mode"] != scan.data_mode
                ):
                    raise ValueError("Conflicting immutable scan audit")

    def get(self, run_id, *, mode):
        with self.lock, self.engine.connect() as db:
            row = (
                db.execute(
                    select(self.table).where(self.table.c.id == run_id, self.table.c.mode == mode)
                )
                .mappings()
                .first()
            )
        if row is None:
            raise LookupError("Unknown mode-scoped scan")
        scan = OpportunityScan.model_validate_json(row["payload"])
        if fingerprint(scan) != row["digest"] or scan.data_mode != mode or scan.run_id != run_id:
            raise ValueError("Corrupt scan audit")
        return scan

    def close(self):
        self.engine.dispose()

    def list(self, *, mode):
        with self.lock, self.engine.connect() as db:
            ids = (
                db.execute(
                    select(self.table.c.id)
                    .where(self.table.c.mode == mode)
                    .order_by(self.table.c.id)
                    .limit(101)
                )
                .scalars()
                .all()
            )
        if len(ids) > 100:
            raise ValueError("Scan inspection bound exceeded")
        return tuple(self.get(i, mode=mode) for i in ids)
