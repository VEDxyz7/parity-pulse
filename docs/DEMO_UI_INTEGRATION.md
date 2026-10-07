# Final DEMO UI integration

Status: PASS for the isolated judge-facing frontend pipeline. Verified 2026-10-07. No commit made.

## Scope and architecture

The backend already supplied every required DEMO stage; no backend change was necessary. Existing `DemoTrustSandbox`, `demoSandbox`, `DemoOpportunityFlow`, `DemoPreparationFlow`, `DemoPaperFlow`, their strict response parsers and `RouteComparison` are reused. The frontend orchestrates existing APIs and displays their validated outcomes. It contains no new prices, ratios, financial calculations, selection rules, classification rules or risk thresholds.

`App.tsx` adds a dedicated hash view at `#demo-sandbox`, with a visible sidebar entry and Overview callout. No routing dependency was added. A verified DEMO runtime opens this view on an otherwise empty URL; `#overview` returns to Overview. The Overview Trust component/client is unchanged. Production Opportunity and Autopilot sidebar buttons remain disabled. Skip-to-main preserves the selected view and moves keyboard focus correctly.

The page displays **DEMO SANDBOX**, **SIMULATED DATA — NOT LIVE MARKET DATA** and **NO REAL FUNDS WILL MOVE**. Scenario buttons select the existing catalog's NORMAL, LIKELY NOISE and LIKELY INFORMATION fixtures. Selection does not run analysis automatically.

`DemoPipelineContext` carries presentation-only events from the existing components. It displays `pending`, `running`, `pass`, `rejected` or `failed` for Trust, Opportunity, Risk, Routing, Quote, Preparation, Simulation, Paper Execution, Position, Monitor, Exit, P&L and Scorecard. Status details come from validated API responses; they are recorded outcomes, not financial decisions or gate approval. Routing is already returned by the Opportunity and Quote APIs, so there is no separate routing request. Position/P&L are already returned by paper lifecycle responses, so no duplicate fetch or calculation is added.

Each existing action remains explicit. The frontend never automatically fills/exits a paper position. Scenario changes clear prior results/status and abort outstanding requests. Leaving the page aborts analysis. Failed requests show sanitized errors and permit the existing safe retry behavior. The backend's expiry, identity binding, simulation, idempotency and paper safeguards remain authoritative and unchanged.

## Judge runbook

Use the existing port-conflict/startup instructions before replacing a development server. Do not start two backends on port 8000, and do not terminate an unrelated listener. From the repository root, start the existing backend in its isolated DEMO runtime:

```sh
RUNTIME_MODE=DEMO DATA_MODE=DEMO EXECUTION_MODE=DRY_RUN APPROVAL_MODE=PROPOSE_ONLY LIVE_TRADING_ENABLED=false REQUIRE_SIMULATION=true .venv/bin/python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
```

In another terminal, from the repository root:

```sh
npm run dev
```

Open <http://127.0.0.1:5173/#demo-sandbox>. These APIs are registered only by the existing `RUNTIME_MODE=DEMO` backend. The ordinary runtime shows a sandbox availability message and setup instructions; it does not fetch DEMO data, call canonical Trust as a substitute or change backend settings. An unavailable/unverified backend cannot run the sandbox.

1. Select NORMAL, run the scenario, then Analyze Opportunity. Trust reports NORMAL, Opportunity reports NO_OPPORTUNITY and Routing reports NO_ROUTE. The stop message shows actual backend reasons. An explicit Risk check returns FAIL; Quote and paper stages remain unrun.
2. Select LIKELY NOISE and repeat. Trust reports LIKELY_NOISE, Opportunity reports REJECTED_BY_TRUST and Routing reports NO_ROUTE. The reason and stand-down path remain visible.
3. Select LIKELY INFORMATION and run the scenario. Analyze Opportunity → Analyze Risk → Generate DEMO Quote → Prepare DEMO Transaction → Run DEMO Simulation → Create Paper Fill → Monitor Synthetic Opening Observation → Exit Paper Position → View Paper Scorecard. Existing components expose routing, position lifecycle and backend-calculated P&L along the way.

The hero scenario produces ACTIONABLE, Risk PASS, ROUTE_SELECTED, QUOTED, PREPARED, SIMULATION_PASS, PAPER_FILLED, OPEN, EXITED and ledger-derived Scorecard. Its currently supplied synthetic fixture returns net PAPER P&L `1.45335603303197526425600` USD and return `2.898018012027866929`%; these are existing backend outputs, not market results or React calculations. NORMAL/Noise never offer quote/preparation/paper actions.

The session-only paper ledger clears on backend restart. Returning to Overview unmounts the view and clears its local display; existing backend paper records are retained for that session. No portfolio restore/list capability was added. Quotes/analyses retain existing expiry constraints; rerun analysis when expired.

## APIs invoked

| Method | Existing endpoint | Purpose |
|---|---|---|
| GET | `/api/health`, `/api/system-status` | Verify connected runtime and unchanged execution configuration |
| GET | `/api/demo/trust/scenarios` | Fetch the marked synthetic scenario catalog |
| GET | `/api/demo/trust/scenarios/{id}` | Run the existing DEMO Trust service |
| POST | `/api/demo/opportunity` | Existing Opportunity/Routing result, bound by Trust assessment ID |
| POST | `/api/demo/risk` | Existing Risk result, bound by Opportunity ID |
| POST | `/api/demo/quote` | Existing quote, Risk revalidation and fresh RouteDecision |
| POST | `/api/demo/prepare` | Existing unsigned synthetic request preparation |
| POST | `/api/demo/simulate` | Existing local DEMO constraint simulation |
| POST | `/api/demo/paper/fills` | Existing isolated, idempotent paper fill and position |
| POST | `/api/demo/paper/positions/{id}/monitor` | Existing explicit synthetic observation |
| POST | `/api/demo/paper/positions/{id}/exit` | Existing paper exit, lifecycle and calculated P&L |
| GET | `/api/demo/paper/positions/{id}/scorecard` | Existing ledger-derived scorecard |

Only Overview's explicit **Assess trust** calls `GET /api/assets/NVDA/trust`. Sandbox never calls it. No provider execution, SWAP, RFQ, wallet, order submission or broadcast endpoint is invoked. Paper APIs represent only isolated synthetic records.

## Verification

- All **510 backend tests PASS**, with all backend code/tests unchanged. The existing Starlette test-client deprecation warning remains.
- All **173 frontend tests PASS**, retaining all 165 existing tests and adding 8 integration tests for scenarios, hero flow, navigation, pending/running/rejected/failed statuses, cancellation, safe retry, ordinary-runtime availability and canonical Overview regression.
- TypeScript typecheck and Vite production build PASS; existing Ruff check/format and security audits PASS.
- Desktop 1440px and mobile 390px built-app checks PASS using actual isolated local backends. All six scenario runs pass; Information traverses every stage through Exit, P&L and Scorecard. No page overflow or browser runtime errors; 39 allowlisted local API responses succeed. Sandbox performs zero canonical Trust calls. A separate ordinary-runtime check explicitly calls canonical Trust and observes INSUFFICIENT_EVIDENCE, with no DEMO fallback requests.
- Baseline hashes verify every backend file, existing test/fixture, gate document, historical evidence, saved timestamp-alignment setup and all eight existing database files remain unchanged. No real historical observation/episode or provider request was added.

[Browser evidence](evidence/DEMO_UI_BROWSER.json) and [final preservation/security evidence](evidence/DEMO_UI_VERIFICATION.json) record the measured scope. New frontend fixtures were captured directly from existing APIs using an isolated memory DEMO app with `_env_file=None`; they are explicitly synthetic, not real Trust coverage.

### Repeat the browser audit

`scripts/check-demo-ui.mjs` uses a disposable local headless Google Chrome profile on macOS and Node 22.12+. Build with `npm run build`. Serve `frontend/dist` using a local static server on port 5174. Start three separate temporary backends on 8011, 8012 and 8013, each with `DATABASE_URL=sqlite:///:memory:`, `DATA_MODE=DEMO`, `EXECUTION_MODE=DRY_RUN`, `APPROVAL_MODE=PROPOSE_ONLY`, `LIVE_TRADING_ENABLED=false`, `REQUIRE_SIMULATION=true`. Use `RUNTIME_MODE=DEMO` for 8011/8012 and `RUNTIME_MODE=LIVE` for 8013; **LIVE here names the ordinary application runtime, while data stays synthetic and execution stays blocked**. Fresh 8011/8012 sessions are needed for repeatable paper-ledger checks. Do not use user/production services for this audit.

Run `node scripts/check-demo-ui.mjs` from the repository root. Its browser interceptor forwards only allowlisted existing APIs to the isolated backends, records method/path/status without bodies or credentials, rejects unexpected requests and verifies execution flags. It opens a fresh document when switching to the ordinary test backend so the prior DEMO status cache cannot affect the regression check. Screenshots go to the OS temporary directory. The browser/profile is cleaned up; stop only the temporary servers you started afterward.

## Files changed

Modified: `README.md`; `frontend/src/App.tsx`; `frontend/src/components/DemoTrustSandbox.tsx`; `frontend/src/components/DemoOpportunityFlow.tsx`; `frontend/src/components/DemoPreparationFlow.tsx`; `frontend/src/components/DemoPaperFlow.tsx`; `frontend/src/styles.css`.

Created: `frontend/src/components/DemoPipeline.tsx`; `frontend/src/test/DemoUiIntegration.test.tsx`; `frontend/src/test/demoUiFixtures.json`; `scripts/check-demo-ui.mjs`; `docs/DEMO_UI_INTEGRATION.md`; `docs/evidence/DEMO_UI_BROWSER.json`; `docs/evidence/DEMO_UI_VERIFICATION.json`.

## Production state preserved

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

Trust/Opportunity/Risk/Routing rules, all production thresholds and gates, financial calculations, simulation/equivalence requirements and wallet restrictions are untouched. Synthetic success does not resolve any real-provider/history/execution blocker. No commit made. STOP after this UI integration milestone.
