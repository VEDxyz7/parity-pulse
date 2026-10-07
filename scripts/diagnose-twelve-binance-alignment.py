"""Isolated regular-session paired market reads; never imported by production."""

import argparse
import importlib.util
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from dotenv import dotenv_values
from pydantic import SecretStr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.clients.binance_web3 import PREFIX, BinanceWeb3Client
from app.clients.common import ProviderError
from app.providers.binance import Price, validate
from app.services.calendar import USEquityCalendar

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "free_provider_diagnostic", Path(__file__).with_name("diagnose-free-providers.py")
)
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)

TOKENS = {
    "NVDAB": "0x02fca66c1d1afb4e2a7884261eb00f63598a7436",
    "NVDAon": "0xa9ee28c80f960b889dfbd1902055218cba016f75",
}
PRICE_PATH = PREFIX + "price"
QUOTE_PARAMS = {
    "symbol": "NVDA",
    "interval": "1min",
    "timezone": "UTC",
    "dp": 11,
    "prepost": "false",
}
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def seconds(delta):
    return Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / 1000000


def price(value):
    result = Decimal(value)
    if not result.is_finite() or result <= 0:
        raise ValueError("Invalid price")
    return str(result)


def secret_values():
    mappings = (dotenv_values(ROOT / ".env"), os.environ)
    return {
        v for mapping in mappings for k, v in mapping.items() if v and ("KEY" in k or "SECRET" in k)
    }


def save(path, text, protected):
    if any(value in text for value in protected):
        raise ValueError("Configured secret detected; output suppressed")
    path.write_text(text)


def equity_read(probe):
    body = probe.get("twelve", "/quote", QUOTE_PARAMS)
    ledger = probe.ledger[-1].copy()
    result = {"endpoint": "GET https://api.twelvedata.com/quote", "request": ledger, "valid": False}
    if not isinstance(body, dict):
        return result
    try:
        raw = body.get("last_quote_at")
        if type(raw) is not int or raw <= 0:
            raise ValueError("Missing actual equity timestamp")
        observed = EPOCH + timedelta(seconds=raw)
        received = datetime.fromisoformat(ledger["received_at"])
        result.update(
            {
                "symbol": body.get("symbol"),
                "currency": body.get("currency"),
                "last_quote_at": raw,
                "observation_timestamp_utc": observed.isoformat(),
                "is_market_open": body.get("is_market_open"),
                "price_usd": price(body.get("close")),
                "received_at_utc": received.isoformat(),
                "age_seconds": str(seconds(received - observed)),
                "timestamp_used": "last_quote_at_only; not candle-start timestamp",
            }
        )
        result["valid"] = body.get("symbol") == "NVDA" and body.get("currency") == "USD"
    except Exception:
        result["failure"] = "EQUITY_IDENTITY_PRICE_OR_TIMESTAMP_INVALID"
    return result


def token_read(client):
    started = datetime.now(UTC)
    result = {
        "endpoint": "POST https://web3.binance.com/build" + PRICE_PATH,
        "requested_at_utc": started.isoformat(),
        "valid": False,
        "tokens": {},
    }
    try:
        data, received, _ = client.read(
            "POST",
            PRICE_PATH,
            body=[{"binanceChainId": "56", "tokenContractAddress": c} for c in TOKENS.values()],
            ttl=0,
        )
        rows = validate(list[Price], data)
        index = {(r.binanceChainId, r.tokenContractAddress): r for r in rows}
        if len(index) != len(rows) or set(index) != {("56", c) for c in TOKENS.values()}:
            raise ValueError("Incomplete or conflicting batch")
        result["received_at_utc"] = received.isoformat()
        result["receipt_semantics"] = (
            "Existing read transport ingestion immediately after validation"
        )
        for symbol, contract in TOKENS.items():
            row = index[("56", contract)]
            if type(row.time) is not int or row.time <= 0:
                raise ValueError("Missing actual token observation timestamp")
            observed = EPOCH + timedelta(milliseconds=row.time)
            result["tokens"][symbol] = {
                "chain": "56",
                "contract": contract,
                "raw_time_ms": row.time,
                "observation_timestamp_utc": observed.isoformat(),
                "price_usd_per_token": price(row.price),
                "received_at_utc": received.isoformat(),
                "age_seconds": str(seconds(received - observed)),
                "timestamp_used": "per-token time; never envelope or receipt time",
            }
        result["valid"] = True
    except ProviderError as error:
        result["failure"] = error.kind
        result["http_status"] = error.http_status
        result["business_status"] = error.business_status
    except Exception:
        result["failure"] = "TOKEN_IDENTITY_PRICE_OR_TIMESTAMP_INVALID"
    result["read_ledger"] = client.evidence[-1:] if client.evidence else []
    return result


def pair(equity, token, regular):
    result = {
        "timestamp_difference_seconds": None,
        "receipt_difference_seconds": None,
        "within_30s": None,
        "eligible": False,
    }
    if not equity.get("valid") or token is None:
        result["rejection"] = "MISSING_OR_INVALID_PROVIDER_DATA"
        return result
    eq = datetime.fromisoformat(equity["observation_timestamp_utc"])
    tk = datetime.fromisoformat(token["observation_timestamp_utc"])
    eq_received = datetime.fromisoformat(equity["received_at_utc"])
    tk_received = datetime.fromisoformat(token["received_at_utc"])
    difference = abs(seconds(eq - tk))
    fresh = all(0 <= Decimal(v) <= 120 for v in [equity["age_seconds"], token["age_seconds"]])
    result.update(
        {
            "timestamp_difference_seconds": str(difference),
            "receipt_difference_seconds": str(abs(seconds(eq_received - tk_received))),
            "within_30s": difference <= 30,
            "both_sources_within_120s": fresh,
            "regular_session": regular,
            "equity_market_open": equity["is_market_open"],
            "eligible": regular and equity["is_market_open"] is True and fresh and difference <= 30,
        }
    )
    return result


def summarize(rounds, count):
    result = {}
    for symbol in [*TOKENS, "ALL"]:
        comparisons = [
            r["pairs"][s] for r in rounds for s in (TOKENS if symbol == "ALL" else [symbol])
        ]
        differences = [
            Decimal(p["timestamp_difference_seconds"])
            for p in comparisons
            if p["timestamp_difference_seconds"] is not None
        ]
        result[symbol] = {
            "expected_pairs": count * (2 if symbol == "ALL" else 1),
            "attempted_pairs": len(comparisons),
            "scorable_pairs": len(differences),
            "within_30s": sum(p["within_30s"] is True for p in comparisons),
            "outside_30s": sum(p["within_30s"] is False for p in comparisons),
            "unscorable": sum(p["within_30s"] is None for p in comparisons),
            "eligible_pairs": sum(p["eligible"] for p in comparisons),
            "maximum_difference_seconds": str(max(differences)) if differences else None,
            "median_difference_seconds": str(median(differences)) if differences else None,
        }
    all_pass = len(rounds) == count and result["ALL"]["eligible_pairs"] == 2 * count
    return {
        "TWELVE_BINANCE_30S_ALIGNMENT": "PASS" if all_pass else "FAIL",
        "by_representation": result,
    }


def report(evidence):
    conclusion = evidence["summary"]["TWELVE_BINANCE_30S_ALIGNMENT"]
    lines = [
        "# Twelve Data / Binance — read-only NVDA timestamp alignment",
        "",
        f"`TWELVE_BINANCE_30S_ALIGNMENT={conclusion}`",
        "",
        f"Actual rounds:{len(evidence['rounds'])}; planned:10; representations per round:2.",
        "Pairs use Twelve Data last_quote_at and Binance per-token time (Unix milliseconds).",
        "Concurrent requests; no source-time substitution or local cached replay,",
        "historical matching, phase targeting or retry-until-aligned strategy is used.",
        "",
        "Equity endpoint: GET https://api.twelvedata.com/quote; NVDA, interval=1min, timezone=UTC.",
        "Token endpoint: POST https://web3.binance.com/build/api/v1/dex/market/price.",
        "POST reads prices only; the batch specifies both verified BSC token contracts.",
        "",
    ]
    for symbol, contract in TOKENS.items():
        stats = evidence["summary"]["by_representation"][symbol]
        lines.extend(
            [
                f"## {symbol}",
                "",
                f"BSC56 contract: `{contract}`.",
                "",
                (
                    "|Round|Equity last_quote_at UTC|Token observation UTC|Source difference s|"
                    "Receipt difference s|Within30s|Eligible|"
                ),
                "|---|---|---|---:|---:|---|---|",
            ]
        )
        for r in evidence["rounds"]:
            e = r["equity"].get("observation_timestamp_utc", "UNAVAILABLE")
            t = (
                r["binance"]
                .get("tokens", {})
                .get(symbol, {})
                .get("observation_timestamp_utc", "UNAVAILABLE")
            )
            p = r["pairs"][symbol]
            lines.append(
                f"|{r['round']}|{e}|{t}|{p['timestamp_difference_seconds']}|"
                f"{p['receipt_difference_seconds']}|{p['within_30s']}|{p['eligible']}|"
            )
        lines.extend(["", "```json", json.dumps(stats, indent=2), "```", ""])
    lines.extend(
        ["## Overall", "", "```json", json.dumps(evidence["summary"], indent=2), "```", ""]
    )
    lines.append(
        "Consistent alignment was observed in this bounded sample. Separately authorized "
        "integration may be investigated, preserving validation and failing closed on bad samples."
        if conclusion == "PASS"
        else "Stable eligible alignment was not demonstrated. This does not justify adding "
        "Twelve Data as an accepted current Trust reference; no threshold relaxation is proposed."
    )
    lines.extend(
        [
            "",
            "This short sample does not prove sustained reliability or pass the full Trust gate.",
            "Missing timestamps are unscorable, never inferred from receipt/envelope time.",
            "JSON preserves prices, market flags, observation times and separate receipt times.",
            "[Full paired capture](evidence/TWELVE_BINANCE_NVDA_ALIGNMENT.json).",
            "No production observations, settings, application logic or gates were changed.",
            "No execution, wallet or trading endpoint was called.",
            "Only diagnostic files; no credentials or signatures. Stop after this diagnostic.",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="Local plan/credential check; no API call"
    )
    parser.add_argument(
        "--start-at", help="Optional future ISO8601 timestamp with explicit timezone"
    )
    args = parser.parse_args()
    calendar = USEquityCalendar()
    now = datetime.now(UTC)
    state = calendar.status(now)
    if args.check:
        configured = dotenv_values(ROOT / ".env")
        ready = all(
            os.environ.get(k) or configured.get(k)
            for k in ["TWELVE_DATA_API_KEY", "BINANCE_WEB3_API_KEY", "BINANCE_WEB3_SECRET_KEY"]
        )
        print(
            json.dumps(
                {
                    "required_credentials_present": bool(ready),
                    "current_regime": state.state,
                    "next_regular_open_utc": state.next_open.isoformat(),
                    "network_calls": 0,
                }
            )
        )
        return
    if args.start_at:
        target = datetime.fromisoformat(args.start_at.replace("Z", "+00:00"))
        if target.tzinfo is None or calendar.status(target).state != "REGULAR":
            parser.error(
                "Start timestamp must be timezone-aware and inside a verified regular session"
            )
        print(
            json.dumps(
                {
                    "scheduled_start_utc": target.astimezone(UTC).isoformat(),
                    "scheduled_start_ist": target.astimezone(ZoneInfo("Asia/Kolkata")).isoformat(),
                    "network_calls_while_waiting": 0,
                }
            ),
            flush=True,
        )
        while (delay := seconds(target - datetime.now(UTC))) > 0:
            time.sleep(min(float(delay), 30))
    if calendar.status(datetime.now(UTC)).state != "REGULAR":
        print(json.dumps({"result": "NOT_TESTED_MARKET_CLOSED", "network_calls": 0}), flush=True)
        return
    output = ROOT / "docs/evidence/TWELVE_BINANCE_NVDA_ALIGNMENT.json"
    markdown = ROOT / "docs/TWELVE_BINANCE_ALIGNMENT.md"
    if output.exists() or markdown.exists():
        raise ValueError("Existing diagnostic evidence/report must not be overwritten")
    protected = secret_values()
    probe = diagnostic.Probe()
    configured = dotenv_values(ROOT / ".env")
    values = [
        os.environ.get(k) or configured.get(k)
        for k in ["BINANCE_WEB3_API_KEY", "BINANCE_WEB3_SECRET_KEY"]
    ]
    if not all(values) or not probe.keys["TWELVE_DATA_API_KEY"]:
        probe.http.close()
        raise ValueError("Required local credentials absent; no provider call made")
    client = BinanceWeb3Client(SecretStr(values[0]), SecretStr(values[1]), attempts=1, cache_ttl=0)
    evidence = {
        "rounds": [],
        "complete": False,
        "count": 10,
        "spacing_seconds": 17,
        "alignment_threshold_seconds": 30,
        "freshness_threshold_seconds": 120,
        "token_contract_provenance": "Existing verified NVDA BSC representation captures",
        "equity_parameters": QUOTE_PARAMS,
        "production_writes": 0,
        "execution_calls": 0,
        "trust_gate_modified": False,
        "no_synthetic_data": True,
    }
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            for number in range(1, 11):
                if calendar.status(datetime.now(UTC)).state != "REGULAR":
                    evidence["stopped_reason"] = "REGULAR_SESSION_ENDED_NO_FURTHER_READS"
                    break
                started = time.monotonic()
                e_future = executor.submit(equity_read, probe)
                b_future = executor.submit(token_read, client)
                equity, binance = e_future.result(), b_future.result()
                regular = calendar.status(datetime.now(UTC)).state == "REGULAR"
                tokens = binance.get("tokens", {}) if binance["valid"] else {}
                comparisons = {s: pair(equity, tokens.get(s), regular) for s in TOKENS}
                evidence["rounds"].append(
                    {"round": number, "equity": equity, "binance": binance, "pairs": comparisons}
                )
                evidence["summary"] = summarize(evidence["rounds"], 10)
                evidence["complete"] = number == 10
                save(output, json.dumps(evidence, indent=2, default=str) + "\n", protected)
                print(json.dumps({"round": number, "pairs": comparisons}), flush=True)
                if number < 10:
                    while (remaining := 17 - (time.monotonic() - started)) > 0:
                        time.sleep(min(remaining, 30))
        evidence["summary"] = summarize(evidence["rounds"], 10)
        save(output, json.dumps(evidence, indent=2, default=str) + "\n", protected)
        save(markdown, report(evidence), protected)
        print(
            json.dumps(
                {
                    "result": evidence["summary"]["TWELVE_BINANCE_30S_ALIGNMENT"],
                    "report": str(markdown.relative_to(ROOT)),
                }
            ),
            flush=True,
        )
    finally:
        client.close()
        probe.http.close()


if __name__ == "__main__":
    main()
