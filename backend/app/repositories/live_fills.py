"""Durable journal of live rebalance legs. One row per plan action; never deleted."""

import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

TERMINAL = {"CONFIRMED", "FAILED", "REJECTED"}


class LiveFillStore:
    def __init__(self, path=None):
        self.lock = threading.RLock()
        if path is not None:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(
            str(path) if path is not None else ":memory:", check_same_thread=False
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS fills (
                action_id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL,
                asset TEXT NOT NULL,
                side TEXT NOT NULL,
                token TEXT,
                status TEXT NOT NULL,
                notional_usd TEXT NOT NULL,
                realized_cost_usd TEXT,
                approve_tx TEXT,
                swap_tx TEXT,
                signer TEXT,
                evidence TEXT NOT NULL,
                reasons TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS rfq_captures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at TEXT NOT NULL,
                vendor TEXT,
                primary_type TEXT,
                domain TEXT,
                verifying_contract TEXT,
                verdict TEXT NOT NULL,
                reason TEXT,
                payload TEXT NOT NULL
            )"""
        )
        self.db.commit()

    def capture_rfq(self, raw, *, verdict, reason=None):
        """Keep every RFQ /swap payload (accepted or refused) so real vendor formats are known."""
        rfq = raw.get("rfq") if isinstance(raw, dict) else None
        typed = rfq.get("typedDataToSign") if isinstance(rfq, dict) else None
        if isinstance(typed, str):
            try:
                typed = json.loads(typed)
            except ValueError:
                typed = None
        typed = typed if isinstance(typed, dict) else {}
        domain = typed.get("domain") if isinstance(typed.get("domain"), dict) else {}
        text = json.dumps(raw, default=str, sort_keys=True)[:262144]
        with self.lock:
            self.db.execute(
                "INSERT INTO rfq_captures (captured_at, vendor, primary_type, domain, "
                "verifying_contract, verdict, reason, payload) VALUES (?,?,?,?,?,?,?,?)",
                (
                    datetime.now(UTC).isoformat(),
                    rfq.get("vendor") if isinstance(rfq, dict) else None,
                    typed.get("primaryType"),
                    json.dumps(domain, default=str, sort_keys=True),
                    domain.get("verifyingContract"),
                    verdict,
                    reason,
                    text,
                ),
            )
            self.db.commit()

    def rfq_captures(self, limit=50):
        with self.lock:
            rows = self.db.execute(
                "SELECT captured_at, vendor, primary_type, domain, verifying_contract, verdict, "
                "reason, payload FROM rfq_captures ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        keys = "captured_at vendor primary_type domain verifying_contract verdict reason payload"
        return [
            {**dict(zip(keys.split(), r, strict=True)), "domain": json.loads(r[3]),
             "payload": json.loads(r[7])}
            for r in rows
        ]

    def close(self):
        self.db.close()

    def get(self, action_id):
        with self.lock:
            row = self.db.execute("SELECT * FROM fills WHERE action_id=?", (action_id,)).fetchone()
            return self._row(row) if row else None

    def for_plan(self, plan_id):
        with self.lock:
            rows = self.db.execute(
                "SELECT * FROM fills WHERE plan_id=? ORDER BY created_at", (plan_id,)
            ).fetchall()
            return [self._row(r) for r in rows]

    def recent(self, limit=50):
        with self.lock:
            rows = self.db.execute(
                "SELECT * FROM fills ORDER BY created_at DESC LIMIT ?", (int(limit),)
            ).fetchall()
            return [self._row(r) for r in rows]

    def upsert(self, action_id, **fields):
        now = datetime.now(UTC).isoformat()
        with self.lock:
            old = self.get(action_id)
            record = {**(old or {}), **fields, "action_id": action_id, "updated_at": now}
            record.setdefault("created_at", now)
            record.setdefault("reasons", [])
            record.setdefault("evidence", {})
            self.db.execute(
                """INSERT OR REPLACE INTO fills VALUES
                (:action_id,:plan_id,:asset,:side,:token,:status,:notional_usd,
                 :realized_cost_usd,:approve_tx,:swap_tx,:signer,:evidence,:reasons,
                 :created_at,:updated_at)""",
                {
                    "token": None,
                    "realized_cost_usd": None,
                    "approve_tx": None,
                    "swap_tx": None,
                    "signer": None,
                    **record,
                    "notional_usd": str(record["notional_usd"]),
                    "realized_cost_usd": None
                    if record.get("realized_cost_usd") is None
                    else str(record["realized_cost_usd"]),
                    "evidence": json.dumps(record["evidence"], default=str, sort_keys=True),
                    "reasons": json.dumps(list(record["reasons"])),
                },
            )
            self.db.commit()
            return self.get(action_id)

    def activity(self, now=None):
        """(trades today, last trade time, realized cost today) for RiskEngine limits."""
        now = now or datetime.now(UTC)
        start = (now - timedelta(days=1)).isoformat()
        with self.lock:
            rows = self.db.execute(
                "SELECT status, realized_cost_usd, updated_at FROM fills WHERE updated_at>=?",
                (start,),
            ).fetchall()
        done = [r for r in rows if r[0] in {"CONFIRMED", "SUBMITTED", "FAILED"}]
        last = max((datetime.fromisoformat(r[2]) for r in done), default=None)
        loss = sum((Decimal(r[1]) for r in done if r[1] is not None), Decimal(0))
        return len(done), last, max(loss, Decimal(0))

    @staticmethod
    def _row(row):
        keys = (
            "action_id plan_id asset side token status notional_usd realized_cost_usd "
            "approve_tx swap_tx signer evidence reasons created_at updated_at"
        ).split()
        record = dict(zip(keys, row, strict=True))
        record["evidence"] = json.loads(record["evidence"])
        record["reasons"] = json.loads(record["reasons"])
        return record
