# Hackathon product workspace

## Scope and preservation

Continued the existing presentation models/API/service rather than replacing them.
The initial adapter had a mismatched economics field, incomplete ratio remapping,
and no frontend integration. These are completed with new tests and real browser journeys.
No branch change, merge, pull, reset, stash, commit or push. The checkout remains on
`main` at `9b6368c`; the pre-existing execution-remediation changes remain in place.
The separate prepared PR resolution was not modified or imported.

## Integration

`PresentationService` is the single offline data owner. It accepts no Settings,
provider transport, wallet, production repository or execution gateway. The only
application wiring additions are its isolated state and `/api/presentation` router.
Each Trust assessment uses the existing `DemoTrustSandbox` and an ephemeral SQLite
memory database. All fixture records retain DEMO/synthetic/as-of identity markers;
the outer envelope adds `PRESENTATION_SCENARIO`, `production_eligible=false`,
`execution_ready=false`, and `transaction_broadcast=false`.

The adapter maps existing fixture episodes and preceding observations into explicit
fictional Atlas/Meridian model identities for the existing supported NVDA/AAPL universe.
It does not claim actual token discovery, issuer metadata, current ratios or pool liquidity.
Model share ratios (0.5/1) apply only to those fictional identities and historical scenario
inputs. They are never backfilled onto real token observations.

TrustService, TrustClassifier, baseline/analogue rules and 120-second/30-second/30/30/3
requirements are unchanged. OpportunityEngine, RiskEngine, RoutingService,
QuoteService, TransactionBuilder and SimulationService calculate the results.
Opportunity ordering uses the existing `ranked` lexicographic policy; no hidden weights
or LLM scoring. Exposure comparison uses the same router over both representations.
Normal and noise scenarios stand down; unsupported combinations remain insufficient.
Reopening studies are explicitly rejected pending opening-model evidence, regardless
of the regular-session fixture classification. A larger budget does not raise the
existing position limits: proposal size is capped at $50 and checked by RiskEngine.

The new default React workspace renders typed, schema-validated API responses.
It shares existing styling and the architectural photograph. Existing `App` and its
provider/operations functionality are retained at `?workspace=verified`.
The canonical browser suite targets that explicit workspace with every original
assertion preserved; the additional browser suite tests the default product workspace.

## Calculations and provenance

- Clock: modeled regular session, **6 October 2026 16:00 UTC**, visibly labelled.
  Freshness/alignment evidence is evaluated at that scenario clock, not wall-clock LIVE.
- Price histories: 48-point deterministic modeled paths ending at the exact market
  snapshot. Backend-normalized effective prices are displayed in the charts.
  These paths are not historical provider candles or empirical calibration samples.
- Scenario equity/reference prices, liquidity, volumes, fees, gas and slippage are
  explicit assumptions. Target equity value is +6%, not a model forecast.
- Market baseline: NVDA news-supported fixture, AAPL normal fixture; both modeled
  representations retain distinct identity, ratio and economics.
- Portfolio: three modeled lots with explicit token quantities and acquisition prices;
  backend valuation, basis, P&L, allocation, concentration, 2% stress estimate and target
  drift all derive from those lots and the same market snapshots. Target-drift
  suggestions are analytical deltas, not approved rebalancing transactions.
- Indicative maximum budget exposure subtracts modeled fees/gas/slippage; the separate
  risk-approved quote uses its constrained notional and exact existing quote economics.
- Scorecard: 60 existing fixture-derived episode outcomes, 30 per asset. Fixed hypothesis:
  absolute initial deviation <=1% predicts reversal, otherwise persistence. Descriptive
  agreement is derived from each displayed record; filtered counts/accuracy use that
  filtered set. No significance, profitability or validated forecasting claim.
- Studies auto-save in a bounded 64-item memory store and can be inspected at
  `GET /api/presentation/research/{id}`. Pinning supports side-by-side comparison.
  Saved studies expire on eviction/restart. Presentation data is not persisted into
  the production database, historical coverage, scorecard or settlement journal.

## API reproduction

All request financial values are exact decimal strings. Precision and magnitude are bounded.

```sh
curl --fail http://127.0.0.1:8000/api/health
curl --fail http://127.0.0.1:8000/api/system-status
curl --fail http://127.0.0.1:8000/api/presentation/workspace
curl --fail -H 'Content-Type: application/json' -d '{"ticker":"NVDA","preset":"news"}' http://127.0.0.1:8000/api/presentation/research
curl --fail -H 'Content-Type: application/json' -d '{"ticker":"NVDA","preset":"low-liquidity"}' http://127.0.0.1:8000/api/presentation/research
curl --fail -H 'Content-Type: application/json' -d '{"ticker":"NVDA","preset":"news","token_price":"55"}' http://127.0.0.1:8000/api/presentation/research
curl --fail -H 'Content-Type: application/json' -d '{"budget":"60","risk_budget":"2","universe":["NVDA","AAPL"],"window":"regular"}' http://127.0.0.1:8000/api/presentation/scan
curl --fail -H 'Content-Type: application/json' -d '{"ticker":"NVDA","budget":"60"}' http://127.0.0.1:8000/api/presentation/exposure
```

## Verification

```sh
.venv/bin/python -m pytest backend/tests/unit/test_presentation.py -q
.venv/bin/python -m pytest backend/tests -q
npm test
npm run build
.venv/bin/ruff check backend scripts
PYTHONPATH=backend .venv/bin/python scripts/generate-ui-contracts.py --check
.venv/bin/python scripts/check-security.py
.venv/bin/python scripts/verify-frontend-phase15.py
```

Browser runner uses credential-free fixture servers on 8054–8057, static built UI on
5178, and disposable local Chrome. It refuses occupied ports and stops only its own
processes. Existing servers on 8000/5173 are not killed. Its API interception refuses
unexpected or external endpoints; report/screenshot paths are printed by the runner.

Final verification:

- Backend: **1,768 passed** in 68.97 seconds. Two existing negative-fixture serializer
  warnings (`postAmount` integer in a string field); no failed tests.
- Frontend: **292 passed**, 16 test files. Includes seven new product integration tests.
- New backend coverage: 30 tests; targeted presentation + boundary suite: 34 passed.
- Typecheck/production build: PASS. Vite reports a non-blocking large-chunk warning
  (843 kB uncompressed entry); bundle optimization remains a future improvement.
- Ruff, generated-contract drift check, security scan and `git diff --check`: PASS.
- Existing provider-workspace browser suite: PASS, desktop/mobile/tablet, six scenario
  journeys, 188 local API requests, zero live execution calls. Original assertions retained.
- Product browser suite: PASS, desktop 1440×1100 and mobile 390×844, all seven sections,
  15 presentation API requests, zero console/runtime errors or execution requests.
  Tested market search/representation selection/reassessment, route comparison,
  scanning/proposal/stand-down inspection, normal/noise/news research, custom token
  price ($55 → $110 effective per share), pin/reset, holdings filter, scorecard filter
  and decision trace, route-preserving reload, mobile navigation, language/overflow checks.
- Desktop overview/opportunities and mobile research screenshots were visually inspected.
- Existing development backend was confirmed as this project's canonical uvicorn process
  and gracefully restarted (92020 → 96277) to load the new routes. Existing Vite process
  86767 was retained. Actual `/api/health`, `/api/system-status`, and presentation workspace
  returned HTTP 200 on port 8000; the presentation API also returned 200 through Vite
  on port 5173. Safe settings were asserted without printing secrets.

Retained browser evidence:

- Provider/operations regression: `/var/folders/hv/m560wcmn6qg0qwwmxw5lsyzc0000gn/T/parity-phase15-browser-iimt4lz6`.
- Final product journeys, JSON request log and twelve screenshots:
  `/var/folders/hv/m560wcmn6qg0qwwmxw5lsyzc0000gn/T/parity-phase15-browser-uzhirlwo`.

For a focused product rerun after building, use
`.venv/bin/python scripts/verify-frontend-phase15.py --presentation-only`.
The default runner still executes all original provider-workspace and MCP checks too.

## Files changed in this increment

New:

- `backend/app/models/presentation.py` — bounded typed scenario/provenance/view contracts.
- `backend/app/services/presentation.py` — centralized isolated data adapter and engine orchestration.
- `backend/app/api/presentation.py` — five calculation/inspection routes, no execution route.
- `backend/tests/unit/test_presentation.py` — engine, calculation, input, isolation and safety coverage.
- `frontend/src/PresentationApp.tsx` — seven product pages and functional controls.
- `frontend/src/presentation.css` — scoped responsive styles using the existing design system.
- `frontend/src/services/presentation.ts` — schema-validated API client.
- `frontend/src/test/PresentationApp.test.tsx` — seven frontend interaction/contract tests.
- `frontend/src/test/presentationFixtures.json` — responses generated from the real isolated engines.
- `scripts/check-presentation-browser.mjs` — actual API desktop/mobile product journeys.
- `docs/PRODUCTIZATION_REPORT.md` — architecture, assumptions, reproduction and results.

Updated:

- `backend/app/main.py` — additive presentation state/router wiring only.
- `backend/tests/security/test_boundaries.py` — retain exact allowlist; add five analytical routes.
- `frontend/src/main.tsx` — default scenario workspace, explicit provider workspace.
- `frontend/src/services/backendSchemas.json` and `frontend/src/types/backend.generated.ts`
  — four additional generated roots; existing seven contracts retained byte-for-byte.
- `scripts/generate-ui-contracts.py` — register the additional response contracts.
- `scripts/check-frontend-phase15.mjs` — explicit `workspace=verified` navigation only.
- `scripts/verify-frontend-phase15.py` — new browser journeys plus focused rerun option.
- `README.md` — default workspace, routes, canonical startup and limitations.

Preservation audit: 573 pre-existing files hashed before edits; 564 remain byte-for-byte
unchanged, and nine were intentionally updated as listed above. For already-dirty
`main.py` and both generated-contract files, removing only this increment's additions
reconstructs the exact original hashes. All other pre-existing dirty/untracked files,
including provider, execution-remediation, gate documents and local data, retain their
original hashes. HEAD remains `9b6368c`; nothing committed or pushed.

## Limits and production gates

This workspace demonstrates scenario reasoning, not current provider coverage or actual
holdings. Two equities, two fictional representations each; no live-price fallback inside
production APIs. Existing provider functionality is separately accessible and unchanged.
No new provider, ratio-history, liquidity-authority, execution-equivalence or 30/30/3 real
evidence is claimed. Production DATA/DRY_RUN remain PASS; TRUST remains BLOCKED;
OPPORTUNITY remains BLOCKED_BY_TRUST; SWAP/RFQ/Agentic Wallet LIVE remain BLOCKED.
LIVE_TRADING_ENABLED=false, PROPOSE_ONLY and simulation requirements remain unchanged.
No external provider, wallet, signing, execution, approval or settlement call is needed
by the product workspace. There is no presentation execute endpoint.

## Subsequent UI refinement (11 October 2026)

The original implementation/evidence above is retained as historical context.
The current UI replaces the modeled history curves with a separate verified Alpaca
historical equity display, qualifies liquidity assumptions, and adds shared buttons,
ambient motion, refreshed read feedback and responsive navigation refinements.
Scenario economics and production gates remain unchanged. See [UI polish report](UI_POLISH_REPORT.md).
