"""Isolated market-data investigation. No application, database, wallet or execution access."""

import argparse
import json
import logging
import os
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import httpx
from dotenv import dotenv_values
from pydantic import ValidationError

from app.clients.alpaca import AlpacaClient
from app.clients.binance_web3 import BinanceWeb3Client
from app.clients.common import ProviderError, ReadTransport
from app.clients.finnhub import EVENT_PATHS, FinnhubClient
from app.config import ROOT_DIR, Settings
from app.models.data import source_time
from app.providers.alpaca import AlpacaProvider, observed_at
from app.providers.binance import (
    PREFIX,
    BinanceMarketProvider,
    BinanceRWAProvider,
    RWAToken,
    metadata,
)
from app.services.calendar import USEquityCalendar

TICKERS = ("TSLA", "NVDA", "GOOGL")
FINNHUB_PATHS = EVENT_PATHS | {"/quote", "/stock/candle"}
INFO_TYPES = {"perpDexs", "metaAndAssetCtxs", "l2Book", "candleSnapshot"}
INFO_URL = "https://api.hyperliquid.xyz/info"
CALENDAR = USEquityCalendar(mode="DEMO")


def now():
    return datetime.now(UTC)


@lru_cache(maxsize=100000)
def regime(at):
    try:
        return CALENDAR.status(at).state
    except ProviderError:
        return "UNKNOWN"


def clean_number(value, *, positive=False):
    if isinstance(value, (bool, float)) or value is None:
        raise ValueError("Invalid exact number")
    value = Decimal(value)
    if not value.is_finite() or (positive and value <= 0):
        raise ValueError("Invalid exact number")
    return str(value)


def history_summary(rows, minutes, start, end):
    times = [r.source_timestamp for r in rows]
    unique = sorted(set(times))
    step = timedelta(minutes=minutes)
    counts = Counter(regime(t) for t in unique)
    # Calendar slots are potential observations, not guaranteed trade-generated bars.
    potential = Counter()
    cursor = observed_at(start)
    while cursor <= observed_at(end):
        potential[regime(cursor)] += 1
        cursor += step
    observed_by_regime = dict(counts)
    return {
        "status": "PASS" if rows else "UNAVAILABLE",
        "valid_observations": len(rows),
        "duplicates": len(times) - len(unique),
        "earliest": unique[0].isoformat() if unique else None,
        "latest": unique[-1].isoformat() if unique else None,
        "interval_minutes": minutes,
        "regime_counts": observed_by_regime,
        "potential_calendar_slots": dict(potential),
        "unobserved_slots_not_necessarily_provider_loss": {
            k: max(v - counts[k], 0) for k, v in potential.items()
        },
        "gaps_larger_than_interval": sum(
            b - a > step for a, b in zip(unique, unique[1:], strict=False)
        ),
        "maximum_gap_seconds": max(
            ((b - a).total_seconds() for a, b in zip(unique, unique[1:], strict=False)),
            default=None,
        ),
        "sample": [r.model_dump(mode="json") for r in ([rows[0], rows[-1]] if rows else [])],
        "historical_revision_asof_verified": False,
    }


class EvidenceMixin:
    """Capture request context and safe rate headers without URLs or authorization material."""

    def setup_http(self):
        self.safe_rate_headers = {}

        def headers(response):
            self.safe_rate_headers = {
                k.lower(): v
                for k, v in response.headers.items()
                if k.lower()
                in {
                    "x-ratelimit-limit",
                    "x-ratelimit-remaining",
                    "x-ratelimit-reset",
                    "retry-after",
                }
                and re.fullmatch(r"[0-9.]+", v)
            }

        return httpx.Client(
            timeout=15, follow_redirects=False, trust_env=False, event_hooks={"response": [headers]}
        )

    def read(self, method, path, params=None, body=None, **kwargs):
        self.current_parameters, self.current_body = params or {}, body
        self.safe_rate_headers = {}
        return super().read(method, path, params, body, **kwargs)

    def record(self, *args):
        super().record(*args)
        self.evidence[-1].update(
            parameters=self.current_parameters,
            payload=self.current_body,
            rate_limit_headers=self.safe_rate_headers.copy(),
        )


class InspectAlpaca(EvidenceMixin, AlpacaClient):
    def __init__(self, settings):
        super().__init__(
            settings.alpaca_api_key, settings.alpaca_secret_key, http=self.setup_http(), attempts=1
        )
        self.payload = {}

    def validate(self, raw):
        result = super().validate(raw)
        self.payload = raw
        return result


class InspectFinnhub(EvidenceMixin, FinnhubClient):
    # Legacy multi-provider diagnostic only; production client remains event-only.
    paths = FINNHUB_PATHS

    def __init__(self, *, key=None, http=None):
        super().__init__(key, http=http or self.setup_http(), attempts=1, timeout=15)


def PublicProbe(provider, **kwargs):
    """Preserve the existing diagnostic entry point while sharing Finnhub transport."""
    if provider == "FINNHUB":
        return InspectFinnhub(**kwargs)
    if provider != "HYPERLIQUID":
        raise ValueError("Unsupported diagnostic provider")
    return HyperliquidProbe(provider, **kwargs)


class HyperliquidProbe(EvidenceMixin, ReadTransport):
    def __init__(self, provider, *, key=None, url=INFO_URL, enabled=True, http=None):
        self.key, self.url, self.enabled = key, url, enabled
        super().__init__(
            provider,
            http=http or self.setup_http(),
            attempts=1,
            min_interval=0.3,
            timeout=15,
        )

    def authorize(self, method, path):
        if method != "POST" or path != "/info":
            raise ProviderError(self.provider, "READ_ONLY_OPERATION_REQUIRED")
        elif not self.enabled:
            raise ProviderError(self.provider, "DISABLED")
        elif self.url != INFO_URL:
            raise ProviderError(self.provider, "UNVERIFIED_INFO_URL")

    def build_request(self, method, path, params, body):
        self.authorize(method, path)
        if params or not isinstance(body, dict) or body.get("type") not in INFO_TYPES:
            raise ProviderError(self.provider, "READ_ONLY_OPERATION_REQUIRED")
        allowed = {
            "perpDexs": {"type"},
            "metaAndAssetCtxs": {"type", "dex"},
            "l2Book": {"type", "coin"},
            "candleSnapshot": {"type", "req"},
        }
        if set(body) != allowed[body["type"]]:
            raise ProviderError(self.provider, "READ_ONLY_OPERATION_REQUIRED")
        return self.http.build_request("POST", self.url, json=body)

    def sensitive_values(self, request):
        return (self.key.get_secret_value(),) if self.key else ()

    def validate(self, raw):
        if isinstance(raw, dict) and ("error" in raw or "message" in raw):
            raise ProviderError(self.provider, "BUSINESS_FAILURE", 200, "ERROR_BODY_SUPPRESSED")
        if not isinstance(raw, (dict, list)):
            raise ValueError("Expected market-data JSON")
        return raw, "OK"


def attempt(client, label, operation):
    before = len(client.evidence)
    try:
        result = operation()
        return {
            "label": label,
            "status": "PASS",
            "result": result,
            "requests": client.evidence[before:],
        }
    except ProviderError as error:
        return {
            "label": label,
            "status": "NOT_CONFIGURED" if error.kind == "NOT_CONFIGURED" else "UNAVAILABLE",
            "reason": error.kind,
            "http_status": error.http_status,
            "business_status": error.business_status,
            "requests": client.evidence[before:],
        }
    except (ValueError, TypeError, KeyError, ArithmeticError):
        return {
            "label": label,
            "status": "NOT_VERIFIED",
            "reason": "INVALID_OR_UNEXPECTED_DATA",
            "requests": client.evidence[before:],
        }


def alpaca(settings, start, end):
    client, checks = InspectAlpaca(settings), []
    try:
        for feed in ("iex", "sip", "delayed_sip", "boats", "overnight"):
            provider = AlpacaProvider(client, feed=feed)  # Entitlement stays UNKNOWN.
            for ticker in TICKERS:

                def quote(ticker=ticker, provider=provider, feed=feed):
                    row = provider.get_latest_quote(ticker)
                    wire = client.payload["quotes"][ticker]
                    result = row.model_dump(mode="json")
                    result.update(
                        receipt_age_seconds=(
                            row.ingestion_timestamp - row.source_timestamp
                        ).total_seconds(),
                        source_regime=regime(row.source_timestamp),
                        retrieval_regime=regime(row.ingestion_timestamp),
                        wire_quote={
                            k: wire.get(k)
                            for k in ("t", "bp", "ap", "bs", "as", "bx", "ax", "c", "z")
                        },
                        feed_confirmed_by_response="IEX_VENUE_CODES_MATCH"
                        if feed == "iex" and wire.get("bx") == wire.get("ax") == "V"
                        else "NOT_VERIFIED_NO_FEED_ECHO",
                    )
                    return result

                checks.append(attempt(client, f"{ticker}:{feed}:quote", quote))
                if feed in {"iex", "sip", "boats"}:
                    for minutes in (1, 5):

                        def bars(ticker=ticker, provider=provider, minutes=minutes):
                            rows = provider.get_historical_bars(
                                ticker, start, end, multiplier=minutes, max_pages=2
                            )
                            result = history_summary(rows, minutes, start, end)
                            result["pagination_complete"] = provider.last_page_complete
                            return result

                        checks.append(attempt(client, f"{ticker}:{feed}:{minutes}minute", bars))
        provider = AlpacaProvider(client, feed="sip")
        for ticker in TICKERS:

            def old(ticker=ticker):
                a, b = "2016-01-04T14:30:00Z", "2016-01-04T15:00:00Z"
                rows = provider.get_historical_bars(ticker, a, b, max_pages=1)
                return history_summary(rows, 1, a, b)

            checks.append(attempt(client, f"{ticker}:sip:2016_depth_probe", old))
        for feed in ("iex", "boats"):
            provider = AlpacaProvider(client, feed=feed)
            for ticker in TICKERS:

                def weekend(ticker=ticker, provider=provider):
                    a, b = "2026-10-03T04:00:00Z", "2026-10-04T04:00:00Z"
                    rows = provider.get_historical_bars(ticker, a, b, max_pages=1)
                    return history_summary(rows, 1, a, b)

                checks.append(attempt(client, f"{ticker}:{feed}:saturday_probe", weekend))
        return {
            "account_plan": "NOT_VERIFIED",
            "configured_feed": settings.alpaca_feed,
            "checks": checks,
            "request_count": len(client.evidence),
        }
    finally:
        client.close()


def finnhub(key):
    client, checks = PublicProbe("FINNHUB", key=key), []
    today = now().date()
    since, until = (today - timedelta(days=7)).isoformat(), today.isoformat()
    earnings_end = (today + timedelta(days=90)).isoformat()
    try:
        for path in ("/stock/market-status", "/stock/market-holiday"):

            def market(path=path):
                raw, received, _ = client.read("GET", path, {"exchange": "US"})
                return {"body": raw, "received_at": received.isoformat()}

            checks.append(attempt(client, path, market))
        for ticker in TICKERS:

            def quote(ticker=ticker):
                raw, received, _ = client.read("GET", "/quote", {"symbol": ticker})
                price = clean_number(raw.get("c"), positive=True)
                timestamp = source_time(raw["t"] * 1000)
                age = (received - timestamp).total_seconds()
                return {
                    "ticker": ticker,
                    "price": price,
                    "source_timestamp": timestamp.isoformat(),
                    "received_at": received.isoformat(),
                    "age_seconds": age,
                    "quality": "STALE" if age > 120 else "UNKNOWN_DELAY_ENTITLEMENT",
                    "source_regime": regime(timestamp),
                    "delay_verified": False,
                    "body": {k: raw.get(k) for k in ("c", "d", "dp", "h", "l", "o", "pc", "t")},
                }

            checks.append(attempt(client, ticker + ":quote", quote))

            def news(ticker=ticker):
                raw, received, _ = client.read(
                    "GET", "/company-news", {"symbol": ticker, "from": since, "to": until}
                )
                if not isinstance(raw, list):
                    raise ValueError()
                unique, duplicates, invalid = {}, 0, 0
                for row in raw:
                    try:
                        published = source_time(row["datetime"] * 1000)
                        if (
                            published > received
                            or not since <= published.date().isoformat() <= until
                        ):
                            raise ValueError()
                        if row.get("related") and ticker not in row["related"].split(","):
                            raise ValueError()
                        identity = str(row["id"])
                        if identity in unique:
                            duplicates += 1
                        unique[identity] = {
                            "id": row["id"],
                            "source": row["source"],
                            "url": row["url"],
                            "published_at": published.isoformat(),
                            "ingested_at": received.isoformat(),
                        }
                    except (KeyError, ValueError, TypeError):
                        invalid += 1
                records = sorted(unique.values(), key=lambda r: r["published_at"])
                return {
                    "ticker": ticker,
                    "requested_from": since,
                    "requested_to": until,
                    "returned_count": len(raw),
                    "unique_valid_count": len(records),
                    "duplicates": duplicates,
                    "invalid_or_outside_window": invalid,
                    "earliest_publication": records[0]["published_at"] if records else None,
                    "latest_publication": records[-1]["published_at"] if records else None,
                    "samples": records[:1] + records[-1:] if records else [],
                    "complete_exhaustive_coverage": False,
                }

            checks.append(attempt(client, ticker + ":news", news))

            def earnings(ticker=ticker):
                raw, received, _ = client.read(
                    "GET",
                    "/calendar/earnings",
                    {"symbol": ticker, "from": until, "to": earnings_end},
                )
                rows = raw["earningsCalendar"]
                if not isinstance(rows, list) or any(r.get("symbol") != ticker for r in rows):
                    raise ValueError()
                return {
                    "ticker": ticker,
                    "requested_from": until,
                    "requested_to": earnings_end,
                    "received_at": received.isoformat(),
                    "count": len(rows),
                    "samples": [
                        {k: r.get(k) for k in ("symbol", "date", "hour", "year", "quarter")}
                        for r in rows[:3]
                    ],
                    "publication_timestamp_available": False,
                }

            checks.append(attempt(client, ticker + ":earnings", earnings))

        def candles():
            params = {
                "symbol": "NVDA",
                "resolution": "1",
                "from": int(observed_at("2026-10-09T13:30:00Z").timestamp()),
                "to": int(observed_at("2026-10-09T14:00:00Z").timestamp()),
            }
            raw, received, _ = client.read("GET", "/stock/candle", params)
            return {
                "business_status": raw.get("s"),
                "count": len(raw.get("t", [])),
                "received_at": received.isoformat(),
            }

        checks.append(attempt(client, "NVDA:optional_historical_candle_entitlement", candles))
        return {
            "checks": checks,
            "request_count": len(client.evidence),
            "account_plan": "NOT_VERIFIED",
        }
    finally:
        client.close()


def hyperliquid(url, enabled):
    client = PublicProbe("HYPERLIQUID", url=url, enabled=enabled)
    checks, instruments, dexs = [], [], []
    try:
        discovery = attempt(
            client, "perpDexs", lambda: client.read("POST", "/info", body={"type": "perpDexs"})[0]
        )
        checks.append(discovery)
        if discovery["status"] != "PASS":
            return {"status": discovery["status"], "checks": checks}
        raw_dexs = discovery.pop("result")
        if not isinstance(raw_dexs, list) or len(raw_dexs) > 30:
            return {
                "status": "NOT_VERIFIED",
                "reason": "UNEXPECTED_OR_UNBOUNDED_DEX_LIST",
                "checks": checks,
            }
        for dex_index, dex in enumerate(raw_dexs):
            if dex is None:
                continue
            name = dex.get("name")
            if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", name):
                continue
            dexs.append({"index": dex_index, "name": name})
            meta = attempt(
                client,
                name + ":metaAndAssetCtxs",
                lambda name=name: client.read(
                    "POST", "/info", body={"type": "metaAndAssetCtxs", "dex": name}
                ),
            )
            checks.append(meta)
            if meta["status"] != "PASS":
                continue
            data, received, _ = meta.pop("result")
            if (
                not isinstance(data, list)
                or len(data) != 2
                or len(data[0].get("universe", [])) != len(data[1])
            ):
                meta.update(status="NOT_VERIFIED", reason="METADATA_CONTEXT_SCHEMA_CONFLICT")
                continue
            universe, contexts = data[0]["universe"], data[1]
            meta["universe_count"] = len(universe)
            for index, (instrument, context) in enumerate(zip(universe, contexts, strict=True)):
                symbol = instrument.get("name")
                if symbol not in {name + ":" + ticker for ticker in TICKERS}:
                    continue
                numeric = {}
                for k in (
                    "markPx",
                    "midPx",
                    "oraclePx",
                    "funding",
                    "openInterest",
                    "dayNtlVlm",
                    "prevDayPx",
                ):
                    numeric[k] = clean_number(context[k]) if context.get(k) is not None else None
                item = {
                    "dex": name,
                    "dex_index": dex_index,
                    "symbol": symbol,
                    "ticker": symbol.split(":", 1)[1],
                    "index_in_meta": index,
                    "asset_id": 100000 + dex_index * 10000 + index,
                    "metadata": {
                        k: instrument.get(k)
                        for k in (
                            "name",
                            "szDecimals",
                            "maxLeverage",
                            "isDelisted",
                            "marginMode",
                            "onlyIsolated",
                            "growthMode",
                        )
                    },
                    "context": numeric,
                    "source_timestamp": None,
                    "retrieved_at": received.isoformat(),
                    "timestamp_quality": "CONTEXT_TIMESTAMP_NOT_EXPOSED",
                    "instrument_type": "SECONDARY_PERPETUAL_NOT_OFFICIAL_EQUITY",
                    "legal_underlying_mapping": "NOT_VERIFIED_BY_TICKER_METADATA_ALONE",
                }

                def book(symbol=symbol):
                    raw, receipt, _ = client.read(
                        "POST", "/info", body={"type": "l2Book", "coin": symbol}
                    )
                    if raw.get("coin") != symbol or len(raw.get("levels", [])) != 2:
                        raise ValueError()
                    timestamp = source_time(raw["time"])
                    return {
                        "coin": symbol,
                        "source_timestamp": timestamp.isoformat(),
                        "raw_time_ms": raw["time"],
                        "received_at": receipt.isoformat(),
                        "age_seconds": (receipt - timestamp).total_seconds(),
                        "level_counts": [len(side) for side in raw["levels"]],
                        "best_bid": raw["levels"][0][0] if raw["levels"][0] else None,
                        "best_ask": raw["levels"][1][0] if raw["levels"][1] else None,
                    }

                item["book"] = attempt(client, symbol + ":book", book)

                def history(symbol=symbol):
                    end_ms = int(now().timestamp()) // 300 * 300000
                    start_ms = end_ms - 48 * 3600000
                    raw, receipt, _ = client.read(
                        "POST",
                        "/info",
                        body={
                            "type": "candleSnapshot",
                            "req": {
                                "coin": symbol,
                                "interval": "5m",
                                "startTime": start_ms,
                                "endTime": end_ms,
                            },
                        },
                    )
                    valid = [
                        r
                        for r in raw
                        if r.get("s") == symbol
                        and r.get("i") == "5m"
                        and start_ms <= r.get("t", 0) < end_ms
                        and r.get("T", end_ms) < end_ms
                    ]
                    times = sorted({r["t"] for r in valid})
                    return {
                        "received_at": receipt.isoformat(),
                        "requested_start_ms": start_ms,
                        "requested_end_ms": end_ms,
                        "returned_count": len(raw),
                        "completed_count": len(valid),
                        "duplicates": len(valid) - len(times),
                        "earliest": source_time(times[0]).isoformat() if times else None,
                        "latest": source_time(times[-1]).isoformat() if times else None,
                        "regime_counts": dict(Counter(regime(source_time(t)) for t in times)),
                        "gaps_larger_than_5m": sum(
                            b - a > 300000 for a, b in zip(times, times[1:], strict=False)
                        ),
                        "not_tokenized_equity_baseline": True,
                    }

                item["history"] = attempt(client, symbol + ":5m_history", history)
                instruments.append(item)
        return {
            "status": "PARTIAL" if instruments else "UNAVAILABLE",
            "dexs": dexs,
            "checks": checks,
            "instruments": instruments,
            "request_count": len(client.evidence),
            "ticker_status": {
                t: "PARTIAL" if any(i["ticker"] == t for i in instruments) else "UNAVAILABLE"
                for t in TICKERS
            },
        }
    finally:
        client.close()


def binance(settings):
    client = BinanceWeb3Client(
        settings.binance_web3_api_key,
        settings.binance_web3_secret_key,
        recv_window=60000,
        attempts=1,
        timeout=15,
    )
    rwa, market, checks = BinanceRWAProvider(client), BinanceMarketProvider(client), []
    try:
        catalog = attempt(client, "BSC:RWA_catalog", lambda: rwa.tokens("56"))
        checks.append(catalog)
        if catalog["status"] != "PASS":
            return {"checks": checks, "request_count": len(client.evidence)}
        tokens = [t for t in catalog.pop("result") if t.ticker in TICKERS]
        catalog["target_representation_count"] = len(tokens)
        catalog["quarantined_catalog_rows"] = len(rwa.catalog_rejections)
        for token in tokens[:12]:

            def profile(token=token):
                row = rwa.profile(token)
                obs = rwa.observation(row)
                info = market.prices([row], info=True)[0]
                return {
                    "ticker": row.ticker,
                    "issuer": row.platform_id,
                    "chain": row.chain_id,
                    "contract": row.contract,
                    "symbol": row.token_symbol,
                    "current_ratio": str(row.token_to_share_ratio),
                    "historical_ratio_asof": "NOT_VERIFIED",
                    "price": str(obs.token_price),
                    "source_timestamp": obs.source_timestamp.isoformat()
                    if obs.source_timestamp
                    else None,
                    "received_at": obs.ingestion_timestamp.isoformat(),
                    "quality": obs.data_quality,
                    "age_seconds": (obs.ingestion_timestamp - obs.source_timestamp).total_seconds()
                    if obs.source_timestamp
                    else None,
                    "market_state": row.market_state,
                    "liquidity": info.provider_metadata.get("liquidity"),
                    "volume24H": str(info.volume) if info.volume is not None else None,
                    "volume_unit": info.volume_unit,
                    "referencePrice_is_independent": False,
                }

            checks.append(attempt(client, token.ticker + ":" + token.platform_id, profile))
        return {
            "checks": checks,
            "request_count": len(client.evidence),
            "production_persistence": False,
        }
    finally:
        client.close()


def catalog_audit(settings):
    """Explain target discovery omissions without repairing or accepting invalid records."""
    client = BinanceWeb3Client(
        settings.binance_web3_api_key,
        settings.binance_web3_secret_key,
        recv_window=60000,
        attempts=1,
        timeout=15,
    )
    try:

        def audit():
            raw, receipt, _ = client.read("GET", PREFIX + "rwa/tokens", {"binanceChainId": "56"})
            if not isinstance(raw, list):
                raise ValueError()
            rows = []
            for row in raw:
                if not isinstance(row, dict) or row.get("underlyingTicker") not in TICKERS:
                    continue
                result = {
                    k: row.get(k)
                    for k in (
                        "underlyingTicker",
                        "platformId",
                        "binanceChainId",
                        "assetType",
                    )
                }
                try:
                    metadata(RWAToken.model_validate(row), receipt)
                    result["status"] = "PASS"
                except ValidationError as error:
                    result.update(
                        status="UNAVAILABLE",
                        rejected_fields=[
                            {"field": list(e["loc"]), "type": e["type"]}
                            for e in error.errors(include_input=False, include_url=False)
                        ],
                    )
                except (ValueError, TypeError):
                    result.update(status="UNAVAILABLE", reason="INVALID_METADATA")
                rows.append(result)
            return {"received_at": receipt.isoformat(), "target_rows": rows}

        check = attempt(client, "BSC:raw_target_catalog_schema_audit", audit)
        return {"checks": [check], "request_count": len(client.evidence)}
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-read-only", action="store_true")
    parser.add_argument("--catalog-audit-only", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--start", default="2026-10-08T00:00:00Z")
    parser.add_argument("--end", default="2026-10-10T00:00:00Z")
    args = parser.parse_args()
    if not args.live_read_only or args.output.exists() or args.output.suffix != ".json":
        parser.error("Explicit read-only authorization and a new JSON output are required")
    if not 0 < (observed_at(args.end) - observed_at(args.start)).total_seconds() <= 172800:
        parser.error("History must be an explicit interval of at most two days")
    logging.disable(logging.CRITICAL)
    settings = Settings()
    values = {**dotenv_values(ROOT_DIR / ".env"), **os.environ}
    key = settings.finnhub_api_key
    url = values.get("HYPERLIQUID_API_URL")
    enabled = str(values.get("HYPERLIQUID_ENABLED", "false")).lower() == "true"
    secrets = [
        v
        for k, v in values.items()
        if v and any(s in k.upper() for s in ("KEY", "SECRET", "PASSWORD"))
    ]
    report = {
        "started_at": now().isoformat(),
        "retrieval_regime": regime(now()),
        "production_changes": False,
        "production_database_writes": False,
        "execution_mode": settings.execution_mode,
        "live_trading_enabled": settings.live_trading_enabled,
        "require_simulation": settings.require_simulation,
        "config": {
            "ALPACA_API_KEY": "CONFIGURED" if settings.alpaca_api_key else "NOT_CONFIGURED",
            "ALPACA_SECRET_KEY": "CONFIGURED" if settings.alpaca_secret_key else "NOT_CONFIGURED",
            "FINNHUB_API_KEY": "CONFIGURED" if key else "NOT_CONFIGURED",
            "HYPERLIQUID_ENABLED": enabled,
            "HYPERLIQUID_API_URL": INFO_URL if url == INFO_URL else "UNVERIFIED_URL",
            "equity_provider": settings.equity_provider,
            "alpaca_quality": settings.alpaca_data_quality,
            "finnhub_consumed_by_production_settings": True,
            "hyperliquid_consumed_by_production_settings": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    operations = [
        ("alpaca", lambda: alpaca(settings, args.start, args.end)),
        ("finnhub", lambda: finnhub(key)),
        ("hyperliquid", lambda: hyperliquid(url, enabled)),
        ("binance", lambda: binance(settings)),
    ]
    if args.catalog_audit_only:
        operations = [("binance_catalog_audit", lambda: catalog_audit(settings))]
    for name, operation in operations:
        report[name] = operation()
        content = json.dumps(report, indent=2, default=str) + "\n"
        if any(secret in content for secret in secrets):
            raise RuntimeError("Evidence refused: sensitive configured value detected")
        args.output.write_text(content)
        print(
            name + " diagnostic saved; requests=" + str(report[name].get("request_count", 0)),
            flush=True,
        )
    report["completed_at"] = now().isoformat()
    args.output.write_text(json.dumps(report, indent=2, default=str) + "\n")


if __name__ == "__main__":
    main()
