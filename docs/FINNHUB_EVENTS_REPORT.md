# Finnhub read-only event/calendar adapter — October 10, 2026

**IMPLEMENTATION PASS for the scoped event-context reader. Production gates unchanged.**
This increment makes typed event context available for later research. It does not replace
Trust's news source or calendar, certify historical decision-time availability, or supply equity
references, liquidity or qualifying 30/30/3 samples.

## Reconnaissance and preserved work

Read [the complete multi-provider diagnostic](MULTI_PROVIDER_DATA_DIAGNOSTIC.md), existing
Finnhub diagnostics, provider protocols, configuration/redaction, common transport, Alpaca/
Massive/Binance paths, data models, SQL tables/repository, DataLayer and relevant tests.
Reviewed current official [Finnhub API documentation](https://finnhub.io/docs/api) and
[official SDK endpoint definitions](https://github.com/Finnhub-Stock-API/finnhub-python/blob/master/finnhub/client.py).
The SDK verifies GET paths, date/symbol/exchange parameters and header authentication;
the earlier real response evidence supplies the tested payload shapes. No new SDK dependency.

Started on branch `main`, HEAD `be34929`, with **25 pre-existing modified/untracked files**.
Saved starting file fingerprints before editing; retained prior Alpaca work and historical
diagnostic evidence. Relevant pre-edit baseline: **92 tests passed**. No reset, stash, branch
switch, commit or push. The authoritative master and production gate documents were not edited.

The only existing Finnhub integration was diagnostic code with a locally configured
`FINNHUB_API_KEY`; production Settings did not yet consume it. There was no typed event
provider. Existing SQL tables support canonical news/equity observations, not nullable
publication times or typed earnings/holiday context; this task does not migrate those tables
or insert the new records into them.

## Architecture and configuration

`FinnhubClient` shares the existing `ReadTransport`: fixed HTTPS host, header-only credentials,
timeouts, bounded transient retries, Retry-After/circuit handling, cache, Decimal JSON parsing,
credential-echo rejection and sanitized errors/logs. Default pacing is 1.1 seconds; at most
three transport attempts are allowed. The actual diagnostic uses one attempt and a ten-second
request timeout. Provider error bodies and authenticated headers are never recorded.

The production client allows **only four GET paths** on `https://finnhub.io/api/v1`:

| Method/path | Parameters | Typed result |
|---|---|---|
| GET `/company-news` | Exact uppercase ticker, explicit `from` / `to`, at most 31 inclusive dates | `EventBatch[CompanyNewsEvent]` |
| GET `/calendar/earnings` | Exact ticker, explicit `from` / `to`, at most 366 inclusive dates | `EventBatch[EarningsCalendarEvent]` |
| GET `/stock/market-status` | `exchange=US` | `USMarketStatus` |
| GET `/stock/market-holiday` | `exchange=US` | `EventBatch[MarketHoliday]` |

Requests with bodies, query credentials, alternate paths, quotes, candles, orders or external
URLs fail before HTTP transport. Responses have an 8 MB transport cap and collection limits
of 2,000 rows; no recursive pagination or unbounded recovery fetch is added. News end dates
cannot be in the future. Unsupported shapes raise sanitized `ProviderError`; malformed individual
rows are quarantined with typed row-index/reason records, without returning validation inputs.

The existing environment name **`FINNHUB_API_KEY`** is now a `SecretStr` Settings field,
excluded from repr/serialization and included in the existing log redactor. Empty keys are
unavailable; `.env` remains ignored. No source-selector or execution configuration was changed.
`DataLayer.events` exposes the reader only with `DATA_MODE=LIVE_READ_ONLY` and a configured key.
It is `None` in DEMO or without a key. Construction performs no HTTP call. Explicit event reads
do not save records. `DataLayer.news` remains the existing Massive/DEMO news path; equity
selection and `USEquityCalendar` remain unchanged.

The separate `EventContextProvider` protocol avoids falsely advertising `NewsProvider` or
`EquityDataProvider` compatibility. The old multi-provider diagnostic now shares this Finnhub
client via a **diagnostic-only** subclass retaining its previously verified quote/candle probes.
Those extra paths are not admitted by `FinnhubClient` or the new event-only diagnostic.
Hyperliquid request construction/discovery and all earlier evidence remain intact. The older
free-provider experiment remains a historical diagnostic, not a production provider.

## Normalization, time semantics and quality

All normalized observations include source `FINNHUB_EVENTS`, stable provider identifier,
endpoint, actual UTC ingestion time, nullable source timestamp, original epoch-second string/
unit where supplied, LIVE data mode, quality status and flags. LIVE mode identifies real-source
data; it does not label an event or quote as fresh or enable trading. New event model types
have no DataRepository/table mapping and cannot become Trust history through existing saves.

- **News:** retains requested ticker, sorted provider-related tickers, explicit mapping confidence,
  headline, publisher, URL and categories. Epoch-second `datetime` becomes publication/source
  time in UTC; `event_date` is explicitly its UTC publication date. Missing publication time
  stays null with MISSING quality; receipt time is never substituted. Missing publisher/headline/
  URL is flagged. Missing related tickers yield REQUEST_SCOPE_ONLY mapping and UNKNOWN quality;
  an explicit conflicting mapping is rejected. Invalid IDs, unsafe URLs, bad timestamps and
  publications outside the requested/observed window are quarantined. Valid old publications
  are HISTORICAL event observations, not historical first-availability evidence.
- **Earnings:** retains exact ticker, provider date, fiscal year/quarter and raw hour code.
  `amc`/`bmo`/`dmh` normalize to broad timing labels; unknown codes remain UNKNOWN. The date
  stays a US-market local calendar date, never midnight UTC, an exact release instant or a
  publication timestamp. Publication/source times stay null; schedule revisions/as-of availability
  remain unverified. No EPS, revenue or forecast calculation is introduced.
- **Market status:** validates US exchange and America/New_York context plus a strict Boolean
  open flag. Preserves actual provider `t`, raw session and holiday label. Known session names
  normalize; unknown values remain explicit. Missing/stale/future status timestamps are marked
  MISSING/STALE/INVALID through existing quality semantics; no price-reference claim follows.
- **Holidays:** preserves date, name, raw trading/post-market hours and separate UTC interval
  boundaries when parseable. Explicit empty trading hours indicate a reported closure; absent
  hours remain UNKNOWN/MISSING. Date-specific America/New_York conversion handles DST and
  rejects ambiguous/nonexistent wall times. A verified-format 09:30–13:00 interval is labelled
  EARLY_CLOSE context, not an authoritative calendar override. Malformed `13:00:17:00` remains
  raw, INVALID and without invented post-market timestamps. Publication/source times stay null.

Identical normalized events with the same ID deduplicate within a response. Conflicting same-ID
versions are **all quarantined**, avoiding order-dependent selection. News IDs use the upstream
event ID; earnings use ticker/date; holidays use US/date. Output order is deterministic. Across
calls these IDs remain stable, but new HTTP receipts retain their own ingestion time; no durable
first-seen, cross-response revision ledger or cross-ticker event database is claimed. Cached
responses retain the original HTTP receipt. A future persistence integration must preserve
versions and ticker associations rather than overwriting old knowledge.

Batches preserve query bounds, receipt, counts, duplicates, rejections and literal
`coverage_complete=false`. Collections remain PARTIAL even when every returned row validates:
the endpoints do not establish exhaustive historical news/schedule coverage. Empty collections
cannot prove “no relevant event”; wholly rejected non-empty collections are UNAVAILABLE.

## Actual authenticated evidence

[FINNHUB_EVENTS_20261010.json](evidence/FINNHUB_EVENTS_20261010.json) records
**08:06:34.595510–08:06:52.360646 UTC** on Saturday October 10, 2026
(**13:36:34–13:36:52 IST**). Exactly **8 HTTP requests**, all **200/business OK**.
No retries, quote/candle probes, execution calls, application startup or database writes.

| Capability | Actual normalized coverage | Result/limit |
|---|---|---|
| US market status | Provider time 08:06:45Z; receipt 08:06:45.435510Z; `is_open=false`, raw session null | PASS for this status observation; UNKNOWN quality does not certify a price/feed |
| Holidays | 62 records, Jan 2, 2023–Dec 24, 2027; receipt 08:06:45.689006Z | PARTIAL; 57 UNKNOWN-quality schedules, 5 INVALID malformed post-market schedules; no publication ledger |
| TSLA news | 244 records; publication Oct 5 10:39:29Z–Oct 10 03:15Z; receipt Oct 10 08:06:46.890704Z | PARTIAL requested Oct 3–10; all returned records structurally valid/HISTORICAL |
| NVDA news | 249 records; publication Oct 8 17:20Z–Oct 10 05:20Z; receipt Oct 10 08:06:49.057664Z | PARTIAL; oldest requested dates not demonstrated |
| GOOGL news | 247 records; publication Oct 7 11:38:56Z–Oct 10 06:02:32Z; receipt Oct 10 08:06:51.315296Z | PARTIAL; exhaustive coverage not demonstrated |
| TSLA earnings | One reported event Oct 20, 2026, `amc`; receipt 08:06:47.909757Z | PARTIAL; requested Oct 10–Jan 8, 2027; publication/revisions unavailable |
| NVDA earnings | One reported event Nov 17, 2026, `amc`, fiscal 2027 Q3; receipt 08:06:50.118205Z | PARTIAL; fiscal year is not event calendar year |
| GOOGL earnings | One reported event Oct 27, 2026, `amc`; receipt 08:06:52.359706Z | PARTIAL; no exact announcement instant/issuer confirmation |

Actual duplicate and rejected-row counts were zero. The five malformed-hour records are
retained as invalid context, not counted as fully valid schedules. Event collections contain
740 news records in total; this does not establish 740 independent stories across tickers or
complete requested-week coverage. Evidence stores bounded first/last normalized samples,
counts, date/time extrema, flags and safe request/status/rate headers, without article text.
No real data is promoted into test fixtures; the new fixture files are explicitly synthetic.

Observed rate headers: limit **60**, remaining **52–59**. No actual 429 or timeout occurred;
offline fixtures verify those failure paths. Account plan, exhaustive retention, licensing,
announcement revisions and original publication of schedules remain NOT_VERIFIED. No load
test was performed and header values are not a daily/long-term entitlement guarantee.

## Reproduction

Run from the repository root. Configure only the existing `FINNHUB_API_KEY` name locally in
ignored `.env` or environment; never place the value in a command. The actual run used the
command below with output `docs/evidence/FINNHUB_EVENTS_20261010.json`. That evidence is
preserved; a **new** filename is mandatory for repetition. This reproducible command uses
`FINNHUB_EVENTS_NEXT.json`, which must also be unused. Adjust explicit dates for future
coverage tests; repeating these dates does not recreate the original receipt or entitlement state.

```sh
PYTHONPATH=backend .venv/bin/python scripts/verify-finnhub-events.py --live-read-only \
  --news-start 2026-10-03 --news-end 2026-10-10 \
  --earnings-start 2026-10-10 --earnings-end 2027-01-08 \
  --output docs/evidence/FINNHUB_EVENTS_NEXT.json
.venv/bin/python -m pytest backend/tests/integration/test_finnhub.py \
  backend/tests/integration/test_alpaca.py backend/tests/integration/test_data_providers.py \
  backend/tests/unit/test_multi_provider_diagnostic.py -q
.venv/bin/python -m pytest -q
npm test
npm run build
.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
PYTHONPATH=backend .venv/bin/python scripts/generate-ui-contracts.py --check
.venv/bin/python scripts/check-security.py
git diff --check
```

For an explicit read without creating the application/database:

```python
from app.clients.finnhub import FinnhubClient
from app.config import Settings
from app.providers.finnhub import FinnhubEventProvider

client = FinnhubClient(Settings().finnhub_api_key)
try:
    events = FinnhubEventProvider(client).get_company_news("NVDA", "2026-10-03", "2026-10-10")
    # Consume typed records, flags and false coverage_complete; do not infer full coverage.
finally:
    client.close()
```

## Validation and changed files

- Targeted provider regression: **168 passed**, including **76 Finnhub tests**. Covers all
  four endpoints, typed provenance, duplicate/conflicting events, missing publication times,
  timezone/DST handling, malformed payloads, provider failures, bounded retries/rate limits,
  missing credentials, DEMO isolation and explicit no-production-persistence checks.
- Complete backend suite: **1,562 passed**. Two existing Pydantic warnings in malformed
  allowance-response tests; no failures.
- Frontend regression: **273 passed across 14 files**. TypeScript/Vite production build passed.
- Ruff lint and formatting: passed, **222 files** already formatted. Seven generated
  Pydantic-derived frontend contracts passed their unchanged-output check.
- Security checks passed: configured-secret leakage, ignored environment files, Docker
  environment exclusion and frontend secret isolation (**517 artifacts scanned**).
- `git diff --check` passed. Starting-file fingerprint audit confirms **18 of 25 pre-existing
  dirty/untracked files remain byte-identical**; only the seven explicitly related files listed
  below received additional changes. Branch `main` and HEAD `be34929` remain unchanged.
  Master specification, gate document, Trust service, prior evidence and README fingerprints
  are unchanged. No full 111-request diagnostic was rerun.

At the final continuation checkpoint, the typed adapter, fixtures, bounded diagnostic and
actual evidence were already implemented. They were retained; the remaining work was final
regression/security/preservation verification and completion of this report, without rebuilding
the adapter or repeating authenticated requests.

Changed existing files in this increment (prior changes retained):

- `.env.example`, `backend/app/config.py`: existing Finnhub key name, secret handling/redaction.
- `backend/app/providers/base.py`: separate typed event-context protocol.
- `backend/app/services/data_layer.py`: optional explicit research reader; no consumer switch/fetch/save.
- `scripts/diagnose-multi-provider.py`: shared Finnhub transport; diagnostic-only quote/candle extension.
- `docs/API_MATRIX.md`, `docs/ARCHITECTURE.md`, `docs/CAPABILITY_GAPS.md`: new dated adapter boundary/status sections; earlier evidence retained.

New files:

- `backend/app/clients/finnhub.py`, `backend/app/providers/finnhub.py`, `backend/app/models/events.py`.
- `backend/tests/integration/test_finnhub.py`.
- `backend/tests/fixtures/finnhub/company_news.json`.
- `backend/tests/fixtures/finnhub/earnings_calendar.json`.
- `backend/tests/fixtures/finnhub/market_status.json`.
- `backend/tests/fixtures/finnhub/market_holiday.json`.
- `backend/tests/fixtures/finnhub/README.md`.
- `scripts/verify-finnhub-events.py`.
- `docs/evidence/FINNHUB_EVENTS_20261010.json`.
- `docs/FINNHUB_EVENTS_REPORT.md`.

No database/table/repository, canonical Trust/risk/routing logic, execution policy, master
specification, gate document or frontend source was changed in this increment. README and
all earlier actual evidence retain their starting bytes. Generated frontend build output is ignored.
No browser recheck was needed for an unchanged frontend; frontend regression/build still ran.

## Remaining limits and unchanged gates

This reader is not automatically consumed or persisted. Future work needs explicit research
consumer policy, event-coverage validation and an immutable first-seen/revision/ticker-association
store if persistence is authorized. Invalid schedule fields must not become authoritative calendar
overrides. Provider-reported earnings dates still need appropriate confirmation/availability evidence.

No equity reference freshness or 30-second alignment was established by event ingestion.
No historical economic ratios, authoritative liquidity or point-in-time feature gaps were closed.
The existing measured qualifying counts remain **0/30 baseline, 0/30 opening model, 0/3 real
analogues**; no sample/episode builder or production backfill ran here. Binance token-derived
`referencePrice`, Finnhub stale quotes and Hyperliquid derivatives were not substituted for cash
equity. Existing Alpaca/Massive/Binance/Hyperliquid behavior is preserved.

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
EXECUTION_MODE=DRY_RUN
LIVE_TRADING_ENABLED=false
```

Stopped after the scoped event/calendar increment. No phase advancement, live execution,
commit or push. Session-aware Trust research/integration remains a separate future task.
