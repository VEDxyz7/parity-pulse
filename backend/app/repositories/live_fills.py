"""Durable execution identities, wallet claims and bounded unsigned RFQ evidence.

SQLite uniqueness/transactions coordinate separate processes, not just Python locks.
Claims never expire automatically: recovery observes chain state, never re-signs/re-sends.
Raw signatures and signed transactions are deliberately not persisted here.
"""

import hashlib
import json
import re
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.models.live import TERMINAL, UNRESOLVED

MAX_CAPTURE_BYTES = 262144
MAX_CAPTURE_ROWS = 128
MAX_CAPTURE_TOTAL_BYTES = 8 * 1024 * 1024
SENSITIVE = {
    "signature",
    "usersignature",
    "rfq_signature",
    "authorization",
    "cookie",
    "privatekey",
    "private_key",
    "secret",
    "apikey",
    "api_key",
    "headers",
    "signaturedata",
    "rawtransaction",
    "raw_transaction",
}
COLUMNS = (
    "action_id plan_id asset side token status notional_usd realized_cost_usd "
    "approve_tx swap_tx signer evidence reasons created_at updated_at"
).split()
TRANSITIONS = {
    "PREPARING": {"QUOTED", "SIGNED", "REJECTED", "RECONCILIATION_REQUIRED"},
    "QUOTED": {"SIGNED", "SUBMITTING", "REJECTED", "RECONCILIATION_REQUIRED"},
    "SIGNED": {"SUBMITTING", "REJECTED", "RECONCILIATION_REQUIRED"},
    "SUBMITTING": {
        "SUBMITTED",
        "SUBMISSION_UNKNOWN",
        "RECONCILIATION_REQUIRED",
        "CONFIRMED",
        "FAILED",
    },
    "SUBMITTED": {"SUBMISSION_UNKNOWN", "RECONCILIATION_REQUIRED", "CONFIRMED", "FAILED"},
    "SUBMISSION_UNKNOWN": {"RECONCILIATION_REQUIRED", "CONFIRMED", "FAILED"},
    "RECONCILIATION_REQUIRED": {"CONFIRMED", "FAILED"},
    "APPROVING": {"RECONCILIATION_REQUIRED"},  # unresolved legacy approval; no automatic replay
}


def clean(value, secrets=(), depth=0):
    if depth > 32:
        raise ValueError("CAPTURE_DEPTH_EXCEEDED")
    if isinstance(value, dict):
        return {
            str(k): clean(v, secrets, depth + 1)
            for k, v in value.items()
            if str(k).lower().replace("-", "_") not in SENSITIVE
            and not any(w in str(k).lower() for w in ("secret", "credential", "api-key"))
        }
    if isinstance(value, (tuple, list)):
        return [clean(v, secrets, depth + 1) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if value is None or type(value) in (bool, int):
        return value
    if isinstance(value, Decimal):
        return str(value)
    raise ValueError("CAPTURE_VALUE_UNSUPPORTED")


class LiveFillStore:
    def __init__(self, path=None, *, redaction_values=()):
        self.lock = threading.RLock()
        self.secrets = tuple(redaction_values)
        if path is not None:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(
            str(path) if path is not None else ":memory:", check_same_thread=False, timeout=10
        )
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS fills (
                action_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, asset TEXT NOT NULL,
                side TEXT NOT NULL, token TEXT, status TEXT NOT NULL, notional_usd TEXT NOT NULL,
                realized_cost_usd TEXT, approve_tx TEXT, swap_tx TEXT, signer TEXT,
                evidence TEXT NOT NULL, reasons TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS execution_claims (
                action_id TEXT PRIMARY KEY, wallet TEXT NOT NULL, intent_digest TEXT NOT NULL,
                owner TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS wallet_claims (
                wallet TEXT PRIMARY KEY, action_id TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS submission_attempts (
                action_id TEXT NOT NULL, kind TEXT NOT NULL, identity TEXT NOT NULL,
                nonce INTEGER, payload_digest TEXT NOT NULL, attempted_at TEXT NOT NULL,
                PRIMARY KEY(action_id,kind), UNIQUE(identity)
            );
            CREATE TABLE IF NOT EXISTS execution_consents (
                confirmation_id TEXT PRIMARY KEY, action_id TEXT NOT NULL,
                payload_digest TEXT NOT NULL, expires_at TEXT NOT NULL, used INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rfq_evidence_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT, captured_at TEXT NOT NULL,
                vendor TEXT, chain_id TEXT, verdict TEXT NOT NULL, reason TEXT,
                source TEXT NOT NULL, schema_version INTEGER NOT NULL, digest TEXT NOT NULL,
                size INTEGER NOT NULL, payload TEXT NOT NULL
            );
        """)
        self.db.commit()

    def close(self):
        self.db.close()

    def get(self, action_id):
        with self.lock:
            row = self.db.execute("SELECT * FROM fills WHERE action_id=?", (action_id,)).fetchone()
            return self._row(row) if row else None

    def claim(self, action_id, *, wallet, intent_digest, **fields):
        """One atomic claim for both action and active wallet/nonce stream."""
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            old = self.get(action_id)
            if old:
                claim = self.db.execute(
                    "SELECT intent_digest FROM execution_claims WHERE action_id=?", (action_id,)
                ).fetchone()
                if claim is None or claim[0] != intent_digest:
                    raise ValueError("ACTION_IDENTITY_CONFLICT")
                return old, None
            unresolved = self.db.execute(
                "SELECT f.status FROM fills f JOIN execution_claims c USING(action_id) "
                "WHERE c.wallet=?",
                (wallet,),
            ).fetchall()
            if any(row[0] not in TERMINAL for row in unresolved):
                raise ValueError("WALLET_EXECUTION_UNRESOLVED")
            owner = uuid4().hex
            try:
                self.db.execute("INSERT INTO wallet_claims VALUES (?,?)", (wallet, action_id))
            except sqlite3.IntegrityError:
                raise ValueError("WALLET_EXECUTION_UNRESOLVED") from None
            self.db.execute(
                "INSERT INTO execution_claims VALUES (?,?,?,?)",
                (action_id, wallet, intent_digest, owner),
            )
            record = self._write(action_id, {**fields, "status": "PREPARING"})
            return record, owner

    def upsert(self, action_id, **fields):
        """Update only an existing claimed row; never INSERT OR REPLACE an action."""
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            old = self.get(action_id)
            if old is None:
                raise ValueError("ATOMIC_EXECUTION_CLAIM_REQUIRED")
            if old["status"] in TERMINAL:
                if fields.get("status", old["status"]) != old["status"]:
                    raise ValueError("TERMINAL_STATE_IMMUTABLE")
                return old
            status = fields.get("status", old["status"])
            if status not in TERMINAL | UNRESOLVED:
                raise ValueError("INVALID_EXECUTION_STATE")
            attempted = self.db.execute(
                "SELECT 1 FROM submission_attempts WHERE action_id=?", (action_id,)
            ).fetchone()
            if status == "REJECTED" and attempted:
                raise ValueError("SUBMISSION_OUTCOME_REQUIRES_RECONCILIATION")
            if status != old["status"] and status not in TRANSITIONS.get(old["status"], set()):
                raise ValueError("INVALID_EXECUTION_TRANSITION")
            if status in {"CONFIRMED", "FAILED"} and not attempted:
                raise ValueError("SETTLEMENT_SUBMISSION_IDENTITY_REQUIRED")
            record = self._write(action_id, {**old, **fields})
            if status in TERMINAL:
                self.db.execute("DELETE FROM wallet_claims WHERE action_id=?", (action_id,))
            return record

    def begin_submission(self, action_id, *, kind, identity, nonce, payload_digest):
        """Durably record hash/nonce or RFQ request UUID BEFORE any broadcast/POST."""
        # SQLite's INTEGER stores this EVM sender nonce exactly in a signed 64-bit
        # column. Reject coercion/overflow; RFQ request identity has no EVM nonce.
        if kind == "SWAP" and not (type(nonce) is int and 0 <= nonce < 2**63):
            raise ValueError("SUBMISSION_NONCE_MISSING_OR_INVALID")
        if kind == "RFQ" and nonce is not None:
            raise ValueError("RFQ_SUBMISSION_NONCE_DOMAIN_INVALID")
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            record = self.get(action_id)
            if record is None or record["status"] not in {"QUOTED", "SIGNED"}:
                raise ValueError("SUBMISSION_STATE_INVALID")
            if kind not in {"SWAP", "RFQ"}:
                raise ValueError("SUBMISSION_KIND_INVALID")
            self.db.execute(
                "INSERT INTO submission_attempts VALUES (?,?,?,?,?,?)",
                (action_id, kind, identity, nonce, payload_digest, datetime.now(UTC).isoformat()),
            )
            self._write(action_id, {**record, "status": "SUBMITTING"})

    def reopen_reorg(self, action_id, *, reason="SETTLEMENT_BLOCK_REORG_RECONCILE"):
        """Revoke settlement when its block or immutable evidence cannot be reverified.

        Never replace a newer wallet claim. An additional unresolved row blocks subsequent
        claims/planning until the operator reconciles both outstanding identities.
        """
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            record = self.get(action_id)
            if record is None or record["status"] not in {"CONFIRMED", "FAILED"}:
                raise ValueError("REORG_STATE_INVALID")
            wallet = self.db.execute(
                "SELECT wallet FROM execution_claims WHERE action_id=?", (action_id,)
            ).fetchone()
            if wallet:
                self.db.execute(
                    "INSERT OR IGNORE INTO wallet_claims VALUES (?,?)", (wallet[0], action_id)
                )
            return self._write(
                action_id,
                {
                    **record,
                    "status": "RECONCILIATION_REQUIRED",
                    "reasons": [reason],
                },
            )

    def submission(self, action_id, kind):
        with self.lock:
            row = self.db.execute(
                "SELECT identity,nonce,payload_digest FROM submission_attempts "
                "WHERE action_id=? AND kind=?",
                (action_id, kind),
            ).fetchone()
            return (
                dict(zip(("identity", "nonce", "payload_digest"), row, strict=True))
                if row
                else None
            )

    def confirm(self, consent, *, now):
        if not consent.confirmed_at <= now < consent.expires_at:
            raise ValueError("CONFIRMATION_EXPIRED")
        with self.lock, self.db:
            try:
                self.db.execute(
                    "INSERT INTO execution_consents VALUES (?,?,?,?,0)",
                    (
                        consent.confirmation_id,
                        consent.action_id,
                        consent.payload_digest,
                        consent.expires_at.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError:
                raise ValueError("CONFIRMATION_ALREADY_RECORDED") from None

    def consume_consent(self, consent, *, payload_digest, now):
        if consent.payload_digest != payload_digest or not consent.confirmed_at <= now < (
            consent.expires_at
        ):
            raise ValueError("INVALID_OR_STALE_EXPLICIT_CONFIRMATION")
        with self.lock, self.db:
            result = self.db.execute(
                "UPDATE execution_consents SET used=1 WHERE confirmation_id=? AND action_id=? "
                "AND payload_digest=? AND expires_at=? AND used=0",
                (
                    consent.confirmation_id,
                    consent.action_id,
                    payload_digest,
                    consent.expires_at.isoformat(),
                ),
            )
            if result.rowcount != 1:
                raise ValueError("CONFIRMATION_MISSING_OR_CONSUMED")

    def _write(self, action_id, fields):
        now = datetime.now(UTC).isoformat()
        record = {
            "token": None,
            "realized_cost_usd": None,
            "approve_tx": None,
            "swap_tx": None,
            "signer": None,
            "created_at": now,
            "reasons": [],
            "evidence": {},
            **fields,
            "action_id": action_id,
            "updated_at": now,
        }
        # The public journal cannot accidentally become a signing-artifact store.
        record["evidence"] = clean(record["evidence"], self.secrets)
        values = {
            **record,
            "notional_usd": str(record["notional_usd"]),
            "realized_cost_usd": None
            if record["realized_cost_usd"] is None
            else str(record["realized_cost_usd"]),
            "evidence": json.dumps(record["evidence"], sort_keys=True),
            "reasons": json.dumps(record["reasons"]),
        }
        columns = ",".join(COLUMNS)
        updates = ",".join(f"{c}=excluded.{c}" for c in COLUMNS if c != "action_id")
        self.db.execute(
            f"INSERT INTO fills ({columns}) VALUES "
            f"({','.join(':' + c for c in COLUMNS)}) "
            f"ON CONFLICT(action_id) DO UPDATE SET {updates}",
            values,
        )
        return self.get(action_id)

    def for_plan(self, plan_id):
        with self.lock:
            return [
                self._row(r)
                for r in self.db.execute(
                    "SELECT * FROM fills WHERE plan_id=? ORDER BY created_at", (str(plan_id),)
                )
            ]

    def recent(self, limit=50):
        with self.lock:
            return [
                self._row(r)
                for r in self.db.execute(
                    "SELECT * FROM fills ORDER BY created_at DESC LIMIT ?",
                    (min(max(limit, 1), 100),),
                )
            ]

    def unresolved(self, plan_id=None):
        rows = self.for_plan(plan_id) if plan_id is not None else self.recent(100)
        if plan_id is None:
            with self.lock:
                rows = [self._row(r) for r in self.db.execute("SELECT * FROM fills")]
        return any(r["status"] not in TERMINAL for r in rows)

    def capture_rfq(self, raw, *, verdict, reason=None, source="BINANCE_WEB3"):
        # Only unsigned protocol fields are evidence. No arbitrary headers/wallet envelope.
        rfq = raw.get("rfq", {}) if isinstance(raw, dict) else {}
        if not isinstance(rfq, dict):
            rfq = {}
        safe = {
            k: rfq[k] for k in ("vendor", "orderId", "typedDataToSign", "signingScheme") if k in rfq
        }
        try:
            if isinstance(safe.get("typedDataToSign"), str):
                safe["typedDataToSign"] = json.loads(safe["typedDataToSign"])
            safe = clean(safe, self.secrets)
            text = json.dumps(safe, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (ValueError, TypeError, RecursionError):
            safe, text, verdict, reason = {}, "{}", "INCOMPLETE", "CAPTURE_SCHEMA_INVALID"
        digest = hashlib.sha256(text.encode()).hexdigest()
        if len(text.encode()) > MAX_CAPTURE_BYTES:
            text = json.dumps({"omitted": "PAYLOAD_SIZE_LIMIT", "original_digest": digest})
            verdict, reason = "INCOMPLETE", "PAYLOAD_SIZE_LIMIT"
        digest = hashlib.sha256(text.encode()).hexdigest()
        typed = safe.get("typedDataToSign", {})
        if not isinstance(typed, dict) or set(typed) != {
            "types",
            "domain",
            "primaryType",
            "message",
        }:
            if reason != "PAYLOAD_SIZE_LIMIT":
                verdict, reason = "INCOMPLETE", "CAPTURE_SCHEMA_INVALID"
        domain = typed.get("domain", {}) if isinstance(typed, dict) else {}
        if not isinstance(domain, dict):
            domain, verdict, reason = {}, "INCOMPLETE", "CAPTURE_SCHEMA_INVALID"
        vendor = safe.get("vendor")
        if vendor not in ("CowSwap", "InchFusion", "PcsXRfq"):
            vendor, verdict, reason = None, "INCOMPLETE", "CAPTURE_SCHEMA_INVALID"
        chain = str(domain.get("chainId", ""))
        if not re.fullmatch(r"[0-9]{1,20}", chain):
            chain, verdict = "", "INCOMPLETE"
            if reason != "PAYLOAD_SIZE_LIMIT":
                reason = "CAPTURE_SCHEMA_INVALID"
        # Metadata has its own bounds: total retention cannot be bypassed with a
        # huge reason/source or accidentally echo a configured credential.
        source = clean(source, self.secrets) if isinstance(source, str) else "UNKNOWN_SOURCE"
        reason = (
            clean(reason, self.secrets)
            if isinstance(reason, str) or reason is None
            else ("CAPTURE_REASON_INVALID")
        )
        if not isinstance(source, str) or not re.fullmatch(r"[A-Z0-9_]{1,128}", source):
            source = "UNKNOWN_SOURCE"
        if reason is not None and (
            not isinstance(reason, str) or not re.fullmatch(r"[A-Z0-9_]{1,256}", reason)
        ):
            reason = "CAPTURE_REASON_INVALID"
        if not isinstance(verdict, str) or verdict not in {"PASS", "REJECTED", "INCOMPLETE"}:
            verdict = "INCOMPLETE"
        with self.lock, self.db:
            self.db.execute(
                "INSERT INTO rfq_evidence_v2 (captured_at,vendor,chain_id,verdict,reason,source,"
                "schema_version,digest,size,payload) VALUES (?,?,?,?,?,?,2,?,?,?)",
                (
                    datetime.now(UTC).isoformat(),
                    vendor,
                    chain,
                    verdict,
                    reason,
                    source,
                    digest,
                    len(text.encode()),
                    text,
                ),
            )
            while True:
                count, size = self.db.execute(
                    "SELECT count(*),coalesce(sum(size + length(captured_at) + "
                    "coalesce(length(vendor),0) + length(chain_id) + length(verdict) + "
                    "coalesce(length(reason),0) + length(source) + length(digest)),0) "
                    "FROM rfq_evidence_v2"
                ).fetchone()
                if count <= MAX_CAPTURE_ROWS and size <= MAX_CAPTURE_TOTAL_BYTES:
                    break
                self.db.execute(
                    "DELETE FROM rfq_evidence_v2 WHERE id=(SELECT min(id) FROM rfq_evidence_v2)"
                )

    def rfq_captures(self, limit=50, *, internal=False):
        with self.lock:
            rows = self.db.execute(
                "SELECT captured_at,vendor,chain_id,verdict,reason,source,schema_version,digest,"
                "size,payload FROM rfq_evidence_v2 ORDER BY id DESC LIMIT ?",
                (min(max(limit, 1), 128),),
            ).fetchall()
        keys = (
            "captured_at vendor chain_id verdict reason source schema_version digest size payload"
        )
        result = []
        for row in rows:
            record = dict(zip(keys.split(), row, strict=True))
            text = record.pop("payload")
            valid = hashlib.sha256(text.encode()).hexdigest() == record["digest"]
            record["integrity"] = "PASS" if valid else "FAIL"
            if internal and valid:
                record["payload"] = json.loads(text)
            result.append(record)
        return result

    def activity(self, now=None):
        now = now or datetime.now(UTC)
        with self.lock:
            rows = self.db.execute(
                "SELECT status,realized_cost_usd,updated_at FROM fills WHERE updated_at>=?",
                ((now - timedelta(days=1)).isoformat(),),
            ).fetchall()
        done = [r for r in rows if r[0] not in {"REJECTED", "NOT_FILLED"}]
        last = max((datetime.fromisoformat(r[2]) for r in done), default=None)
        loss = sum((Decimal(r[1]) for r in done if r[1] is not None), Decimal(0))
        return len(done), last, max(loss, Decimal(0))

    @staticmethod
    def _row(row):
        record = dict(zip(COLUMNS, row, strict=True))
        record["evidence"] = json.loads(record["evidence"])
        record["reasons"] = json.loads(record["reasons"])
        return record
