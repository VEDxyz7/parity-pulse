# Phase 2 — data layer report

PHASE: **2**  
STATUS: **PASS**  
Date:2026-10-06. Scope: read-only data layer only. Phase3 has not started. Capability states and every execution-safety rule remain unchanged.

## Phase numbering reconciliation

Added 2026-10-06. **"Phase 2 — Data Layer" is an engineering milestone, not the canonical Master Specification Phase 2. Data Layer is PASS. Canonical Trust Layer Phase 2 has NOT started and is NOT complete.** The original title, PHASE/STATUS fields, acceptance results, test counts and evidence below are preserved as Engineering Stage 2 history.

Engineering Stage 1 — Foundation supports Canonical Phase 1 — Working Ask Flow. Engineering Stage 2 — Data Layer supports Canonical Phase 1 and prepares Canonical Phase 2 — Trust Layer. The complete Working Ask Flow, including foundational exposure/comparison/quote/DRY_RUN capabilities, remains incomplete. Data ingestion and calendar/quality validation do not constitute Trust Layer functionality.

The historical PHASE_2_DEVELOPMENT_GATE=PASS below means Engineering Stage 2 only. Historical "Phase3" / "NEXT PHASE" references mean the engineering DIRECT EXPOSURE stage; they do not authorize Canonical Phase 3 — Opportunity Mode. Opportunity must not begin until the Trust Layer is complete and TRUST_GATE=PASS. No feature implementation is authorized or started by this reconciliation. See [PHASE_MAP.md](PHASE_MAP.md) for the preserved master sequence and runtime-label interpretation.

Current reconciled development state:

```text
DATA_GATE=PASS
TRUST_GATE=NOT_YET_TESTED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
DRY_RUN_GATE=NOT_YET_TESTED
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

The [current gate definitions](EXECUTION_GATES.md) distinguish data readiness, future Trust/Opportunity readiness, full DRY_RUN readiness and each LIVE capability. Every original execution-safety requirement remains unchanged.

## Implemented providers and persistence

One centralized BinanceWeb3Client signs the exact /build request bytes and accepts only the13 reviewed RWA/Market reads. BinanceRWAProvider and BinanceMarketProvider normalize strict raw contracts. MassiveProvider implements independently sourced equity/news/status/holidays/actions to actual entitlement level. RWADataProvider, EquityDataProvider, NewsProvider and CalendarProvider protocols define the boundaries; the versioned exchange calendar supplies bounded session interpretation.

TrackedAsset, Issuer, TokenMetadata, TokenObservation, EquityObservation, NewsEvent and MarketStatus retain provenance, mode, quality, exact raw source timestamp/unit and UTC source/ingestion times. Money and ratios remain Decimal/canonical JSON text through REST and SQLite; no authoritative financial computation occurs in the frontend. Seven record tables and ingestion checkpoints are schema revision2. Metadata changes retain versions; conflicting identical observation IDs reject overwrites. Every read requires explicit DEMO/LIVE mode. Historical ingestion has bounded page budgets, retry/backoff, deduplication, durable checkpoints and progress guards.

## Actual read-only evidence

**Binance RWA: PASS.** All six endpoints were actually called: GET platforms, search, tokens, underlying-profile, price and underlying-market under /api/v1/dex/market/rwa/. Initial probes returned HTTP200/business0. Runtime stock-first NVDA discovery/profile/ratio/price/status validated both Ondo and BStock BSC representations and persisted them.

**Binance Market: PASS within explicit unit/schema limits.** All seven selected operations were actually called: GET supported/chain, token/search, candles and trades; POST token/basic-info, price and price-info under /api/v1/dex/market/. These POSTs are data reads. Initial probes returned HTTP200/business0. Raw financial precision and timestamp fields, exact methods/body/query contracts, candle windows and cursor paging are exercised in tests.

The initial [Binance ledger](evidence/PHASE_2_BINANCE_READS.json) contains13 successful reads. The final [typed pipeline ledger](evidence/PHASE_2_PIPELINE.json) contains17 Binance calls and5 Massive calls, with every typed capability check PASS; its snapshot403 remains an isolated limitation. Separately, the initial [Massive ledger](evidence/PHASE_2_MASSIVE_READS.json) contains9 calls:7 successful reads and2 forbidden operations. [Candle bound](evidence/PHASE_2_CANDLE_BOUNDS.json) and [cursor](evidence/PHASE_2_CANDLE_PAGE.json) probes are additional actual calls. These are separate runs, not unique endpoint counts or sustained performance measurements. Transport ENVELOPE_PASS is deliberately distinct from typed payload PASS.

**Equity provider: PASS TO VERIFIED ENTITLEMENT LEVEL.** The configured account returns200 for945 NVDA minute bars on2026-10-05,3 daily bars on2026-10-01…05, status, upcoming holidays, news, splits and dividends. Snapshot and latest NBBO return403/FORBIDDEN. Exact account plan, current quote delay and redistribution rights remain UNKNOWN. Current equity observations are absent rather than substituted. Synthetic tests verify snapshot/NBBO ns timestamps and DELAYED/UNKNOWN labeling; they are not real account-access evidence.

Independent NVDA regular close is **239.11 USD/share**, from Massive, source bar timestamp **2026-10-05T19:59:00Z**, raw **1791230340000 ms**, ingestion **2026-10-06T11:46:38.616904Z**, quality **HISTORICAL**. This is the completed15:59–16:00 New York regular-session minute, selected using the actual previous session. It is not a current snapshot or quote. No Binance referencePrice supplies this value.

**News: PASS TO VERIFIED CAPABILITY LEVEL.** The initial probe validated2 NVDA articles; the full bounded first page persisted100. Publisher, URL, ticker, headline, optional categories, publication and ingestion time remain separate. Future publication dates are rejected. Continuation exists, so news_history=PAGINATION_BOUND_REACHED; complete history/revisions/point-in-time availability are not certified.

**Calendar: PASS WITH BOUNDED COVERAGE.** Versioned official [NYSE2026–2028 schedule](https://www.nyse.com/trade/hours-calendars), America/New_York session interpretation and UTC storage; tests cover regular/premarket/postmarket/overnight/weekend/holiday/DST/13:00 early close/multi-day closure/reopening. Extended-hour policy is specifically NYSE American equities,07:00 premarket and20:00 postmarket (17:00 early-close days). Other venues, older schedules and emergency closures remain unverified. Out-of-coverage queries fail. Massive upcoming24-row holiday response is supplemental rather than invented historical coverage.

## Assets discovered

| Stock | Issuer | Chain | Provider-discovered contract | Symbol | Exact shares/token | Market state at verification |
|---|---|---|---|---|---|---|
| NVDA | bstock | "56" | 0x02fca66c1d1afb4e2a7884261eb00f63598a7436 | NVDAB | 1.000778223752807865 | UNKNOWN (provider null) |
| NVDA | ondo | "56" | 0xa9ee28c80f960b889dfbd1902055218cba016f75 | NVDAon | 1.0017152487959898 | premarket |

Addresses are measured output, never hard-coded discovery input. No xStocks issuer is assumed. Live BSC catalog contains488 rows;451 pass critical normalization and37 are excluded, with an explicit PARTIAL limitation. Stock-first discovery additionally filters assetType1 and runtime issuer/chain/search identities. No incomplete universe is presented as an exhaustive opportunity scan.

## Observations persisted

Separate local `data/phase2-verification.db`, after the actual verification attempts:

| LIVE partition | Count | Meaning |
|---|---|---|
| TokenObservation | 25 | 8 PRICE,4 PRICE_INFO,3 completed CANDLE,10 quarantined TRADE |
| EquityObservation | 946 | 945 independent minute bars and1 last regular close |
| NewsEvent | 100 | Bounded first page; history partial |
| TrackedAsset / Issuer / TokenMetadata / MarketStatus | 1 / 2 / 4 / 2 | NVDA, runtime issuers, retained metadata versions, issuer states |

DEMO observations in this verification database: **0** for all three observation/news types. Totals include multiple actual attempts; they are not claimed as all newly inserted in the final run. Final repeat equity ingestion inserted0 duplicates; the earlier run inserted945 bars, retained in [pre-boundary-fix evidence](evidence/PHASE_2_PIPELINE_PRE_BOUNDARY_FIX.json). Final scoped token candle ingestion inserted3, completed in2 pages and excluded196 out-of-window rows. One-page trade ingestion remained explicitly incomplete, with a resume cursor.

Running default DEMO application uses a different database and explicitly synthetic demo:AAPL/demo:NVDA representations. No real contract is invented for DEMO and no fixture substitutes for failed live reads.

## Validation and local services

| Check | Actual result |
|---|---|
| Backend Phase2 and Phase1 regression suite | **107 passed,0 failed;93% application statement coverage** |
| Frontend regression/status suite | **15 passed,0 failed**, including Phase2 render and unchanged blocked gates |
| Ruff lint and formatting | PASS |
| TypeScript noEmit and Vite production build | PASS |
| Python dependency consistency | PASS; no broken requirements |
| Exact canonical backend command | PASS; running PID88967 at127.0.0.1:8000 |
| /api/health and /api/system-status | HTTP200; phase2, correct modes and unchanged gates |
| /api/assets, /api/assets/NVDA and unavailable lookup | HTTP200; explicit DEMO/provenance/Decimal strings |
| Existing frontend/root npm run dev and proxy | PASS; PID86767 retained at127.0.0.1:5173 |
| Actual frontend browser load | PASS in disposable headless Chrome; backend connected, Phase2, DEMO/DRY_RUN, disabled later-phase navigation |
| Configured credential/source/fixture/bundle/database audit | PASS; no values printed, no credentials committed or exposed |
| Docker image/run | NOT_RUN; Docker remains unavailable |

Tests cover signing vectors/raw bytes, allowlisted reads/no writes, raw schema failures, all selected adapters, ratios/Decimal/ns-ms precision, timestamp/freshness/nullable data, dynamic issuer mapping, news publication separation, calendar, transient/auth failures, Retry-After including final attempts, cache/single-flight, pagination/SSRF/secret-free checkpoints, persistence/conflicts/idempotence/resume and mode isolation. Tests use sanitized real fixtures where possible and synthetic credential/quote cases otherwise. One upstream Starlette TestClient httpx migration warning remains; it is not suppressed. Frontend has no separate ESLint script; its configured strict TypeScript/build checks pass.

The existing backend had no reload flag. After implementation/tests, the confirmed prior Parity Pulse PID86726 was gracefully stopped and the exact canonical command rerun to load Phase2. A final review tightened boolean rejection across all asset-type schemas and corrected Massive schema-error provenance; the confirmed Phase2 PID88786 was then gracefully reloaded once more after107 tests passed. Current PID88967 runs the final code. Frontend was retained throughout. [Local read checks](evidence/PHASE_2_LOCAL_READS.json), [actual browser result](evidence/PHASE_2_BROWSER.json). No application port or foundation architecture workaround was introduced.

## Normalization decisions and known limitations

- RWA list/search decimals may be strings; basic-info decimals are integer. Strict measured conversion preserves decimals and rejects booleans/invalid ranges. Source-less metadata is UNKNOWN; null market state remains UNKNOWN even when openState=true.
- Current official marketStatus enum is pause, while runtime includes paused; unknown asset types/missing names also occur. Entire malformed representations are excluded with an explicit incomplete-catalog limitation, never coerced into tradable data.
- Documented exclusive candle bounds differ from observed responses. Client excludes t≤before/t==after, rejects t>after and requires backwards progress; it retains requested parameters and counts exclusions. Completion refers to the requested window. Unfinished bars are excluded;1M completion remains unavailable. Candle volume unit is UNKNOWN.
- NVDA/NVDAB reported trade price near1 conflicts with token USD price near241. Preserve reported_price with price_unit=NOT_VERIFIED, token_price=null, data_quality=CONFLICTING; do not use those reported prices as authoritative USD prices.
- Historical token observations retain the exact ratio from the metadata used at ingestion; historical as-of ratio availability is not proven. Historical token market state is UNKNOWN. Metadata versions/corporate-action reads do not establish a look-ahead-safe adjusted series or sufficient research samples. Such analysis remains blocked pending later evidence.
- Current independent equity snapshot/NBBO is FORBIDDEN; account plan/delay/redistribution unknown. Historical close is explicitly HISTORICAL. No fresh current equity value is fabricated.
- News first-page history is partial. Calendar is bounded to NYSE2026–2028 and specified venue hours; emergency closures/revisions/other venues are unverified.
- No real429 was observed. Rate-limit/retry/circuit behavior is verified with mock responses; conservative pacing is implemented, not a claimed throughput benchmark. Final actual call durations range175.01–12721.74ms. Two slow default-window probes returned401; explicit60000ms verification passed. Window expiry is a plausible inference, not a confirmed business error reason. Default client remains5000ms; auth failures do not retry automatically.
- Full OpenAPI download/schema diff, research sources/statistical boundary, replay baselines and every LIVE execution blocker remain unresolved. No scheduler, later-phase intelligence, risk change, trade, signature, broadcast, wallet mutation or funds movement was introduced.

## Phase 2 gate

All16 requested gate items PASS within the explicit verified entitlement/capability scope: practical Binance RWA and Market reads; equity/news to allowed access; calendar; dynamic discovery; normalized metadata/ratios; token/equity persistence; supported history; mode isolation; safe failures; secret isolation; passing tests; absence of later-phase logic. The user explicitly allows verified, isolated and documented provider entitlement limitations without automatically failing the phase.

```text
PHASE_2_DEVELOPMENT_GATE=PASS
DATA_GATE=PASS
DRY_RUN_GATE=NOT_YET_TESTED
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

NEXT PHASE: **STOPPED. Phase3 requires a separate instruction. LIVE execution remains blocked.** The canonical root/docs master files remain byte-identical and unchanged.

## Files changed

Added backend clients/common/binance_web3/massive; provider protocols/binance/massive/demo; normalized data models/ORM tables/repository; calendar/discovery/ingestion/data-layer services; read-only assets API; their package initializers;3 provider/ingestion test modules and sanitized fixture corpus/hash manifest. Added `data/demo/data-layer.json`, `data/calendar/nyse-2026-2028.json`, `scripts/verify-data-layer.py`, this report and Phase2 evidence JSON.

Updated backend config/database/main/status schema/logging and3 foundation regression tests; frontend App/status parser/status types/test; runtime/dev Python dependency declarations and .env.example; security audit; README; API_MATRIX, ARCHITECTURE, CAPABILITY_GAPS, DEVELOPER_EXPERIENCE and Phase1 dependency record. No .env credential file, master specification, execution gate document or execution-safety setting was modified.
