# Premium reference redesign

Completed October 11, 2026 (Asia/Kolkata). Frontend presentation increment on
the existing `main` working tree; all previous uncommitted work preserved.

## Reference and integration

Inspected both supplied images in `frontend/`: `PHOTO-2026-10-11-01-22-52.jpg`
is the building photograph, and `PHOTO-2026-10-11-01-51-22.jpg` is the target
dashboard composition. The original photograph already exists byte-for-byte
in `src/assets/parity-pulse-architecture.jpg`; it remains the only bundled
image. The reference screenshot is not used as application content.

The existing React/Vite application, hash routes, clients, refresh policy,
decimal strings, provenance and downstream services are retained. Changes:

- `frontend/src/App.tsx`: balance the observation desk against the editorial
  headline; display the market workspace's unavailable state even when the
  backend cannot be verified. Existing actions, navigation and Trust flow remain.
- `frontend/src/components/MarketSnapshot.tsx`: compact four-metric strip;
  two-column observations/trend composition; reference/alignment details and
  source records retained in accessible disclosures; functional View all link.
  No market request runs without a verified mode and existing dry-run gate.
- `frontend/src/styles.css`: refined shared navigation typography, lighter
  hero typography, more visible warm architecture, rounded observation desk,
  compact vertical metric separators, denser right-aligned numeric table cells,
  subtle empty trend grid and responsive analytical layout.
- `frontend/src/test/MarketSnapshot.test.tsx`: three additional tests for the
  unverified-mode/no-request state, bounded counts and missing trend honesty.
  All existing tests and evidence checks remain intact.

Other routes retain their existing functional components and analytical
surfaces, using the shared navigation/palette. No new financial engine, chart
library, provider, API request type or dependency is introduced.

## Data semantics and limitations

- Tracked Assets counts distinct underlying tickers in the returned bounded
  snapshot, not the provider's full universe. Pagination limitations remain.
- Eligible Observations counts only rows classified `ANALYTICAL_ONLY` by the
  backend. It does not confer Trust verification, trade eligibility or approval.
- Largest Verified Deviation is explicitly unavailable: the snapshot supplies
  no verified aggregate. Individual backend decimal values remain unchanged.
- Data Freshness summarizes backend freshness classifications; synthetic
  clocks are identified. It never treats snapshot generation time as quote age.
- The API does not expose an aligned token/equity historical series. The
  Deviation Trend panel is an explicit empty state with no fabricated line,
  numerical axes, series or asset selector. Replay episodes and isolated
  current observations are not repurposed into a trend.
- Global US session/next opening remains unavailable in the observation desk;
  existing per-asset market classifications remain accessible.
- The Vite development backend was unavailable during preview. Amber service
  warnings and unknown data states remained visible. Browser regression used
  isolated synthetic fixture backends, not current market data.

## Validation actually performed

- Visually inspected rendered Vite screenshots at desktop 1440 × 1100,
  tablet 768 × 1024 and mobile 390 × 844, plus the full mobile hero.
- Inspected built-UI fixture screenshots of Overview, Markets, proposal/Trust
  review, Opportunities, Portfolio and Research Lab.
- `npm test`: **285 tests passed**, 15 files (282 existing + 3 new).
- `npm run build`: TypeScript and Vite passed.
- `.venv/bin/ruff check backend scripts`: passed. No frontend lint script exists.
- `.venv/bin/python scripts/check-security.py`: passed.
- `PYTHONPATH=backend .venv/bin/python scripts/generate-ui-contracts.py --check`:
  all seven contracts unchanged.
- `.venv/bin/python scripts/verify-frontend-phase15.py`: passed; 36 workspace
  journeys, six scenario runs, 189 local API requests, zero runtime errors,
  zero external browser requests and zero live execution calls. Includes
  desktop/tablet/mobile overflow checks, keyboard navigation, reduced motion,
  failure/recovery, ordinary Trust rejection and disabled execution controls.
- `git diff --check`: passed. Before/after file fingerprints verify that no
  backend, provider, contract, gate/configuration or unrelated file was changed
  by this increment. Backend regression was not rerun because none were touched.

Evidence is saved under `docs/evidence/PREMIUM_UI_*_20261011.*`; fixture-labelled
screenshots contain illustrative data. The development preview is reproduced
with `npm run dev` from the repository root, then `http://127.0.0.1:5173/#overview`.
The browser regression command above creates and stops its own credential-free
servers and Chrome profile and refuses occupied test ports.

All backend data logic, reference admission, Trust/Opportunity criteria,
execution settings, wallet restrictions and safety gates are unchanged.
No transactions, swaps, RFQs, signatures or approvals submitted.
No commit, push, branch switch or phase advancement.
