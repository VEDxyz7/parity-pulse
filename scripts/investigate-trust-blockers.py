"""Isolated real historical backfill/audit. Never imported by the application.

No production DB writes, as-of ratio backdating, Trust changes or execution calls.
All new raw history retains actual receipt provenance and null historical ratios.
"""

import argparse
import importlib.util
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import httpx
from dotenv import dotenv_values
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.clients.binance_web3 import PREFIX, BinanceWeb3Client  # noqa: E402
from app.clients.common import ProviderError  # noqa: E402
from app.clients.massive import MassiveClient  # noqa: E402
from app.providers.massive import Bar, validate  # noqa: E402
from app.services.calendar import USEquityCalendar  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "free_probe", Path(__file__).with_name("diagnose-free-providers.py")
)
free = importlib.util.module_from_spec(spec)
spec.loader.exec_module(free)

TOKENS = free.TOKENS
POOLS = {
    "bstock": "0x8fb4243b553ac29ba088acf00b9b7da24bd6690c",
    "ondo": "0xb90bdbfbdffd4af5a636b5805539edeafb969308",
}
BACKFILL = ROOT / "docs/evidence/TRUST_BLOCKER_HISTORICAL_BACKFILL.json"
AUDIT = ROOT / "docs/evidence/TRUST_BLOCKER_HISTORICAL_AUDIT.json"
DURATIONS = {"1m": 60, "1h": 3600, "1d": 86400}


def now():
    return datetime.now(UTC)


def dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def ms(value):
    return int(value.timestamp() * 1000)


def secrets():
    values = {**dotenv_values(ROOT / ".env"), **os.environ}
    return [str(v) for k, v in values.items() if v and ("KEY" in k or "SECRET" in k)]


def save(path, data):
    encoded = json.dumps(data, indent=2, default=str) + "\n"
    if any(s in encoded for s in secrets()):
        raise ValueError("Protected value detected; output suppressed")
    path.write_text(encoded)


def inventory():
    tables = [
        "token_observations",
        "equity_observations",
        "token_metadata",
        "trust_samples",
        "trust_episodes",
        "news_events",
    ]
    unique = {t: {} for t in tables}
    per_db = {}
    for path in sorted((ROOT / "data").glob("*.db")):
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as c:
            available = {
                r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            counts = {}
            for table in tables:
                rows = (
                    c.execute(f"SELECT id,payload FROM {table} WHERE data_mode='LIVE'").fetchall()
                    if table in available
                    else []
                )
                counts[table] = len(rows)
                for key, payload in rows:
                    record = json.loads(payload)
                    old = unique[table].get(key)
                    received = record.get("ingestion_timestamp") or record.get(
                        "outcome_available_at", record.get("features", {}).get("available_at")
                    )
                    prior = (
                        (
                            old.get("ingestion_timestamp")
                            or old.get(
                                "outcome_available_at", old.get("features", {}).get("available_at")
                            )
                        )
                        if old
                        else None
                    )
                    if old is None or received and prior and received < prior:
                        unique[table][key] = record
            per_db[str(path.relative_to(ROOT))] = counts
    return {t: list(v.values()) for t, v in unique.items()}, per_db


def windows(calendar, start, end):
    day, result = start.date(), []
    while day <= end.date():
        session = calendar.session(day)
        if session and start <= session[0] <= end:
            prior = calendar.previous_session(session[0])[1]
            if (session[0].date() - prior.date()).days > 1:
                result.append({"close": prior, "open": session[0]})
        day += timedelta(days=1)
    return result


class DiagnosticBinance(BinanceWeb3Client):
    """One documented market GET addition, isolated from the production allowlist."""

    def authorize(self, method, path):
        if method == "GET" and path == PREFIX + "token/top-liquidity":
            if not self.api_key or not self.secret_key:
                raise ProviderError(self.provider, "NOT_CONFIGURED")
            return
        super().authorize(method, path)


def candle(row, issuer, bar, received, lower, upper):
    if not isinstance(row, list) or len(row) != 7:
        return None, "MALFORMED"
    try:
        prices = [Decimal(str(v)) for v in row[:5]]
        o, h, low, c, volume = prices
        stamp, trades = row[5:]
        if not all(p.is_finite() for p in prices) or min(o, h, low, c) <= 0 or volume < 0:
            raise ValueError
        if not low <= min(o, c) <= max(o, c) <= h:
            raise ValueError
        if type(stamp) is not int or type(trades) is not int or trades < 0:
            raise ValueError
        observed = datetime.fromtimestamp(stamp / 1000, UTC)
        if not lower <= observed < upper:
            return None, "OUTSIDE_EXCLUSIVE_QUERY_WINDOW"
        if observed + timedelta(seconds=DURATIONS[bar]) > received:
            return None, "UNCOMPLETED"
    except (ValueError, TypeError, ArithmeticError, OverflowError):
        return None, "MALFORMED"
    return {
        "source": "BINANCE_MARKET",
        "authority_role": "PRIMARY_RAW_TOKEN_HISTORY",
        "ticker": "NVDA",
        "issuer": issuer,
        "chain": "56",
        "contract": TOKENS[issuer],
        "interval": bar,
        "start_utc": observed.isoformat(),
        "raw_timestamp_ms": stamp,
        "first_seen": received.isoformat(),
        "open": str(o),
        "high": str(h),
        "low": str(low),
        "close": str(c),
        "volume": str(volume),
        "trade_count": trades,
        "volume_unit": "UNKNOWN",
        "historical_ratio": None,
        "historical_ratio_verified": False,
        "historical_liquidity": None,
        "point_in_time_availability_verified": False,
        "synthetic": False,
    }, None


def collect():
    if BACKFILL.exists():
        raise ValueError("Existing backfill must not be overwritten")
    config = {**dotenv_values(ROOT / ".env"), **os.environ}

    def key(name):
        return SecretStr(config[name]) if config.get(name) else None

    client = DiagnosticBinance(
        key("BINANCE_WEB3_API_KEY"),
        key("BINANCE_WEB3_SECRET_KEY"),
        attempts=1,
        cache_ttl=0,
        recv_window=60000,
        min_interval=0.5,
    )
    equity = MassiveClient(
        key("MASSIVE_API_KEY") or key("POLYGON_API_KEY"), attempts=1, cache_ttl=0
    )
    probe = free.Probe()
    start = now() - timedelta(days=180)
    end = now().replace(hour=0, minute=0, second=0, microsecond=0)
    calendar = USEquityCalendar()
    candidates = windows(calendar, start, end)
    result = {
        "started_at": now().isoformat(),
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "evidence_kind": "REAL_ISOLATED_BACKFILL",
        "production_writes": 0,
        "execution_calls": 0,
        "gates_modified": False,
        "token_bars": [],
        "equity_bars": [],
        "captures": [],
        "gecko": {},
        "ratio": {},
        "liquidity": {},
        "documentation": {},
    }
    save(BACKFILL, result)

    def read(method, endpoint, params=None, body=None):
        item = {"endpoint": method + " " + PREFIX + endpoint, "parameters": params or {}}
        try:
            data, received, envelope = client.read(method, PREFIX + endpoint, params, body)
            item.update(
                {
                    "http_status": 200,
                    "business_status": envelope.get("code"),
                    "received_at": received.isoformat(),
                }
            )
        except ProviderError as error:
            item.update(
                {
                    "http_status": error.http_status,
                    "business_status": error.business_status,
                    "result": error.kind,
                    "received_at": now().isoformat(),
                }
            )
            data, received = None, now()
        result["captures"].append(item)
        return data, received, item

    def pages(issuer, bar, lower, upper, bound):
        cursor, seen, rows = upper, set(), {}
        for page in range(bound):
            params = {
                "binanceChainId": "56",
                "tokenContractAddress": TOKENS[issuer],
                "bar": bar,
                "before": ms(lower) - 1,
                "after": ms(cursor),
                "limit": 100,
            }
            raw, received, ledger = read("GET", "candles", params)
            if not isinstance(raw, list):
                ledger["stop_reason"] = "DENIED_OR_INVALID_HISTORY"
                break
            rejected = Counter()
            stamps = []
            for row in raw:
                record, reason = candle(row, issuer, bar, received, lower, cursor)
                if reason:
                    rejected[reason] += 1
                else:
                    rows.setdefault(record["raw_timestamp_ms"], record)
                if isinstance(row, list) and len(row) == 7 and type(row[5]) is int:
                    stamps.append(row[5])
            ledger.update({"returned": len(raw), "excluded": dict(rejected), "page": page + 1})
            if not stamps:
                ledger["stop_reason"] = "EMPTY_RESPONSE_NOT_RETENTION_PROOF"
                break
            next_cursor = min(stamps)
            if next_cursor >= ms(cursor) or next_cursor in seen:
                ledger["stop_reason"] = "PAGINATION_NON_ADVANCING"
                break
            if next_cursor <= ms(lower):
                ledger["stop_reason"] = "REQUESTED_LOWER_BOUND_REACHED"
                break
            seen.add(next_cursor)
            cursor = datetime.fromtimestamp(next_cursor / 1000, UTC)
            ledger["stop_reason"] = "PAGE_BOUND_NOT_COMPLETE_RETENTION"
        result["token_bars"].extend(rows.values())
        save(BACKFILL, result)

    try:
        for issuer, contract in TOKENS.items():
            params = {"binanceChainId": "56", "tokenContractAddress": contract}
            raw, received, _ = read("GET", "rwa/underlying-profile", params)
            result["ratio"][issuer] = {
                "current_capture": {
                    k: raw.get(k)
                    for k in [
                        "binanceChainId",
                        "tokenContractAddress",
                        "platformId",
                        "underlyingTicker",
                        "tokenToShareRatio",
                    ]
                }
                if isinstance(raw, dict)
                else None,
                "received_at": received.isoformat(),
                "historical_ratio": None,
                "classification": "HISTORICAL_RATIO_UNAVAILABLE",
            }
            pools, received, _ = read("GET", "token/top-liquidity", params)
            result["liquidity"][issuer] = {
                "binance_top_pools": pools,
                "received_at": received.isoformat(),
            }
            pages(issuer, "1d", start, end, 3)
            pages(issuer, "1h", start, end, 20)
            for window in candidates:
                pages(issuer, "1m", window["open"] - timedelta(minutes=30), window["open"], 1)
            print(
                json.dumps(
                    {
                        "stage": "BINANCE_HISTORY",
                        "issuer": issuer,
                        "stored_raw_rows": len(result["token_bars"]),
                    }
                ),
                flush=True,
            )
        infos, received, _ = read(
            "POST",
            "price-info",
            body=[{"binanceChainId": "56", "tokenContractAddress": c} for c in TOKENS.values()],
        )
        result["binance_price_info"] = {"rows": infos, "received_at": received.isoformat()}
        save(BACKFILL, result)

        # Only historical equity bars: no quote/snapshot/current alignment diagnostic.
        # Exact millisecond windows avoid backfilling irrelevant sessions.
        for number, window in enumerate(candidates, 1):
            for multiplier, lo, hi in [
                (1, window["close"] - timedelta(minutes=1), window["close"]),
                (5, window["open"], window["open"] + timedelta(minutes=5)),
            ]:
                path = f"/v2/aggs/ticker/NVDA/range/{multiplier}/minute/{ms(lo)}/{ms(hi) - 1}"
                ledger = {
                    "endpoint": "GET " + path,
                    "parameters": {"adjusted": "true", "sort": "asc", "limit": 5000},
                }
                try:
                    data, received, envelope = equity.read("GET", path, ledger["parameters"])
                    ledger.update(
                        {
                            "http_status": 200,
                            "business_status": envelope.get("status"),
                            "received_at": received.isoformat(),
                        }
                    )
                    if data.get("ticker") != "NVDA" or data.get("adjusted") is not True:
                        raise ProviderError("MASSIVE", "CONFLICTING_IDENTITY_OR_ADJUSTMENT")
                    raw_rows = validate(list[Bar], data.get("results", []))
                    ledger["returned"] = len(raw_rows)
                    ledger["next_page_present"] = bool(data.get("next_url"))
                    for row in raw_rows:
                        observed = datetime.fromtimestamp(row.t / 1000, UTC)
                        if observed != lo or observed + timedelta(minutes=multiplier) > received:
                            continue
                        if not row.l <= min(row.o, row.c) <= max(row.o, row.c) <= row.h:
                            continue
                        result["equity_bars"].append(
                            {
                                "source": "MASSIVE",
                                "ticker": "NVDA",
                                "currency": "USD",
                                "interval": f"{multiplier}minute",
                                "start_utc": observed.isoformat(),
                                "first_seen": received.isoformat(),
                                "adjusted": True,
                                "open": str(row.o),
                                "high": str(row.h),
                                "low": str(row.l),
                                "close": str(row.c),
                                "volume": str(row.v),
                                "point_in_time_availability_verified": False,
                                "revision_history_verified": False,
                                "synthetic": False,
                            }
                        )
                except ProviderError as error:
                    ledger.update(
                        {
                            "http_status": error.http_status,
                            "business_status": error.business_status,
                            "result": error.kind,
                            "received_at": now().isoformat(),
                        }
                    )
                result["captures"].append(ledger)
                save(BACKFILL, result)
            print(
                json.dumps({"stage": "HISTORICAL_EQUITY", "window": number, "of": len(candidates)}),
                flush=True,
            )

        # Secondary public pool history: preserve pool scope; never promote to token authority.
        for issuer, pool in POOLS.items():
            detail = probe.get(
                "gecko", f"/networks/bsc/pools/{pool}", {"include": "base_token,quote_token,dex"}
            )
            item = {
                "pool": pool,
                "contract": TOKENS[issuer],
                "network": "bsc",
                "authority_role": "SECONDARY_EXPERIMENTAL_POOL_ONLY",
                "detail": detail,
                "detail_received_at": now().isoformat(),
                "older_hourly": [],
            }
            prior = json.loads(
                (ROOT / "docs/evidence/FREE_PROVIDER_FEASIBILITY_PAIRING.json").read_text()
            )
            earliest = prior["per_representation"][issuer]["historical_pool_coverage"]["hour"][
                "earliest"
            ]
            cursor = int(dt(earliest).timestamp())
            for _ in range(4):
                data = probe.get(
                    "gecko",
                    f"/networks/bsc/pools/{pool}/ohlcv/hour",
                    {
                        "aggregate": 1,
                        "before_timestamp": cursor,
                        "limit": 1000,
                        "currency": "usd",
                        "token": TOKENS[issuer],
                        "include_empty_intervals": "false",
                    },
                )
                if not data:
                    break
                raw = data.get("data", {}).get("attributes", {}).get("ohlcv_list", [])
                received = now()
                valid = []
                for row in raw:
                    try:
                        if len(row) != 6 or type(row[0]) is not int:
                            raise ValueError
                        o, h, low, c, v = [Decimal(str(x)) for x in row[1:]]
                        if not all(x.is_finite() for x in [o, h, low, c, v]):
                            raise ValueError
                        if not 0 < low <= min(o, c) <= max(o, c) <= h or v < 0:
                            raise ValueError
                        if row[0] >= cursor or row[0] + 3600 > received.timestamp():
                            raise ValueError
                        valid.append(row)
                    except (TypeError, ValueError, ArithmeticError):
                        continue
                item["older_hourly"].append(
                    {
                        "bars": valid,
                        "first_seen": received.isoformat(),
                        "historical_ratio": None,
                        "historical_liquidity": None,
                    }
                )
                if not valid or min(r[0] for r in valid) >= cursor:
                    break
                cursor = min(r[0] for r in valid)
                if cursor <= start.timestamp():
                    break
            result["gecko"][issuer] = item
            save(BACKFILL, result)

        # Current public API schemas only. No invented historical-ratio endpoint.
        urls = {
            "binance_schema": "https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/1.0.0/schema.json",
            "gecko_schema": "https://api.geckoterminal.com/docs/v2/swagger.json",
        }
        with httpx.Client(timeout=30, follow_redirects=False) as public:
            for name, url in urls.items():
                response = public.get(url)
                item = {
                    "url": url,
                    "http_status": response.status_code,
                    "received_at": now().isoformat(),
                }
                if response.status_code == 200:
                    schema = response.json()
                    item["paths"] = {}
                    for path, methods in schema.get("paths", {}).items():
                        if (name == "binance_schema" and "/rwa/" in path) or (
                            name == "gecko_schema" and "ohlcv" in path
                        ):
                            item["paths"][path] = {
                                method: [
                                    p.get("name", p.get("$ref")) for p in body.get("parameters", [])
                                ]
                                for method, body in methods.items()
                                if method in {"get", "post"}
                            }
                    item["ratio_named_paths"] = [
                        p
                        for p in schema.get("paths", {})
                        if "ratio" in p.lower() or "multiplier" in p.lower()
                    ]
                result["documentation"][name] = item
        result["ondo_anonymous_ratio_probe"] = probe.get(
            "ondo", "/v1/assets/NVDAon/shares-multiplier", {"range": "all"}
        )
        result["public_reads"] = probe.ledger
        result["completed_at"] = now().isoformat()
        save(BACKFILL, result)
        print(
            json.dumps(
                {
                    "backfill": str(BACKFILL.relative_to(ROOT)),
                    "token_bars": len(result["token_bars"]),
                    "equity_bars": len(result["equity_bars"]),
                    "production_writes": 0,
                    "execution_calls": 0,
                }
            ),
            flush=True,
        )
    finally:
        client.close()
        equity.close()
        probe.http.close()


def summary(rows, timestamp="start_utc"):
    """Coverage by source and interval. Sparse event observations are not a cadence guarantee."""
    groups = {}
    for row in rows:
        if row.get(timestamp):
            groups.setdefault(row.get("interval") or "EVENT", []).append(row)
    result = {}
    for interval, group in groups.items():
        times = sorted({dt(r[timestamp]) for r in group})
        duration = {"1m": 60, "1h": 3600, "1d": 86400, "1minute": 60, "5minute": 300}.get(interval)
        gaps = [
            {"from": a.isoformat(), "to": b.isoformat(), "seconds": int((b - a).total_seconds())}
            for a, b in zip(times, times[1:], strict=False)
        ]
        gaps.sort(key=lambda r: r["seconds"], reverse=True)
        result[interval] = {
            "rows": len(group),
            "unique_timestamps": len(times),
            "earliest": times[0].isoformat(),
            "latest": times[-1].isoformat(),
            "interval_seconds": duration,
            "largest_gaps": gaps[:5],
            "gaps_exceeding_interval": sum(g["seconds"] > duration for g in gaps)
            if duration
            else None,
            "synthetic_fill": False,
        }
    return result


def deepen():
    """Append reviewed older history to this task's isolated capture; preserve all prior rows."""
    data = json.loads(BACKFILL.read_text())
    if not data.get("completed_at") or data.get("deepening_completed_at"):
        raise ValueError("One completed initial capture, not already deepened, required")
    config = {**dotenv_values(ROOT / ".env"), **os.environ}

    def key(name):
        return SecretStr(config[name]) if config.get(name) else None

    client = DiagnosticBinance(
        key("BINANCE_WEB3_API_KEY"),
        key("BINANCE_WEB3_SECRET_KEY"),
        attempts=1,
        cache_ttl=0,
        recv_window=60000,
        min_interval=0.5,
    )
    equity = MassiveClient(
        key("MASSIVE_API_KEY") or key("POLYGON_API_KEY"), attempts=1, cache_ttl=0
    )
    data["deepening_started_at"] = now().isoformat()
    try:
        for issuer in TOKENS:
            new_pool_times = [
                datetime.fromtimestamp(int(r[0]), UTC)
                for capture in data["gecko"][issuer]["older_hourly"]
                for r in capture["bars"]
            ]
            lower = min([dt(data["requested_start"]), *new_pool_times])
            for bar, bound in [("1h", 40), ("1d", 3)]:
                existing = [
                    r for r in data["token_bars"] if r["issuer"] == issuer and r["interval"] == bar
                ]
                cursor = min(dt(r["start_utc"]) for r in existing)
                for _page in range(bound):
                    if cursor <= lower:
                        break
                    params = {
                        "binanceChainId": "56",
                        "tokenContractAddress": TOKENS[issuer],
                        "bar": bar,
                        "after": ms(cursor),
                        "before": ms(lower) - 1,
                        "limit": 100,
                    }
                    ledger = {
                        "endpoint": "GET " + PREFIX + "candles",
                        "parameters": params,
                        "capture_stage": "OLDER_PRIMARY_HISTORY",
                    }
                    try:
                        raw, received, envelope = client.read("GET", PREFIX + "candles", params)
                        ledger.update(
                            {
                                "http_status": 200,
                                "business_status": envelope["code"],
                                "received_at": received.isoformat(),
                                "returned": len(raw),
                            }
                        )
                    except ProviderError as error:
                        ledger.update(
                            {
                                "http_status": error.http_status,
                                "result": error.kind,
                                "received_at": now().isoformat(),
                            }
                        )
                        data["captures"].append(ledger)
                        break
                    rejected, stamps = Counter(), []
                    for row in raw:
                        record, reason = candle(row, issuer, bar, received, lower, cursor)
                        if record:
                            data["token_bars"].append(record)
                        else:
                            rejected[reason] += 1
                        if isinstance(row, list) and len(row) == 7 and type(row[5]) is int:
                            stamps.append(row[5])
                    ledger["excluded"] = dict(rejected)
                    data["captures"].append(ledger)
                    save(BACKFILL, data)
                    if not stamps or min(stamps) >= ms(cursor):
                        ledger["stop_reason"] = "EMPTY_OR_NON_ADVANCING_NOT_RETENTION_PROOF"
                        break
                    cursor = datetime.fromtimestamp(min(stamps) / 1000, UTC)
                    ledger["stop_reason"] = (
                        "LOWER_BOUND_REACHED" if cursor <= lower else "PAGE_BOUND"
                    )
            print(
                json.dumps(
                    {
                        "stage": "OLDER_PRIMARY_HISTORY",
                        "issuer": issuer,
                        "raw_rows": len(data["token_bars"]),
                    }
                ),
                flush=True,
            )

        # Five extra completed reopening dates revealed by the older secondary history.
        older = [
            datetime.fromtimestamp(int(r[0]), UTC)
            for c in data["gecko"]["ondo"]["older_hourly"]
            for r in c["bars"]
        ]
        calendar = USEquityCalendar()
        for window in windows(calendar, min(older), dt(data["requested_start"])):
            for multiplier, lo, hi in [
                (1, window["close"] - timedelta(minutes=1), window["close"]),
                (5, window["open"], window["open"] + timedelta(minutes=5)),
            ]:
                path = f"/v2/aggs/ticker/NVDA/range/{multiplier}/minute/{ms(lo)}/{ms(hi) - 1}"
                ledger = {
                    "endpoint": "GET " + path,
                    "capture_stage": "OLDER_EQUITY_TARGET",
                    "parameters": {"adjusted": "true", "sort": "asc", "limit": 5000},
                }
                try:
                    raw, received, envelope = equity.read("GET", path, ledger["parameters"])
                    ledger.update(
                        {
                            "http_status": 200,
                            "business_status": envelope["status"],
                            "received_at": received.isoformat(),
                        }
                    )
                    if raw.get("ticker") != "NVDA" or raw.get("adjusted") is not True:
                        raise ProviderError("MASSIVE", "CONFLICTING_IDENTITY_OR_ADJUSTMENT")
                    rows = validate(list[Bar], raw.get("results", []))
                    ledger["returned"] = len(rows)
                    for row in rows:
                        stamp = datetime.fromtimestamp(row.t / 1000, UTC)
                        if stamp != lo or stamp + timedelta(minutes=multiplier) > received:
                            continue
                        if not row.l <= min(row.o, row.c) <= max(row.o, row.c) <= row.h:
                            continue
                        data["equity_bars"].append(
                            {
                                "source": "MASSIVE",
                                "ticker": "NVDA",
                                "currency": "USD",
                                "interval": f"{multiplier}minute",
                                "start_utc": stamp.isoformat(),
                                "first_seen": received.isoformat(),
                                "adjusted": True,
                                "open": str(row.o),
                                "high": str(row.h),
                                "low": str(row.l),
                                "close": str(row.c),
                                "volume": str(row.v),
                                "point_in_time_availability_verified": False,
                                "revision_history_verified": False,
                                "synthetic": False,
                            }
                        )
                except ProviderError as error:
                    ledger.update(
                        {
                            "http_status": error.http_status,
                            "result": error.kind,
                            "received_at": now().isoformat(),
                        }
                    )
                data["captures"].append(ledger)
                save(BACKFILL, data)
            print(
                json.dumps({"stage": "OLDER_EQUITY_TARGET", "opening": window["open"].isoformat()}),
                flush=True,
            )
        data["deepening_completed_at"] = now().isoformat()
        save(BACKFILL, data)
    finally:
        client.close()
        equity.close()


def density(rows, opening):
    start = opening - timedelta(minutes=30)
    # A historical one-minute OHLC row is usable only after its complete minute.
    times = sorted(
        {
            dt(r["start_utc"]) + timedelta(minutes=1)
            for r in rows
            if r.get("interval") == "1m"
            and start <= dt(r["start_utc"])
            and dt(r["start_utc"]) + timedelta(minutes=1) <= opening
        }
    )
    gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:], strict=False)]
    passes = (
        len(times) >= 2
        and times[0] <= start + timedelta(seconds=120)
        and times[-1] >= opening - timedelta(seconds=120)
        and max(gaps, default=0) <= 120
    )
    return {
        "completed_minute_bars": len(times),
        "first_completed_at": times[0].isoformat() if times else None,
        "last_completed_at": times[-1].isoformat() if times else None,
        "max_internal_gap_seconds": max(gaps, default=None),
        "density_only_pass": bool(passes),
        "qualified_features": False,
    }


def outcome(rows, close, opening, source):
    reference = [
        r
        for r in rows
        if r["source"] == source
        and r.get("interval") == "1minute"
        and dt(r["start_utc"]) + timedelta(minutes=1) == close
    ]
    target = [
        r
        for r in rows
        if r["source"] == source
        and r.get("interval") == "5minute"
        and dt(r["start_utc"]) == opening
    ]
    if not reference or not target:
        return {
            "status": "UNSCORABLE",
            "reason": "EXACT_CLOSE_OR_FIRST_5M_BAR_MISSING",
            "opening_return": None,
        }
    if (
        len({Decimal(r["close"]) for r in reference}) > 1
        or len({Decimal(r["close"]) for r in target}) > 1
    ):
        return {
            "status": "UNSCORABLE",
            "reason": "CONFLICTING_CAPTURE_REVISIONS",
            "opening_return": None,
        }
    previous, first = reference[0], target[0]
    if (
        previous.get("adjusted") != first.get("adjusted")
        or previous.get("ticker") != "NVDA"
        or first.get("ticker") != "NVDA"
        or dt(previous["first_seen"]) < close
        or dt(first["first_seen"]) < opening + timedelta(minutes=5)
    ):
        return {
            "status": "UNSCORABLE",
            "reason": "CONFLICTING_OR_INCOMPLETE_OUTCOME",
            "opening_return": None,
        }
    with localcontext() as ctx:
        ctx.prec = 256
        value = (Decimal(first["close"]) - Decimal(previous["close"])) / Decimal(previous["close"])
    return {
        "status": "POSTHOC_OUTCOME_ONLY",
        "source": source,
        "previous_close": previous["close"],
        "first_5m_close": first["close"],
        "opening_return": str(value),
        "completed_at": (opening + timedelta(minutes=5)).isoformat(),
        "first_seen": first["first_seen"],
        "decision_feature": False,
        "revision_history_asof_verified": False,
    }


def historical_gate(primary, secondary, equities, close, opening):
    """No ratio, liquidity, first-seen or feature is inferred from raw price rows."""
    rows = [
        r
        for r in primary
        if r.get("interval") in {"1m", "1h"}
        and close <= dt(r["start_utc"])
        and dt(r["start_utc"]) + timedelta(seconds=DURATIONS[r["interval"]]) <= opening
    ]
    pools = [
        r
        for r in secondary
        if r.get("interval") in {"1m", "1h"}
        and close <= dt(r["start_utc"])
        and dt(r["start_utc"]) + timedelta(seconds=DURATIONS[r["interval"]]) <= opening
    ]
    primary_density, pool_density = density(primary, opening), density(secondary, opening)
    anchors = [
        r
        for r in primary + secondary
        if r.get("interval") in {"1m", "1h"}
        and dt(r["start_utc"]) + timedelta(seconds=DURATIONS[r["interval"]]) == close
    ]
    paired = outcome(equities, close, opening, "MASSIVE")
    stages = {
        "token_intraday_primary": bool(rows),
        "token_intraday_any_captured_source": bool(rows or pools),
        "exact_independent_close_and_opening_bar": paired["status"] == "POSTHOC_OUTCOME_ONLY",
        "raw_token_bar_completing_at_previous_close": bool(anchors),
        "primary_minute_density": primary_density["density_only_pass"],
        "secondary_pool_minute_density": pool_density["density_only_pass"],
        "historical_asof_economic_ratio": False,
        "historical_authoritative_liquidity": False,
        "verified_comparable_volume_units": False,
        "point_in_time_features_and_revisions": False,
        "decision_time_news_coverage": False,
        "complete_authoritative_trust_samples": False,
    }
    reasons = []
    if not anchors:
        reasons.append("RAW_CLOSE_TIME_TOKEN_BAR_MISSING_FOR_WEEKEND_RETURN")
    if any(r.get("capture_revision_conflict") for r in rows):
        reasons.append("PRIMARY_CAPTURE_REVISIONS_CONFLICT")
    if not stages["token_intraday_any_captured_source"]:
        reasons.append("NO_CAPTURED_OFF_HOURS_INTRADAY_TOKEN_ROWS")
    if not stages["exact_independent_close_and_opening_bar"]:
        reasons.append(paired["reason"])
    if not stages["primary_minute_density"]:
        reasons.append("PRIMARY_END_WINDOW_DENSITY_INSUFFICIENT")
    if stages["secondary_pool_minute_density"] and not stages["primary_minute_density"]:
        reasons.append("SECONDARY_POOL_DENSITY_IS_NOT_PRIMARY_TOKEN_AUTHORITY")
    reasons.extend(
        [
            "ASOF_TOKEN_SHARE_RATIO_UNVERIFIED",
            "HISTORICAL_AUTHORITATIVE_LIQUIDITY_ABSENT",
            "PRIMARY_CANDLE_VOLUME_UNIT_UNKNOWN",
            "HISTORICAL_FIRST_AVAILABILITY_UNPROVEN",
            "HISTORICAL_REVISION_LEDGER_UNVERIFIED",
            "DECISION_TIME_NEWS_COVERAGE_UNVERIFIED",
            "NO_QUALIFYING_TRUST_FEATURE_SAMPLES",
        ]
    )
    return {
        "previous_regular_close": close.isoformat(),
        "decision_at": opening.isoformat(),
        "primary_off_hours_intraday_rows": len(rows),
        "secondary_off_hours_rows": len(pools),
        "raw_previous_close_token_bars": anchors,
        "primary_density": primary_density,
        "secondary_density": pool_density,
        "stages": stages,
        "outcome": paired,
        "historical_ratio": None,
        "effective_price_per_share": None,
        "normalized_deviation": None,
        "required_features": None,
        "qualifies": False,
        "rejection_reasons": reasons,
    }


def audit():
    if AUDIT.exists():
        raise ValueError("Existing audit must not be overwritten")
    backfill = json.loads(BACKFILL.read_text())
    if not backfill.get("completed_at"):
        raise ValueError("Complete the isolated capture before auditing")
    # The first capture retained the transport's third return (raw envelope).
    # Preserve that evidence while exposing its scalar business status correctly.
    for capture in backfill["captures"]:
        status = capture.get("business_status")
        if isinstance(status, dict):
            capture["response_envelope"] = status
            capture["business_status"] = status.get("code", status.get("status"))
    save(BACKFILL, backfill)
    existing, databases = inventory()
    equity_rows = [
        {
            "source": r["source"],
            "ticker": r["ticker"],
            "interval": r.get("interval"),
            "start_utc": r["source_timestamp"],
            "first_seen": r["ingestion_timestamp"],
            "adjusted": r.get("adjusted"),
            "close": r["close"],
        }
        for r in existing["equity_observations"]
        if r.get("kind") == "BAR"
    ]
    equity_rows.extend(backfill["equity_bars"])
    twelve_rows = []
    for name in ["TWELVE_DATA_NVDA_AUTHENTICATED_FEASIBILITY", "TWELVE_DATA_NVDA_HISTORICAL_DEPTH"]:
        data = json.loads((ROOT / f"docs/evidence/{name}.json").read_text())
        for interval, history in data["historical"].items():
            twelve_rows.extend(
                {
                    **r,
                    "source": "TWELVE_DATA",
                    "ticker": "NVDA",
                    "interval": "1minute" if interval == "1min" else "5minute",
                    "first_seen": history["first_seen"],
                    "adjusted": True,
                }
                for r in history["bars"]
            )
    calendar = USEquityCalendar()
    at = dt(backfill.get("deepening_completed_at", backfill["completed_at"]))
    start = at - timedelta(days=180)
    result = {
        "timestamp_utc": now().isoformat(),
        "evidence_kind": "REAL_DATA_AUDIT_NO_SYNTHETIC_COUNTS",
        "production_writes": 0,
        "gates_modified": False,
        "execution_calls": 0,
        "database_live_counts": databases,
        "unique_existing_live_counts": {t: len(rows) for t, rows in existing.items()},
        "new_raw_binance_rows": len(backfill["token_bars"]),
        "new_raw_massive_rows": len(backfill["equity_bars"]),
        "equity_existing_massive": summary(
            [{**r, "start_utc": r["source_timestamp"]} for r in existing["equity_observations"]]
        ),
        "equity_combined_massive": summary(equity_rows),
        "equity_twelve_diagnostic_only": summary(twelve_rows),
        "calendar": calendar.data,
        "lookback_start": start.isoformat(),
        "calendar_reopenings_in_180_days": len(windows(calendar, start, at)),
        "representations": {},
    }

    for issuer, contract in TOKENS.items():
        old = [r for r in existing["token_observations"] if r.get("contract") == contract]
        raw = [
            {
                "source": r["source"],
                "interval": r.get("interval"),
                "start_utc": r["source_timestamp"],
                "first_seen": r["ingestion_timestamp"],
                "close": r.get("close"),
                "historical_ratio": None,
            }
            for r in old
            if r.get("kind") == "CANDLE" and r.get("source_timestamp")
        ]
        raw.extend(r for r in backfill["token_bars"] if r["issuer"] == issuer)
        unique = {}
        conflicts = set()
        for row in raw:
            row["start_utc"] = dt(row["start_utc"]).isoformat()
            key = (row["interval"], row["start_utc"])
            if key in unique and Decimal(unique[key]["close"]) != Decimal(row["close"]):
                conflicts.add(key)
            if key not in unique or row["first_seen"] < unique[key]["first_seen"]:
                unique[key] = row
        raw = list(unique.values())
        for row in raw:
            row["capture_revision_conflict"] = (row["interval"], row["start_utc"]) in conflicts
        secondary = []
        for name in [
            "FREE_PROVIDER_GECKOTERMINAL_FEASIBILITY",
            "FREE_PROVIDER_GECKOTERMINAL_REVERIFIED",
        ]:
            data = json.loads((ROOT / f"docs/evidence/{name}.json").read_text())
            for frame, history in data["geckoterminal"][issuer].get("history", {}).items():
                if history.get("pool") != POOLS[issuer]:
                    continue
                interval = {"minute": "1m", "minute_preopen": "1m", "hour": "1h", "day": "1d"}[
                    frame
                ]
                secondary.extend(
                    {
                        "source": "GECKOTERMINAL_POOL",
                        "interval": interval,
                        "start_utc": datetime.fromtimestamp(int(r[0]), UTC).isoformat(),
                        "close": str(r[4]),
                        "first_seen": data["completed_at"],
                    }
                    for r in history["bars"]
                )
        if issuer == "ondo":
            data = json.loads(
                (
                    ROOT / "docs/evidence/FREE_PROVIDER_GECKOTERMINAL_HOURLY_RECOVERY.json"
                ).read_text()
            )
            rows = data["response"]["data"]["attributes"]["ohlcv_list"]
            secondary.extend(
                {
                    "source": "GECKOTERMINAL_POOL",
                    "interval": "1h",
                    "start_utc": datetime.fromtimestamp(int(r[0]), UTC).isoformat(),
                    "close": str(r[4]),
                    "first_seen": data["timestamp_utc"],
                }
                for r in rows
                if int(r[0]) + 3600 <= dt(data["timestamp_utc"]).timestamp()
            )
        for capture in backfill["gecko"][issuer]["older_hourly"]:
            secondary.extend(
                {
                    "source": "GECKOTERMINAL_POOL",
                    "interval": "1h",
                    "start_utc": datetime.fromtimestamp(int(r[0]), UTC).isoformat(),
                    "close": str(r[4]),
                    "first_seen": capture["first_seen"],
                }
                for r in capture["bars"]
            )
        secondary = list({(r["interval"], r["start_utc"]): r for r in secondary}.values())
        all_times = [dt(r["start_utc"]) for r in raw + secondary]
        earliest, latest = min(all_times), max(all_times)
        full = windows(calendar, earliest, latest)
        bounded = windows(calendar, max(start, earliest), min(at, latest))
        episodes = [
            historical_gate(raw, secondary, equity_rows, w["close"], w["open"]) for w in bounded
        ]
        all_episodes = [
            historical_gate(raw, secondary, equity_rows, w["close"], w["open"]) for w in full
        ]
        for episode in all_episodes:
            episode["inside_current_baseline_180_day_lookback"] = (
                dt(episode["decision_at"]) >= start
            )
            if not episode["inside_current_baseline_180_day_lookback"]:
                episode["rejection_reasons"].append("OUTSIDE_CURRENT_BASELINE_180_DAY_LOOKBACK")
        independent = (
            {k: sum(e["stages"][k] for e in episodes) for k in episodes[0]["stages"]}
            if episodes
            else {}
        )
        order = [
            "token_intraday_primary",
            "exact_independent_close_and_opening_bar",
            "primary_minute_density",
            "historical_asof_economic_ratio",
            "historical_authoritative_liquidity",
            "verified_comparable_volume_units",
            "point_in_time_features_and_revisions",
            "decision_time_news_coverage",
            "complete_authoritative_trust_samples",
        ]
        cumulative, survivors = {}, episodes
        for k in order:
            survivors = [e for e in survivors if e["stages"][k]]
            cumulative[k] = len(survivors)
        metadata = [r for r in existing["token_metadata"] if r.get("contract") == contract]
        result["representations"][issuer] = {
            "contract": contract,
            "chain": "56",
            "diagnostic_pool": POOLS[issuer],
            "existing_observation_count": len(old),
            "existing_kind_counts": dict(Counter(r["kind"] for r in old)),
            "existing_observation_coverage": summary(
                [{**r, "start_utc": r["source_timestamp"]} for r in old]
            ),
            "primary_candle_coverage": summary(raw),
            "secondary_pool_coverage": summary(secondary),
            "primary_unique_candles": len(raw),
            "secondary_unique_candles": len(secondary),
            "primary_price_revision_conflicts": len(conflicts),
            "historical_ratio_classification": "HISTORICAL_RATIO_UNAVAILABLE",
            "existing_ratio_metadata_versions": [
                {
                    "ratio": r["token_to_share_ratio"],
                    "observed_at": r["ingestion_timestamp"],
                    "source_timestamp": r["source_timestamp"],
                }
                for r in metadata
            ],
            "historical_row_ratio_was_not_asof_ledger": True,
            "candidate_windows_full_captured_span": len(full),
            "candidate_windows_180_days": len(bounded),
            "survivors_independent_by_stage": independent,
            "survivors_cumulative_primary": cumulative,
            "rejection_counts": dict(
                Counter(reason for e in episodes for reason in e["rejection_reasons"])
            ),
            "episodes": episodes,
            "full_span_episodes": all_episodes,
            "full_span_rejection_counts": dict(
                Counter(reason for e in all_episodes for reason in e["rejection_reasons"])
            ),
            "full_span_posthoc_outcome_count": sum(
                e["outcome"]["status"] == "POSTHOC_OUTCOME_ONLY" for e in all_episodes
            ),
            "survivors_full_span_independent_by_stage": {
                k: sum(e["stages"][k] for e in all_episodes) for k in all_episodes[0]["stages"]
            }
            if all_episodes
            else {},
            "qualifying_baseline_episodes": 0,
            "qualifying_opening_model_episodes": 0,
            "real_analogues": 0,
            "liquidity_authority": "UNVERIFIED",
        }
    result["candidate_representation_windows"] = sum(
        r["candidate_windows_180_days"] for r in result["representations"].values()
    )
    result["distinct_candidate_opening_dates"] = len(
        {e["decision_at"] for r in result["representations"].values() for e in r["episodes"]}
    )
    result["distinct_posthoc_opening_outcomes"] = len(
        {
            e["decision_at"]
            for r in result["representations"].values()
            for e in r["episodes"]
            if e["outcome"]["status"] == "POSTHOC_OUTCOME_ONLY"
        }
    )
    result["full_span_distinct_posthoc_opening_outcomes"] = len(
        {
            e["decision_at"]
            for r in result["representations"].values()
            for e in r["full_span_episodes"]
            if e["outcome"]["status"] == "POSTHOC_OUTCOME_ONLY"
        }
    )
    result["real_qualifying_baseline_episodes"] = 0
    result["real_qualifying_opening_model_episodes"] = 0
    result["real_eligible_analogues"] = 0
    result["liquidity_authority"] = "UNVERIFIED"
    result["minimums_unchanged"] = {"baseline": 30, "opening_model": 30, "analogues": 3}
    save(AUDIT, result)
    print(
        json.dumps(
            {
                "audit": str(AUDIT.relative_to(ROOT)),
                "qualifying_counts": [0, 0, 0],
                "candidates": {
                    k: v["candidate_windows_180_days"] for k, v in result["representations"].items()
                },
            }
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--deepen", action="store_true")
    args = parser.parse_args()
    if args.collect:
        collect()
    if args.deepen:
        deepen()
    if args.audit:
        audit()


if __name__ == "__main__":
    main()
