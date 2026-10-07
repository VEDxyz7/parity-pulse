# Hackathon DEMO Stage 3A — Opportunity and financial Risk core

**Status: PASS for isolated synthetic analytical demonstration.** Production Canonical Phase 3 has not passed its gate. No commit was made. This stage ends after Risk analysis; it does not implement QuoteService, TransactionBuilder, Simulation or Paper Execution.

The initial audit reused the Stage 1 Trust sandbox and the Stage 2 service inventory. Existing Trust contracts, token metadata, independent reference evidence, normalization, Phase 1 indicative proposals, conditional DEMO runtime, API middleware and frontend validation were inspected. Opportunity and financial Risk implementations were genuinely absent. They are now implemented once each as `OpportunityEngine` and `RiskEngine`; no alternate Trust classifier, scenario-to-outcome table, production gate override or second Opportunity engine was created.

## Architecture and contracts

The existing GET Trust scenario endpoint still runs the unchanged `DemoTrustSandbox`/`TrustService` against a fresh memory database. Its exact typed result is additionally retained in a bounded DEMO-only memory cache. The adapter then calls the shared deterministic Opportunity engine with that assessment, its representation, the existing synthetic token metadata and a separate economic fixture. Risk consumes the resulting immutable server-generated Opportunity decision. Neither request accepts client-supplied prices, classifications, edge, risk policy or execution flags.

`OpportunityInputs` supplies identity, as-of time, a **hypothetical scenario target**, requested notional, fees, gas, slippage in bps, execution buffer, minimum USD edge and validity. `OpportunityDecision` records its ID and source assessment ID, underlying/representation/issuer, classification, uncalibrated confidence, evidence quality, price and ratio inputs, deviation, hypothetical adjustment/return, gross/net hypothetical USD edge, status/action, reason codes, validity and limitations. Statuses are `NO_OPPORTUNITY`, `REJECTED_BY_TRUST`, `REJECTED` and `ACTIONABLE`. `BUY` means an analytical direction only. All contracts carry synthetic/non-production markers and false execution/broadcast flags; quote/preparation/simulation are explicitly UNAVAILABLE.

`RiskInputs` explicitly supplies cash budget, stress-risk budget, adverse-move fraction, available wallet funds, existing exposure, daily loss, trade count and last-trade time. `RiskPolicy` supplies position/portfolio/day-loss/risk-budget/trade-count limits, minimum confidence, absolute liquidity floor and baseline p50 requirement, maximum liquidity participation, slippage tolerance, edge minimum, cooldown and fixed 120-second freshness/30-second alignment limits. This fixture's minimum confidence is LOW under `SYNTHETIC_DEMO_ONLY`; Trust confidence remains LOW and uncalibrated. This is not a production risk policy or a production confidence relaxation.

`RiskDecision` contains PASS/FAIL, `approved_for_demo_analysis`, individual checks and explanations, rejection codes, the maximum allowed USD notional, proposed analytical notional/token/share size on PASS, stress loss including supplied costs, slippage tolerance and liquidity cap. FAIL never returns an approved size. PASS is not permission to trade. The engine checks actionable calculated economics, Trust/evidence, confidence, expiry, freshness/alignment, risk/day/trade/cooldown limits, slippage, liquidity/p50, net edge, size metadata and each financial cap. Positive rounded token size is required.

Only explicitly marked DEMO inputs are supported at this stage. The new engines have no provider, order, wallet, transaction or database interface. The adapter handles a single synthetic representation, not production full-universe discovery/ranking. REGULAR-session inputs are supported; weekday overnight and weekend/reopening inputs are rejected. No opening prediction is implemented and the production 30-opening-example safeguard is not bypassed.

## Deterministic calculations

All financial inputs reject floats, non-finite/malformed values and unsupported magnitudes. Arithmetic uses Decimal with local precision 256. Derived metrics/caps use 18-decimal floor rounding; token quantity is rounded down to at most 18 places and never more than the token's declared decimals. Source inputs remain exact strings. The independent equity reference is the supplied `DEMO_EQUITY` observation; Binance referencePrice is never substituted.

For token price `P`, shares-per-token ratio `R`, independent equity price `E`, hypothetical target price `T`, requested notional `N`, slippage fraction `s=bps/10000`, fees `F`, gas `G` and execution buffer `B`:

```text
effective share price = P / R
reference deviation = (P - E*R) / (E*R)
hypothetical share adjustment = T - P/R
hypothetical return fraction = (T - P/R) / (P/R)
gross hypothetical edge USD = N * hypothetical return fraction
estimated slippage USD = N * s
net hypothetical edge USD = gross - N*s - F - G - B
```

Deviation is a current price comparison, not a predicted return. Target and costs are supplied synthetic assumptions, not provider quotes, calibrated predictions or financial facts. The same economic/risk fixture is supplied to all three scenarios; it contains no scenario IDs or final decisions. Information is necessary but insufficient: invalid evidence, restricted tokens, unsupported regime, stale/future/misaligned data, non-positive adjustment or insufficient net edge rejects the candidate.

For adverse-move fraction `a`, fixed costs `C=F+G+B` and observed liquidity `L`, the maximum analytical notional is the minimum of:

```text
max position
max(0, (cash budget - C)/(1+s))
max(0, (wallet available - C)/(1+s))
max(0, max portfolio exposure - existing exposure)
max(0, (risk budget - C)/(a+s))
max(0, (max daily loss - existing daily loss - C)/(a+s))
L * maximum liquidity fraction
```

The requested notional must satisfy every cap; it is rejected rather than silently resized with an unrecomputed edge. Stress loss is `N*(a+s)+C`. It is a scenario estimate, not a guaranteed maximum loss. Confidence never increases position size. The p50 check uses the existing same-scope Trust baseline liquidity quantile rather than inventing a liquidity percentile.

## Measured scenario behavior

| Selection | Derived Trust | Opportunity | Risk | Actual decision reason |
|---|---|---|---|---|
| `steady` | NORMAL | NO_OPPORTUNITY / NONE | FAIL, no proposed size | NORMAL_TRUST_NO_INFORMATION_SIGNAL; OPPORTUNITY_ACTIONABLE and TRUST_REQUIRED fail |
| `thin-move` | LIKELY_NOISE | REJECTED_BY_TRUST / NONE | FAIL, no proposed size | TRUST_NOT_LIKELY_INFORMATION; Trust/actionable checks and liquidity/participation checks fail |
| `supported-move` | LIKELY_INFORMATION | ACTIONABLE / BUY, analytical only | PASS, analytical only | Positive calculated net hypothetical edge and all configured DEMO risk checks pass |

Information's inputs: token USD51, ratio0.5, independent share USD100, effective share USD102, hypothetical target USD106 and adjustment USD4/share. USD50 notional yields gross hypothetical edge `1.960784313725490196`; USD0.10 fees, USD0.05 gas, USD0.10 slippage (20bps) and USD0.10 buffer give **net hypothetical edge `1.610784313725490196`**. Both edge minima are USD0.25.

The cash budget is USD60 including supplied costs, risk budget USD2, adverse move2%, wallet available USD100, existing exposure/day loss/trade count zero, position cap USD75, portfolio cap USD100, daily loss cap USD20, maximum risk budget USD5, maximum trades5, cooldown60s, liquidity USD5000, absolute liquidity floor USD1000 and participation cap1%. This yields maximum allowed notional **USD50**, proposed tokens `0.980392156862745098`, shares `0.490196078431372549`, stress loss including costs **USD1.35** and slippage tolerance50bps. All are synthetic analytical values.

Mutation tests keep the Information label while lowering target or increasing each cost/threshold and obtain REJECTED. Replacing the `steady` selection's evidence with Information evidence yields ACTIONABLE despite the unchanged NORMAL title. Risk mutations reject excessive position/portfolio/wallet/budget/stress/day/trade/slippage/edge constraints, inadequate confidence/liquidity/p50, missing size metadata, zero rounded size, cooldown, expired/future decisions and skew. No scenario title determines an engine result.

## API and UI

Register these routes only when `RUNTIME_MODE=DEMO` and `DATA_MODE=DEMO`:

1. `GET /api/demo/trust/scenarios/{identifier}` — unchanged derived Trust response; retain assessment reference in memory.
2. `POST /api/demo/opportunity` with `{"trust_assessment_id":"<returned assessment UUID>"}` — evaluate the selected scenario's exact retained assessment.
3. `POST /api/demo/risk` with `{"opportunity_id":"<returned Opportunity UUID>"}` — assess that retained Opportunity.

The two new POSTs are analytics, not orders. Unknown/evicted/expired references return sanitized HTTP410. Malformed IDs or extra body fields return422, query parameters return404, unsupported methods return405, and both routes are404 in the default LIVE runtime. Production status response fields and ordinary Trust/Ask behavior are unchanged.

Each cache holds at most64 results, is process-local/thread-protected and disappears on restart. Trust/Opportunity references cannot be reused after120 wall-clock seconds. Opportunity validity is at most60 seconds and never beyond120 seconds after the originating Trust assessment. A monotonic elapsed clock advances the fixed synthetic assessment clock, so frozen fixtures do not grant indefinite analytical approval. Late Risk calls fail expiry/freshness; they cannot execute anything.

At the existing sandbox panel, select a scenario, Run demo scenario, Analyze Opportunity, then Analyze Risk. No downstream analysis runs automatically. The UI displays reasons, hypothetical inputs/costs/edge, Risk checks and analytical size, plus the audit contracts. It validates markers, production gates, source IDs/identity, classifications, schema/safety flags, required checks, exact-decimal schema comparisons and status/approval consistency. Replacement selection/reruns abort pending analysis and discard downstream results; unavailable/invalid replies have no substitute result. Expired analytical proposals disable Risk and remain visibly expired. Production Opportunity/Autopilot navigation stays disabled. Synthetic markers remain prominent.

Run the existing sandbox backend from the repository root:

```sh
RUNTIME_MODE=DEMO DATA_MODE=DEMO .venv/bin/python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
npm run dev
```

Respect an already occupied port; do not terminate unrelated services. Verification here used unused ports8011/5174 and disposable Chrome, then stopped those verification services. No existing user service was restarted.

## Verification and preservation

| Validation | Result |
|---|---|
| Full backend `.venv/bin/python -m pytest` | 404 passed; 59 added, all345 existing retained |
| Full frontend `npm test` | 99 passed; 33 added, all66 existing retained |
| `npm run build` | TypeScript noEmit and Vite production build PASS |
| Ruff check / format check, `backend scripts` | PASS |
| Established security audit and extended configured-secret scan | PASS; values never printed |
| `git diff --check` | PASS |
| Actual browser desktop1440 / mobile390 | All three Trust → Opportunity → Risk flows PASS; no horizontal overflow or runtime errors; expanded audit view checked |
| External providers / live execution | Zero; forbidden client/transport/socket checks passed |
| Existing production DBs / historical coverage | All eight DBs byte-identical and counts unchanged; no synthetic historical ingestion |

The upstream Starlette/httpx TestClient deprecation warning remains. No test was removed or weakened. Validation fixtures were derived offline from the actual typed engines and are explicitly marked synthetic; they are not production evidence.

Machine evidence: [verification](evidence/DEMO_OPPORTUNITY_STAGE_3A_VERIFICATION.json), [actual browser requests/scenarios](evidence/DEMO_OPPORTUNITY_STAGE_3A_BROWSER.json). The verification records SHA256 preservation of production Trust code/models, production gate documents/evidence, both master specifications, historical reports, original Trust fixtures, saved alignment diagnostic and all existing DBs. Stage 2 audit and Stage 1 evidence are retained. The alignment diagnostic was neither run nor scheduled by this stage. No credential/provider research was performed. Source, docs, new fixtures and bundle were scanned without exposing configured keys.

## Files changed

Modified:

- `README.md` — current isolated DEMO stage and scope/runbook references.
- `backend/app/main.py` — construct/clear the DEMO adapter and conditionally register its API.
- `backend/app/api/demo_sandbox.py` — retain the exact existing Trust result for downstream reference.
- `frontend/src/components/DemoTrustSandbox.tsx` — mount the downstream panel keyed by assessment ID.
- `frontend/src/styles.css` — scoped spacing/wrapping for the added panel.

Added:

- `backend/app/models/opportunity.py` — exact marked economic inputs/decision and shared analytical safety contract.
- `backend/app/models/risk.py` — mandate/policy/check/decision contracts.
- `backend/app/models/demo_opportunity.py` — strictly validated request IDs and DEMO response/fixture envelopes.
- `backend/app/services/opportunity.py` — the single deterministic Opportunity engine.
- `backend/app/services/risk.py` — the single deterministic financial Risk engine.
- `backend/app/services/demo_opportunity.py` — bounded memory-only orchestration/cache adapter.
- `backend/app/api/demo_opportunity.py` — the two DEMO analytical endpoints.
- `data/demo/opportunity/inputs.json` — one shared explicitly synthetic economic/risk fixture.
- `backend/tests/unit/test_opportunity_risk.py` — calculations, mutations and fail-closed boundaries.
- `backend/tests/integration/test_demo_opportunity.py` — exact evidence flow, API, isolation, expiry/cache and LIVE regression checks.
- `frontend/src/services/demoOpportunity.ts` — typed API client and fail-closed contract validation.
- `frontend/src/components/DemoOpportunityFlow.tsx` — minimal manual Opportunity/Risk UI.
- `frontend/src/test/DemoOpportunityFlow.test.tsx` — scenarios, invalid responses, failures, cancellation, expiry and timeout.
- `frontend/src/test/demoOpportunityFixtures.json` — offline marked real-engine response fixtures for UI tests.
- `docs/DEMO_OPPORTUNITY_STAGE_3A.md` — this report/runbook.
- `docs/evidence/DEMO_OPPORTUNITY_STAGE_3A_VERIFICATION.json` — measured preservation/decision/check evidence.
- `docs/evidence/DEMO_OPPORTUNITY_STAGE_3A_BROWSER.json` — actual desktop/mobile local API browser evidence.

## Production gates and Stage 3B prerequisites

Production gates are unchanged:

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

The real baseline/opening/analogue requirements remain30/30/3; real qualifying coverage remains0/30,0/30,0/3. Current independent reference/entitlement, token liquidity authority, historical ratios/as-of/evidence and real history blockers remain external production blockers. No production capability was unlocked by synthetic success.

**Exact next recommended work: separately authorized DEMO Stage 3B downstream design/integration, after these prerequisites are agreed and supplied:**

1. A marked quote contract and QuoteService that consume this exact representation, identity/ratio, analytical size and freshness window. The existing Phase 1 PRICE-only indicative estimator cannot silently consume/relabel this sandbox's PRICE_INFO observation; no unrelated Ask fixture may substitute for it. Separate indicative estimates from provider execution quotes and distinguish supplied assumptions from measured fees/slippage/gas. Re-evaluate net edge/Risk using actual downstream terms.
2. An explicitly scoped transaction representation/builder interface, immutable fingerprints, identity/amount/time checks and route/simulation equivalence. Preparation success cannot be asserted without its implemented component and supported inputs.
3. An implemented simulation contract/service with honest UNAVAILABLE/FAIL states. It must operate only where supported and cannot manufacture success or bypass REQUIRE_SIMULATION.
4. Keep the same DEMO provenance/gate boundary, caches/expiry and execution prohibitions. Any later Paper Execution requires its own authorization, isolated ledger, fill/cost/outcome assumptions and state machine. No wallet/order/broadcast access is available here.

These components are prerequisites, not implementations in this stage. **STOP after Stage 3A.**
