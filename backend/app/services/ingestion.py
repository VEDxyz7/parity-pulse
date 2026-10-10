from datetime import UTC, datetime
from urllib.parse import urlencode

from app.clients.common import ProviderError
from app.models.data import EquityObservation
from app.providers.massive import Bar, ticker_path, validate


class HistoricalIngestion:
    def __init__(self, repository, market=None, equity=None):
        self.repository, self.market, self.equity = repository, market, equity

    def token_candles(
        self, token, *, bar="1h", before=None, after=None, max_pages=3, limit=100, resume=True
    ):
        if not 1 <= max_pages <= 10:
            raise ValueError("Bounded requests required")
        resource = f"candles:{token.chain_id}:{token.contract}:{bar}:{before}:{after}"
        saved = self.repository.resume(mode=token.data_mode, resource=resource) if resume else None
        cursor = saved if saved is not None else after
        inserted = 0
        excluded = 0
        for page in range(max_pages):
            rows = self.market.candles(token, bar=bar, before=before, after=cursor, limit=limit)
            excluded += len(getattr(self.market, "candle_rejections", []))
            if not rows:
                return {
                    "inserted": inserted,
                    "pages": page + 1,
                    "complete": True,
                    "cursor": cursor,
                    "excluded_out_of_bounds": excluded,
                }
            next_cursor = min(int(r.raw_source_timestamp) for r in rows)
            if cursor is not None and next_cursor >= cursor:
                raise ProviderError("INGESTION", "PAGINATION_NOT_ADVANCING")
            inserted += self.repository.save(rows)
            self.repository.checkpoint(
                mode=token.data_mode,
                resource=resource,
                cursor=next_cursor,
                received=rows[0].ingestion_timestamp,
            )
            cursor = next_cursor
        return {
            "inserted": inserted,
            "pages": max_pages,
            "complete": False,
            "cursor": cursor,
            "excluded_out_of_bounds": excluded,
        }

    def token_trades(self, token, *, max_pages=3, limit=100, resume=True):
        if not 1 <= max_pages <= 10:
            raise ValueError("Bounded requests required")
        resource = f"trades:{token.chain_id}:{token.contract}"
        cursor = self.repository.resume(mode=token.data_mode, resource=resource) if resume else None
        seen = set()
        inserted = 0
        for page in range(max_pages):
            rows, next_cursor = self.market.trades(token, cursor=cursor, limit=limit)
            if next_cursor and (next_cursor == cursor or next_cursor in seen):
                raise ProviderError("INGESTION", "PAGINATION_NOT_ADVANCING")
            inserted += self.repository.save(rows)
            self.repository.checkpoint(
                mode=token.data_mode,
                resource=resource,
                cursor=next_cursor or None,
                received=rows[0].ingestion_timestamp if rows else datetime.now(UTC),
            )
            if not next_cursor:
                return {"inserted": inserted, "pages": page + 1, "complete": True, "cursor": None}
            seen.add(next_cursor)
            cursor = next_cursor
        return {"inserted": inserted, "pages": max_pages, "complete": False, "cursor": cursor}

    def equity_bars(self, ticker, start, end, *, max_pages=3, resume=True):
        # This legacy checkpoint is Massive-specific; never send its paths to Alpaca.
        if getattr(self.equity.client, "provider", None) != "MASSIVE":
            raise ProviderError("INGESTION", "PROVIDER_CHECKPOINT_NOT_SUPPORTED")
        if not 1 <= max_pages <= 10:
            raise ValueError("Bounded requests required")
        ticker = ticker_path(ticker)
        # Reuse the adapter's verified date validation before any call.
        for d in [start, end]:
            datetime.fromisoformat(d)
        if start > end:
            raise ValueError("Invalid historical range")
        path = f"/v2/aggs/ticker/{ticker}/range/1/minute/{start}/{end}"
        resource = "equity:" + path
        saved = self.repository.resume(mode=self.equity.mode, resource=resource) if resume else None
        request_path, params = (
            self.equity.client.page(saved, path)
            if saved
            else (path, {"adjusted": "true", "sort": "asc", "limit": 5000})
        )
        seen = set()
        inserted = 0
        for page in range(max_pages):
            data, received, _ = self.equity.client.read("GET", request_path, params, ttl=30)
            if data.get("ticker") != ticker or data.get("adjusted") is not True:
                raise ProviderError("MASSIVE", "CONFLICTING_BAR_CONTEXT")
            records = [
                EquityObservation(
                    **self.equity.prov(ticker + ":BAR", received, r.t, historical=True),
                    ticker=ticker,
                    price=r.c,
                    open=r.o,
                    high=r.h,
                    low=r.l,
                    close=r.c,
                    volume=r.v,
                    kind="BAR",
                    interval="1minute",
                    adjusted=True,
                )
                for r in validate(list[Bar], data.get("results"))
            ]
            next_url = data.get("next_url")
            if next_url:
                if next_url in seen:
                    raise ProviderError("MASSIVE", "PAGINATION_LOOP")
                request_path, params = self.equity.client.page(next_url, path)
                seen.add(next_url)
                # Persist only a validated provider URL with any apiKey removed.
                next_url = "https://api.massive.com" + request_path
                if params:
                    next_url += "?" + urlencode(params)
            inserted += self.repository.save(records)
            self.repository.checkpoint(
                mode=self.equity.mode, resource=resource, cursor=next_url, received=received
            )
            if not next_url:
                return {"inserted": inserted, "pages": page + 1, "complete": True, "cursor": None}
        return {
            "inserted": inserted,
            "pages": max_pages,
            "complete": False,
            "cursor": "SAVED_CHECKPOINT",
        }
