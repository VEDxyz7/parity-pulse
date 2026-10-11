"""At most four historical market-data GETs; display artifact only, no DB writes.

Credentials come from existing Settings and are never printed or saved. Reuses the
verified Alpaca client/provider; does not alter provider selection or reference admission.
"""

import json
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from app.clients.alpaca import AlpacaClient
from app.clients.common import ProviderError
from app.config import Settings
from app.models.display_history import END, START, DisplayHistory
from app.providers.alpaca import AlpacaProvider
from app.services.display_history import HISTORY_PATH


def main():
    settings = Settings()
    client = AlpacaClient(
        settings.alpaca_api_key,
        settings.alpaca_secret_key,
        attempts=1,
        timeout=10,
        cache_ttl=0,
    )
    provider = AlpacaProvider(client, feed="sip", freshness="UNKNOWN")
    records, report = {}, {}
    try:
        for ticker in ("NVDA", "AAPL"):
            try:
                rows = provider.get_historical_bars(
                    ticker, START.isoformat(), END.isoformat(), multiplier=5, max_pages=2
                )
                if not provider.last_page_complete:
                    raise ValueError("Pagination incomplete")
                rows = [
                    r
                    for r in rows
                    if r.source_timestamp.astimezone(ZoneInfo("America/New_York")).weekday() < 5
                    and time(9, 30)
                    <= r.source_timestamp.astimezone(ZoneInfo("America/New_York")).time()
                    < time(16)
                ]
                item = DisplayHistory(
                    ticker=ticker,
                    status="AVAILABLE" if rows else "UNAVAILABLE",
                    captured_at=datetime.now(UTC),
                    observations=rows,
                )
                records[ticker] = item.model_dump(mode="json")
                report[ticker] = {
                    "status": item.status,
                    "bars": len(rows),
                    "first": rows[0].source_timestamp.isoformat() if rows else None,
                    "last": rows[-1].source_timestamp.isoformat() if rows else None,
                    "days": sorted({r.source_timestamp.date().isoformat() for r in rows}),
                }
            except (ProviderError, ValueError) as error:
                # Do not overwrite any previously verified capture with an error response.
                report[ticker] = {
                    "status": "UNAVAILABLE",
                    "reason": error.kind if isinstance(error, ProviderError) else "INVALID_HISTORY",
                    "http_status": error.http_status if isinstance(error, ProviderError) else None,
                }
        if records:
            existing = json.loads(HISTORY_PATH.read_text()) if HISTORY_PATH.exists() else {}
            existing.update(records)
            HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            temporary = HISTORY_PATH.with_suffix(".tmp")
            temporary.write_text(json.dumps(existing, indent=2) + "\n")
            temporary.replace(HISTORY_PATH)
    finally:
        client.close()
    print(
        json.dumps(
            {
                "endpoint": "GET /v2/stocks/bars",
                "feed": "sip",
                "results": report,
                "production_database_writes": 0,
                "execution_calls": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
