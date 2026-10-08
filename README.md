# Parity Pulse

Master Phase 9 — Agentic Wallet: **IMPLEMENTATION PASS; local runtime UNAVAILABLE**.
The official `baw` read adapter, normalized wallet contracts, DRY_RUN gateway checks and
read-only reconciliation reuse Phase 8 safety infrastructure. No wallet executor is enabled.
See [Phase 9 report](docs/PHASE_9_REPORT.md) and
[capability matrix](docs/AGENTIC_WALLET_CAPABILITIES.md).

From the repository root, `.venv/bin/python scripts/inspect-wallet.py --read-only` opts into
installed official CLI reads and prints only sanitized capability metadata. It currently returns
`BAW_UNAVAILABLE`; it never installs, authenticates, signs or submits an order. The public app
does not spawn a CLI worker. DATA/DRY_RUN remain PASS, TRUST remains BLOCKED, OPPORTUNITY
remains BLOCKED_BY_TRUST, and all three LIVE gates remain BLOCKED. Phase 10 was NOT started.
The dated milestones below remain historical checkpoints.

Master Phase 8 — Safety and Execution: **IMPLEMENTATION PASS**. Deterministic Risk,
funding/base-unit checks, Binance quote/build contracts, approvals, fingerprints, simulation,
durable state/status tracking and a fail-closed ExecutionGateway are implemented as host-only
services. No public execution API, signing, broadcast or RFQ submission is enabled.
See [Phase 8 report and changed files](docs/PHASE_8_REPORT.md) and
[verification evidence](docs/evidence/PHASE_8_VERIFICATION.json).

Production gates remain DATA_GATE=PASS, DRY_RUN_GATE=PASS, TRUST_GATE=BLOCKED,
OPPORTUNITY_GATE=BLOCKED_BY_TRUST and all three LIVE gates=BLOCKED.
Fixture simulation does not prove live execution equivalence. Phase 9 was NOT started.
The sole authoritative specification is [docs/MASTER_SPEC.md](docs/MASTER_SPEC.md).
The dated milestone descriptions below remain historical checkpoints.

Master Phase 7 — Opportunity Mode: **IMPLEMENTATION PASS**. The production Opportunity gate
remains **BLOCKED_BY_TRUST**; all LIVE execution remains blocked. See
[Phase 7 report](docs/PHASE_7_REPORT.md) for the full candidate contract, rejection/ranking,
risk-budget semantics, tests and remaining real-data limitations. Phase 8 is not started.

Offline synthetic scan (existing DEMO fixtures; no provider calls or real funds):

```sh
.venv/bin/python scripts/scan-opportunities.py --demo supported-move --budget 60 --risk-budget 2
```

Analytical API: `POST /api/opportunities/scan`, `GET /api/opportunities/{run_id}`.
Budget and risk budget are explicit separate inputs; the risk budget is ex-ante and does
not guarantee a maximum realized loss. Ordinary production navigation remains locked.
The older dated milestone descriptions below are retained as history.

Master Phase 6 — Multi-Agent Intelligence is implemented; its production data dependency remains
BLOCKED. The authoritative specification is [docs/MASTER_SPEC.md](docs/MASTER_SPEC.md).
Six structured agents share DEMO/LIVE_READ_ONLY evidence adapters, bounded calls/tools,
look-ahead-safe memory and server-calculated confidence. Existing UI and production gates are unchanged.
[Phase 6 report and validation](docs/PHASE_6_REPORT.md). Phase 7 has NOT started.

Offline structured JSON, from the repository root; no credentials/network/execution calls:

```sh
.venv/bin/python scripts/analyze-agents.py --demo steady
.venv/bin/python scripts/analyze-agents.py --demo thin-move
.venv/bin/python scripts/analyze-agents.py --demo supported-move
# Existing real replay only; expected DEFER/INSUFFICIENT_EVIDENCE:
.venv/bin/python scripts/analyze-agents.py --real-replay \
  data/research/phase5/a3e7be2630acccb2b7496d87f2e584ce2cf8af34811461738336d42aba59e98e.json
```

The default sample mandate is $60 with a separately explicit $2 risk budget, matching the existing
synthetic risk inputs; it proposes no more than the existing $50 scenario notional. These are DEMO
assumptions, not recommendations or live prices. `--intent` supplies another bounded explicit mandate;
a risk-budget mismatch safely defers. Audit/memory storage is isolated under `data/agents/phase6/`;
`--store` can select another separate directory. Optional LLM_PROVIDER/LLM_MODEL configuration
belongs to a verified injected transport host; no provider is automatically enabled or assumed available.

The following dated Phase 5 and earlier sections remain historical evidence.

Master engineering Phase 5 — Research / Prediction is implemented; its real data gate remains
**BLOCKED**. Offline point-in-time episodes, cosine retrieval, rolling Decimal OLS and deterministic
replay reuse existing Trust evidence. No production gate or completed DEMO behavior changes.
See [Phase 5 architecture, exact data blockers and verification](docs/PHASE_5_REPORT.md).
From the repository root, run `.venv/bin/python scripts/replay-research.py`; it needs no API key or
network and writes only to the separate, Git-ignored `data/research/phase5/` artifact store.
Predictions remain unavailable on the current real history: 0/30 baseline, 0/30 model episodes,
0/3 analogues. Next engineering phase is Phase 6, requiring separate authorization.

Hackathon Demo Stage 4 extends the explicit **DEMO SANDBOX** through Trust → Opportunity → Risk → synthetic Quote → Risk revalidation → unsigned Request Preparation → local constraint Simulation → Paper Fill → Position → synthetic Monitor/Exit → calculated P&L → ledger-derived Scorecard. Three synthetic scenarios use the unchanged Trust engine; economic targets/costs and financial risk limits are separate marked assumptions. Opt in with `RUNTIME_MODE=DEMO DATA_MODE=DEMO`; sandbox databases are disposable memory and analysis references are bounded in-memory caches. Production Trust and Opportunity remain blocked. The default `RUNTIME_MODE=LIVE` preserves the existing application path and does not enable live trading. See the [Stage 1 sandbox runbook](docs/DEMO_TRUST_SANDBOX.md), [Stage 3A core contracts](docs/DEMO_OPPORTUNITY_STAGE_3A.md) and [Stage 3B contracts, flow and verification](docs/DEMO_PREPARATION_STAGE_3B.md). These quotes/requests are synthetic, simulation is a local constraint check, and nothing is executable, signed or broadcast. The paper ledger is isolated in memory, idempotent within a DEMO backend session and cleared on restart. See the [Stage 4 paper lifecycle, runbook and evidence](docs/DEMO_PAPER_STAGE_4.md). No real funds move.

Canonical Phase 1 — Working Ask Flow is PASS for deterministic, non-executable exposure estimates and persisted DRY_RUN proposals. Engineering Stages 1/2 remain PASS. The backend implements dynamic Binance RWA discovery, market data, independent Massive equity/news adapters, a versioned U.S. calendar, exact Decimal normalization and isolated SQLite persistence. The frontend accepts stock budget requests and displays backend-authoritative estimates, issuer comparison, unknown costs and execution blockers. Canonical Phase 2 adds a separate deterministic analytical Trust endpoint/panel; its gate remains BLOCKED by unavailable real evidence. Production Opportunity scanning and live execution remain deferred. Master Phase 6 adds bounded, non-executable agents; see the current Phase 6 report.

**All LIVE execution is blocked.** The application rejects LIVE configuration even if a flag is set to true. Its ordinary runtime has no live order, broadcast, wallet mutation, portfolio or trading endpoints. DEMO paper APIs operate only on synthetic memory records.

## Product roadmap and engineering stages

Canonical product roadmap: Phase 0 — Reconnaissance; Phase 1 — Working Ask Flow; Phase 2 — Trust Layer; Phase 3 — Opportunity Mode; Phase 4 — Safety + Execution / remaining terminal capabilities. The master section 88 engineering stages and all later definitions remain unchanged; [PHASE_MAP.md](docs/PHASE_MAP.md) provides the complete mapping.

Engineering Stage 1 — Foundation and Engineering Stage 2 — Data Layer have passed. Foundation supports Canonical Phase 1; Data Layer supports Canonical Phase 1 and prepares Canonical Phase 2. **The current canonical milestone is Phase 1 — Working Ask Flow, PASS:** request parsing, exposure comparison, indicative result/route and persisted DRY_RUN proposal are verified. Vendor quotes and transaction simulation remain unavailable and never reported as successful. Canonical Phase 2 — Trust Layer is analytically implemented and software-verified, with TRUST_GATE=BLOCKED by current equity403, missing mandatory metrics/history and partial news. Production Canonical Phase 3 — Opportunity Mode must not begin before Trust completion and TRUST_GATE=PASS. Separately authorized DEMO Stage 3A demonstrates Opportunity/Risk core calculations using synthetic evidence, without advancing either production gate.

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

### Judge-facing DEMO SANDBOX

Start the existing backend with `RUNTIME_MODE=DEMO DATA_MODE=DEMO` (see the [DEMO UI runbook](docs/DEMO_UI_INTEGRATION.md) for the complete command), then run `npm run dev` from the repository root. Open <http://127.0.0.1:5173/#demo-sandbox> or select **DEMO SANDBOX** in navigation. NORMAL and LIKELY_NOISE show backend stand-down reasons; LIKELY_INFORMATION can proceed through the existing quote, preparation, local simulation, paper position/exit/P&L and scorecard stages. Every stage has an explicit status; React performs no financial calculations.

Overview's **Assess trust** remains the canonical assessment. The production Opportunity sidebar item remains disabled. In the ordinary runtime, the sandbox page explains that DEMO APIs are disabled and makes no fallback calls. Production gates and all live execution restrictions are unchanged.

### Master Phase 10: durable position machinery

The canonical lifecycle now persists positions, execution evidence, quantities, exit intents and monitor jobs in mode-separated SQLite stores under `data/positions/phase10/`. `GET /api/positions` and `GET /api/positions/{position_id}` inspect the local single-account records. They expose no write or execution operation. The existing DEMO paper ledger remains separate and synthetic.

`POSTOPEN_EXIT_MINUTES=10` schedules the deterministic exit after the first verified NYSE regular opening at or after confirmed entry. It accepts integer minutes from 1 to 120. A bounded startup recovery restores jobs and reconciles existing execution IDs; an expired lease can be reclaimed, while unresolved settlement blocks dependent preparation. Run the one-shot monitor from the repository root (a host scheduler may invoke it once per minute):

```sh
.venv/bin/python scripts/monitor-positions.py --limit 100
```

The monitor only reads existing status and records due exits. Fresh host-verified risk/funding/allowance facts are still required for exit preparation through the existing safety pipeline. Actual exits remain blocked; a quote or simulation does not close a position. Production refuses in-memory canonical storage. See the [Phase 10 report](docs/PHASE_10_REPORT.md) for evidence, recovery behavior and remaining live blockers. Phase 11 has not started.

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
| LLM_API_KEY | Reserved for explicitly injected LLM transport; excluded from agent inputs/output; CLI does not load it |

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

## Deterministic routing milestone

The Ask Flow now evaluates every discovered representation with the shared `RoutingService`, also used by the DEMO Opportunity and Quote adapters. The Route Comparison view exposes eligibility, ranking, rejection reasons and provenance. Verified complete costs use exact all-in cost per real share; missing costs produce a clearly labeled, non-executable price-only comparison. Opportunity routing additionally requires the existing Trust, Risk, liquidity and cost controls. No issuer or ticker is hardcoded as the winner.

See the [routing architecture, policy, examples and verification](docs/ROUTING_MILESTONE.md). Production Trust and Opportunity gates remain blocked; all live execution gates remain blocked. Existing DEMO fixtures, production historical coverage and the scheduled timestamp-alignment diagnostic are unchanged. Routing does not authorize execution.

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

DRY_RUN_GATE=PASS is scoped to verified indicative Ask estimates and non-executable proposals, with unavailable simulations failing execution readiness. REQUIRE_SIMULATION stays true; transaction simulation is UNAVAILABLE. All three LIVE blockers remain unresolved. The five legacy system-status fields report DATA/DRY_RUN PASS and three blocked LIVE gates; the separate Trust endpoint returns trust_gate=BLOCKED. Production Opportunity remains gated; the separately authorized synthetic Opportunity/Risk engine does not advance that gate.

See [Engineering Stage 2 Data Layer report](docs/PHASE_2_REPORT.md), [phase map](docs/PHASE_MAP.md), [architecture](docs/ARCHITECTURE.md), [API matrix](docs/API_MATRIX.md) and [execution gates](docs/EXECUTION_GATES.md). See [Canonical Phase 1 report](docs/PHASE_1_REPORT.md#canonical-phase-1--working-ask-flow) and [automated gate evidence](docs/evidence/CANONICAL_PHASE_1_GATE.json). See the [Canonical Phase 2 Trust report](docs/PHASE_2_TRUST_REPORT.md), [data contracts/policy](docs/DATA_CONTRACTS.md), [test matrix](docs/TEST_MATRIX.md) and [Trust gate evidence](docs/evidence/CANONICAL_PHASE_2_TRUST_GATE.json). Production advancement still requires Phase 2 data/capability remediation and Trust gate re-verification. The historical [DEMO Stage 3B](docs/DEMO_PREPARATION_STAGE_3B.md) stops after local synthetic simulation. The separately authorized [DEMO Stage 4](docs/DEMO_PAPER_STAGE_4.md) adds isolated paper fills, positions, synthetic exit/P&L and scorecards without advancing production gates.


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
