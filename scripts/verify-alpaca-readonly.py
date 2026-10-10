"""Explicit, isolated Alpaca data diagnostic. No database, trading or wallet access."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.clients.alpaca import AlpacaClient
from app.clients.common import ProviderError
from app.config import Settings
from app.providers.alpaca import AlpacaProvider, observed_at


def diagnose(provider, start, end):
    report = {
        "scope": "NVDA_READ_ONLY_NO_PERSISTENCE",
        "tested_at": datetime.now(UTC).isoformat(),
        "feed": provider.feed,
        "account_plan": "UNKNOWN",
        "feed_entitlement": "NOT_VERIFIED",
        "trust_eligible": False,
        "token_equity_alignment": "NOT_TESTED",
        "transaction_broadcast": False,
        "checks": [],
    }
    for name, endpoint, operation in [
        ("quote", "/v2/stocks/quotes/latest", lambda: provider.get_latest_quote("NVDA")),
        (
            "1minute",
            "/v2/stocks/bars",
            lambda: provider.get_historical_bars("NVDA", start, end, multiplier=1, max_pages=1),
        ),
        (
            "5minute",
            "/v2/stocks/bars",
            lambda: provider.get_historical_bars("NVDA", start, end, multiplier=5, max_pages=1),
        ),
    ]:
        before = len(provider.client.evidence)
        check = {"check": name, "endpoint": "GET " + endpoint}
        try:
            result = operation()
            check["status"] = "PASS"
            if name == "quote":
                age = (result.ingestion_timestamp - result.source_timestamp).total_seconds()
                check.update(
                    observation=result.model_dump(mode="json"),
                    age_at_receipt_seconds=age,
                    within_120_seconds=0 <= age <= 120,
                    semantics="BID_ASK_MIDPOINT_NOT_LAST_TRADE_OR_OFFICIAL_CLOSE",
                )
            else:
                check.update(
                    count=len(result),
                    earliest=result[0].source_timestamp.isoformat() if result else None,
                    latest=result[-1].source_timestamp.isoformat() if result else None,
                    complete=provider.last_page_complete,
                    historical_revision_asof_verified=False,
                )
                if not result:
                    check["status"] = "NO_DATA"
        except ProviderError as error:
            check.update(
                status=error.kind,
                http_status=error.http_status,
                business_status=error.business_status,
            )
        except (ValueError, TypeError, ArithmeticError):
            check.update(status="INVALID_DATA_OR_CONFIGURATION")
        check["requests"] = provider.client.evidence[before:]
        check["completed_at"] = datetime.now(UTC).isoformat()
        report["checks"].append(check)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Authorize only the three data checks")
    parser.add_argument("--start", required=True, help="Explicit UTC RFC3339 history start")
    parser.add_argument("--end", required=True, help="Explicit UTC RFC3339 history end")
    parser.add_argument(
        "--output", type=Path, help="New .json evidence file; existing files refused"
    )
    args = parser.parse_args()
    if not args.live:
        parser.error("No calls made: --live is required for read-only provider verification")
    begin, finish = observed_at(args.start), observed_at(args.end)
    if not 0 < (finish - begin).total_seconds() <= 172800 or finish > datetime.now(UTC):
        parser.error("History must be a completed interval of at most two days")
    if args.output and (args.output.suffix != ".json" or args.output.exists()):
        parser.error("Output must be a new .json file")
    try:
        settings = Settings()
    except ValueError:
        parser.error("Invalid local settings; values suppressed")
    client = AlpacaClient(settings.alpaca_api_key, settings.alpaca_secret_key, attempts=1)
    try:
        report = diagnose(AlpacaProvider(client, feed=settings.alpaca_feed), args.start, args.end)
    finally:
        client.close()
    content = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as target:
            target.write(content)
    print(content, end="")


if __name__ == "__main__":
    main()
