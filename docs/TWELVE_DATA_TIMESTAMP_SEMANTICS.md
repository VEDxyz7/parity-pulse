# Twelve Data — final NVDA timestamp semantics diagnostic

Read-only GET `https://api.twelvedata.com/quote`, with `symbol=NVDA`, `interval=1min`, `timezone=UTC`, `dp=11`, `prepost=false`. Protected header authentication; no credential value or authenticated header is recorded. This report supplements the [earlier feasibility capture](TWELVE_DATA_FEASIBILITY.md); its candle-start age assessment is preserved as historical evidence.

## Active regular-session evidence

Five requests were started 65 seconds apart on **October 6, 2026 UTC** (October 7 Asia/Kolkata). All returned HTTP 200, no business error, NVDA/USD/NASDAQ identity and `is_market_open=true`. Receipts were within the US regular-session clock window. All reported prices were finite and positive.

| Receipt UTC | close USD | timestamp UTC | datetime UTC | last_quote_at UTC | receipt − timestamp | receipt − last_quote_at |
|---|---:|---|---|---|---:|---:|
|18:55:41.610491|240.37000000000|18:54:00|2026-10-06 18:54:00|18:55:00|101.610491s|41.610491s|
|18:56:46.553840|240.41500000000|18:55:00|2026-10-06 18:55:00|18:56:00|106.553840s|46.553840s|
|18:57:51.679669|240.40500000000|18:56:00|2026-10-06 18:56:00|18:57:00|111.679669s|51.679669s|
|18:58:56.754968|240.41000000000|18:57:00|2026-10-06 18:57:00|18:58:00|116.754968s|56.754968s|
|19:00:01.585238|240.40500000000|18:58:00|2026-10-06 18:58:00|18:59:00|121.585238s|61.585238s|

The [official quote contract](https://twelvedata.com/docs/market-data/quote) defines `timestamp`/`datetime` as the selected candle's opening time and `last_quote_at` as the last minute candle time. The fields have different meanings; candle-start age is **not assumed to be quote freshness**. In these responses, `last_quote_at` was exactly 60s greater than the candle-start timestamp, advanced by 60s on each successive read, and remained nonfuture and within the existing **120s** age limit on all five reads. Quote prices changed as the minute fields advanced.

**Empirical conclusion for this active-session sample:** `last_quote_at` tracks minute-level quote activity closely enough to pass the unchanged 120s age condition, while the fifth candle-start timestamp alone exceeds 120s. This supports a separate timestamp-semantic assessment; it does not claim an exact last-trade timestamp, consolidated-market coverage, a sustained-latency guarantee or passing 30s token/equity skew. No token-provider call was made in this diagnostic.

## Closed-session evidence

Three actual requests were started 65s apart after the October 6 regular close at 20:00 UTC. All returned HTTP 200, no business error, the same NVDA/USD/NASDAQ identity and `is_market_open=false`. All three returned `close=239.17500000000`, `timestamp=1791316740`, `datetime=2026-10-06 19:59:00` and `last_quote_at=1791316740`. Both Unix fields therefore correspond to **2026-10-06 19:59:00 UTC**.

| Receipt UTC | is_market_open | receipt − timestamp | receipt − last_quote_at |
|---|---|---:|---:|
|20:02:00.698803|false|180.698803s|180.698803s|
|20:03:05.810036|false|245.810036s|245.810036s|
|20:04:10.864352|false|310.864352s|310.864352s|

**Observed closed behavior:** `last_quote_at`, candle timestamp and price remained fixed across all three responses, while their ages increased with elapsed receipt time. The newest minute field was no longer within 120s. These closed-session prices were not labeled as current LIVE references or used by production. Historical requests, documentation examples and selecting an old date were not substituted for actual closed-session observations.

The difference between `last_quote_at` and `timestamp` was **60s during the five active reads but 0s during the three closed reads**. There is no assumption of a universal `timestamp + 60s` mapping. The empirical result verifies the documented minute-candle/update behavior for these measured open and closed windows, not exact last-trade timing or all possible sessions/corrections.

## Diagnostic result and scope

```text
TWELVE_DATA_CURRENT_EQUITY_BY_LAST_QUOTE_AT=PASS
TWELVE_DATA_120S_FRESHNESS=PASS
TIMESTAMP_SEMANTICS=VERIFIED
```

The first two statuses refer to the five measured active-session reads and the age condition only. The third verifies the observed field definitions, advancement while open and stopped updating in the measured closed window. Using the candle-start timestamp alone is insufficient to judge the separate latest-minute field's age. The earlier candle-start FAIL does not establish that `last_quote_at` fails regular-session freshness; the new five-read evidence passes that condition.

**Twelve Data can satisfy the unchanged 120s freshness condition using `last_quote_at` in this measured active-session sample.** Production Trust source/kind/quality validation, 120s freshness, 30s token/equity alignment and all other requirements remain unchanged. Exact quote-price/source-time mapping and synchronous alignment would still require separately authorized integration verification; no exact-trade or full replacement guarantee is claimed. This is not a production provider integration or a Trust gate pass. No closed-session value is promoted to a current reference. No production quality label was assigned and no Binance reference price was substituted.

All eight responses showed `api-credits-used=1` and `api-credits-left=7`, consistent with minute quota resets at this sampling frequency. No 429 or business/entitlement denial was observed; quota exhaustion was not tested. Actual measured receipts span 18:55:41–20:04:10 UTC on October 6, or 00:25:41–01:34:10 Asia/Kolkata on October 7. No provider calls were made during the intervening wait for the regular close.

- [Active-session raw fields, Unix timestamps, separate age calculations and HTTP ledger](evidence/TWELVE_DATA_TIMESTAMP_ACTIVE.json).
- [Closed-session raw fields, Unix timestamps, separate age calculations and HTTP ledger](evidence/TWELVE_DATA_TIMESTAMP_CLOSED.json).
- [Isolated diagnostic script](../scripts/diagnose-twelve-timestamps.py).

Verification: actual eight-response age arithmetic, active advancement and closed-state stability checks PASS. Ruff lint/format PASS for all 71 Python files. Existing security audit PASS for 207 artifacts; an extended in-memory scan including the Twelve Data credential also PASS. SHA256 comparison confirms all 189 pre-existing files remain byte-identical, including production sources/databases and the formal Trust gate (`f84e8489a756df2924b9a21f5486d84d563c9270362f076e0463f6c79c8aabdd`). The application test suite was not rerun because production implementation was unchanged.

Only this report, the isolated diagnostic script and the two timestamp evidence files were added. No production source, database, settings, threshold or gate change. No trading, execution, wallet or Opportunity work. Prior evidence is preserved. Both sampling processes finished successfully; no further diagnostic requests are scheduled. **Stop after this diagnostic.**
