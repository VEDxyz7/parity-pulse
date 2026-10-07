# Parity Pulse

Canonical Phase 1 — Working Ask Flow is PASS for deterministic, non-executable exposure estimates and persisted DRY_RUN proposals. Engineering Stages 1/2 remain PASS. The backend implements dynamic Binance RWA discovery, market data, independent Massive equity/news adapters, a versioned U.S. calendar, exact Decimal normalization and isolated SQLite persistence. The frontend accepts stock budget requests and displays backend-authoritative estimates, issuer comparison, unknown costs and execution blockers. Canonical Phase 2 adds a separate deterministic analytical Trust endpoint/panel; its gate remains BLOCKED by unavailable real evidence. Opportunity, agents and live execution remain deferred.

**All LIVE execution is blocked.** The application rejects LIVE configuration even if a flag is set to true. It has no order, broadcast, wallet mutation, portfolio or trading endpoints.

## Product roadmap and engineering stages

Canonical product roadmap: Phase 0 — Reconnaissance; Phase 1 — Working Ask Flow; Phase 2 — Trust Layer; Phase 3 — Opportunity Mode; Phase 4 — Safety + Execution / remaining terminal capabilities. The master section 88 engineering stages and all later definitions remain unchanged; [PHASE_MAP.md](docs/PHASE_MAP.md) provides the complete mapping.

Engineering Stage 1 — Foundation and Engineering Stage 2 — Data Layer have passed. Foundation supports Canonical Phase 1; Data Layer supports Canonical Phase 1 and prepares Canonical Phase 2. **The current canonical milestone is Phase 1 — Working Ask Flow, PASS:** request parsing, exposure comparison, indicative result/route and persisted DRY_RUN proposal are verified. Vendor quotes and transaction simulation remain unavailable and never reported as successful. Canonical Phase 2 — Trust Layer is analytically implemented and software-verified, with TRUST_GATE=BLOCKED by current equity403, missing mandatory metrics/history and partial news. Canonical Phase 3 — Opportunity Mode must not begin before Trust completion and TRUST_GATE=PASS.

Original PHASE_1/PHASE_2 reports and the legacy `phase: 2` status field refer to engineering milestones. PHASE_1_REPORT now additionally records the completed canonical Ask milestone, and the current UI labels it Canonical Phase 1. The Data Layer report remains PASS and is not renamed as Trust Layer; [EXECUTION_GATES.md](docs/EXECUTION_GATES.md) records current development gates.

## Local startup

Requirements: Python 3.12+; Node 22.12+ (verified with Python 3.12.10 and Node 24.12.0). Run from the repository root.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci
```

Start the backend in one terminal:

```sh
.venv/bin/python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
```

Start the frontend in another terminal:

```sh
npm run dev
```

Open <http://127.0.0.1:5173>. Vite proxies `/api` to the backend at port 8000. No provider credentials are needed. Stop each service with Ctrl+C; backend shutdown disposes its database engine.

### An existing development server occupies the port

Run only one backend on port 8000 and one frontend on port 5173. A second launch can initialize successfully and then fail to bind because the first instance is still running. Inspect the listener before taking action:

```sh
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

Confirm the process command and working directory belong to this project. For a previous Parity Pulse instance, stop it with Ctrl+C in its original terminal or send SIGTERM to its confirmed PID, then rerun the documented command. Do not terminate an unrelated listener. `npm run dev` is the canonical frontend command from the repository root; the root npm workspace delegates to `frontend`.

See the [post-gate startup verification](docs/PHASE_1_POST_GATE_DEBUG.md) for the resolved duplicate-instance conflict and fresh backend/frontend checks.

## Configuration

Defaults work without an environment file. Optional settings can be supplied through the process environment or a local root `.env`; process variables take precedence. See [.env.example](.env.example). Preserve any existing `.env`; never overwrite it with the example or commit it. The frontend reads no backend configuration file.

| Variable | Default / allowed values through Engineering Stage 2 |
|---|---|
| APP_ENV | development; development/test/production |
| DATA_MODE | DEMO; DEMO/LIVE_READ_ONLY |
| EXECUTION_MODE | DRY_RUN; LIVE is rejected |
| APPROVAL_MODE | PROPOSE_ONLY; AUTONOMOUS is rejected |
| LIVE_TRADING_ENABLED | false; true is rejected |
| REQUIRE_SIMULATION | true; false is rejected |
| DATABASE_URL | SQLite file under root data/; local SQLite only; sqlite:///:memory: supported for tests |
| LOG_LEVEL | INFO; DEBUG/INFO/WARNING/ERROR/CRITICAL |
| BINANCE_WEB3_API_KEY / BINANCE_WEB3_SECRET_KEY | Required only for Binance LIVE_READ_ONLY reads |
| MASSIVE_API_KEY | Required only for independent LIVE_READ_ONLY equity/news reads |
| MASSIVE_DATA_QUALITY | UNKNOWN; UNKNOWN/DELAYED/REALTIME, subject to verified entitlement; a missing source time is never a fresh quote |
| LLM_API_KEY | Optional future placeholder; unused |

Boolean settings use `true` or `false`. Invalid enum values, malformed database URLs and unsafe combinations refuse startup with a sanitized error. LIVE_READ_ONLY enables reviewed provider reads when configured. It never loads DEMO fixtures or enables execution. Credential absence, permission failure or invalid data returns an explicit limitation/error, not substitute data. Keep MASSIVE_DATA_QUALITY=UNKNOWN unless an entitlement is independently verified; this account currently rejects current snapshots/NBBO.

## Architecture through Canonical Phase 2

```text
backend/app/        FastAPI, read clients/providers, normalized models, repositories, ingestion, calendar
backend/tests/      unit, API/lifecycle and security tests
frontend/src/       React shell, typed status service, TanStack Query hook, tests
data/demo/          deterministic, explicitly labeled DEMO metadata and financial fixtures
scripts/           localhost/security audits and bounded read-only verification
docs/              canonical specifications, capability gates and phase reports
```

Startup validates settings and initializes SQLite schema revision4, retaining existing data/checkpoint/proposal tables and adding isolated Trust assessment/sample/episode tables. DEMO seeds only explicitly labeled fixtures. LIVE_READ_ONLY startup performs no external calls; asset inspection invokes bounded provider reads. The fixture's fixed ID/timestamp, DEMO label and `execution_allowed=false` prevent a data fixture from claiming execution authority. The frontend tests' synthetic fixture is isolated from production code and is never an unavailable-backend fallback.

Each request has a generated `X-Request-ID`, a validated/generated UUID `X-Correlation-ID` and an application `X-Run-ID`. Responses and error envelopes retain these IDs. Application/request logs are JSON; request logs include route templates, not raw query strings, bodies or headers. Known credentials are redacted, raw exception messages/tracebacks are omitted, and unexpected log metadata is dropped. Provider fields are excluded from settings serialization; API responses use explicit public schemas.

`GET /api/health` checks lifecycle readiness and a real SQLite query. `GET /api/system-status` returns safe environment/mode/gate/version/fixture status. Database unavailability returns HTTP 503. Unknown routes and errors use sanitized envelopes. Neither endpoint accepts settings changes; query parameters cannot enable execution. Engineering Stage 2 adds only `GET /api/assets` and `GET /api/assets/{ticker}` for backend-authoritative data inspection, with Decimal strings and explicit mode/quality/provenance/limitations.

The frontend shows verified status or an explicit unavailable state and discards stale health/results after failure. The Ask form makes a proposal POST only after explicit submission; it displays financial strings computed by the backend and hides expired selected quantities. Opportunity and Autopilot remain disabled. No execution controls or frontend financial calculations exist.

## Tests and checks

```sh
.venv/bin/python -m pytest --cov=app --cov-report=term-missing
.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
npm test
npm run build
.venv/bin/python scripts/check-security.py
```

With both local servers running:

```sh
npm run test:integration
```

Tests use temporary SQLite databases, sanitized real response fixtures and synthetic credentials without loading the developer's `.env` or contacting providers. They cover signing/wire contracts, adapters, precision, source timestamps, data quality, malformed schemas, retries/rate limits, calendar/DST, discovery, pagination, persistence/conflicts/resumability, mode isolation and Engineering Stage 1 regressions. The security audit reads configured values only into memory, scans source/docs/build/fixture/local-database artifacts without printing matches, validates Git ignore semantics in a temporary repository and checks frontend bundle isolation. This workspace is not automatically initialized or committed as a Git repository.

## Docker

Docker Engine with Compose is required. No Binance credentials are passed to containers; `.env` files are excluded from build contexts. Compose only interpolates the explicitly listed application settings.

```sh
docker compose build
docker compose up -d
docker compose ps
curl --fail http://127.0.0.1:8080/api/health
docker compose down
```

Open <http://127.0.0.1:8080>. The frontend container serves the production bundle and proxies `/api` to the backend. Both services bind host ports to loopback. The backend runs as an unprivileged user and persists SQLite data-layer records in `parity_data`. Fixture files are separate from the writable database volume. Each image defines a health check; frontend startup waits for backend health. The frontend uses an unprivileged nginx image. Named database data survives `down`.

Optional environment configuration uses the same typed settings table; changing a setting to an unsafe LIVE combination causes backend startup to fail. For a backend-only image: `docker build -t parity-pulse-backend .`; `docker run --rm -p 127.0.0.1:8000:8000 parity-pulse-backend`. The SQLite file is ephemeral in that standalone command unless a volume is mounted at `/app/var`.

Docker configuration is included, but Docker is unavailable in the current development environment; image build/run verification is recorded as NOT_RUN in the phase report.

## Gates and phase boundary

```text
CANONICAL_PHASE_1_GATE=PASS
DATA_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
DRY_RUN_GATE=PASS
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

DRY_RUN_GATE=PASS is scoped to verified indicative Ask estimates and non-executable proposals, with unavailable simulations failing execution readiness. REQUIRE_SIMULATION stays true; transaction simulation is UNAVAILABLE. All three LIVE blockers remain unresolved. The five legacy system-status fields report DATA/DRY_RUN PASS and three blocked LIVE gates; the separate Trust endpoint returns trust_gate=BLOCKED. Opportunity remains a development dependency without an engine.

See [Engineering Stage 2 Data Layer report](docs/PHASE_2_REPORT.md), [phase map](docs/PHASE_MAP.md), [architecture](docs/ARCHITECTURE.md), [API matrix](docs/API_MATRIX.md) and [execution gates](docs/EXECUTION_GATES.md). See [Canonical Phase 1 report](docs/PHASE_1_REPORT.md#canonical-phase-1--working-ask-flow) and [automated gate evidence](docs/evidence/CANONICAL_PHASE_1_GATE.json). See the [Canonical Phase 2 Trust report](docs/PHASE_2_TRUST_REPORT.md), [data contracts/policy](docs/DATA_CONTRACTS.md), [test matrix](docs/TEST_MATRIX.md) and [Trust gate evidence](docs/evidence/CANONICAL_PHASE_2_TRUST_GATE.json). STOP after Phase 2. Next recommended work is Phase 2 data/capability remediation and Trust gate re-verification. Do not begin Opportunity Mode.


## Read-only data inspection and verification

With the backend running in its default DEMO mode:

```sh
curl --fail http://127.0.0.1:8000/api/assets
curl --fail http://127.0.0.1:8000/api/assets/NVDA
```

For provider inspection, configure credentials locally and start with DATA_MODE=LIVE_READ_ONLY while retaining DRY_RUN, PROPOSE_ONLY, false LIVE enablement and required simulation. No source-code port or safety setting changes are required. BSC stock discovery uses runtime issuer/chain/catalog data; invalid representations are excluded with an explicit PARTIAL limitation. Unavailable equity snapshots do not become Binance reference prices.

The optional verification command is an explicit bounded real-data operation, not a startup hook or scheduler. It reads configured credentials only in memory, uses the same allowlisted clients and writes LIVE records into `data/phase2-verification.db`, independently of the running DEMO database. Safe result metadata goes to `docs/evidence/PHASE_2_PIPELINE.json`.

```sh
.venv/bin/python scripts/verify-data-layer.py --recv-window 60000
```

The client default receive window remains5000ms. The documented optional60000ms window was used for this verification after slow requests returned401; authentication errors are not automatically retried. The script makes no order, transaction, wallet or fund-moving call. It can take over a minute because Massive reads are conservatively paced at12.1 seconds/request.

Historical ingestion is a backend service with bounded page budgets/checkpoints and explicit completion status. News history is partial, token trade price units and candle volume units are unverified, and historical token ratios come from metadata available at ingestion rather than proven as-of ratios. Current independent snapshot/NBBO access is403; historical close is labeled HISTORICAL. The static calendar covers only verified NYSE2026–2028 sessions and NYSE American extended hours. These limitations must be resolved before affected later-phase analysis.

## Working Ask Flow — DRY_RUN only

At <http://127.0.0.1:5173>, submit “I have $50 of Nvidia” or “Buy $50 Apple”. In DEMO, all prices/issuers/ratios are visibly synthetic. LIVE_READ_ONLY dynamically discovers real representations; failed reads never fall back to fixtures.

```sh
curl --fail http://127.0.0.1:8000/api/exposure/quote \
  -H 'Content-Type: application/json' \
  --data '{"text":"I have $50 of Nvidia"}'
.venv/bin/python scripts/verify-ask-flow.py
```

The result includes resolved company/ticker, eligible and excluded representations, selected issuer, exact shares/token and USD/token, effective USD/share, budget, rounded tokens/share exposure, cost/remainder, source times, route reason, explicit unknown costs, independent-reference availability, expiry, proposal UUID and no-broadcast statement. POST /api/intent/parse separately exposes bounded parsing; GET /api/exposure/proposals/{proposal_id} retrieves an isolated stored proposal.

Indicative estimates use token price and ratio only, before unknown fees/gas/slippage/funding conversion. Selection is not a tradable route or cheapest all-in execution. Unknown/closed/paused/overnight issuer states, stale/malformed/contradictory token data, missing decimals and unsupported requests fail closed. Missing/stale independent equity prevents any current equity comparison or execution readiness; it cannot become a Binance reference price or historical-current substitute. Every proposal has execution_ready=false, simulation_status=UNAVAILABLE, require_simulation=true and transaction_broadcast=false.

The verification command above uses only existing synthetic DEMO fixtures and an isolated database. Optional actual provider verification uses configured secrets in memory and the unchanged market-only allowlist:

```sh
.venv/bin/python scripts/verify-ask-flow.py --live-read-only
```

It writes a separate LIVE verification database and sanitized evidence; it never starts a wallet, obtains a signature, calls a Trading/Transaction endpoint, submits an RFQ order or broadcasts. Actual verification found two NVDA representations and selected Ondo for an indicative proposal; current independent snapshot returned403. This is a measured read-only result, not a current-equity entitlement, executable vendor quote or simulation certificate.

## Canonical Phase 2 — analytical Trust Layer

Submit a supported uppercase ticker in the separate Trust panel, or request:

```sh
curl --fail http://127.0.0.1:8000/api/assets/NVDA/trust
.venv/bin/python scripts/verify-trust.py
```

Results include representations/ratios/prices, independent reference source/kind/quality/times, scheduled regime, exact comparable value/deviation where available, freshness, baseline/sample counts, verified liquidity, aligned news, historical analogues, classification/reasons and explicit missing evidence. The backend is authoritative; the frontend performs no Trust/financial calculation. Default fixed DEMO fixtures are not refreshed into fictitious current data or history, so insufficient evidence is expected. All live/ready/broadcast flags remain false. Trust never changes Ask proposals or execution behavior.

REGULAR requires a fresh verified independent current quote; Massive snapshot403 yields INSUFFICIENT_EVIDENCE, not a Binance or historical-current fallback. Closed sessions may use the previous actual regular close explicitly labeled HISTORICAL. Required baseline30/analogue3 safeguards, exact stock/representation/regime/ratio partitions and available-time checks remain mandatory. V1 classification rules are documented uncalibrated engineering heuristics with LOW confidence cap, not validated profitability or news causality. No LLM is used, including provider LLM sentiment.

Optional explicit read-only verification:

```sh
.venv/bin/python scripts/verify-trust.py --live-read-only
node scripts/check-trust-browser.mjs
node scripts/check-ask-browser.mjs
```

Provider verification uses new isolated phase2-trust databases and sanitized evidence. Browser checks use disposable Chrome profiles against the running DEMO app; their new Trust/Ask-regression artifacts preserve historical Phase 1/Data Layer evidence. Actual NVDA evaluation discovered two issuers but current-equity403, absent mandatory liquidity/activity, partial news and insufficient real history keep TRUST_GATE=BLOCKED. No executable transaction is constructed or submitted.
