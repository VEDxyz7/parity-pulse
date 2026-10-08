"""Durable retry receipts only. Never creates execution, RFQ, rebalance or wallet actions."""

import hashlib
from pathlib import Path
from threading import RLock

from sqlalchemy import Column, MetaData, String, Table, Text, create_engine, select
from sqlalchemy.pool import StaticPool

from app.models.agent_api import ToolResult


class ToolReceipts:
    def __init__(self, directory=None):
        self.lock = RLock()
        if directory is None:
            self.engine = create_engine(
                "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
            )
        else:
            path = Path(directory)
            path.mkdir(parents=True, exist_ok=True)
            self.engine = create_engine(f"sqlite:///{path / 'tool-receipts.sqlite'}")
        metadata = MetaData()
        self.table = Table(
            "tool_receipts",
            metadata,
            Column("key", String, primary_key=True),
            Column("input_digest", String, nullable=False),
            Column("payload", Text),
            Column("digest", String),
        )
        metadata.create_all(self.engine)

    def claim(self, key, digest):
        with self.lock, self.engine.begin() as db:
            changed = db.execute(
                self.table.insert().prefix_with("OR IGNORE").values(key=key, input_digest=digest)
            ).rowcount
            row = db.execute(select(self.table).where(self.table.c.key == key)).mappings().one()
            if row["input_digest"] != digest:
                raise ValueError("IDEMPOTENCY_CONFLICT")
            if changed:
                return None
            if row["payload"] is None:
                raise LookupError("RECONCILIATION_REQUIRED")
            if hashlib.sha256(row["payload"].encode()).hexdigest() != row["digest"]:
                raise ValueError("RECEIPT_INTEGRITY_FAILURE")
            result = ToolResult.model_validate_json(row["payload"])
            if key.split(":")[:2] != [result.data_mode, result.tool]:
                raise ValueError("RECEIPT_SCOPE_MISMATCH")
            return result

    def finish(self, key, digest, result):
        result = ToolResult.model_validate_json(result.model_dump_json())
        if key.split(":")[:2] != [result.data_mode, result.tool]:
            raise ValueError("RECEIPT_SCOPE_MISMATCH")
        payload = result.model_dump_json()
        with self.lock, self.engine.begin() as db:
            row = db.execute(select(self.table).where(self.table.c.key == key)).mappings().one()
            if row["input_digest"] != digest or row["payload"] is not None:
                raise ValueError("RECEIPT_CONFLICT")
            db.execute(
                self.table.update()
                .where(self.table.c.key == key)
                .values(payload=payload, digest=hashlib.sha256(payload.encode()).hexdigest())
            )

    def close(self):
        self.engine.dispose()
