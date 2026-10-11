"""Isolated NVDA Twelve Data reads; no production integration or database writes."""

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "free_provider_diagnostic", Path(__file__).with_name("diagnose-free-providers.py")
)
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)

from app.utils.artifacts import diagnostic_output  # noqa: E402


def age_seconds(received, observed):
    delta = received - observed
    return Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / 1000000


def quote_check(body, received):
    if not body:
        return {"result": "FAIL", "reason": "NO_VALID_RESPONSE", "freshness": "FAIL"}
    fields = [
        "symbol",
        "name",
        "exchange",
        "mic_code",
        "currency",
        "datetime",
        "timestamp",
        "last_quote_at",
        "close",
        "is_market_open",
        "is_extended_hours",
        "type",
    ]
    actual = {k: body.get(k) for k in fields}
    timestamps = {}
    for name in ["timestamp", "last_quote_at"]:
        value = body.get(name)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            observed = datetime.fromtimestamp(value, UTC)
            age = age_seconds(received, observed)
            timestamps[name] = {
                "raw_seconds": value,
                "utc": observed.isoformat(),
                "age_at_receipt_seconds": str(age),
                "passes_120s_age": 0 <= age <= 120,
                "semantics": "SELECTED_INTERVAL_OPEN"
                if name == "timestamp"
                else "LAST_MINUTE_CANDLE_TIME",
            }
    identity = body.get("symbol") == "NVDA" and body.get("currency") == "USD"
    try:
        price = Decimal(body["close"])
        valid_price = price.is_finite() and price > 0
    except Exception:
        valid_price = False
    # Use the selected one-minute interval's documented bar-start timestamp;
    # last_quote_at is separately reported, never recast as an exact trade time.
    fresh = bool(timestamps.get("timestamp", {}).get("passes_120s_age"))
    return {
        "result": "PASS" if identity and valid_price and fresh else "FAIL",
        "freshness": "PASS" if fresh else "FAIL",
        "actual_fields": actual,
        "timestamps": timestamps,
        "received_at": received.isoformat(),
        "identity_and_positive_price": identity and valid_price,
        "price_timestamp_is_exact_last_trade": False,
        "token_equity_skew_30s": "NOT_TESTED_TWELVE_DATA_ONLY_SCOPE",
        "production_reference_source_allowlist": "MASSIVE_ONLY_UNCHANGED",
        "production_data_quality_assigned": False,
    }


def history_check(body, interval, received):
    if not body or body.get("status") != "ok":
        return {"result": "FAIL", "reason": "NO_VALID_HISTORY", "interval": interval}
    meta = body.get("meta", {})
    rows, invalid = [], 0
    for row in body.get("values", []):
        try:
            ts = datetime.fromisoformat(row["datetime"]).replace(tzinfo=UTC)
            prices = {k: Decimal(row[k]) for k in ["open", "high", "low", "close"]}
            if not all(p.is_finite() and p > 0 for p in prices.values()):
                raise ValueError("Nonpositive/nonfinite historical price")
            if (
                not prices["low"]
                <= min(prices["open"], prices["close"])
                <= max(prices["open"], prices["close"])
                <= prices["high"]
            ):
                raise ValueError("Inconsistent OHLC")
            if ts + timedelta(minutes=1 if interval == "1min" else 5) > received:
                raise ValueError("Uncompleted historical bar")
            rows.append(
                {
                    "start_utc": ts.isoformat(),
                    **{k: str(v) for k, v in prices.items()},
                    "volume": row.get("volume"),
                }
            )
        except Exception:
            invalid += 1
    rows.sort(key=lambda r: r["start_utc"])
    valid_identity = (
        meta.get("symbol") == "NVDA"
        and meta.get("currency") == "USD"
        and meta.get("interval") == interval
    )
    starts = [datetime.fromisoformat(r["start_utc"]) for r in rows]
    duplicates = len(starts) - len(set(starts))
    return {
        "result": "PASS"
        if valid_identity and rows and invalid == 0 and duplicates == 0
        else "FAIL",
        "data_use": "HISTORICAL_ONLY_NOT_CURRENT_OR_LIVE_REFERENCE",
        "meta": meta,
        "interval": interval,
        "bar_count": len(rows),
        "invalid_rows": invalid,
        "duplicate_timestamps": duplicates,
        "earliest": starts[0].isoformat() if starts else None,
        "latest": starts[-1].isoformat() if starts else None,
        "maximum_gap_seconds": max(
            ((b - a).total_seconds() for a, b in zip(starts, starts[1:], strict=False)),
            default=None,
        ),
        "requested_timezone": "UTC",
        "requested_adjustment": "splits",
        "first_seen": received.isoformat(),
        "historical_first_availability_or_revision_verified": False,
        "synthetic_fill": False,
        "bars": rows,
    }


def opening_control(one, five):
    previous = [r for r in one.get("bars", []) if r["start_utc"] == "2026-10-02T19:59:00+00:00"]
    target = [r for r in five.get("bars", []) if r["start_utc"] == "2026-10-05T13:30:00+00:00"]
    if not previous or not target:
        return {"status": "UNSCORABLE", "reason": "EXACT_PREVIOUS_CLOSE_OR_FIRST_5M_BAR_ABSENT"}
    p, t = Decimal(previous[0]["close"]), Decimal(target[0]["close"])
    with localcontext() as ctx:
        ctx.prec = 256
        value = (t - p) / p
    return {
        "status": "POSTHOC_EQUITY_TARGET_ONLY_NOT_TRUST_EPISODE",
        "previous_regular_close": str(p),
        "first_5m_close": str(t),
        "opening_return": str(value),
        "target_completed_at": "2026-10-05T13:35:00+00:00",
        "historical_ratio_or_liquidity_verified": False,
        "outcome_is_decision_feature": False,
    }


def main():
    output = diagnostic_output(diagnostic.ROOT, "TWELVE_DATA_NVDA_AUTHENTICATED_FEASIBILITY.json")
    if output.exists():
        raise ValueError("Existing evidence must not be overwritten")
    probe = diagnostic.Probe()
    if not probe.keys["TWELVE_DATA_API_KEY"]:
        probe.http.close()
        raise ValueError("Configured Twelve Data key absent; no call made")
    try:
        result = {
            "started_at": datetime.now(UTC).isoformat(),
            "evidence_kind": "REAL_AUTHENTICATED_READ_ONLY_TWELVE_DATA_DIAGNOSTIC",
        }
        quote_params = {"symbol": "NVDA", "interval": "1min", "timezone": "UTC", "dp": 11}
        body = probe.get("twelve", "/quote", quote_params)
        received = datetime.fromisoformat(probe.ledger[-1]["received_at"])
        result["quote_first"] = quote_check(body, received)
        histories = {}
        for interval in ["1min", "5min"]:
            body = probe.get(
                "twelve",
                "/time_series",
                {
                    "symbol": "NVDA",
                    "interval": interval,
                    "timezone": "UTC",
                    "dp": 11,
                    "start_date": "2026-10-02 00:00:00",
                    "end_date": "2026-10-05 23:59:59",
                    "outputsize": 5000,
                    "order": "ASC",
                    "prepost": "false",
                    "adjust": "splits",
                },
            )
            received = datetime.fromisoformat(probe.ledger[-1]["received_at"])
            histories[interval] = history_check(body, interval, received)
        result["historical"] = histories
        body = probe.get("twelve", "/quote", quote_params)
        received = datetime.fromisoformat(probe.ledger[-1]["received_at"])
        result["quote_recheck"] = quote_check(body, received)
        result["opening_equity_control"] = opening_control(histories["1min"], histories["5min"])
        result["results"] = {
            "TWELVE_DATA_CURRENT_EQUITY": "PASS"
            if all(result[k]["result"] == "PASS" for k in ["quote_first", "quote_recheck"])
            else "FAIL",
            "TWELVE_DATA_HISTORICAL": "PASS"
            if all(h["result"] == "PASS" for h in histories.values())
            else "FAIL",
            "TWELVE_DATA_FRESHNESS": "PASS"
            if all(result[k]["freshness"] == "PASS" for k in ["quote_first", "quote_recheck"])
            else "FAIL",
        }
        result.update(
            {
                "completed_at": datetime.now(UTC).isoformat(),
                "reads": probe.ledger,
                "production_writes": 0,
                "execution_calls": 0,
                "trust_gate_modified": False,
                "account_subscription_identity": "NOT_INSPECTED",
                "public_redisplay_license_verified": False,
            }
        )
        text = json.dumps(result, indent=2, default=str) + "\n"
        protected = [*probe.secrets, *[key for key in probe.keys.values() if key]]
        assert all(secret not in text for secret in protected), (
            "Configured secret detected; output suppressed"
        )
        output.write_text(text)
        print(
            json.dumps(
                {
                    "artifact": str(output.relative_to(diagnostic.ROOT)),
                    "results": result["results"],
                    "network_reads": len(probe.ledger),
                    "production_writes": 0,
                }
            )
        )
    finally:
        probe.http.close()


if __name__ == "__main__":
    main()
