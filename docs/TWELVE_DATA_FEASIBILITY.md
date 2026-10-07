# Twelve Data NVDA feasibility — authenticated read-only diagnostic

Measured **2026-10-06 18:47:07–18:49:40 UTC**, or **2026-10-07 00:17:07–00:19:40 Asia/Kolkata**. This report records actual responses using the locally configured credential. It supplements, and preserves, the earlier missing-credential [free-provider report](FREE_PROVIDER_FEASIBILITY.md).

```text
TWELVE_DATA_CURRENT_EQUITY=FAIL
TWELVE_DATA_HISTORICAL=PASS
TWELVE_DATA_FRESHNESS=FAIL
```

**Current-equity FAIL means a consistently eligible Trust reference was not demonstrated; quote access itself passed.** Both quote reads returned the correct independent NVDA/USD identity and positive prices. One exceeded the unchanged 120-second age limit using the documented quote timestamp; the second passed that age check. Two reads cannot establish a long-run latency guarantee, and this diagnostic does not prove that every Twelve Data quote is stale. Historical PASS means the tested real 1-minute and 5-minute windows were accessible and valid, not that all historical Trust requirements have passed.

No application source, production observations/database, configuration, dependencies, Trust threshold or gate was changed. No execution, wallet, order, RFQ, swap or Binance endpoint was called. All calls were GETs to Twelve Data. Authentication used a protected request header; neither credential value nor authenticated headers/query strings were recorded. No purchase or subscription change occurred. Diagnostic files are separate from production observations.

## Endpoints and actual status

API origin: `https://api.twelvedata.com`.

| Endpoint | Public parameters | Calls | HTTP / business result |
|---|---|---:|---|
| GET `/quote` | `symbol=NVDA`, `interval=1min`, `timezone=UTC`, `dp=11` | 2 | Both 200; no business error; `is_market_open=true` |
| GET `/time_series` | Same symbol/timezone/precision; `interval=1min` and `5min`; `start_date=2026-10-02 00:00:00`, `end_date=2026-10-05 23:59:59`, `outputsize=5000`, `order=ASC`, `prepost=false`, `adjust=splits` | 2 | Both 200; business `status=ok` |
| GET `/time_series` | Same history parameters; `start_date=2026-01-02 00:00:00`, `end_date=2026-01-05 23:59:59` | 2 | Both 200; business `status=ok` |

`/price` was not necessary: the quote supplies price plus timestamp fields, whereas the documented `/price` response alone does not establish a source timestamp. Market-open status came from `/quote`; a separate market-state endpoint was not tested. Returned exchange identity was NASDAQ, MIC `XNGS`, currency USD. Extended-hours entitlement was not tested.

## Price timestamps and freshness

The official [quote contract](https://twelvedata.com/docs/market-data/quote) defines `timestamp` and `datetime` as the selected interval's opening time, `last_quote_at` as the last minute candle time, and `close` as the bar's close price. Neither timestamp is documented as an exact last-trade timestamp. The quote interval was explicitly 1 minute, rather than the default daily interval. Documentation was retrieved directly when browser extraction exceeded its content-size limit.

| Read | Reported price USD | Quote `timestamp` UTC | Received UTC | Age at receipt | Unchanged 120s age check |
|---|---:|---|---|---:|---|
| First | 240.05500000000 | Oct 6 18:45:00 | Oct 6 18:47:08.707849 | 128.707849s | FAIL |
| Recheck | 240.03000000000 | Oct 6 18:46:00 | Oct 6 18:47:31.587120 | 91.587120s | PASS |

`last_quote_at` was respectively Oct 6 **18:46:00 UTC** and **18:47:00 UTC**, aged **68.707849s** and **31.587120s** at receipt. Those later candle times are retained separately; they are not silently substituted for the selected price's timestamp or relabeled as exact trades. No assumption that adding a minute proves the last trade's time was made. Freshness is measured at receipt, not at report-writing time.

Production [Trust evidence validation](../backend/app/services/trust_evidence.py) requires a regular-session independent reference to have a nonfuture source timestamp aged at most **120s**, acceptable reference kind/quality, matching identity/mode, and at most **30s token/equity timestamp skew**. It currently admits `MASSIVE` as the LIVE independent-reference source. That allowlist and all checks remain unchanged. A public marketing claim of real-time coverage or HTTP 200 does not establish those conditions. The first sample fails the conservative bar-start age check; the second passes that check alone. No production LIVE quality was assigned. No historical bar was labeled as a current quote, and Binance `referencePrice` was not substituted.

**30s token/equity skew: NOT TESTED.** This task authorizes Twelve Data only, so there was no new synchronous token-provider request. A timestamp check alone cannot establish full Trust reference eligibility.

## Observed historical date coverage

All times below are UTC bar **starts**, with regular-session data only. Intraday output explicitly requested UTC; the metadata also identifies the exchange timezone as America/New_York. Winter/summer session starts are consistent with the expected UTC offset.

| Requested window | Interval | Actual first bar | Actual last bar | Bars |
|---|---|---|---|---:|
| Jan 2–5, 2026 | 1min | Jan 2 14:30:00 | Jan 5 20:59:00 | 780 |
| Jan 2–5, 2026 | 5min | Jan 2 14:30:00 | Jan 5 20:55:00 | 156 |
| Oct 2–5, 2026 | 1min | Oct 2 13:30:00 | Oct 5 19:59:00 | 780 |
| Oct 2–5, 2026 | 5min | Oct 2 13:30:00 | Oct 5 19:55:00 | 156 |

Each sampled regular session contains 390 one-minute bars and 78 five-minute bars, including the opening bars. All rows have finite positive and internally consistent OHLC values, completed bars and unique timestamps. The maximum gap is 235,860s for 1min and 236,100s for 5min: the Friday-to-Monday market closure. Within these four sampled sessions, spacing is exactly the requested interval. No missing bar was synthesized.

The final 5min bars complete Jan 5 21:00 UTC and Oct 5 20:00 UTC; these are not current prices. The October opening control has an actual Oct 2 19:59 1min close of **233.99000549316** and Oct 5 13:30 5min close of **237.37600708008**, completing at 13:35. The diagnostic records a posthoc equity target separately; it is not a decision-time feature or a qualifying Trust episode.

This verifies sampled history as far back as **January 2, 2026**, and through **October 5, 2026**. It does **not** establish the provider's absolute earliest retention date, continuous coverage between the samples, or coverage for today's unfinished session. Historical data was first captured now; historical first availability/revisions and split-adjustment point-in-time behavior have not been verified. Today's token/share ratio was not backfilled, and this diagnostic does not qualify any production historical episodes.

## Entitlement, quota and permitted use

No 403, 429, business denial or retry response occurred. The first four reads exposed `api-credits-used=1,2,3,4` and `api-credits-left=7,6,5,4`. The later pair exposed used `1,2` and left `7,6`, consistent with a minute reset and one credit per tested read. Calls were spaced at least 8s within each run. The quota was not deliberately exhausted; actual 429 behavior, remaining daily quota and sustained-load behavior are untested. Account subscription identity was not queried.

Current [individual pricing](https://twelvedata.com/pricing) advertises Basic at no charge with 8 API credits/minute and 800/day, real-time US equities/ETFs, and internal non-display usage. Individual usage is described as personal, internal and noncommercial; public Parity Pulse price redisplay is **not** verified as permitted. The [official US-equity guide](https://support.twelvedata.com/en/articles/9935903-us-equities-market-data) describes default real-time venue coverage around 5% of US trading volume, with historical/EOD broader-volume availability after midnight Eastern on the next trading day. No consolidated SIP/NBBO entitlement is claimed. Public plan descriptions do not prove this account's subscription or commercial display rights.

## Replacement decision and remaining verification

**Twelve Data cannot yet be accepted as a verified replacement for Massive for the unchanged Trust Layer.** It demonstrably provides independent NVDA quotes and useful historical minute bars. Current-reference acceptance remains unresolved because freshness was mixed, bar-time semantics need an explicitly verified mapping, and contemporaneous 30s token/equity alignment was not measured. No production adapter or source allowlist change was authorized or made.

Further provider verification is needed before any separately authorized integration: sample current quote latency across minute boundaries; verify which source time is valid for the returned price without inventing trade precision; perform synchronized read-only token/equity alignment; check the necessary historical windows and asof adjustment/revision availability; and establish usage rights appropriate to the product. This diagnostic neither requests a paid plan nor concludes that a free replacement is impossible. Equity data access alone cannot resolve historical ratio, authoritative liquidity, episode-count or analogue blockers.

Evidence:

- [Four-read authenticated quote/recent-history capture](evidence/TWELVE_DATA_NVDA_AUTHENTICATED_FEASIBILITY.json).
- [Two-read January historical-depth capture](evidence/TWELVE_DATA_NVDA_HISTORICAL_DEPTH.json).
- [Isolated read-only diagnostic script](../scripts/diagnose-twelve-data.py), which refuses evidence overwrite and checks serialized output for configured secrets. The January depth capture used the same isolated probe and validator with the exact bounded parameters retained in its read ledger.

Verification: actual capture integrity, quote-age arithmetic, interval spacing/session counts and configured-secret scans PASS. Ruff lint/format PASS for all 70 Python files; the existing security audit PASS for 203 artifacts. The pre-task SHA256 manifest verifies all 185 pre-existing files remain byte-identical, including production code, databases and formal Trust gate evidence. Only this report, the isolated diagnostic script and its two evidence JSON files were added. The unchanged formal Trust gate SHA256 is `f84e8489a756df2924b9a21f5486d84d563c9270362f076e0463f6c79c8aabdd`. The application test suite was not rerun for this isolated diagnostic; no production implementation was changed.

**TRUST_GATE was not modified.** Opportunity and all LIVE execution remain blocked. Stop after this diagnostic.
