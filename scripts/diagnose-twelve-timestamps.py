"""Isolated GET-only NVDA timestamp observation; never imported by production."""

import argparse
import importlib.util
import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

spec = importlib.util.spec_from_file_location(
    "free_provider_diagnostic", Path(__file__).with_name("diagnose-free-providers.py")
)
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


def age(received, observed):
    delta = received - observed
    return Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / 1000000


def record(body, received):
    if not isinstance(body, dict):
        return {"received_at_utc": received.isoformat(), "valid": False}
    fields = {
        name: body.get(name)
        for name in [
            "symbol",
            "currency",
            "exchange",
            "mic_code",
            "close",
            "timestamp",
            "datetime",
            "last_quote_at",
            "is_market_open",
        ]
    }
    result = {"returned": fields, "received_at_utc": received.isoformat(), "ages": {}}
    for name in ["timestamp", "last_quote_at"]:
        value = fields[name]
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            observed = datetime.fromtimestamp(value, UTC)
            seconds = age(received, observed)
            result["ages"][name] = {
                "utc": observed.isoformat(),
                "receipt_minus_field_seconds": str(seconds),
                "within_unchanged_120s": 0 <= seconds <= 120,
            }
    try:
        price = Decimal(fields["close"])
        good_price = price.is_finite() and price > 0
    except Exception:
        good_price = False
    result["valid"] = (
        fields["symbol"] == "NVDA"
        and fields["currency"] == "USD"
        and good_price
        and len(result["ages"]) == 2
        and all(Decimal(t["receipt_minus_field_seconds"]) >= 0 for t in result["ages"].values())
    )
    expected_datetime = result["ages"].get("timestamp", {}).get("utc")
    result["datetime_matches_candle_timestamp"] = expected_datetime is not None and fields[
        "datetime"
    ] == datetime.fromisoformat(expected_datetime).strftime("%Y-%m-%d %H:%M:%S")
    local = received.astimezone(ZoneInfo("America/New_York"))
    result["receipt_in_regular_clock_window"] = local.weekday() < 5 and (9, 30) <= (
        local.hour,
        local.minute,
    ) < (16, 0)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True, choices=["active", "closed"])
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--spacing", type=int, default=65)
    args = parser.parse_args()
    if args.count < (5 if args.session == "active" else 3) or not 8 <= args.spacing <= 300:
        parser.error("Require at least five active or three closed reads and 8–300s spacing")
    output = diagnostic.ROOT / f"docs/evidence/TWELVE_DATA_TIMESTAMP_{args.session.upper()}.json"
    if output.exists():
        raise ValueError("Existing evidence must not be overwritten")
    probe = diagnostic.Probe()
    if not probe.keys["TWELVE_DATA_API_KEY"]:
        probe.http.close()
        raise ValueError("Configured Twelve Data key absent; no call made")
    protected = [*probe.secrets, *[key for key in probe.keys.values() if key]]
    params = {"symbol": "NVDA", "interval": "1min", "timezone": "UTC", "dp": 11, "prepost": "false"}
    evidence = {
        "session_tested": args.session,
        "request_parameters": params,
        "planned_count": args.count,
        "spacing_seconds": args.spacing,
        "samples": [],
        "reads": [],
        "complete": False,
        "production_writes": 0,
        "execution_calls": 0,
        "trust_gate_modified": False,
        "freshness_threshold_seconds": 120,
        "exact_last_trade_timestamp_claimed": False,
    }
    try:
        for number in range(args.count):
            started = time.monotonic()
            body = probe.get("twelve", "/quote", params)
            received = datetime.fromisoformat(probe.ledger[-1]["received_at"])
            sample = record(body, received)
            evidence["samples"].append(sample)
            evidence["reads"] = probe.ledger
            evidence["complete"] = number + 1 == args.count
            text = json.dumps(evidence, indent=2, default=str) + "\n"
            assert all(secret not in text for secret in protected), (
                "Secret detected; output suppressed"
            )
            output.write_text(text)
            print(
                json.dumps(
                    {
                        "sample": number + 1,
                        "valid": sample["valid"],
                        "ages": sample.get("ages", {}),
                        "complete": evidence["complete"],
                    }
                ),
                flush=True,
            )
            if number + 1 < args.count:
                while (remaining := args.spacing - (time.monotonic() - started)) > 0:
                    time.sleep(min(remaining, 30))
    finally:
        probe.http.close()


if __name__ == "__main__":
    main()
