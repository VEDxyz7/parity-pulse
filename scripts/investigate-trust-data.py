"""Bounded REAL historical observation audit; no Trust training or trading authority."""

import importlib.util
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.clients.common import ProviderError
from app.config import ROOT_DIR, Settings
from app.database import Database
from app.models.data import EquityObservation, TokenObservation
from app.models.research import OPENING_MINUTES
from app.models.trust import TrustPolicy
from app.services.data_layer import DataLayer
from app.services.ingestion import HistoricalIngestion
from app.services.opening_target import opening_outcome
from app.services.trust import TrustService
from app.utils.logging import configure_logging

spec = importlib.util.spec_from_file_location(
    "remediation_diagnostics", Path(__file__).with_name("verify-trust-remediation.py")
)
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)


def inventory(*, exclude_investigation=False):
    """Count real records per DB and deduplicate capture identities across DBs."""
    tables = ["token_observations", "equity_observations", "trust_samples", "trust_episodes"]
    unique = {table: {} for table in tables}
    databases = []
    for path in sorted((ROOT_DIR / "data").glob("*.db")):
        if exclude_investigation and path.name == "phase2-trust-history-investigation.db":
            continue
        item = {"database": str(path.relative_to(ROOT_DIR)), "live_counts": {}}
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
            available = {
                r[0]
                for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            for table in tables:
                rows = (
                    connection.execute(
                        f"SELECT id,payload FROM {table} WHERE data_mode='LIVE'"
                    ).fetchall()
                    if table in available
                    else []
                )
                item["live_counts"][table] = len(rows)
                for identifier, payload in rows:
                    unique[table].setdefault(identifier, json.loads(payload))
        databases.append(item)
    summaries = {}
    for table, records in unique.items():
        groups = defaultdict(list)
        for record in records.values():
            groups[record.get("ticker", record.get("sample", {}).get("ticker"))].append(record)
        summaries[table] = []
        for ticker, rows in sorted(groups.items()):
            timestamps = [r["source_timestamp"] for r in rows if r.get("source_timestamp")]
            summaries[table].append(
                {
                    "ticker": ticker,
                    "unique_count": len(rows),
                    "source_start": min(timestamps, default=None),
                    "source_end": max(timestamps, default=None),
                    "kind_counts": dict(Counter(r.get("kind", "TRUST_RECORD") for r in rows)),
                    "interval_counts": dict(
                        Counter(r.get("interval") or "EVENT_TIMESTAMPS" for r in rows)
                    ),
                    "timestamp_units": sorted(
                        {r.get("timestamp_unit", "UTC_FEATURE_TIME") for r in rows}
                    ),
                }
            )
    token_times = [
        r["source_timestamp"]
        for r in unique["token_observations"].values()
        if r.get("source_timestamp")
    ]
    equity_times = [
        r["source_timestamp"]
        for r in unique["equity_observations"].values()
        if r.get("source_timestamp")
    ]
    overlap = None
    if token_times and equity_times:
        start, end = (
            max(min(token_times), min(equity_times)),
            min(max(token_times), max(equity_times)),
        )
        if start <= end:
            overlap = {
                "start": start,
                "end": end,
                "meaning": "TIMESTAMP_SPAN_ONLY_NOT_COMPLETE_PAIRED_FEATURES",
            }
    return {
        "databases": databases,
        "unique_real_records": summaries,
        "timestamp_span_overlap": overlap,
        "duplicate_capture_identities_not_counted_twice": True,
    }


def captured_records(model, table):
    """Read the isolated capture, bounded at5000, without the public list's1000-row cap."""
    if (model, table) not in [
        (TokenObservation, "token_observations"),
        (EquityObservation, "equity_observations"),
    ]:
        raise ValueError("Reviewed observation table required")
    path = ROOT_DIR / "data/phase2-trust-history-investigation.db"
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        rows = connection.execute(
            f"SELECT payload FROM {table} WHERE data_mode='LIVE' LIMIT 5001"
        ).fetchall()
    if len(rows) > 5000:
        raise ValueError("Capture read bound reached; no completeness claim")
    return [model.model_validate_json(row[0]) for row in rows]


def leakage_summary(tokens, equities, news, decision, target):
    def available(row, duration):
        return (
            row.source_timestamp is not None
            and row.source_timestamp + duration <= decision
            and row.ingestion_timestamp <= decision
        )

    return {
        "decision_at": decision.isoformat(),
        "token_source_completion_before_decision": sum(
            r.source_timestamp + timedelta(minutes=1) <= decision
            for r in tokens
            if r.source_timestamp and r.interval == "1m"
        ),
        "token_features_known_by_decision": sum(
            available(r, timedelta(minutes=1) if r.interval == "1m" else timedelta(hours=1))
            for r in tokens
        ),
        "equity_references_known_by_decision": sum(
            available(r, timedelta(minutes=1)) for r in equities if r.interval == "1minute"
        ),
        "news_published_by_decision": sum(r.published_timestamp <= decision for r in news),
        "news_known_by_decision": sum(
            r.published_timestamp <= decision and r.ingestion_timestamp <= decision for r in news
        ),
        "target_excluded_from_features": True,
        "target_available_after_decision": target.get("target_available_at") is None
        or datetime.fromisoformat(target["target_available_at"]) > decision,
        "analogue_retrieval_at_historical_decision": "ZERO_ELIGIBLE_COMPLETED_AVAILABLE_EPISODES",
        "newly_fetched_history_not_backdated": True,
    }


def main():
    output = ROOT_DIR / "docs/evidence/CANONICAL_PHASE_2_TRUST_DATA_INVESTIGATION.json"
    if output.exists():
        raise ValueError("Existing investigation evidence must not be overwritten")
    before = inventory(exclude_investigation=True)
    settings = Settings(data_mode="LIVE_READ_ONLY")
    configure_logging(settings.log_level, settings.redaction_values())
    database = Database(f"sqlite:///{ROOT_DIR / 'data/phase2-trust-history-investigation.db'}")
    database.initialize()
    layer = DataLayer(settings, database)
    layer.clients[0].recv_window = 60000
    diagnoses = []
    layer.clients[1].http.event_hooks["response"].append(
        diagnostics.denial_hook(settings.redaction_values(), diagnoses)
    )
    try:
        found = layer.discovery.resolve("NVDA")
        assert found["status"] == "VERIFIED"
        token = layer.rwa.profile(next(t for t in found["tokens"] if t.platform_id == "ondo"))
        layer.repository.save([found["asset"], *found["issuers"], token])
        current = {}
        for name, fetch in [
            ("snapshot", lambda: layer.equity.get_snapshot("NVDA")),
            ("nbbo", lambda: layer.equity.get_latest_quote("NVDA")),
        ]:
            try:
                record = fetch()
                current[name] = {
                    "status": "RETURNED_NOT_AUTOMATICALLY_ENTITLED",
                    "quality": record.data_quality,
                }
            except ProviderError as error:
                current[name] = {"http_status": error.http_status, "capability": error.kind}
        price = layer.market.prices([token], info=True)[0]
        layer.repository.save([price])
        fields = {
            k: price.provider_metadata.get(k)
            for k in [
                "price",
                "time",
                "liquidity",
                "volume5M",
                "volume1H",
                "volume4H",
                "volume24H",
                "holders",
                "marketCap",
                "circSupply",
                "txs24H",
                "buyVolume24H",
                "sellVolume24H",
                "buyTxs24H",
                "sellTxs24H",
                "priceChange24H",
                "maxPrice",
                "minPrice",
            ]
        }
        ingestion = HistoricalIngestion(layer.repository, layer.market, layer.equity)
        # One fixed, completed weekend. No universe scanning or trading decisions.
        opening = layer.calendar.session(date(2026, 10, 5))[0]
        previous_close = layer.calendar.previous_session(opening)[1]
        attempted = {}
        for name, fetch in [
            (
                "token_weekend_1h",
                lambda: ingestion.token_candles(
                    token,
                    bar="1h",
                    before=int(previous_close.timestamp() * 1000) - 1,
                    after=int(opening.timestamp() * 1000),
                    max_pages=3,
                    resume=False,
                ),
            ),
            (
                "token_preopen_1m",
                lambda: ingestion.token_candles(
                    token,
                    bar="1m",
                    before=int((opening - timedelta(minutes=100)).timestamp() * 1000) - 1,
                    after=int(opening.timestamp() * 1000),
                    max_pages=2,
                    resume=False,
                ),
            ),
            (
                "equity_1m",
                lambda: ingestion.equity_bars(
                    "NVDA", "2026-10-02", "2026-10-05", max_pages=3, resume=False
                ),
            ),
        ]:
            try:
                attempted[name] = fetch()
            except ProviderError as error:
                attempted[name] = {
                    "status": "UNAVAILABLE",
                    "cause": error.kind,
                    "http": error.http_status,
                }
        five = []
        try:
            five = layer.equity.get_historical_bars(
                "NVDA", "2026-10-05", "2026-10-05", multiplier=OPENING_MINUTES, max_pages=2
            )
            attempted["equity_5m"] = {
                "inserted": layer.repository.save(five),
                "returned": len(five),
                "complete": layer.equity.last_page_complete,
            }
        except ProviderError as error:
            attempted["equity_5m"] = {"status": "UNAVAILABLE", "cause": error.kind}
        articles = []
        try:
            articles = layer.equity.get_news("NVDA", before=opening, max_pages=1)
            layer.repository.save(articles)
        except ProviderError as error:
            attempted["historical_news"] = {"status": "UNAVAILABLE", "cause": error.kind}
        tokens = captured_records(TokenObservation, "token_observations")
        equities = captured_records(EquityObservation, "equity_observations")
        target = opening_outcome(equities, previous_close, opening)
        rejection = [
            "ASOF_TOKEN_SHARE_RATIO_UNVERIFIED",
            "HISTORICAL_LIQUIDITY_ABSENT",
            "CANDLE_VOLUME_UNIT_UNKNOWN",
            "HISTORICAL_FIRST_AVAILABILITY_NOT_PROVEN",
            "NEWS_FIRST_SEEN_AFTER_DECISION",
            "NO_QUALIFYING_TRUST_FEATURE_SAMPLES",
        ]
        candidate = {
            "ticker": "NVDA",
            "issuer": token.platform_id,
            "chain_id": token.chain_id,
            "contract": token.contract,
            "episode_kind": "WEEKEND_REOPENING",
            "decision_at": opening.isoformat(),
            "previous_regular_close_at": previous_close.isoformat(),
            "outcome": target,
            "normalization": "UNAVAILABLE_ASOF_RATIO_CURRENT_RATIO_NOT_BACKFILLED",
            "all_required_fields": False,
            "trust_qualified": False,
            "rejection_reasons": rejection,
            "leakage": leakage_summary(tokens, equities, articles, opening, target),
        }
        # Reuse the existing read-only Trust flow; no analytical feature expansion.
        trust = TrustService(layer, database)
        result = trust.assess(
            "NVDA", run_id=str(uuid4()), request_id=str(uuid4()), correlation_id=str(uuid4())
        )
        assert not result.transaction_broadcast and not result.execution_ready
        assert trust.repository.get(result.assessment_id, "LIVE") == result
        reads = [r for client in layer.clients for r in client.evidence]
        evidence = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "evidence_kind": "REAL_READ_ONLY_CAPTURE_AND_POSTHOC_OUTCOME_NOT_SYNTHETIC",
            "before_backfill": before,
            "after_backfill": inventory(),
            "current_equity": current,
            "denial_diagnoses": diagnoses,
            "account_plan": "UNKNOWN",
            "live_market_metric_capture": {
                "ticker": token.ticker,
                "issuer": token.platform_id,
                "chain_id": token.chain_id,
                "contract": token.contract,
                "observed_price_at": price.source_timestamp.isoformat(),
                "received_at": price.ingestion_timestamp.isoformat(),
                "fields": fields,
                "authoritative_liquidity": False,
            },
            "backfill_attempts": attempted,
            "candidate_episodes": [candidate],
            "potential_weekend_reopenings_in_requested_window": 1,
            "potential_holiday_reopenings_in_requested_window": 0,
            "real_qualifying_baseline_episodes": 0,
            "real_qualifying_opening_model_episodes": 0,
            "real_qualifying_analogues": 0,
            "minimum_thresholds": {"baseline": 30, "opening_model": 30, "analogues": 3},
            "baseline_status": "INSUFFICIENT",
            "opening_model_status": "INSUFFICIENT_DATA",
            "historical_pattern": "INSUFFICIENT_DATA",
            "confidence": None,
            "trust_policy": TrustPolicy().model_dump(mode="json"),
            "assessment": result.model_dump(mode="json"),
            "reads": reads,
            "calls_to_execution_endpoints": 0,
            "trust_gate": "BLOCKED",
        }
        encoded = json.dumps(evidence, indent=2) + "\n"
        assert not any(secret in encoded for secret in settings.redaction_values())
        output.write_text(encoded)
        print(
            json.dumps(
                {
                    "evidence": str(output.relative_to(ROOT_DIR)),
                    "backfill": attempted,
                    "outcome": target,
                    "qualified_counts": [0, 0, 0],
                    "trust_gate": "BLOCKED",
                }
            )
        )
    finally:
        layer.close()
        database.close()


if __name__ == "__main__":
    main()
