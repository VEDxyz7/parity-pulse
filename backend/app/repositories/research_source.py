"""Bounded offline source loader: SQLite read-only and existing primary raw captures only."""

import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from app.models.data import EquityObservation, NewsEvent, TokenMetadata, TokenObservation
from app.models.research import RawTokenBar
from app.models.trust import TrustEpisode, TrustSample
from app.repositories.historical_inputs import (
    BACKFILL_NAME,
    DIRECTORY,
    input_metadata,
    read_historical_input,
)
from app.services.research_episodes import fingerprint

TABLES = {
    "token_metadata": TokenMetadata,
    "token_observations": TokenObservation,
    "equity_observations": EquityObservation,
    "news_events": NewsEvent,
    "trust_samples": TrustSample,
    "trust_episodes": TrustEpisode,
}


class HistoricalSource:
    """No credentials/configured provider clients; immutable original availability retained."""

    def __init__(self, root):
        self.root = Path(root)
        self.records = defaultdict(list)
        self.provenance = []
        self.rejected = Counter()

    def load(self):
        self.records.clear()
        self.provenance.clear()
        self.rejected.clear()
        unique = {name: {} for name in TABLES}
        for path in sorted((self.root / "data").glob("*.db")):
            snapshot = {}
            # URI mode=ro cannot initialize schemas or write execution state.
            with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
                connection.execute("PRAGMA query_only=ON")
                connection.execute("BEGIN")
                tables = {
                    r[0]
                    for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                for name, model in TABLES.items():
                    if name not in tables:
                        continue
                    rows = connection.execute(
                        f"SELECT id,payload FROM {name} "
                        "WHERE data_mode='LIVE' ORDER BY id LIMIT 20001"
                    ).fetchall()
                    if len(rows) > 20000:
                        raise ValueError("Historical source read bound exceeded")
                    snapshot[name] = rows
                    for identifier, raw in rows:
                        try:
                            record = model.model_validate_json(raw)
                        except ValueError:
                            self.rejected[name + ":MALFORMED"] += 1
                            continue
                        mode = (
                            record.sample.data_mode
                            if isinstance(record, TrustEpisode)
                            else record.data_mode
                        )
                        if mode != "LIVE":
                            self.rejected[name + ":MODE_CONFLICT"] += 1
                            continue
                        previous = unique[name].get(identifier)
                        if previous is not None:
                            # Copies can retain different receipt times/quality. Any conflicting
                            # prices/identity/version must stop, not silently choose a capture.
                            excluded = {"ingestion_timestamp", "data_quality"}
                            old, new = previous.model_dump(), record.model_dump()
                            if {k: v for k, v in old.items() if k not in excluded} != {
                                k: v for k, v in new.items() if k not in excluded
                            }:
                                raise ValueError("Conflicting source identity")
                            if getattr(record, "ingestion_timestamp", None) is not None:
                                record = min(
                                    (previous, record), key=lambda r: r.ingestion_timestamp
                                )
                        unique[name][identifier] = record
            self.provenance.append(str(path.relative_to(self.root)) + ":" + fingerprint(snapshot))
        for name, rows in unique.items():
            self.records[name] = sorted(rows.values(), key=fingerprint)
        raw_path = self.root / DIRECTORY / BACKFILL_NAME
        if raw_path.exists() or (self.root / DIRECTORY / "manifest.json").exists():
            raw = read_historical_input(self.root, BACKFILL_NAME)
            if raw.get("evidence_kind") is None or raw.get("execution_calls") != 0:
                raise ValueError("Unverified diagnostic capture")
            for bar in raw["token_bars"]:
                if (
                    bar.get("synthetic") is not False
                    or bar.get("historical_ratio") is not None
                    or bar.get("source") != "BINANCE_MARKET"
                ):
                    raise ValueError("Unverified raw token history")
                self.records["raw_token_bars"].append(
                    RawTokenBar(
                        source=bar["source"],
                        provider_identifier=bar["contract"],
                        source_timestamp=bar["start_utc"],
                        raw_source_timestamp=str(bar["raw_timestamp_ms"]),
                        timestamp_unit="ms",
                        ingestion_timestamp=bar["first_seen"],
                        data_mode="LIVE",
                        data_quality="HISTORICAL",
                        ticker=bar["ticker"],
                        issuer=bar["issuer"],
                        chain_id=bar["chain"],
                        contract=bar["contract"],
                        interval=bar["interval"],
                        token_price=bar["close"],
                        volume=bar["volume"],
                    )
                )
            for bar in raw["equity_bars"]:
                if bar.get("synthetic") is not False or bar["source"] != "MASSIVE":
                    raise ValueError("Unverified equity capture")
                self.records["equity_observations"].append(
                    EquityObservation(
                        source="MASSIVE",
                        provider_identifier=bar["ticker"],
                        source_timestamp=bar["start_utc"],
                        raw_source_timestamp=bar["start_utc"],
                        timestamp_unit="RFC3339",
                        ingestion_timestamp=bar["first_seen"],
                        data_mode="LIVE",
                        data_quality="HISTORICAL",
                        ticker=bar["ticker"],
                        price=bar["close"],
                        open=bar["open"],
                        high=bar["high"],
                        low=bar["low"],
                        close=bar["close"],
                        volume=bar["volume"],
                        kind="BAR",
                        interval=bar["interval"],
                        adjusted=bar["adjusted"],
                    )
                )
            # Logical provenance identifies the original capture, not its storage location.
            identity = input_metadata(self.root, BACKFILL_NAME)["original_path"]
            self.provenance.append(identity + ":" + fingerprint(raw))
        # Event deduplication is independent of provider_identifier serialization differences
        # between application records and raw files. Earliest actual ingestion wins.
        for name in ("raw_token_bars", "equity_observations"):
            by_event = {}
            for row in self.records[name]:
                key = (
                    row.source,
                    row.ticker,
                    getattr(row, "contract", None),
                    getattr(row, "kind", None),
                    row.interval,
                    row.source_timestamp,
                )
                old = by_event.get(key)
                if old is not None:
                    values = (
                        getattr(
                            row, "close", row.token_price if isinstance(row, RawTokenBar) else None
                        ),
                        getattr(row, "adjusted", None),
                    )
                    prior = (
                        getattr(
                            old, "close", old.token_price if isinstance(old, RawTokenBar) else None
                        ),
                        getattr(old, "adjusted", None),
                    )
                    if values != prior:
                        raise ValueError("Conflicting historical event revisions")
                    row = min((old, row), key=lambda r: r.ingestion_timestamp)
                by_event[key] = row
            self.records[name] = sorted(by_event.values(), key=fingerprint)
        return self

    def coverage(self):
        result = {}
        tokens = [*self.records["token_observations"], *self.records["raw_token_bars"]]
        for issuer in sorted({p.issuer for p in tokens}):
            by_event = {}
            for p in tokens:
                if p.issuer == issuer and p.kind == "CANDLE":
                    by_event[(p.source, p.contract, p.interval, p.source_timestamp)] = p
            rows = list(by_event.values())
            times = [p.source_timestamp for p in rows if p.source_timestamp]
            result[issuer] = {
                "historical_candles": len(rows),
                "start": min(times).isoformat() if times else None,
                "end": max(times).isoformat() if times else None,
                "interval_counts": dict(Counter(p.interval for p in rows)),
                "historical_ratio": "UNAVAILABLE",
            }
        equity = self.records["equity_observations"]
        bars = [b for b in equity if b.kind == "BAR"]
        return {
            "representations": result,
            "unique_existing_token_records": len(self.records["token_observations"]),
            "unique_primary_raw_bars": len(self.records["raw_token_bars"]),
            "equity_bar_count": len(bars),
            "equity_interval_counts": dict(Counter(b.interval for b in bars)),
            "equity_start": min(b.source_timestamp for b in bars).isoformat() if bars else None,
            "equity_end": max(b.source_timestamp for b in bars).isoformat() if bars else None,
            "persisted_real_baseline_episodes": len(self.records["trust_episodes"]),
            "persisted_real_trust_samples": len(self.records["trust_samples"]),
            "malformed_rows": dict(self.rejected),
            "loaded_at": None,  # No wall-clock values in reproducibility identities.
        }
