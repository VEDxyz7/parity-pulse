# UI polish — implementation checklist and evidence

Scope: refinement of the existing landing page, scenario workspace and provider workspace.
Branch `main`; substantial uncommitted execution, provider, presentation and landing work
exists and must be retained. No Git reset/stash/clean, commit, push or deployment.

## Continuation and primary visual reference

The continuation audit confirmed the shared buttons, ambient background, wordmark,
historical charts, seven pages and their existing workflows were already implemented.
They were reused. The final user-supplied multi-page Parity Pulse mockup is the primary
visual reference for composition, hierarchy, colors and density; none of its prices,
liquidity, holdings or performance figures are application inputs.

`docs/MASTER_SPEC.md` was read completely, all 5,321 lines, before the final reference
adjustments. Its financial, provider, workflow and safety requirements remain intact.
Its hash is recorded in the retained evidence manifest.

Screenshot comparison identified excessive workspace heading/hero spacing as the largest
remaining visual difference. Final changes tighten the shared scenario shell, reduce
headline size, place Overview metrics before the retained hero/chart, expand chart priority,
and use bordered translucent metric cards and compact table rows across the seven sections.
The original landing composition and architectural hero photograph remain. A portfolio
valuation qualifier now explicitly identifies modeled scenario holdings.

The mockup's second independently sourced token chart, liquidity figures, wider asset
universe, account avatar and performance curve are not reproduced as capabilities:
unverified token history/liquidity remain qualified, the actual supported universe is used,
and scorecard filters/records retain their real backend-derived fixture evaluations.

Final browser evidence, request logs, **35 screenshots**, test/build logs and hashed
manifest are retained in [ui-polish-2026-10-11](evidence/ui-polish-2026-10-11/manifest.json).
Screenshots include all seven pages at desktop/tablet/mobile, selected asset detail at each
size, paper landing/static/context-loss, and provider workspace examples. The final run
also asserts metric/chart order and desktop terminal density. Screenshots were inspected
and compared against the visual reference; observed data and existing workflows stay
distinct from the illustrative mockup.

## Inspection

- Two existing workspace entry points: presentation by default; `?workspace=verified`
  selects the provider app. Existing hash routes and scenario APIs stay intact.
- Default presentation values are backend-derived synthetic fixtures: Atlas/Meridian,
  NVDA/AAPL, fixed October 6 clock, modeled holdings and 60 fixture evaluations.
- Repeated $5,000 liquidity is the shared synthetic Trust fixture's USD assumption,
  not measured executable market liquidity. Qualify it consistently rather than inventing
  venue measurements or changing routing inputs.
- The existing history interpolates synthetic values. Remove that visual from financial
  screens; use separate verified historical equity bars where available. Never normalize
  a real historical token series with today's scenario ratio.
- Workspace refresh GET returns cached deterministic scenarios. Add read-completion and
  unchanged-data feedback; do not claim provider refresh or create random changes.
- Existing dependencies: React 19, Vite 8, Three.js, Lucide, TanStack Query. No chart or
  shader-button library. Reuse SVG for charts and CSS for metallic/ambient treatments;
  avoid additional WebGL contexts. Add only pinned official GSAP for short route reveals.

## Checklist

- [x] Shared tokens, semantic button variants, focus/loading/disabled/reduced-motion.
- [x] Persistent ambient CSS gradient, visibility/low-power/static fallback.
- [x] Small GSAP route entrance with cleanup; no scroll hijacking.
- [x] Preserve landing composition; complete wordmark and metal entrance.
- [x] Historical chart with UTC axes, keyboard/touch/pointer tooltip and provenance.
- [x] Explain liquidity, scenario evidence, portfolio and scorecard units.
- [x] Search, selected-representation state and refresh feedback.
- [x] Regression, build/type, lint/security and API contract checks.
- [x] Actual desktop/tablet/mobile browser journeys and screenshot inspection.

## Delivered refinement

- **Landing:** original paper, composition, headline, background wordmark, drag/hover,
  native scroll transition and entry navigation retained. Full PARITY PULSE replaces
  P. in both the rendered texture and static fallback. Entrance uses the shared dark
  emerald metallic pill. Ambient dashboard layer hides/pauses while the landing is active.
- **Overview:** real historical equity chart replaces the interpolated fixture curve.
  Model share economics remain explicitly separate. Episode count is labelled scenario
  episodes; portfolio is modeled. Refresh records read time and unchanged-input feedback.
- **Markets:** shared chart follows the selected underlying; token history is not invented.
  Search also matches token symbols, selected rows are highlighted, inspect/reassess and
  route comparison stay functional. Ratio header states shares/token. Liquidity values
  retain their actual fixture values with scenario USD assumption labels.
- **Trust & Signals:** evidence grid, reason details and badges retain backend outcomes.
  Baseline/analogue counts and the freshness clock explicitly belong to scenarios.
  Confidence is heuristic, not a probability. Modeled reference, 24h USD volume,
  persistence, risk checks and proposal costs remain backend-derived.
- **Opportunities:** mandate, universe, session filters, ranking policy, proposal/stand-down
  inspection and shared router retained; cleaner controls/table/status hierarchy. No
  production gate bypass or new opportunity rules.
- **Portfolio:** allocation, issuer/sector holdings, drift and exposure comparison retain
  backend calculations. Basis is assumed; mark-to-basis P&L is modeled/unrealized. Suggested
  adjustments are proposals, not transactions. Filters do not recalculate headline totals.
- **Research Lab:** responsive input grid, shared buttons, pin/current comparison and
  reset workflows; explicit scenario assumptions and bounded in-memory persistence.
- **Scorecard:** filters, outcome records and decision traces retained. Synthetic fixture
  counts/agreement remain descriptive, not production backtest or predictive validation.
- **Provider workspace:** original API/service contracts and workflows preserved, with
  shared button/surface/navigation treatments and read feedback for status, Terminal,
  market snapshot, portfolio/settings workspace, scorecard and audit. Material gate,
  source, wallet and settlement limitations remain accessible.

## Shared interaction and performance design

`Button` preserves native form/button semantics and handlers. Primary/secondary/outline,
icon/compact/destructive variants support focus, pressed, disabled and loading states.
`MetalLink` preserves anchor navigation. Reflective layered CSS gradients and a bounded
pointer ripple adapt the supplied liquid-metal reference; no shader-button package or
additional GPU context is needed. Retained native links also share primary button styling.

Central tokens cover palette, surface, spacing, radii, shadows and motion.
`AmbientBackground` is one persistent, pointer-transparent CSS gradient/grain layer:
compositor transforms only, no JS animation loop or WebGL context. Reduced motion,
Save-Data/low-core devices and missing motion APIs use the static treatment. Document
visibility pauses motion; listeners clean up. Landing retains its specialized renderer.

Pinned GSAP 3.13.0 is lazy loaded for a short heading translation only; financial content
is never hidden pending animation. Contexts revert on route changes/unmount; reduced
motion, visibility and failed chunk loading retain static usable content. No ScrollTrigger,
scroll hijacking or new WebGL loop. Existing paper renderer cleanup and fallbacks retained.

Read refresh uses an in-flight guard, visible completion/error state and UTC receipt time.
It never claims provider observations updated. Scenario refresh re-reads cached deterministic
inputs without random changes. Section navigation starts at its heading. Skip navigation
focuses main content without mutating the financial page hash. Tables have keyboard-focusable
scroll regions and small-screen scroll hints rather than compressing all columns.

## Historical data and credibility

Actual capture: `data/display/equity-history.json`; bounded manifest/hash in
`docs/evidence/UI_HISTORY_CAPTURE.json`.

- Source: existing authenticated **Alpaca** read-only client/provider.
- Endpoint: `GET https://data.alpaca.markets/v2/stocks/bars`.
- Request: NVDA/AAPL, `5Min`, `feed=sip`, `adjustment=raw`, `asof=-`, `currency=USD`.
- Window: October 5 00:00 UTC through October 10 00:00 UTC exclusive, 2026.
- Returned/validated: **390 bars per ticker**, 78 per day for October 5–9.
- First bar: October 5 **13:30 UTC**; last: October 9 **19:55 UTC**.
- Session: America/New_York regular 09:30–16:00, UTC 13:30–20:00; times mark bar starts.
- No missing five-minute bars within the five captured regular sessions.
- Captured October 11, 2026 at **02:48:47 UTC**. Raw unadjusted prices; historical revision
  as-of is unverified. SIP is the requested feed; it is not independently certified here.
- SVG draws observed closes on actual timestamp/USD axes, breaking overnight or >5m
  gaps. Pointer/touch selection and a labelled native keyboard range expose observed
  time/price; resize uses one cleaned-up observer. No fabricated token line or current-ratio
  historical normalization. The historical close readout comes from those same bars.

The additive `/api/display-history/{ticker}` endpoint reads only this bounded, validated
local artifact. It cannot refresh providers, write databases, admit a Trust reference,
change a gate or execute. Unsupported ticker, corrupt capture, duplicate bars, wrong
identity/feed/quality/session, missing time/close or oversized input fail to empty history.
`production_reference_eligible=false` is invariant. Missing captures show an explicit
historical-series-not-captured state, never the old interpolated curve.

**Repeated $5,000:** inspected source is the existing synthetic Trust fixture's liquidity
USD assumption, reused across fictional model representations. It is neither measured
pool liquidity nor executable size/depth. Values are retained for unchanged engine inputs
and qualified in tables, detail metrics, research assumptions and route/proposal copy.
Scenario prices/ratios/news/volumes/costs/holdings and 60 evaluations remain isolated.
No captured equity bar contributes to the production 30/30/3 evidence requirement.

## Reproduction

From repository root (credentials remain in the existing local backend environment):

```sh
# Optional bounded read-only recapture: at most four historical GETs, no DB writes.
PYTHONPATH=backend .venv/bin/python scripts/capture-display-history.py
# Normal application, in separate terminals:
.venv/bin/python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
npm run dev
# Verification:
.venv/bin/python -m pytest
npm test
npm run build
.venv/bin/ruff check backend scripts
PYTHONPATH=backend .venv/bin/python scripts/generate-ui-contracts.py --check
.venv/bin/python scripts/check-security.py
.venv/bin/python scripts/verify-frontend-phase15.py
# Focused scenario/landing rerun:
.venv/bin/python scripts/verify-frontend-phase15.py --presentation-only
```

New display data is optional at runtime; removal cannot silently create a replacement
curve. Refresh does not recapture provider history. Configure only existing backend
`ALPACA_API_KEY` and `ALPACA_SECRET_KEY` for recapture; never expose them in Vite.

## Validation and visual review

- Full backend: **1,834 passed**; continuation rerun in 68.02 seconds. Two existing malformed negative-fixture
  Pydantic serializer warnings; no failures. New display validation/closed-route tests
  cover corruption, duplicate/promotion, timestamp, identity, session and missing-price cases.
- Full frontend: **312 passed**, 18 files. New chart/keyboard/gap/provenance/failure,
  button/loading/non-submission, ambient fallback/cleanup, refresh duplicate/unchanged,
  token search/liquidity labelling and skip-link coverage. Existing tests preserved.
- Typecheck + production build, Ruff, scoped new-file formatting, twelve generated wire
  contracts, credential/bundle isolation scan and `git diff --check`: **PASS**.
- Final reference-adjusted rerun: **312 frontend tests passed**, TypeScript/build passed;
  provider browser six scenarios / 189 local API requests, scenario browser three journeys /
  31 requests, landing six journeys / 17 requests; zero execution requests and zero runtime
  errors. The harness stopped all five owned servers and touched no unrelated process.
- Final development smoke: frontend 5173, backend health/system status and Vite-proxied
  historical display returned HTTP 200. Runtime independently reports DRY_RUN,
  PROPOSE_ONLY, LIVE_TRADING_ENABLED=false and REQUIRE_SIMULATION=true; its three LIVE
  gates remain BLOCKED. See `evidence/ui-polish-2026-10-11/development-smoke.json`.
- Built UI uses actual isolated fixture backend calculations, with only allowlisted local
  API traffic. Provider workspace, all seven scenario pages, research normal/noise/news,
  custom price normalization, quote/local simulation, routing, portfolio filters,
  scorecard traces, refresh/reload and back/forward tested in Chromium.
- Desktop **1440×1100**, tablet **820×1180**, mobile **390×844** workspace journeys.
  Landing additionally covers short/compact phones and landscape (six sizes), drag/hover,
  touch scroll, keyboard entry, reduced motion, visibility pause/resume, WebGL failure
  and actual context loss. No execution request or external browser request.
- Actual screenshots of all seven scenario pages across the three sizes were inspected,
  including chart detail and provider workspace examples. Visual review caught/fixed
  ambient-layer occlusion of the landing, CTA position override, desktop mobile-menu
  visibility, mobile header insets and tablet metric spacing. Assertions were added for
  landing/background separation and section scroll restoration.
- Local development backend identity was verified and gracefully restarted to load the
  new read-only route (PID 96277 → 3085). Vite PID 86767 retained. Health/system status and
  both history endpoints return 200 on 8000; Vite proxy history returns 200 on 5173.
  Restart clears ephemeral scenario studies; persisted files/databases were not reset.
  See `docs/evidence/UI_DEVELOPMENT_SERVER.json`.

## Limitations and unchanged authority

- Historical equity only; no independently verified historical token/equity pair. Scenario
  financial inputs remain modeled and cannot be interpreted as current investment evidence.
- Historical revision as-of and public redistribution rights were not established; local
  authorized data retrieval is not a public-data redistribution entitlement.
- Headless landing uses software WebGL2 (SwiftShader); hardware/mobile battery/FPS performance
  was not measured. Static CSS ambiance introduces no extra renderer. Existing Vite warning
  remains: entry ~861 kB and optional Three.js chunk ~530 kB uncompressed. GSAP chunk ~69 kB
  lazy loaded. No bundle-size warning is suppressed.
- Scenario studies remain memory-bound/cleared on restart. No new persistence or financial
  engine is introduced. Live wallet/runtime and execution-equivalence blockers remain.

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

No Trust/Risk/Routing thresholds, provider reference selection, consent, simulation,
signing/broadcast/settlement rules, gates or execution modes changed. No secrets printed,
production observations backfilled, orders submitted, transactions signed/broadcast,
funds moved, commits, pushes, merges or deployments. Existing dirty work retained.

## Files in this UI increment (pre-existing unrelated changes excluded)

- Shared UI: `frontend/src/ui/{Button,ReadRefresh,AmbientBackground,HistoricalChart}.tsx`,
  `useRouteMotion.ts`, `design-system.css`, `polish.css`.
- Shells: `frontend/src/{main,App,PresentationApp}.tsx`.
- Landing: `frontend/src/landing/{LandingEntrance,PaperScene}.tsx`, `paperTexture.ts`.
- Retained workflow button/read integrations: `frontend/src/components/{AgentApi,AskFlow,
  DemoOpportunityFlow,DemoPaperFlow,DemoPreparationFlow,DemoTrustSandbox,MarketSnapshot,
  OpportunityView,ProposalReview,ScorecardAudit,Terminal,TrustPanel,WorkspaceViews}.tsx`.
- Generated display contract: `frontend/src/types/backend.generated.ts`,
  `frontend/src/services/backendSchemas.json`, `scripts/generate-ui-contracts.py`.
- Historical display: `backend/app/{api,models,services}/display_history.py`, additive
  router registration in `backend/app/main.py`, `scripts/capture-display-history.py`,
  `data/display/equity-history.json`.
- Tests: `backend/tests/unit/test_display_history.py`, explicit read-only route entry
  in `backend/tests/security/test_boundaries.py`, `frontend/src/test/{PresentationApp,
  UiPolish}.test.tsx`, `historyFixture.json` (three actual captured bars for geometry tests).
- Browser checks: `scripts/check-{presentation,landing}-browser.mjs`.
- Dependency: `frontend/package.json`, root `package-lock.json` (only pinned GSAP added
  in this increment; earlier dependency/remediation work retained).
- Docs: `README.md`, this report, appended follow-up to `docs/PRODUCTIZATION_REPORT.md`,
  `docs/evidence/UI_{HISTORY_CAPTURE,DEVELOPMENT_SERVER}.json` and UI browser evidence.
