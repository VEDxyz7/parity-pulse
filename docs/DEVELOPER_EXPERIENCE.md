# Developer experience log — Phase 0

Date: 2026-10-06. The initial Phase 0 observations below are preserved historically. Phase 0.1 measured results appear at the end and supersede the earlier no-authenticated-calls state. Official contracts belong in API_MATRIX.md; credentials and raw responses are never logged.

| Observation | Actual result | Interpretation |
|---|---|---|
| Workspace inventory | One root MASTER_BUILD_PROMPT.md; no docs directory initially | No application or uploaded proposal/schema to inspect |
| Requested master path read | File not found | Used root master, preserved original |
| baw lookup | command -v baw returned exit 1 / no executable | CLI unavailable on PATH; not proof about remote support |
| Public documentation browsing | Official API pages and schema text accessible through browser tool | Documentation access, not business API success |
| First direct schema download | Sandbox curl DNS resolution failed | Network restriction; retried with approved escalation |
| Escalated download | curl exit 0, zero-byte body | Exit 0 did not mean valid schema |
| Retry with user agent / response headers | HTTP 202, content-length 0, x-amzn-waf-action: challenge | WAF challenge, not a JSON schema; not retained as valid snapshot |
| Current schema review | Browser showed OpenAPI 3.0.2 / info.version 1.0.0 and relevant paths | Partial inspection; no complete downloaded artifact/hash |
| Complete paper access | SSRN landing metadata/abstract discoverable; full paper content not obtained | Numeric table claims unverified |
| Multi-agent research | arXiv v3 full-text HTML accessible | Current-version text used instead of stale indexed abstracts |

## Not measured during the original Phase 0

Time to first successful **authenticated business API call**: NOT MEASURED; no such call made. Request signing errors, RWA keyword behavior, actual issuer inventory, runtime executionMode, quote expiry, response latency, rate-limit behavior, ratio updates, actual liquidity/slippage, off-hours response behavior, wallet constraints, approval/simulation outcomes and RFQ settlement are NOT TESTED.

Documentation GETs are not counted as successful market/trading API calls. Published examples are not real fixtures. No artificial timings, response bodies, fills or success rates are reported.

## Future evidence format

For authorized read-only integration tests record UTC time, operation, sanitized request shape, HTTP/application status, latency, request/correlation ID, freshness timestamps, provider version and fixture hash. Redact secrets/signatures. Keep docs-derived expectations separate from measured observations. For execution tests record exact non-capital environment, preview coverage, fingerprint, expiry and gateway behavior; never claim real settlement without terminal evidence.

## Phase 0.1 observed changes

- Requested master path fixed by exact raw-byte copy; direct equality and matching SHA-256 passed at 2026-10-06T09:41:27.435774Z. No specification edit.
- Initial environment lookup found no expected credentials. User then configured a project .env; local parsing loaded only the two expected variables, without shell evaluation or value logging.
- Seven initial sandbox probes produced no HTTP/business status. The approved network-enabled retry returned HTTP200/business0 for all seven, followed by three successful metadata/price/quote probes. [Exact five-field evidence and timestamps](evidence/BINANCE_READONLY_STATUS.json). Earliest successful probe timestamp: 2026-10-06T09:46:02.279Z; last: 09:47:36.655Z. These are request timestamps, not invented latency metrics.
- baw executable lookup returned null; targeted global npm package listing exited1 with no package dependency; bounded Binance skill-manifest inventory returned no matching local skills. Node reports v24.12.0. No installed CLI version, connected wallet state or worker control was inferred.
- Documentation identifies official installation/App connection paths, but this read-only task performed no install, pairing, settings change, wallet preview/signature or transaction action.

Actual wallet address/balance/order queries, RWA RFQ quoting, route building, exact transaction simulation, wallet gateway equivalence, session behavior and final settlement remain NOT_TESTED. Read-only access successes do not close those gaps. Full data freshness/issuer constraints and independent Massive entitlements remain unverified. No live position, order, approval or broadcast was created.

## Phase 1 — foundation observations

Date: 2026-10-06. Scope: non-live foundation only. No external business API, wallet or entitlement verification was attempted.

| Observation | Actual result | Interpretation |
|---|---|---|
| Dependency installation | Isolated Python3.12 virtual environment; exact Python pins and npm workspace lock installed | Reproducible foundation dependencies; future analytics/provider packages deferred |
| Sandbox network/port restrictions | Initial pip resolution and localhost bind/connect failed; authorized retries succeeded | Environmental restriction, not an application failure |
| Frontend test compatibility | Latest jsdom30 required a newer Node24 minor; compatible jsdom27.4 pinned; root placement fixed hoisted Vitest resolution | Final tests/build pass with Node24.12.0 |
| Backend tests | 34 unit/API/security tests pass;98% app statement coverage | Includes unsafe LIVE rejection, initialization, degradation, IDs, fixture isolation, sanitized errors/logs and no business routes |
| Frontend tests | 14 React/status tests pass | Includes connected/unavailable/recovery states, safe parsing, DEMO isolation and GET-only behavior |
| Build / lint | TypeScript/Vite build, Ruff lint/format and dependency checks pass | No current compiler/lint/required peer errors |
| Actual local startup/shutdown | Backend initializes file SQLite; localhost services and proxy work; terminated backend emits shutdown and disposes engine | Startup, shutdown and running integration verified |
| Actual unsafe startup | Uvicorn factory exits with sanitized startup-refused error for LIVE/false combination | No port binding or execution workflow starts |
| Secret audit | No configured credential values in audited source/docs/bundle; Git ignore semantics and Docker exclusion checked | .env preserved, no commits made and no backend secrets exposed to frontend |
| Docker | Binary/engine unavailable; Compose YAML parses, Dockerfiles/contexts reviewed | Actual image build/run NOT_RUN |
| Native UI visual inspection | Browser connector had no available browser; native Chrome access returned Computer Use permissions are not granted | Visual browser QA NOT_RUN; React DOM/build and localhost proxy checks are verified |
| Upstream warning | Starlette1.7 TestClient warns about future httpx2 migration;34 tests pass | Not suppressed or represented as a failure |

Only foundation metadata, logs, typed status APIs and shell behavior are implemented. The full transaction DRY_RUN gate remains NOT_YET_TESTED; SWAP/RFQ/Agentic Wallet LIVE remain BLOCKED. [Full Phase 1 report](PHASE_1_REPORT.md).


## Phase 2 — actual implementation/verification observations

Date:2026-10-06. [Report](PHASE_2_REPORT.md) and machine-readable evidence record actual runtime scope. Configured Binance/Massive credentials were loaded only in memory; .env was preserved. Initial13 Binance data reads returned200/business0. Initial Massive reads returned200 for history/status/holidays/news/actions and403 for snapshot/NBBO; permission failure remains isolated.

The full488-row catalog exposed37 critical schema failures, including paused versus documented pause and invalid types/names. Rows are excluded with an explicit PARTIAL limitation. BStock null marketStatus stays UNKNOWN. Real candle requests ignored before and included after; an initial historical check failed safely. A retained failed-attempt ledger plus two boundary fixtures support the subsequent local exclusive-window filter/progress tests and successful ingestion. Token trade price units disagree with plausible USD token price; reported values are retained only as CONFLICTING/non-authoritative.

Two slow default5000ms-window requests returned401; no automatic auth retry occurred. A later explicit verification with the documented60000ms window succeeded. This supports a timing hypothesis, not a proven Binance error diagnosis. No actual429 was observed; retry/quota/circuit tests are synthetic. Massive is paced conservatively at12.1 seconds/read because the account plan is unknown.

The final persisted pipeline passes:25 token observations,946 independent equity observations and100 news items in a separate LIVE verification database; no DEMO observations mixed in. Previous actual NVDA regular close239.11 is HISTORICAL with its original19:59Z bar time, not a current quote. Repeated equity ingestion adds0 rows. News history remains partial; historical ratios lack verified as-of availability.

107 backend tests pass (93% app statement coverage);15 frontend tests pass; Ruff, strict TypeScript/Vite build, pip consistency, local read routes/proxy, disposable headless Chrome rendering and configured-secret/source/fixture/bundle/local-database audit pass. The upstream Starlette httpx warning remains. No new dependencies were installed; existing httpx0.28.1 moved from dev-only to runtime declarations.

Confirmed prior backend86726 was gracefully restarted to load Phase2 because its command lacks reload. Final enum-validation/provenance fixes were followed by107 passing tests and one additional controlled reload of the confirmed Phase2 PID88786; current backend88967 serves final Phase2 on8000. Existing frontend86767 was preserved on5173. No port/source workaround was added. Docker remains unavailable, image execution NOT_RUN. All LIVE gates remain BLOCKED and full DRY_RUN workflow NOT_YET_TESTED. Phase3 has not started.
