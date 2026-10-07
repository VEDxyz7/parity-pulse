# Hackathon DEMO Stage 3B — Quote, preparation and local simulation

**Status: PASS for the single authorized DEMO milestone.** The complete Information path reaches a calculated quote, an unsigned request and SIMULATION_PASS. Normal and Noise stop before a quote is issued. No commit, execution, wallet operation or Paper Execution was performed. Production gates remain unchanged.

## Initial audit and reuse

The clean committed Stage 3A checkpoint was inspected: typed Opportunity/Risk contracts and deterministic engines, the marked economic/risk fixture, token/representation and Trust evidence schemas, Phase 1 indicative proposal/estimator, conditional DEMO runtime, API context/error conventions and frontend contracts. QuoteService, TransactionBuilder and SimulationService were absent. The Binance client has only allowlisted market reads and no transaction simulation integration. No genuine Binance simulation adapter was found to reuse; none was invented or called.

The new path reuses the exact server-derived Trust/Opportunity references, OpportunityEngine, RiskEngine, Decimal normalization conventions, existing synthetic fixture and bounded memory-cache infrastructure. Existing Trust/Opportunity/Risk engines, financial policies, master specifications, production gate documents and original fixtures were not changed. Stage 3A's historical report remains intact. Phase 1's INDICATIVE_ONLY proposal is not an executable quote and is not substituted for the new quote. PRICE_INFO stays PRICE_INFO.

## Exact flow and scope

```text
DEMO Trust assessment
→ Opportunity analysis
→ explicit Risk analysis
→ re-evaluate Opportunity with current DEMO economic assumptions
→ Risk revalidation before issuing quote
→ synthetic Quote
→ Risk revalidation of rounded quoted size/costs/edge
→ Risk + input/expiry/fingerprint revalidation at preparation
→ unsigned DEMO request preparation
→ current Risk revalidation + local simulation constraints
→ SIMULATION_PASS or SIMULATION_FAIL
→ STOP
```

The adapter accepts only cached server-issued IDs. A prior Risk PASS is necessary but never sufficient to reuse obsolete economics. Before quoting it recomputes Opportunity economics using the current marked fixture and reruns Risk. It keeps the source Opportunity ID and original expiry; it cannot extend an expired Opportunity by refreshing the quote. Changed market-dataset inputs reject reuse of the old Trust snapshot. A fresh still-eligible cost assumption can yield a new quote, but invalidates the prior quote/context for preparation and simulation.

After quote generation, Risk evaluates the exact rounded quoted mark notional and current economic assumptions. Preparation repeats Risk and checks quote validity, canonical fingerprint and an exact digest of the selected market dataset plus economic/risk fixture. Simulation repeats current Risk and those binding checks. Even a still-eligible input change requires a new quote/preparation. All caches are bounded to64 entries, process-local, thread-protected and restart-discarded; nothing enters a production database or an execution ledger.

The quote TTL is30 seconds, capped by the source Opportunity expiry. Reference caches remain bounded by120 elapsed seconds. Time is the existing fixed synthetic assessment clock advanced by monotonic wall elapsed time. Quote issuance is fresh within that DEMO clock and validity window; the frozen underlying fixture observation is displayed separately and never relabeled a fresh LIVE observation. No provider refresh is claimed.

## Quote contract and deterministic economics

`DemoQuote` includes deterministic quote ID, fingerprint/context digest, source Opportunity/Risk IDs, ticker/issuer/chain/token/symbol/decimals, BUY direction, DEMO_USD funding unit, issuance/expiry and original market observation time/kind. It supplies mark/execution price, token/share ratio, requested/mark/input notionals, output tokens/share exposure, fees, gas, buffer reserve, slippage assumption/amount, required cash and quoted net hypothetical edge. `source=DEMO`, `quote_type=SYNTHETIC_ECONOMIC_QUOTE`, `provider_quote_id=null`, `executable=false` and synthetic/non-production markers are mandatory.

The synthetic target/costs come from the unchanged explicitly marked fixture. They are not provider quotes or a calibrated forecast. For mark price `P`, slippage fraction `s=bps/10000`, requested notional `N`, ratio `R`, hypothetical share target `T` and fixed costs/reserve `C=fees+gas+buffer`:

```text
synthetic BUY execution price = P*(1+s)
output tokens = floor_to_token_precision(N / execution_price)
mark notional = output_tokens * P
input DEMO USD = output_tokens * execution_price
estimated slippage = input - mark notional
required cash including costs/reserve = input + C
quoted net hypothetical edge = output_tokens*T*R - input - C
```

Slippage is embedded in execution price and is not charged again as cash. The buffer is a conservative reserve/edge deduction, not an assertion of a paid fee. The existing Risk engine operates on mark notional and adds its slippage/cost terms once, so the adapter supplies the quoted mark notional and recomputed economics. Token quantity is rounded down at the minimum of18 places and declared token decimals. Decimal arithmetic uses local precision256; edge/cap metrics use conservative18-decimal rounding. Base-unit conversion uses exact Fraction/integer arithmetic. Floats, non-finite/malformed values and invalid modes/identities are rejected.

For identical full input records, IDs/provenance and evaluation time, quote and prepared-request content/IDs are deterministic. SHA256 covers canonical sorted JSON with explicit financial strings; UUID5 is derived from the fingerprint. New source assessments or issuance times are distinct binding inputs and intentionally produce new IDs. Risk audit UUIDs do not introduce randomness into quote content. No signing secret is involved.

Measured default Information values:

| Item | Actual synthetic value |
|---|---|
| Mark / ratio / target | USD51 per token /0.5 shares per token / USD106 per share assumption |
| Requested notional / slippage | USD50 /20bps |
| Execution price | USD51.10200 per token |
| Output tokens | `0.978435286290164768` |
| Share exposure | `0.4892176431450823840` |
| Mark notional | `49.90019960079840316800` USD |
| Input | `49.99999999999999997433600` DEMO USD |
| Embedded slippage | `0.09980039920159680633600` USD |
| Fees / gas / reserve | USD0.10 / USD0.05 / USD0.10 |
| Cash including costs/reserve | `50.24999999999999997433600` USD |
| Quoted net hypothetical edge | `1.607070173378732729` USD |
| Post-quote Risk | PASS for synthetic analysis only |

The initial Stage 3A edge `1.610784313725490196` is recalculated, not copied: the quoted token quantity now fits USD50 at the slippage-adjusted price.

## Transaction preparation contract

`PreparedDemoRequest` contains deterministic request/transaction ID, canonical fingerprint, quote ID/fingerprint, context digest, Opportunity ID, preparation/expiry, `transaction_type=DEMO_BUY_REQUEST`, `encoding=CANONICAL_JSON_DEMO_REQUEST` and typed `DemoBuyParameters`. Parameters bind ticker/issuer, synthetic chain/token, symbol/decimals, exact base units, direction, funding unit, quantity, mark notional, maximum input, minimum output, slippage and costs/reserve.

Default base units: `978435286290164768`. Minimum output equals the quoted token quantity; no extra unmodeled slippage is authorized. The request is a logical synthetic manifest describing the proposed action, **not EVM calldata or a chain transaction**. Chain is DEMO and token is `demo:NVDA`; no real address is fabricated. `calldata=null`, `signature=null`, `signed=false`, `broadcastable=false`, `transaction_broadcast=false`, `funds_moved=false` and `execution_ready=false`. Preparation cannot sign or send anything. Its exact validity remains bound to the quote.

## Simulation contract and actual failure evidence

`DemoSimulation` contains simulation ID, transaction ID/fingerprint, quote ID/fingerprint, evaluated/expiry time, fresh Risk decision, reason codes and18 individually explained checks. Method is `LOCAL_DEMO_CONSTRAINT_EVALUATION` with `chain_simulation=false`. It reports SIMULATION_PASS only when every check passes; otherwise SIMULATION_FAIL with failing codes. It does not perform EVM/state/RPC simulation or imply Binance execution/simulation equivalence. REQUIRE_SIMULATION and all production blockers remain intact.

Checks cover quote/request expiry/future times, current context equality, both canonical fingerprints/derived IDs, quote/Opportunity binding, representation identity/status/ratio/decimals, current Risk, allowed size, slippage, liquidity participation, execution-price formula, exact input/output/mark equivalence, smallest units, recomputed net edge, bound costs/reserve, cash budget/wallet limits and absence of signature/calldata/broadcast/funds movement.

Tests prove actual failures, including:

- At30/31/60 elapsed seconds the quote is expired: preparation is BLOCKED with no request; a previously prepared request yields SIMULATION_FAIL / QUOTE_VALID and REQUEST_VALID.
- Reduced wallet/risk/position limits, excessive slippage or liquidity requirements, increased fees/gas and a target below effective share cost trigger current Risk rejection and simulation failure.
- Changed but still-eligible fees produce a distinct valid new quote and invalidate the old context.
- Quantity, amount, minimum output, slippage, base units, token identity, fees or quote ID tampering fails the relevant semantic check **even after recomputing the request fingerprint**.
- An invented USD100 edge fails QUOTED_NET_EDGE and quote fingerprint checks. A restricted token fails representation validation. Invalid real-chain/signed/broadcast/float contracts are rejected.

No simulation result is forced by scenario name or Trust label.

## API / UI / scenarios

Conditional DEMO analytical endpoints:

- `POST /api/demo/quote` — `{"risk_id":"<server Risk UUID>"}`.
- `POST /api/demo/prepare` — `{"quote_id":"<server DEMO quote UUID>"}`.
- `POST /api/demo/simulate` — `{"transaction_id":"<server prepared request UUID>"}`.

They follow existing typed responses, correlation headers and sanitized errors. Unknown/evicted/over120-second references return410, invalid/extra body fields422, query parameters404 and unsupported methods405. Valid identified analyses can return200 with explicit BLOCKED/SIMULATION_FAIL; HTTP success does not mean analytical approval. The routes and adapter are absent in the default LIVE runtime. No order/wallet/broadcast/SWAP/RFQ operation or client allowlist was added.

The existing sandbox gains manual Generate DEMO Quote, Prepare DEMO Transaction and Run DEMO Simulation steps only after actionable Opportunity and Risk PASS. It shows quote quantities/prices/costs/expiry, pre/post-quote Risk, prepared parameters/fingerprint and simulation status/checks. It prominently marks DEMO SANDBOX / SIMULATED DATA — NOT LIVE MARKET DATA, unsigned/not-executed requests and local/non-chain simulation. No money-moved success or execution button appears.

The frontend validates source IDs/identity, provenance, gates, safety flags, monetary schema, quote/request parameter equivalence, stage/Risk consistency and all required simulation checks. Replies cannot substitute an unsafe success. Scenario/Opportunity/Risk replacement unmounts/aborts downstream requests and removes prior results. New quotes clear previous preparation/simulation; failed preparation leaves no stale request/simulation. Quote expiry disables preparation/simulation and marks old evidence expired. No downstream stage runs automatically.

| Scenario | Opportunity / Risk | Quote / Preparation / Simulation |
|---|---|---|
| NORMAL | NO_OPPORTUNITY / FAIL | No controls or issued artifacts; direct quote request returns BLOCKED without invoking downstream services |
| LIKELY_NOISE | REJECTED_BY_TRUST / FAIL | Same stop boundary |
| LIKELY_INFORMATION | ACTIONABLE / PASS | QUOTED → revalidated Risk PASS → PREPARED → SIMULATION_PASS for the default fixture |

Use the existing DEMO startup commands from the repository root (`RUNTIME_MODE=DEMO DATA_MODE=DEMO` with the canonical uvicorn factory command, then `npm run dev`). Verification used unused localhost ports8011/5174 and disposable Chrome; those temporary services were stopped afterward. Existing user services were not restarted.

## Validation / preservation / files

| Validation | Result |
|---|---|
| Initial relevant Stage 3A tests |59 PASS before implementation |
| Full backend `.venv/bin/python -m pytest` |442 PASS;38 added; all404 existing retained |
| Full frontend `npm test` |128 PASS;29 added; all99 existing retained |
| `npm run build` | TypeScript noEmit + Vite PASS |
| Ruff check / format check `backend scripts` | PASS;95 Python files formatted |
| Established security + extended configured-key audit | PASS; no secret values exposed |
| `git diff --check` | PASS |
| Actual desktop1440 / mobile390 browser | All three flows PASS; Information completes all stages; no runtime errors/horizontal overflow |
| Production DB/history / core logic / gates | Byte-identical protected artifacts and all eight DBs; counts unchanged |

The upstream Starlette/httpx TestClient deprecation warning remains. No existing test was changed or weakened. Browser verification forwards only reviewed local DEMO analytical requests to the real isolated backend. No external provider, wallet, trading, order, broadcast or alignment diagnostic was called. No production observations, historical examples, positions or scorecard records were written. Git HEAD is unchanged; no automatic commit.

Evidence: [verification and preservation manifest](evidence/DEMO_PREPARATION_STAGE_3B_VERIFICATION.json), [desktop/mobile actual API flows](evidence/DEMO_PREPARATION_STAGE_3B_BROWSER.json).

Modified files:

- `README.md` — current DEMO milestone/scope/report links.
- `backend/app/main.py` — conditional adapter/router lifecycle in DEMO only.
- `backend/app/services/demo_opportunity.py` — bounded memory cache of exact existing Risk results; response semantics unchanged.
- `frontend/src/components/DemoOpportunityFlow.tsx` — mount the downstream panel only after Risk PASS and discard it on replacement.
- `frontend/src/services/demoOpportunity.ts` — export unchanged shared schema validators for reuse.

Added files:

- `backend/app/models/demo_execution.py` — explicit marked quote/request/simulation contracts, strict ID-only requests and fingerprints.
- `backend/app/services/quote.py` — deterministic synthetic QuoteService and quoted economics.
- `backend/app/services/transaction.py` — unsigned logical TransactionBuilder.
- `backend/app/services/simulation.py` — deterministic18-check local SimulationService.
- `backend/app/services/demo_preparation.py` — memory-only downstream orchestration, freshness/context/Risk revalidation.
- `backend/app/api/demo_preparation.py` — three DEMO-only analytical endpoints.
- `backend/tests/unit/test_demo_preparation.py` — math/determinism/expiry/current-input/fingerprint/semantic failures.
- `backend/tests/integration/test_demo_preparation_api.py` — complete API flow, stop boundaries, isolation, LIVE/gate regression and invalid requests.
- `frontend/src/services/demoPreparation.ts` — typed clients and fail-closed contract validation.
- `frontend/src/components/DemoPreparationFlow.tsx` — minimal three-step UI.
- `frontend/src/test/DemoPreparationFlow.test.tsx` — outcomes, mutations, expiry, unavailable/cancelled results and ineligible scenarios.
- `frontend/src/test/demoPreparationFixtures.json` — marked offline actual engine outputs, including a real local simulation expiry failure.
- `docs/DEMO_PREPARATION_STAGE_3B.md` — this report.
- `docs/evidence/DEMO_PREPARATION_STAGE_3B_VERIFICATION.json` — measured contracts, failures, validation and preserved hashes/counts.
- `docs/evidence/DEMO_PREPARATION_STAGE_3B_BROWSER.json` — actual browser evidence.

## Production gates / remaining Paper Execution + Position/Scorecard

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

Production Trust30/30/3 safeguards and real coverage0/30,0/30,0/3 are unchanged. DEMO simulation success supplies no live capability evidence and unlocks no production execution. The existing reference/entitlement, liquidity authority, historical ratio/as-of and qualifying real-history blockers remain.

**Exact next work requires separate authorization: isolated Paper Execution + Position/Scorecard.** It still needs:

1. A DEMO paper ledger/state machine with idempotent fill records bound to a still-valid quote/request/simulation fingerprint and explicit rejection of stale/mismatched context. No real account or chain access.
2. Explicit synthetic entry/exit/fill-price, slippage, fee/gas and price-trajectory assumptions, including how the execution reserve is treated. Quoting/simulation alone is not a fill; never double-charge embedded slippage or count a reserve as a paid fee without a defined rule.
3. Position lifecycle, exit logic/timers and realized/unrealized P&L, supported by a defined synthetic clock/mark sequence and closed-position evidence.
4. Stateful paper cash/exposure/day-loss/trade-count/cooldown updates feeding the existing Risk engine; current fixtures supply a static mandate, not a portfolio ledger. Revalidate Risk before each paper entry/exit.
5. A clearly synthetic Position/Scorecard contract/UI and meaningful outcome metrics with persistence/restart/reconciliation tests, without contributing any synthetic episode to production Trust coverage or claiming empirical performance.

No such ledger, fills, positions, exit scheduler, P&L or scorecard was implemented. Real provider Quote/Build/chain simulation integration and execution equivalence remain separate blocked capabilities. **STOP after this one Stage 3B milestone.**
