"""Throwaway read-only feasibility capture, never imported by the application.

Writes diagnostic JSON only. No database writes, provider installation, production
settings mutation, synthetic candles, or execution calls. Keys use headers only.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

TOKENS = {
    "bstock": "0x02fca66c1d1afb4e2a7884261eb00f63598a7436",
    "ondo": "0xa9ee28c80f960b889dfbd1902055218cba016f75",
}
STABLES = {
    "0x55d398326f99059ff775485246999027b3197955": "USDT",
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": "USDC",
}
BASES = {
    "gecko": "https://api.geckoterminal.com/api/v2",
    "twelve": "https://api.twelvedata.com",
    "finnhub": "https://finnhub.io/api/v1",
    "ondo": "https://api.gm.ondo.finance",
}


def now():
    return datetime.now(UTC)


def stamp(value):
    return datetime.fromtimestamp(int(value), UTC).isoformat()


def summarize(rows, interval_seconds):
    times = sorted({int(r[0]) for r in rows})
    return {
        "real_bar_count": len(times),
        "earliest": stamp(times[0]) if times else None,
        "latest": stamp(times[-1]) if times else None,
        "interval_seconds": interval_seconds,
        "maximum_gap_seconds": max(
            (b - a for a, b in zip(times, times[1:], strict=False)), default=None
        ),
        "gaps_larger_than_interval": sum(
            b - a > interval_seconds for a, b in zip(times, times[1:], strict=False)
        ),
        "synthetic_fill": False,
    }


class Probe:
    def __init__(self):
        values = dotenv_values(ROOT / ".env")
        self.keys = {
            name: os.environ.get(name) or values.get(name)
            for name in ["TWELVE_DATA_API_KEY", "FINNHUB_API_KEY"]
        }
        self.secrets = [
            v for k, v in {**values, **os.environ}.items() if v and ("KEY" in k or "SECRET" in k)
        ]
        self.ledger = []
        self.last_request = {}
        self.http = httpx.Client(timeout=30, follow_redirects=False)

    def get(self, provider, path, params=None):
        assert provider in BASES and path.startswith("/")
        allowed = {
            "twelve": {"/price", "/quote", "/time_series", "/market_state"},
            "finnhub": {"/quote", "/stock/candle"},
            "ondo": {"/v1/assets/NVDAon/shares-multiplier"},
        }
        if provider == "gecko":
            assert re.fullmatch(
                r"/networks/bsc/(?:tokens/0x[0-9a-f]{40}/pools|"
                r"pools/0x[0-9a-f]{40,64}(?:-\d+)?(?:/ohlcv/(?:day|hour|minute))?)",
                path,
            ), "Unreviewed public read path"
        else:
            assert path in allowed[provider], "Unreviewed diagnostic read endpoint"
        headers = {"Accept": "application/json"}
        if provider in {"twelve", "finnhub"}:
            key = self.keys["TWELVE_DATA_API_KEY" if provider == "twelve" else "FINNHUB_API_KEY"]
            if not key:
                self.ledger.append(
                    {
                        "provider": provider,
                        "endpoint": "GET " + path,
                        "http_status": None,
                        "result": "NOT_TESTED_CREDENTIAL_ABSENT",
                        "timestamp_utc": now().isoformat(),
                    }
                )
                return None
            headers["Authorization" if provider == "twelve" else "X-Finnhub-Token"] = (
                "apikey " + key if provider == "twelve" else key
            )
        elif provider == "gecko":
            headers["Accept"] = "application/json;version=20230302"
        spacing = 8
        elapsed = time.monotonic() - self.last_request.get(provider, 0)
        if elapsed < spacing:
            time.sleep(spacing - elapsed)
        self.last_request[provider] = time.monotonic()
        entry = {
            "provider": provider,
            "endpoint": "GET " + path,
            "parameters": params or {},
            "requested_at": now().isoformat(),
        }
        try:
            response = self.http.get(BASES[provider] + path, params=params, headers=headers)
            entry.update(
                {
                    "http_status": response.status_code,
                    "received_at": now().isoformat(),
                    "rate_limit_headers": {
                        k: v
                        for k, v in response.headers.items()
                        if k.lower()
                        in {
                            "retry-after",
                            "api-credits-used",
                            "api-credits-left",
                            "x-ratelimit-limit",
                            "x-ratelimit-remaining",
                            "x-ratelimit-reset",
                        }
                    },
                }
            )
            if response.status_code != 200:
                entry["result"] = (
                    "RATE_LIMITED" if response.status_code == 429 else "HTTP_DENIED_OR_UNAVAILABLE"
                )
                if response.status_code == 429:
                    self.last_request[provider] = time.monotonic() + 30
                body = None
            else:
                body = json.loads(response.text, parse_float=Decimal)
                entry["result"] = "RESPONSE_RECEIVED_NOT_AUTOMATIC_TRUST_ELIGIBILITY"
                if isinstance(body, dict) and (body.get("status") == "error" or body.get("error")):
                    entry["result"] = "BUSINESS_ERROR_BODY_NOT_RETAINED"
                    entry["business_code"] = (
                        body.get("code") if isinstance(body.get("code"), int) else None
                    )
                    body = None
        except Exception as error:
            entry.update(
                {
                    "result": "NETWORK_OR_SCHEMA_FAILURE",
                    "error_type": type(error).__name__,
                    "received_at": now().isoformat(),
                }
            )
            body = None
        self.ledger.append(entry)
        return body


def equity(probe):
    result = {}
    for provider in ["twelve", "finnhub"]:
        if provider == "twelve":
            price = probe.get(provider, "/price", {"symbol": "NVDA"})
            quote = probe.get(
                provider, "/quote", {"symbol": "NVDA", "interval": "1min", "timezone": "UTC"}
            )
            bars = {
                interval: probe.get(
                    provider,
                    "/time_series",
                    {
                        "symbol": "NVDA",
                        "interval": interval,
                        "timezone": "UTC",
                        "start_date": "2026-10-02 00:00:00",
                        "end_date": "2026-10-05 23:59:59",
                        "outputsize": 5000,
                        "order": "ASC",
                        "prepost": "false",
                    },
                )
                for interval in ["1min", "5min"]
            }
            market = probe.get(provider, "/market_state", {"exchange": "NASDAQ"})
        else:
            quote = probe.get(provider, "/quote", {"symbol": "NVDA"})
            price = None
            bars = {
                interval: probe.get(
                    provider,
                    "/stock/candle",
                    {
                        "symbol": "NVDA",
                        "resolution": interval,
                        "from": 1790899200,
                        "to": 1791244799,
                    },
                )
                for interval in ["1", "5"]
            }
            market = None
        result[provider] = {
            "price": price,
            "quote": quote,
            "history": bars,
            "market_state": market,
            "credential_available": bool(
                probe.keys["TWELVE_DATA_API_KEY" if provider == "twelve" else "FINNHUB_API_KEY"]
            ),
            "runtime_plan": "UNKNOWN",
            "public_redisplay_authorized": False,
        }
        if quote:
            ts = quote.get("timestamp") if provider == "twelve" else quote.get("t")
            result[provider]["quote_timestamp"] = stamp(ts) if ts else None
            result[provider]["quote_timestamp_semantics"] = (
                "INTERVAL_OPEN_NOT_LAST_TRADE" if provider == "twelve" else "QUOTE_UNIX_SECONDS"
            )
            if provider == "twelve":
                result[provider]["last_minute_candle_at"] = (
                    stamp(quote["last_quote_at"]) if quote.get("last_quote_at") else None
                )
            result[provider]["age_at_receipt_seconds"] = (
                str(Decimal(str(now().timestamp())) - Decimal(str(ts))) if ts else None
            )
    return result


def gecko(probe, cached_pools=None):
    results = {}
    end = int(now().timestamp())
    for issuer, token in TOKENS.items():
        pools, included = [], {}
        exhausted = False
        for page in [] if cached_pools else range(1, 4):
            data = probe.get(
                "gecko",
                f"/networks/bsc/tokens/{token}/pools",
                {"include": "base_token,quote_token,dex", "page": page},
            )
            if not data:
                break
            batch = data.get("data", [])
            pools.extend(batch)
            included.update({i["id"]: i for i in data.get("included", [])})
            if len(batch) < 20:
                exhausted = True
                break
        if cached_pools:
            capture = cached_pools["geckoterminal"][issuer]
            pools = capture["pools"]
            included = {i["id"]: i for i in capture["included"]}
            exhausted = capture["enumeration_exhausted"]
        # Stable-counterasset and exact token identity, rather than assuming rank1
        # is largest reserve or the entire token market. Never aggregate reserves.
        choices = []
        for pool in pools:
            rel = pool.get("relationships", {})
            base = rel.get("base_token", {}).get("data", {}).get("id", "").removeprefix("bsc_")
            quote = rel.get("quote_token", {}).get("data", {}).get("id", "").removeprefix("bsc_")
            other = quote if base == token else base if quote == token else None
            reserve = pool.get("attributes", {}).get("reserve_in_usd")
            if (
                other in STABLES
                and reserve is not None
                and Decimal(str(reserve)) > 0
                and Decimal(str(pool["attributes"].get("volume_usd", {}).get("h24") or "0")) > 0
            ):
                choices.append((Decimal(str(reserve)), pool, "base" if base == token else "quote"))
        selected = max(choices, key=lambda x: x[0]) if choices else None
        item = {
            "contract": token,
            "pools": pools,
            "included": list(included.values()),
            "enumeration_exhausted": exhausted,
            "pool_count": len({p["id"] for p in pools}),
            "enumeration_page_bound": 3,
            "historical_pool_reserves": "NOT_PROVIDED_BY_OHLCV",
            "token_market_complete_or_equivalent": False,
        }
        if cached_pools:
            item["enumeration_capture_completed_at"] = cached_pools["completed_at"]
        if selected:
            _, pool, side = selected
            address = pool["attributes"]["address"]
            item.update(
                {
                    "selected_pool": pool,
                    "selected_token_side": side,
                    "selection_reason": (
                        "LARGEST_REPORTED_RESERVE_AMONG_ENUMERATED_EXACT_TOKEN_"
                        "ACTIVE_STABLE_COUNTERASSET_POOLS_FOR_DIAGNOSTIC_ONLY"
                    ),
                    "pool_current_detail": probe.get(
                        "gecko",
                        f"/networks/bsc/pools/{address}",
                        {"include": "base_token,quote_token,dex"},
                    ),
                }
            )
            histories = {}
            for frame, before in [
                ("day", end),
                ("hour", end),
                ("minute", end),
                ("minute_preopen", 1791207000),
            ]:
                timeframe = "minute" if frame == "minute_preopen" else frame
                rows, pages = {}, 0
                stop = "BOUNDED_NOT_EXHAUSTIVE"
                for _ in range(5 if frame == "hour" else 1):
                    data = probe.get(
                        "gecko",
                        f"/networks/bsc/pools/{address}/ohlcv/{timeframe}",
                        {
                            "aggregate": 1,
                            "before_timestamp": before,
                            "limit": 1000,
                            "currency": "usd",
                            "token": token,
                            "include_empty_intervals": "false",
                        },
                    )
                    pages += 1
                    if not data:
                        stop = "DENIED_OR_UNAVAILABLE"
                        break
                    batch = data.get("data", {}).get("attributes", {}).get("ohlcv_list", [])
                    valid = [
                        r
                        for r in batch
                        if len(r) == 6
                        and int(r[0]) < before
                        and int(r[0]) + {"day": 86400, "hour": 3600, "minute": 60}[timeframe] <= end
                    ]
                    rows.update({int(r[0]): r for r in valid})
                    if not valid:
                        stop = "NO_MORE_VALID_RETURNED_BARS_NOT_PROOF_OF_FULL_RETENTION"
                        break
                    before = min(int(r[0]) for r in valid)
                    if len(batch) < 1000:
                        stop = "RETURNED_FEWER_THAN_LIMIT_NOT_PROOF_OF_FULL_RETENTION"
                        break
                seconds = {"day": 86400, "hour": 3600, "minute": 60}[timeframe]
                ordered = sorted(rows.values(), key=lambda r: r[0])
                histories[frame] = {
                    "summary": summarize(ordered, seconds),
                    "bars": ordered,
                    "pages": pages,
                    "stop_reason": stop,
                    "currency": "USD",
                    "pool": address,
                    "token": token,
                    "availability": "FIRST_SEEN_NOW_NOT_BACKDATED",
                }
            item["history"] = histories
        results[issuer] = item
    return results


def existing_tokens():
    rows = {}
    for path in sorted((ROOT / "data").glob("*.db")):
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as c:
            tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "token_observations" in tables:
                for identifier, payload in c.execute(
                    "SELECT id,payload FROM token_observations WHERE data_mode='LIVE'"
                ):
                    rows.setdefault(identifier, json.loads(payload))
    return list(rows.values())


def pairing(tokens, pools):
    from app.services.calendar import USEquityCalendar

    calendar = USEquityCalendar()
    results = {}
    for issuer, contract in TOKENS.items():
        times = [
            datetime.fromisoformat(r["source_timestamp"].replace("Z", "+00:00"))
            for r in tokens
            if r.get("contract") == contract and r.get("source_timestamp")
        ]
        history = pools.get(issuer, {}).get("history", {})
        hour = history.get("hour", {}).get("bars", [])
        times.extend(datetime.fromtimestamp(int(r[0]), UTC) for r in hour)
        if not times:
            results[issuer] = {"potential_windows": [], "qualifying_episodes": 0}
            continue
        lo, hi = min(times), max(times)
        day, windows = lo.date(), []
        while day <= hi.date():
            session = calendar.session(day)
            if session and session[0] <= now():
                previous = calendar.previous_session(session[0])
                if (session[0].date() - previous[1].date()).days > 1 and lo <= session[
                    0
                ] <= hi + timedelta(days=3):
                    candles = [
                        r
                        for r in hour
                        if previous[1].timestamp() <= int(r[0])
                        and int(r[0]) + 3600 <= session[0].timestamp()
                    ]
                    windows.append(
                        {
                            "previous_close": previous[1].isoformat(),
                            "decision_at": session[0].isoformat(),
                            "first_5m_target_completes_at": (
                                session[0] + timedelta(minutes=5)
                            ).isoformat(),
                            "real_pool_hourly_bars_in_closed_window": len(candles),
                            "paired_equity_from_new_free_providers": False,
                            "qualifies": False,
                            "rejection_reasons": [
                                "FREE_EQUITY_CAPTURE_NOT_VERIFIED",
                                "HISTORICAL_ASOF_RATIO_NOT_VERIFIED",
                                "HISTORICAL_POOL_LIQUIDITY_ABSENT",
                                "FIRST_AVAILABILITY_REVISION_PROVENANCE_NOT_VERIFIED",
                                "TIME_ALIGNED_HISTORICAL_NEWS_NOT_VERIFIED",
                                "END_WINDOW_DENSITY_NOT_VERIFIED",
                            ],
                        }
                    )
            day += timedelta(days=1)
        results[issuer] = {
            "token_source_start": lo.isoformat(),
            "token_source_end": hi.isoformat(),
            "potential_windows": windows,
            "qualifying_episodes": 0,
            "qualifying_analogues": 0,
        }
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", choices=["all", "gecko", "equity"], default="all")
    parser.add_argument("--output", required=True)
    parser.add_argument("--cached-pools")
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise ValueError("Diagnostic evidence already exists; use a new output filename")
    probe = Probe()
    try:
        data = {
            "evidence_kind": "REAL_READ_ONLY_FEASIBILITY_NOT_PRODUCTION_DATA",
            "started_at": now().isoformat(),
            "production_writes": 0,
            "execution_calls": 0,
            "gates_modified": False,
        }
        if args.section in {"all", "gecko"}:
            data["geckoterminal"] = gecko(
                probe,
                json.loads(Path(args.cached_pools).read_text()) if args.cached_pools else None,
            )
            data["existing_token_inventory_count"] = len(existing_tokens())
            data["dry_run_pairing"] = pairing(existing_tokens(), data["geckoterminal"])
            data["ondo_ratio_history_unauthenticated_probe"] = probe.get(
                "ondo", "/v1/assets/NVDAon/shares-multiplier", {"range": "all"}
            )
        if args.section in {"all", "equity"}:
            data["equity"] = equity(probe)
        data.update({"completed_at": now().isoformat(), "reads": probe.ledger})
        text = json.dumps(data, indent=2, default=str) + "\n"
        assert all(secret not in text for secret in probe.secrets), (
            "Secret detected; output suppressed"
        )
        output.write_text(text)
        print(
            json.dumps(
                {
                    "diagnostic_artifact": str(output),
                    "read_count": len(probe.ledger),
                    "production_writes": 0,
                    "execution_calls": 0,
                }
            )
        )
    finally:
        probe.http.close()


if __name__ == "__main__":
    main()
