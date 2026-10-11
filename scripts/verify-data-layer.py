"""Explicit, bounded read-only Phase 2 verification. Never prints credential values."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.clients.common import ProviderError
from app.config import ROOT_DIR, Settings
from app.database import Database
from app.models.data import EquityObservation, NewsEvent, TokenObservation
from app.services.data_layer import DataLayer
from app.services.ingestion import HistoricalIngestion
from app.utils.artifacts import diagnostic_output
from app.utils.logging import configure_logging


def main(recv_window=5000):
    settings = Settings(data_mode="LIVE_READ_ONLY")
    configure_logging(settings.log_level, settings.redaction_values())
    db = Database(f"sqlite:///{ROOT_DIR / 'data/phase2-verification.db'}")
    db.initialize()
    layer = DataLayer(settings, db)
    if not 1 <= recv_window <= 60000:
        raise ValueError("Invalid receive window")
    layer.clients[0].recv_window = recv_window
    result = {
        "timestamp": datetime.now(UTC).isoformat(),
        "data_mode": "LIVE",
        "checks": [],
        "limitations": {},
        "live_execution": "BLOCKED",
        "binance_recv_window_ms": recv_window,
    }

    def check(name, action):
        try:
            value = action()
            result["checks"].append(
                {"capability": name, "payload_schema_validation": "PASS", "result": "PASS"}
            )
            print(json.dumps({"capability": name, "result": "PASS"}), flush=True)
            return value
        except (ProviderError, ValueError) as error:
            kind = error.kind if isinstance(error, ProviderError) else "VALIDATION_FAILED"
            result["checks"].append(
                {"capability": name, "payload_schema_validation": "NOT_VALIDATED", "result": kind}
            )
            print(json.dumps({"capability": name, "result": kind}), flush=True)
            return None

    try:
        detail = check(
            "NVDA stock-first RWA discovery/profile/ratio/price/market", lambda: layer.asset("NVDA")
        )
        if not detail or detail["status"] != "VERIFIED":
            raise ProviderError("VERIFICATION", "STOCK_DISCOVERY_FAILED")
        result["limitations"].update(detail["limitations"])
        result["discovered"] = [
            {
                "ticker": t.ticker,
                "issuer": t.platform_id,
                "chain": t.chain_id,
                "contract": t.contract,
                "symbol": t.token_symbol,
                "token_to_share_ratio": str(t.token_to_share_ratio),
                "market_state": t.market_state,
            }
            for t in detail["tokens"]
        ]
        tokens = detail["tokens"]
        for name, action in [
            ("market supported chains", layer.market.chains),
            ("market token search", lambda: layer.market.search("56", "NVDA")),
            ("market basic metadata", lambda: layer.market.basic_info(tokens[0])),
            ("market batch price", lambda: layer.market.prices(tokens)),
            ("market batch price-info", lambda: layer.market.prices(tokens, info=True)),
        ]:
            records = check(name, action)
            if records and isinstance(records, list) and isinstance(records[0], TokenObservation):
                layer.repository.save(records)
        ingestion = HistoricalIngestion(layer.repository, market=layer.market, equity=layer.equity)
        now = datetime.now(UTC)
        after = int((now - datetime(1970, 1, 1, tzinfo=UTC)).total_seconds()) * 1000
        before = after - 4 * 3600 * 1000
        result["token_history"] = check(
            "bounded resumable token candle ingestion",
            lambda: ingestion.token_candles(tokens[0], before=before, after=after, max_pages=2),
        )
        result["token_trades"] = check(
            "bounded token trades preserving unverified reported price units",
            lambda: ingestion.token_trades(tokens[0], max_pages=1, limit=5, resume=False),
        )
        session = layer.calendar.previous_session(now)
        day = session[0].astimezone(layer.calendar.zone).date().isoformat()
        result["equity_history"] = check(
            "independent Massive minute-history ingestion",
            lambda: ingestion.equity_bars("NVDA", day, day, max_pages=2, resume=False),
        )
        result["equity_idempotence"] = check(
            "independent history repeat is idempotent",
            lambda: ingestion.equity_bars("NVDA", day, day, max_pages=2, resume=False),
        )
        close = check(
            "independent last actual regular close",
            lambda: layer.equity.get_previous_regular_close("NVDA", now, layer.calendar),
        )
        if close:
            layer.repository.save([close])
            result["independent_equity"] = {
                "ticker": close.ticker,
                "source": close.source,
                "price": str(close.price),
                "raw_source_timestamp": close.raw_source_timestamp,
                "timestamp_unit": close.timestamp_unit,
                "source_timestamp": close.source_timestamp.isoformat(),
                "ingestion_timestamp": close.ingestion_timestamp.isoformat(),
                "data_quality": close.data_quality,
                "semantics": "LAST_COMPLETED_REGULAR_SESSION_CLOSE; not a current snapshot",
            }
        for name, action in [
            ("Massive market status", layer.equity.get_market_status),
            ("Massive holidays", layer.equity.get_market_holidays),
        ]:
            check(name, action)
        check("versioned NYSE calendar", lambda: layer.calendar.status(now))
        result["persisted"] = {
            model.__name__: len(layer.repository.list(model, mode="LIVE"))
            for model in [TokenObservation, EquityObservation, NewsEvent]
        }
        result["demo_partition"] = {
            model.__name__: len(layer.repository.list(model, mode="DEMO"))
            for model in [TokenObservation, EquityObservation, NewsEvent]
        }
        result["calls"] = [record for client in layer.clients for record in client.evidence]
        result["result"] = (
            "PASS" if all(row["result"] == "PASS" for row in result["checks"]) else "FAIL"
        )
    finally:
        layer.close()
        db.close()
        diagnostic_output(ROOT_DIR, "PHASE_2_PIPELINE.json").write_text(
            json.dumps(result, indent=2)
        )
    print(
        json.dumps(
            {
                "result": result["result"],
                "persisted": result["persisted"],
                "limitations": result["limitations"],
                "live_execution": "BLOCKED",
            }
        ),
        flush=True,
    )
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recv-window", type=int, default=5000)
    args = parser.parse_args()
    try:
        raise SystemExit(main(args.recv_window))
    except (ProviderError, ValueError) as error:
        print(
            json.dumps(
                {
                    "result": "FAIL",
                    "reason": error.kind
                    if isinstance(error, ProviderError)
                    else "VALIDATION_FAILED",
                }
            )
        )
        raise SystemExit(1) from None
