"""Immutable mode-scoped scan audit. Dedicated SQLite store; no production table access."""

from pathlib import Path

from sqlalchemy import Column, MetaData, String, Table, create_engine, select
from sqlalchemy.pool import StaticPool

from app.models.opportunity_scan import OpportunityScan
from app.services.research_episodes import fingerprint


class OpportunityScanStore:
    def __init__(self, directory=None):
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
        with self.engine.begin() as db:
            old = (
                db.execute(select(self.table).where(self.table.c.id == scan.run_id))
                .mappings()
                .first()
            )
            if old:
                if (
                    old["digest"] != checksum
                    or fingerprint(OpportunityScan.model_validate_json(old["payload"])) != checksum
                ):
                    raise ValueError("Conflicting immutable scan audit")
            else:
                db.execute(
                    self.table.insert().values(
                        id=scan.run_id, mode=scan.data_mode, digest=checksum, payload=payload
                    )
                )

    def get(self, run_id, *, mode):
        with self.engine.connect() as db:
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
