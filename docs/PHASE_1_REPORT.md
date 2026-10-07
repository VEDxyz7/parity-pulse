**Current canonical verification (2026-10-06): CANONICAL_PHASE_1_GATE=PASS; DRY_RUN_GATE=PASS for non-executable indicative estimates/proposals.** The complete [Working Ask Flow report](#canonical-phase-1--working-ask-flow) follows the preserved original Foundation report below. The original “Phase 1 — Foundation” and “Phase 2 — Data Layer” references are historical engineering milestones. Canonical Phase 2 Trust Layer remains NOT STARTED; Opportunity and all LIVE gates remain blocked.

# Phase 1 — Foundation report

Date: 2026-10-06 (Asia/Calcutta). **PHASE: 1. STATUS: PASS.**

The non-live foundation is implemented and verified locally. Phase 2 has not started. The original development-gate amendment and LIVE safety requirements remain unchanged; the canonical master copies remain byte-identical with SHA-256 `45ef4fbc1547c850308267cefb6041293351d0cc36d7be423348b18d3b17991f`.

## Architecture created

- FastAPI application factory and lifespan; immutable typed settings; deterministic SQLite/SQLAlchemy bootstrap with only one foundational schema-version table; cleanup on shutdown.
- Explicit public health/system-status response schemas, sanitized error envelopes and request/correlation/run IDs. Application/request/server JSON logging with configured-secret redaction and allowed scalar metadata; no raw headers, bodies, query strings or exception details.
- React/Vite/TypeScript/Tailwind workspace shell, Lucide icons and TanStack Query. Backend status is fetched through the same-origin proxy, validated and displayed with loading/unavailable/recovery states and bounded checks. Product-mode navigation is deferred and disabled.
- Deterministic DEMO foundation metadata, with fixed identity/time and no execution authority. It is never loaded in LIVE_READ_ONLY or used as an unavailable-backend fallback.
- Pinned Python/npm dependencies, unit/API/security/React tests, localhost integration and secret/ignore audits, plus backend/frontend Dockerfiles and loopback-only Compose configuration.

No Binance API clients, wallet runtime, financial calculations, route builders, RFQ/SWAP execution, simulation engine, trust/prediction/opportunity/agents/autopilot/portfolio/positions are implemented. Provider credentials are optional future placeholders and unused. No entitlement or LIVE blocker verification was attempted.

## Phase 1 gate

| Requirement | Result | Evidence |
|---|---|---|
| Backend starts | PASS | Actual Uvicorn factory startup on localhost, file database readiness and restart verified |
| Frontend starts | PASS | Vite running on localhost; HTTP shell serving and React DOM tests pass |
| Database initializes | PASS | Idempotent temporary/file/memory tests; actual local file startup; only schema_metadata table |
| /api/health works | PASS | API tests and running frontend-proxy request return200/ok; unavailable DB returns503 |
| /api/system-status works | PASS | Public schema/gate/API tests and running frontend-proxy request pass |
| Safe defaults work | PASS | DEMO/DRY_RUN/PROPOSE_ONLY/false/true startup with no required provider credentials |
| Unsafe LIVE configuration rejected | PASS | Unit tests and actual Uvicorn factory refusal before startup; true flag cannot unlock LIVE either |
| Deterministic demo fixture | PASS | Repeated exact fixture equality, DEMO/false marker and LIVE_READ_ONLY isolation tests |
| Tests pass | PASS | 34 backend + 14 frontend tests; localhost integration check passes |
| Frontend build passes | PASS | Strict TypeScript check and Vite production build pass |
| No detected secret leakage | PASS | Synthetic response/config/log tests and local configured-value source/docs/bundle audit; ignore rules verified |
| No later-phase trading introduced | PASS | OpenAPI contains only the two foundation business endpoints; mutation/financial routes absent |

## Commands to run

Run from the repository root; preserve an existing `.env`. No Binance credentials are required.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci
```

Backend and frontend, in separate terminals:

```sh
.venv/bin/python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
npm run dev
```

Open <http://127.0.0.1:5173>. Tests/checks:

```sh
.venv/bin/python -m pytest --cov=app --cov-report=term-missing
.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
npm test
npm run build
.venv/bin/python scripts/check-security.py
npm run test:integration
```

The last command requires both local servers. Docker: `docker compose build`, `docker compose up -d`, then check <http://127.0.0.1:8080/api/health>. See [README](../README.md) for all environment variables, Docker volume/health behavior and shutdown commands.

## Tests run / passed / failed

| Check | Final result |
|---|---|
| pytest unit/API/security/lifecycle suite | 34 PASSED; 0 FAILED; 98% app statement coverage |
| Vitest React/status/timeout suite | 14 PASSED; 0 FAILED |
| Strict TypeScript + Vite production build | PASS |
| Running frontend/backend proxy and correlation check | PASS |
| Actual unsafe-LIVE Uvicorn startup refusal | PASS |
| Ruff lint and format | PASS |
| pip dependency consistency / npm peer tree | PASS |
| Configured-value leakage, frontend bundle and Git/Docker .env exclusion audit | PASS |
| Compose YAML parsing and static build-context review | PASS |
| Actual Docker build/run | NOT_RUN — Docker binary/engine unavailable |
| Native browser visual inspection | NOT_RUN — computer-use permissions unavailable |

Initial frontend syntax/dependency compatibility/resolution errors were fixed and affected tests/build rerun. Final outstanding test failures: **0**. No tests placed trades, called external business APIs or accessed wallet funds/settings. No commit was made; `.env` is preserved and ignored. Startup/shutdown and rejected unsafe configuration were checked in actual local processes as well as tests.

## Known limitations

Docker files/configuration are provided and statically reviewed, but images/containers cannot be certified as run here because Docker is absent. Native Chrome inspection returned `Computer Use permissions are not granted`; React DOM tests, builds and real HTTP/proxy integration passed, but screenshots, mobile layout and native browser visual QA remain unverified. An upstream Starlette1.7 TestClient deprecation warning recommends future httpx2 migration; the pinned current suite passes and the warning is not suppressed.

LIVE_READ_ONLY is a safe configuration boundary with no external integration in Phase 1. The full proposal/build/simulation DRY_RUN workflow is not implemented; its gate remains NOT_YET_TESTED. Future provider/schema/data/precision and LIVE gaps retain their original evidence requirements. The service is local foundation infrastructure, with no later-phase authentication/deployment or business capabilities implied.

## Current execution-gate status

```text
DATA_GATE = PASS
DRY_RUN_GATE = NOT_YET_TESTED
SWAP_LIVE_GATE = BLOCKED
RFQ_LIVE_GATE = BLOCKED
AGENTIC_WALLET_LIVE_GATE = BLOCKED
```

Required current configuration: DATA_MODE=DEMO or LIVE_READ_ONLY; EXECUTION_MODE=DRY_RUN; APPROVAL_MODE=PROPOSE_ONLY; LIVE_TRADING_ENABLED=false; REQUIRE_SIMULATION=true. No broadcast, RFQ submission, wallet settings change, fund movement or real position is possible through the implemented routes. Passing the foundation gate does not pass a LIVE gate or the transaction DRY_RUN gate.

## Files changed

The inventory below lists the Phase 1 source/config/test/documentation files. Generated dependencies, build output, caches and runtime databases are ignored and excluded. Both master specifications and original Binance evidence are unchanged.

```text
.dockerignore
.env.example
.gitignore
Dockerfile
README.md
backend/app/__init__.py
backend/app/api/__init__.py
backend/app/api/middleware.py
backend/app/api/schemas.py
backend/app/api/system.py
backend/app/config.py
backend/app/database.py
backend/app/demo.py
backend/app/main.py
backend/app/models/__init__.py
backend/app/models/base.py
backend/app/utils/__init__.py
backend/app/utils/logging.py
backend/tests/conftest.py
backend/tests/integration/test_application.py
backend/tests/security/test_boundaries.py
backend/tests/unit/test_config.py
backend/tests/unit/test_database_demo.py
compose.yaml
data/demo/foundation.json
docs/API_MATRIX.md
docs/ARCHITECTURE.md
docs/DEPENDENCIES.md
docs/DEVELOPER_EXPERIENCE.md
docs/PHASE_1_DEPENDENCIES.md
docs/PHASE_1_REPORT.md
frontend/Dockerfile
frontend/index.html
frontend/nginx.conf
frontend/package.json
frontend/src/App.tsx
frontend/src/components/StatusBadge.tsx
frontend/src/hooks/useSystemStatus.ts
frontend/src/main.tsx
frontend/src/services/system.ts
frontend/src/styles.css
frontend/src/test/App.test.tsx
frontend/src/test/fixtures.ts
frontend/src/test/setup.ts
frontend/src/types/system.ts
frontend/tsconfig.json
frontend/vite.config.ts
package-lock.json
package.json
pyproject.toml
requirements-dev.txt
requirements.txt
scripts/check-integration.mjs
scripts/check-security.py
```

## Next phase

**PHASE 2 — DATA LAYER, not started. STOP after Phase 1.**

## Post-gate startup verification

The manually reported address-in-use error was caused by the previous Parity Pulse backend left running on port 8000. Its identity was verified before graceful termination. The exact canonical backend command was rerun successfully; both direct endpoints returned HTTP 200. The root `npm run dev` command was verified with a fresh Vite launch, and isolated headless Chrome rendered the connected DEMO/DRY_RUN frontend with all five expected gates. All 34 backend and 14 frontend tests, build/type checks, Ruff and localhost integration were rerun successfully. No application code or architecture was changed. See [the post-gate debug report](PHASE_1_POST_GATE_DEBUG.md) for process identities, actions, final results and limitations. Phase 1 is PASS; Phase 2 remains not started.

## Canonical Phase 1 — Working Ask Flow

Formal verification date: 2026-10-06 (Asia/Calcutta), completed after the interrupted implementation run. **CANONICAL_PHASE_1_GATE=PASS. DRY_RUN_GATE=PASS.** Scope: deterministic indicative exposure estimates and persisted non-executable proposals. Simulation remains UNAVAILABLE and execution readiness remains false. This does not certify executable vendor quotes or authorize live execution.

### Phase 1 audit and completed existing work

The resumption audit read PHASE_MAP, the accepted PHASE_2_REPORT, EXECUTION_GATES, this historical Foundation report, API_MATRIX and ARCHITECTURE; reviewed the Ask services/models/routes/repository/frontend and preserved verification artifacts; and reran the entire established suite before making documentation changes. The prior [pre-implementation audit](CANONICAL_PHASE_1_AUDIT.md) records which Foundation/Data Layer capabilities were reused and which Ask pieces were originally missing.

| Acceptance target | Existing implementation / actual evidence | Gate |
|---|---|---|
| User stock budget request | Deterministic bounded grammar supports “I have $50 of Nvidia”, “Buy $50 Apple” and explicit budget/ticker forms; invalid or ambiguous requests need clarification | PASS |
| Company/ticker resolution | Reuses stock-first discovery; company/ticker matching is provider-derived; actual read-only run resolved Nvidia to NVDA | PASS |
| Tokenized representations | Reuses issuer/chain/search/catalog validation, with no hard-coded real contracts; actual read-only run discovered two NVDA representations | PASS |
| Issuer comparison / selection | Exact normalized P/R comparison of estimate-eligible representations, deterministic tie-break, explicit exclusions and unknown fees/liquidity/trust; actual read-only proposal selected Ondo | PASS |
| Normalization / effective share cost | Positive finite exact ratio/price; USD/share=P/R, conservatively rounded upward to18 fractional places for display; ranking uses the exact rational value | PASS |
| Budget / quantity / share exposure | Integer token units=floor(budget/price ×10^decimals); quantity=units/10^decimals; shares=quantity×ratio; exact cost and unallocated notional preserved as strings | PASS |
| Quote/result / dry-run proposal | Typed ask-1 result includes company/ticker, compared representations, selected issuer, ratio/price/effective cost, budget/quantities/exposure, route reason, unknown costs, provenance, expiry and blockers | PASS |
| No broadcast / failure handling | DRY_RUN/PROPOSE_ONLY only; transaction_broadcast=false, execution_ready=false, require_simulation=true, simulation=UNAVAILABLE; no execution gateway or order/transaction/wallet endpoint | PASS |
| Persistence / audit | Schema revision3 adds exposure_proposals, preserves prior tables/records, stores decimal JSON with policy/run/request/correlation IDs, logs sanitized proposal UUID/status/mode; expiry removes selected route | PASS |
| DEMO/LIVE separation | DEMO fixtures stay explicitly synthetic; LIVE_READ_ONLY never substitutes DEMO data; stored retrieval uses an explicit mode partition; mixed-mode inputs reject the whole proposal | PASS |
| Working interface | Explicit Ask submission, backend-value display, failure/retry/expiry states; desktop/mobile browser tests pass; Opportunity/Autopilot remain disabled | PASS |

**Already complete from the interrupted run:** the entire acceptance chain above, 189 backend tests, 33 frontend tests, read-only verification, safe persistence and the working Ask UI. The implementation was preserved, not rebuilt.

**Missing at resumption:** the formal canonical section in this report and CANONICAL_PHASE_1_GATE.json. Several current docs already anticipated PASS, but their report/evidence links were unfinished. No actual Phase 1 behavior or test-coverage gap was found. No application or test code was changed after the resumption instruction; only the report, formal evidence and current gate/map documentation were completed. README already describes the implemented scope and links this report, so no additional README edit was needed on resumption.

Git status/diff checks were attempted; the workspace has no Git metadata. No repository was initialized and no commit was made. Saved SHA-256 baselines were used to review changes, prove application/test preservation on resumption and confirm that the canonical masters, protected settings/provider clients, historical Data Layer report/fixtures/evidence were unchanged.

### Tests and verification results

| Established check | Actual resumption result |
|---|---|
| All backend unit/API/security/provider/ingestion tests | 189 passed,0 failed;93.76% application statement coverage |
| All frontend tests | 33 passed,0 failed |
| npm run build | PASS; strict TypeScript noEmit and Vite production build |
| Ruff lint and formatting | PASS; all51 Python files formatted |
| scripts/check-security.py | PASS; configured-secret leakage, Git/Docker environment exclusions and frontend secret isolation |
| Python dependency consistency | PASS; no broken requirements |
| Exact canonical backend startup, /api/health and /api/system-status | PASS; unchanged command/port, healthy SQLite and safe settings |
| npm run test:integration | PASS; actual frontend proxy, health/status IDs and persisted non-executable Ask result |
| Existing browser verifier, desktop/mobile | PASS; default Nvidia Ask, unsupported stock NO_PROPOSAL, no automatic proposal POST, no page-wide horizontal overflow,0 runtime exceptions |
| Preserved DEMO/LIVE proposal arithmetic | PASS; independently recomputed base units, P/R, tokens×ratio, cost/remainder and mode isolation from existing verification databases opened read-only |
| Historical masters/Data Layer records | PASS; byte/hash preservation |
| Actual Docker build/run | NOT_RUN; Docker remains unavailable |

The upstream Starlette TestClient/httpx migration warning remains unsuppressed; no failures. Frontend has no separate ESLint command; configured TypeScript/build checks pass. Tests are not weakened or removed. The earlier implementation legitimately updated exact route/table inventories for the new proposal endpoints/table and the expected DRY_RUN PASS; assertions that execution/configuration bypasses are prohibited remain intact. The original107 backend and15 frontend tests are still present, with82 new backend and18 new frontend cases covering the Ask scope. Resumption needed no additional tests.

Test coverage includes ticker/company parsing and resolution, dynamic representation discovery, issuer comparison, exact shares/token normalization, effective price/share, budget-to-token units/share exposure, order-independent tie-breaks, response schema, missing prices/decimals, unsupported and malformed requests/data, issuer unknown/pause/overnight status, conflicting identity/ratios, stale/future prices, current-equity unavailability/delay/history, no Binance reference-price fallback, persistence failure, audit IDs, proposal expiry (including the exact freshness deadline), DEMO/LIVE isolation and absence of network/wallet execution in DEMO. Frontend tests verify safe mode/flag/schema checks, decimal-string display, failures/retry, expiry, timeout/cancellation and no trade controls.

### DRY_RUN evidence and limits

[Automated gate record](evidence/CANONICAL_PHASE_1_GATE.json) maps each acceptance criterion to actual passing tests and retains source/test fingerprints. [Preserved DEMO result](evidence/CANONICAL_PHASE_1_DEMO.json), [preserved actual read-only provider run](evidence/CANONICAL_PHASE_1_LIVE.json), [original browser result](evidence/CANONICAL_PHASE_1_BROWSER.json) and [fresh browser verification](evidence/CANONICAL_PHASE_1_BROWSER_REVERIFICATION.json) are distinct artifacts. Historical PHASE_2 evidence/report is untouched.

For the **synthetic DEMO** request “I have $50 of Nvidia”, the stored result has ticker NVDA, issuer demo-issuer, ratio1.000000000000000001 shares/token and token price150.9876543210987654321 USD/token. Effective cost is150.987654321098765282 USD/share; budget50 USD produces0.331152902698039216 tokens and0.331152902698039216331152902698039216 synthetic share exposure. These are fixed fixture values, never current market data or real contracts. The result includes **“No real transaction was broadcast.”**

The interrupted run's actual LIVE_READ_ONLY verification at2026-10-06T12:26–12:27Z used only existing Binance Market/RWA and Massive snapshot reads. Eight Binance reads returned HTTP200/business0. Massive first had a transport timeout, then returned403/FORBIDDEN; independent current equity remained UNAVAILABLE. Two NVDA representations were discovered and an indicative Ondo proposal was persisted in a separate LIVE verification database. Catalog validation excluded37 malformed representations, reported as PARTIAL. The endpoint ledger retains only endpoint, HTTP/business status, permission/capability result and timestamp; no key, secret, signature, header or raw provider body was recorded there. No external provider calls were repeated on resumption; the existing factual evidence and persisted proposal arithmetic were verified.

Prices and ratios support token-only exposure estimates without inventing an independent equity quote. A missing/stale/unverified independent current equity price stays null and blocks execution readiness/current-equity comparison; historical closes and Binance referencePrice are never substituted. In every mode, fees/gas/slippage/liquidity/funding conversion are unknown, not zero. The chosen representation is eligible for an **indicative estimate only**, never trade eligibility or lowest all-in execution cost. Vendor quotes, route builds, funds/wallet checks and transaction simulation are unavailable. No simulation PASS, RFQ settlement safety, risk authorization or real position is claimed.

The current service is running at127.0.0.1:8000, PID92598, using the exact canonical Uvicorn factory command. The owned prior PID89685 was confirmed by command/cwd and gracefully reloaded once so final already-tested freshness validation was loaded. Frontend PID86767 was retained at127.0.0.1:5173. This was an environment verification step, not an application change or Phase 1 rebuild. Browser checks used disposable Chrome profiles and preserved the earlier evidence.

### Exact gate state, remaining blockers and stop

```text
CANONICAL_PHASE_1_GATE=PASS
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=NOT_YET_TESTED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

Remaining blockers are outside the completed indicative Phase 1 scope:

- Current independent Massive snapshot/NBBO is forbidden; exact plan/delay/redistribution remains unknown. Independent current-equity comparisons cannot be manufactured.
- Fees, liquidity, slippage/gas, funding conversion/balances, wallet eligibility and executable vendor routes are unverified. Ratio receipt time does not prove historical source/as-of validity; broader history/schema/unit gaps remain as documented in the Data Layer report.
- Transaction simulation remains UNAVAILABLE. SWAP exact simulated/executed equivalence is NOT_VERIFIED.
- RFQ final-settlement simulation/equivalence remains NOT_VERIFIED; no order submission or signing is enabled.
- Agentic Wallet CLI/runtime/session/worker integration remains NOT_VERIFIED; no wallet execution is enabled.
- Canonical Trust Layer is NOT STARTED / NOT COMPLETE. Opportunity remains blocked by Trust. No LLM agents, prediction, Opportunity, risk-rule changes or live functionality were introduced.

No Phase 1 acceptance blocker remains. **Exact next recommended phase: Canonical Phase 2 — Trust Layer**, requiring a separate instruction. STOP after Phase 1. Passing these development/dry-run gates never authorizes live actions or relaxes simulation, wallet, risk, approval, equivalence or RFQ rules.

### Files changed — canonical Ask implementation and formal verification

Original Working Ask implementation additions:

```text
backend/app/api/exposure.py
backend/app/models/exposure.py
backend/app/repositories/exposure.py
backend/app/services/exposure.py
backend/app/services/intent.py
backend/tests/integration/test_ask_flow.py
backend/tests/unit/test_exposure.py
frontend/src/components/AskFlow.tsx
frontend/src/services/exposure.ts
frontend/src/test/AskFlow.test.tsx
scripts/check-ask-browser.mjs
scripts/verify-ask-flow.py
docs/CANONICAL_PHASE_1_AUDIT.md
docs/evidence/CANONICAL_PHASE_1_DEMO.json
docs/evidence/CANONICAL_PHASE_1_LIVE.json
docs/evidence/CANONICAL_PHASE_1_BROWSER.json
```

Original Working Ask implementation updates:

```text
backend/app/api/schemas.py
backend/app/database.py
backend/app/main.py
backend/app/models/data_tables.py
backend/app/utils/logging.py
backend/tests/integration/test_application.py
backend/tests/security/test_boundaries.py
backend/tests/unit/test_database_demo.py
frontend/src/App.tsx
frontend/src/services/system.ts
frontend/src/styles.css
scripts/check-integration.mjs
README.md
docs/API_MATRIX.md
docs/ARCHITECTURE.md
docs/CAPABILITY_GAPS.md
docs/EXECUTION_GATES.md
docs/PHASE_0_GATE.md
docs/PHASE_MAP.md
```

Resumption/formal verification changes only:

```text
docs/PHASE_1_REPORT.md
docs/EXECUTION_GATES.md
docs/PHASE_MAP.md
docs/evidence/CANONICAL_PHASE_1_GATE.json
docs/evidence/CANONICAL_PHASE_1_BROWSER_REVERIFICATION.json
```

Source/test files, protected configuration, dependencies, credentials, master copies, DEMO/provider fixtures and historical PHASE_2 evidence/report were not changed on resumption. Build/test caches and runtime databases are generated/ignored artifacts; verification persisted only non-executable proposals. Original Foundation report above remains preserved verbatim, with its time-specific engineering Phase 1 scope and evidence distinguished from this canonical report.
