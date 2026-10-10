"""Eight bounded Finnhub event/calendar reads. No app, database, quotes or execution."""

import argparse
import json
import logging
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.clients.common import ProviderError
from app.clients.finnhub import FinnhubClient
from app.config import Settings
from app.models.events import EventBatch
from app.providers.finnhub import FinnhubEventProvider, date_bounds
from app.providers.massive import ticker_path


class DiagnosticClient(FinnhubClient):
    def __init__(self, api_key):
        self.rate_headers = {}

        def headers(response):
            self.rate_headers = {
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

        super().__init__(
            api_key,
            attempts=1,
            timeout=10,
            http=httpx.Client(
                timeout=10,
                follow_redirects=False,
                trust_env=False,
                event_hooks={"response": [headers]},
            ),
        )

    def read(self, method, path, params=None, body=None, **kwargs):
        self.parameters, self.rate_headers = params or {}, {}
        return super().read(method, path, params, body, **kwargs)

    def record(self, *args):
        super().record(*args)
        self.evidence[-1].update(
            parameters=self.parameters, rate_limit_headers=self.rate_headers.copy()
        )


def summarize(result):
    if not isinstance(result, EventBatch):
        return result.model_dump(mode="json")
    records = result.records
    samples = records[:1] + records[-1:] if len(records) > 1 else records
    # Keep evidence bounded; no article text is necessary to prove normalization.
    samples = [r.model_dump(mode="json", exclude={"headline", "url"}) for r in samples]
    published = [r.published_timestamp for r in records if getattr(r, "published_timestamp", None)]
    dates = [r.event_date for r in records if getattr(r, "event_date", None)]
    return {
        **result.model_dump(mode="json", exclude={"records"}),
        "normalized_count": len(records),
        "quality_counts": dict(Counter(r.data_quality for r in records)),
        "quality_flags": dict(Counter(f for r in records for f in r.quality_flags)),
        "earliest_publication": min(published).isoformat() if published else None,
        "latest_publication": max(published).isoformat() if published else None,
        "earliest_event_date": min(dates).isoformat() if dates else None,
        "latest_event_date": max(dates).isoformat() if dates else None,
        "samples": samples,
    }


def diagnose(provider, tickers, news_start, news_end, earnings_start, earnings_end):
    checks = []
    operations = [
        ("US:status", "/stock/market-status", provider.get_market_status),
        ("US:holidays", "/stock/market-holiday", provider.get_market_holidays),
    ]
    for ticker in tickers:
        operations.extend(
            [
                (
                    ticker + ":news",
                    "/company-news",
                    lambda ticker=ticker: provider.get_company_news(ticker, news_start, news_end),
                ),
                (
                    ticker + ":earnings",
                    "/calendar/earnings",
                    lambda ticker=ticker: provider.get_earnings_calendar(
                        ticker, earnings_start, earnings_end
                    ),
                ),
            ]
        )
    for name, endpoint, operation in operations:
        before = len(provider.client.evidence)
        check = {"check": name, "endpoint": "GET " + endpoint}
        try:
            result = operation()
            status = result.status if isinstance(result, EventBatch) else "PASS"
            if not isinstance(result, EventBatch) and result.data_quality in {
                "MISSING",
                "STALE",
                "INVALID",
            }:
                status = "UNAVAILABLE" if result.data_quality == "INVALID" else "PARTIAL"
            check.update(status=status, result=summarize(result))
        except ProviderError as error:
            check.update(
                status="NOT_CONFIGURED" if error.kind == "NOT_CONFIGURED" else "UNAVAILABLE",
                reason=error.kind,
                http_status=error.http_status,
                business_status=error.business_status,
            )
        except (ValueError, TypeError, ArithmeticError):
            check.update(status="UNAVAILABLE", reason="INVALID_DATA_OR_CONFIGURATION")
        check["requests"] = provider.client.evidence[before:]
        checks.append(check)
    return {"checks": checks, "request_count": sum(len(c["requests"]) for c in checks)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-read-only", action="store_true")
    parser.add_argument("--news-start", required=True)
    parser.add_argument("--news-end", required=True)
    parser.add_argument("--earnings-start", required=True)
    parser.add_argument("--earnings-end", required=True)
    parser.add_argument("--tickers", nargs="+", default=["TSLA", "NVDA", "GOOGL"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.live_read_only or args.output.suffix != ".json" or args.output.exists():
        parser.error("Explicit read-only flag and a new JSON evidence path are required")
    try:
        tickers = tuple(ticker_path(t) for t in args.tickers)
        if not 1 <= len(tickers) <= 3 or len(set(tickers)) != len(tickers):
            raise ValueError()
        _, news_finish = date_bounds(args.news_start, args.news_end, 31)
        if news_finish > datetime.now(UTC).date():
            raise ValueError()
        date_bounds(args.earnings_start, args.earnings_end, 366)
        settings = Settings()
    except ValueError:
        parser.error("Invalid bounded input/configuration; values suppressed")
    logging.disable(logging.CRITICAL)
    started = datetime.now(UTC)
    client = DiagnosticClient(settings.finnhub_api_key)
    try:
        report = diagnose(
            FinnhubEventProvider(client),
            tickers,
            args.news_start,
            args.news_end,
            args.earnings_start,
            args.earnings_end,
        )
    finally:
        client.close()
    report.update(
        started_at=started.isoformat(),
        completed_at=datetime.now(UTC).isoformat(),
        credential_status="CONFIGURED" if settings.finnhub_api_key else "NOT_CONFIGURED",
        scope="READ_ONLY_EVENT_CONTEXT_NO_DATABASE_WRITES",
        execution_mode=settings.execution_mode,
        live_trading_enabled=settings.live_trading_enabled,
        gates_changed=False,
        equity_quotes_requested=False,
        historical_candles_requested=False,
        production_persistence=False,
        transaction_broadcast=False,
    )
    content = json.dumps(report, indent=2) + "\n"
    if any(secret in content for secret in settings.redaction_values()):
        raise RuntimeError("Evidence refused: configured sensitive value detected")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as target:
        target.write(content)
    print("Finnhub event diagnostic saved; requests=" + str(report["request_count"]))


if __name__ == "__main__":
    main()
