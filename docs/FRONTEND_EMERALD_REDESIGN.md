# Frontend emerald redesign — 10 October 2026

This increment changes frontend presentation and browser regression checks. It adds no financial engine, provider integration, execution capability or phase advancement. The starting branch was `main`, HEAD `be34929`. Existing uncommitted provider, event/calendar, configuration, Trust investigation and documentation work was preserved.

## Reference and inspected structure

The supplied Traders’ Society screenshot and complete HTML/CSS attachment were inspected before implementation. The visual system uses their near-black emerald background (`#060E0B`), mint accent (`#79EFCC`), off-white text (`#ECF2EE`), secondary text (`#B5BDB6`), fine green borders (`#26332C`), uppercase editorial hierarchy and restrained square panels. Existing system fonts replace an external font dependency. Unrelated branding, campus photographs, fabricated market snapshots and decorative financial charts were not imported.

The previous app used hash navigation, a sidebar, floating configuration widgets, a glass frame, health-backed metrics, a placeholder market chart and existing functional React workflows. API clients already supplied typed, backend-authoritative exposure, Trust, routing, scenario, quote, preparation, simulation, paper, portfolio, audit and terminal contracts. Those services and wire contracts remain intact.

## Result

- Shared slim navigation, workspace tools, connectivity status, editorial overview and consistent panels/forms/tables across existing pages.
- Overview reads the existing bounded `GET /api/terminal?limit=25&offset=0`, using the same query key and client as Markets. It does not refresh external providers or submit a proposal automatically. Reads require a verified backend and the existing non-live workflow gate.
- Comparison rows render backend decimal strings for token prices, normalized share costs, independent references and deviations. No frontend reference substitution, price normalization, signal classification or financial arithmetic was added.
- Coverage counts describe this page of records, not the whole market. Stored Trust coverage counts actual non-null assessment IDs, not fallback rows without an assessment. Synthetic freshness is explicitly relative to the illustrative clock.
- Trust summaries retain missing-evidence reasons and assessment age. Activity separates synthetic records, simulations and completed-trade flags. Provenance retains source identities, contracts, observation/availability timestamps, request/run IDs and digests.
- Ordinary UI uses “Research Lab,” “Illustrative data,” “Create exposure proposal,” “Prepare Unsigned Request” and “Run Local Simulation.” Raw runtime modes, phase numbers and startup environment commands were removed from normal dashboard headings/configuration cards. The empty hash now opens Overview; the existing `#demo-sandbox` deep link remains available.
- The Research Lab retains NORMAL, LIKELY_NOISE and LIKELY_INFORMATION through the original isolated services. Canonical Overview → Assess trust remains a separate, unchanged assessment call.
- Existing routes, filters, pagination, controls, expiry/cancellation handling, failure states, API clients and financial contracts are retained. The unused floating-widget/placeholder-chart component was removed.

## Truthful data presentation

Synthetic datasets remain clearly marked “Illustrative data” / synthetic inputs, not live market data. Paper positions and local constraint checks retain explicit no-real-funds/no-chain-simulation disclosures. Provider observations are labeled read only and cached, never automatically described as live. Per-row freshness, reference status, timestamps, rejection reasons and source data quality remain available. Source identifiers or instrument names containing `DEMO` and raw audit JSON are intentionally retained where they identify original evidence; they are not renamed to resemble real issuers or provider observations. Developer API examples and capability inspections retain their technical contracts.

Missing independent prices, normalized comparisons, liquidity, historical evidence, news feeds and opening schedules are not fabricated. Binance token/reference prices are not substituted for an independent equity reference. The overview has no price-history series because its existing snapshot API supplies none.

## Responsive and accessibility work

Desktop (1440 px), tablet (768 px) and mobile (390 px) reflow without page overflow. Wide financial tables remain in scroll regions, with keyboard access added to comparison/spread tables. Mobile navigation uses a labeled Menu button with `aria-expanded` and `aria-controls`; all existing destinations remain available. The skip link, semantic forms, focus rings, tabular numerals, contextual states and reduced-motion CSS/anchor scrolling are retained or improved. Screenshots were visually inspected. This is functional accessibility verification, not a claim of a complete WCAG certification or screen-reader audit.

## Verification

Run from the repository root:

```sh
npm test
npm run build
.venv/bin/python -m pytest -q
.venv/bin/ruff check backend scripts
PYTHONPATH=backend .venv/bin/python scripts/generate-ui-contracts.py --check
.venv/bin/python scripts/check-security.py
.venv/bin/python scripts/verify-frontend-phase15.py
```

- Frontend: **282 tests passed**, 15 files; all original 273 tests retained, with presentation selectors updated, plus nine overview/navigation tests.
- TypeScript and Vite production build: **PASS**. No dependencies added.
- Backend regression: **1,562 passed**, two existing malformed-allowance Pydantic serialization warnings.
- Ruff: **PASS**. The project has no separate frontend ESLint script.
- Seven generated Pydantic-derived frontend contracts: **PASS**, unchanged.
- Secret leakage / frontend isolation / environment ignore / container exclusion checks: **PASS**.
- Built Chrome regression: **PASS** against disposable, credential-free fixture backends. NORMAL and NOISE stand down; INFORMATION completes routing → quote → unsigned preparation → local constraints → paper fill → monitor → exit → backend P&L → scorecard on desktop and mobile. Exposure review, opportunity scans, portfolio/mandate views, audit links and failure recovery run on desktop/tablet/mobile. The unchanged simulation service also rejects the failing-risk fixture.
- Snapshot tests cover exact decimals, separate observation/availability times, partial/stale/missing references, empty/loading/error states, no fallback prices, data-mode mismatch, no automatic writes and mobile menu state. Browser checks cover source disclosures, stale rows, keyboard skip navigation, mobile menu expansion, reduced-motion styling, page overflow and existing service-error recovery.
- The Chrome harness separately records confirmed client-cancelled read-only snapshot requests during navigation. Only cancelled GET snapshots with a matching Chrome cancellation event are accepted; writes, application runtime exceptions and unexpected requests still fail.

The browser runner starts only its own local servers (8054–8057 and 5178), loads no project `.env`, uses in-memory/disposable databases and stops its processes afterward. It refuses occupied ports. Screenshots/evidence are written into the temporary directory reported by the runner. Historical reports/evidence were not overwritten. Separately invokable historical Ask/Trust/demo browser scripts received label/selector updates; this increment used the comprehensive isolated runner rather than executing those scripts against an existing local backend.

Final evidence: [browser record](evidence/FRONTEND_EMERALD_BROWSER_20261010.json), [desktop](evidence/FRONTEND_EMERALD_DESKTOP_20261010.png), [tablet](evidence/FRONTEND_EMERALD_TABLET_20261010.png), [mobile](evidence/FRONTEND_EMERALD_MOBILE_20261010.png), [mobile navigation](evidence/FRONTEND_EMERALD_NAVIGATION_20261010.png), [Markets](evidence/FRONTEND_EMERALD_MARKETS_20261010.png).

## Safety and limits

No backend, provider, environment, API service/contract, Trust threshold, risk rule or phase-gate file was changed by this increment. Starting tracked/untracked files were fingerprinted before work; existing files outside the frontend and the four browser check scripts remain byte-for-byte unchanged. No commit, push, branch switch or production database backfill occurred.

```text
EXECUTION_MODE=DRY_RUN
APPROVAL_MODE=PROPOSE_ONLY
LIVE_TRADING_ENABLED=false
REQUIRE_SIMULATION=true

DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

No live execution, signing, RFQ submission, swap submission, wallet mutation or allowance change was performed. Backend provider availability, freshness, historical 30/30/3 evidence, authoritative liquidity and execution-equivalence blockers remain unresolved by a frontend redesign. Event context and global next-opening information are not exposed by the current overview snapshot API. The Research Lab still requires the isolated scenario runtime; the ordinary runtime shows an explicit unavailable state. Financial tables intentionally scroll inside their regions on small screens. No new chart series or invented financial values were added.

## Files changed by this increment

New:

- `frontend/src/components/DataContext.tsx`
- `frontend/src/components/MarketSnapshot.tsx`
- `frontend/src/test/MarketSnapshot.test.tsx`
- `docs/FRONTEND_EMERALD_REDESIGN.md`
- `docs/evidence/FRONTEND_EMERALD_BROWSER_20261010.json`
- `docs/evidence/FRONTEND_EMERALD_DESKTOP_20261010.png`
- `docs/evidence/FRONTEND_EMERALD_TABLET_20261010.png`
- `docs/evidence/FRONTEND_EMERALD_MOBILE_20261010.png`
- `docs/evidence/FRONTEND_EMERALD_NAVIGATION_20261010.png`
- `docs/evidence/FRONTEND_EMERALD_MARKETS_20261010.png`

Updated:

- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/src/components/AgentApi.tsx`
- `frontend/src/components/AskFlow.tsx`
- `frontend/src/components/DemoOpportunityFlow.tsx`
- `frontend/src/components/DemoPaperFlow.tsx`
- `frontend/src/components/DemoPipeline.tsx`
- `frontend/src/components/DemoPreparationFlow.tsx`
- `frontend/src/components/DemoTrustSandbox.tsx`
- `frontend/src/components/ProposalReview.tsx`
- `frontend/src/components/RouteComparison.tsx`
- `frontend/src/components/ScorecardAudit.tsx`
- `frontend/src/components/Terminal.tsx`
- `frontend/src/components/TrustEvidence.tsx`
- `frontend/src/components/TrustPanel.tsx`
- `frontend/src/components/WorkspaceViews.tsx`
- `frontend/src/test/App.test.tsx`
- `frontend/src/test/AskFlow.test.tsx`
- `frontend/src/test/DemoOpportunityFlow.test.tsx`
- `frontend/src/test/DemoPaperFlow.test.tsx`
- `frontend/src/test/DemoPreparationFlow.test.tsx`
- `frontend/src/test/DemoTrustSandbox.test.tsx`
- `frontend/src/test/DemoUiIntegration.test.tsx`
- `frontend/src/test/Routing.test.tsx`
- `frontend/src/test/ScorecardAudit.test.tsx`
- `frontend/src/test/Terminal.test.tsx`
- `scripts/check-ask-browser.mjs`
- `scripts/check-demo-ui.mjs`
- `scripts/check-frontend-phase15.mjs`
- `scripts/check-trust-browser.mjs`

Removed: `frontend/src/components/DashboardVisuals.tsx` (unused health widgets and placeholder chart).

Stop condition: this frontend increment only. No backend feature or phase was started.
