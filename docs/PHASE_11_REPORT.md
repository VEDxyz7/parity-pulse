# Master Phase 11 — Portfolio / Autopilot

PHASE_11_IMPLEMENTATION = PASS for the deterministic, persistent **non-live** portfolio machinery described below. Production input assembly and provider verification remain PARTIAL; live execution remains BLOCKED. This is not a claim of live trading readiness.

## Authority and continuation audit

The authoritative October 7 specification, `docs/MASTER_SPEC.md`, was read completely before implementation. Its SHA-256 is `f69a9bd01a622c001c3ec6cb654e00562f6b3d03a8310f9e5ccf68efe4b49c84`; Phase 11, Autopilot section 53, API section 77 and acceptance tests in 83O were also reviewed. The specification was not edited.

Baseline commit: `c558d0b5ce66664129597feec328777ee0ab472b`. On the continuation request, the existing working tree, full diff, portfolio implementation and tests were inspected. The already implemented configuration, snapshot, drift, routing, persistence, API and preparation work was retained. Remaining work covered actual provider-route comparison at the existing handoff boundary, wallet-control regression coverage, safe completion/ownership linkage, full validation and evidence/report finalization. No reset, replacement implementation, commit or push was performed.

Phase 10 remains the position authority. Phase 8 remains the execution authority. Existing Trust, Risk, Funding, Routing, provider quote selection, transaction building, fingerprinting, simulation, wallet and gateway components are reused. There is no second market, position or execution engine.

## Implemented behavior

- A single local user/account portfolio has explicit ticker targets, a mandatory CASH allocation, per-asset drift bands, a funding symbol, maximum drift, rebalance notional, risk budget and stock-exposure caps. Unique targets must sum exactly to one; the universe is bounded at 25 targets and 100 captured positions/actions. Configuration changes use version compare-and-swap and cannot change the runtime mode or grant execution permission.
- Financial inputs reject binary floating-point values. Prices, ratios, USD values and weights use Decimal; token quantities use explicit base-unit integers. Band comparisons use exact rational arithmetic, so rounding a displayed weight cannot change eligibility. Quantities round down and cannot exceed the requested delta or confirmed remaining holdings.
- A mode-scoped snapshot binds the configuration version, source inputs, provider timestamps, Phase 10 positions and a content fingerprint. Confirmed remaining token quantities determine current value; remaining normalized share exposure comes from Phase 10. Current cash is valued only from fresh, verified FundingState inputs. Native gas reserves remain separate from investment capital.
- Drift is the current weight minus the configured target weight. A band boundary is inclusive. Plans return `NO_ACTION`, `REBALANCE_REQUIRED` or `BLOCKED`, with current/target values, exposure, required deltas, reasons and route evidence. Sales precede purchases; larger absolute USD deltas precede smaller ones; deterministic identity ordering resolves ties. Cash drift is repaired only through explicitly configured stock targets.
- Existing `RoutingService` evaluates issuer, token/share normalization, liquidity, costs, Trust, Risk, tradability and eligibility. Purchases compare eligible representations using the existing all-in exposure-cost ranking. Sales are constrained to confirmed held representations, ordered by held value and identity; this is not a claim of global sell-proceeds optimization. The supported execution boundary is the existing BSC/EVM path; an unsupported chain or unverified contract cannot reach quote preparation.
- Existing RiskEngine and FundingService check each action. Aggregate checks enforce notional, stress-loss budget, stock exposure, trade limits and current cash. Future sale proceeds are not assumed available for a purchase. A failed required action or aggregate check suppresses preparation of the whole plan.
- The existing bounded agent Mandate may suggest an AUTOPILOT allocation, but explicit user-reviewed ticker targets and limits must match it. Agents do not supply authoritative balances, arithmetic, eligibility or execution permissions. No new LLM calls or agent subsystem were added.
- Optional BTC/ETH slots are modeled explicitly with zero weight and disabled execution. Nonzero crypto allocations are rejected because an independently verified crypto data/execution path has not been established. No second trading subsystem was added.

## Position and execution safety

OPEN and EXIT_PENDING retain their confirmed owned exposure. EXIT_PENDING cannot create a competing reduction. OPENING, EXITING, UNKNOWN, RECONCILIATION_REQUIRED, running lifecycle jobs, conflicting settlement and unreconciled newer execution evidence block financial planning. CLOSED positions contribute no remaining holdings. Quoted, simulated or submitted quantities never become owned exposure.

Phase 10 gained an immutable `PORTFOLIO_DRIFT` exit policy selected only when creating a new portfolio position from confirmed canonical execution evidence. The existing Opportunity policy remains `FIRST_REGULAR_OPEN_PLUS_MINUTES`, including its original schedule and exit checks. Existing positions cannot have their policy changed. A portfolio reduction requires an exact persisted-plan authorization over position, quantity, decision, Risk evidence and FundingState before the original Phase 10 exit preparation can proceed.

Host-only preparation follows the existing pipeline:

`Risk → Funding → provider Quote → existing provider Route selection → Build → Fingerprint → Simulation → Wallet Controls / ExecutionGateway eligibility`

Portfolio planning performs representation selection first; provider quotes then retain their own quote IDs, vendor/provider identity, execution mode, transaction details and simulation fingerprint through the original execution pipeline. Portfolio code does not construct a transaction or call an execution transport. Public portfolio endpoints cannot prepare, sign, submit, broadcast, settle or cancel an order.

Host-only `register_confirmed_entry` requires an already confirmed canonical execution and matching discovered instrument/as-of metadata, then delegates actual filled ownership to Phase 10. Host-only `complete` requires every action to have matching confirmed execution evidence and a reconciled Phase 10 entry/reduction link. It records a completion snapshot and settled execution IDs before releasing the pending intent. Simulation, partial processing, unknown settlement, lost links and incomplete inventory cannot complete a rebalance. Synthetic settlement fixtures used to test these boundaries are not real settlement evidence.

## Persistence, recovery and APIs

Configuration, snapshots/drift, plans, action evidence, preparation references, completion evidence, request/correlation IDs and a hash-checked audit are stored in the portfolio SQLite repository. Immutable decision evidence cannot be overwritten. An idempotency key returns its existing plan; a database uniqueness constraint and atomic claim permit only one active rebalance per mode, including concurrent workers. Coalesced requests retain their newly captured inputs in the audit. Recovery restores pending work and safely links an already journaled canonical preparation after a crash without obtaining another quote or submitting anything.

Disk-backed ordinary runtimes use the existing database directory under `portfolio/phase11/<data_mode>`. DEMO/test runtimes retain the application's isolated in-memory policy. Disk-backed isolated fixtures separately verify fresh-process restart and concurrent-store recovery. No production observation database was populated from fixtures.

The minimal API surface is:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/portfolio` | Configuration, latest decision, pending plan and Phase 10 active positions |
| GET | `/api/autopilot` | Same non-executable portfolio state |
| POST | `/api/autopilot` | Validated configuration only |
| PUT | `/api/portfolio/config` | Versioned validated configuration |
| POST | `/api/portfolio/drift` | Persist an audited, idempotent drift decision |
| POST | `/api/portfolio/plans` | Same deterministic plan operation |
| GET | `/api/portfolio/plans/{plan_id}` | Inspect a mode-scoped plan |
| GET | `/api/portfolio/pending` | Inspect pending non-executable actions |
| GET | `/api/portfolio/audit` | Inspect the bounded structured audit |

Financial facts and host service dependencies cannot be installed through these APIs. Extra authorization, execution, mode and query fields are rejected. Frontend code was not changed; the production Opportunity navigation remains disabled. Phase 12 was not started.

## Production routing status and external blockers

**Deterministic routing implementation: PASS.** Portfolio uses the existing shared router for DEMO and LIVE_READ_ONLY contracts. Tests cover changed economics/order, unavailable and unsupported routes, provider quote comparison, fingerprint binding, Risk rejection and actual existing wallet quota controls. No DemoRouter or hardcoded issuer selector was introduced.

**Production provider verification: PARTIAL / NOT VERIFIED for this milestone.** The default `CachedPortfolioSource` reads mode-scoped existing token metadata/observations. It does not fetch data, manufacture balances or replace the provider cache with fixtures. It returns explicit `CURRENT_FUNDING_UNAVAILABLE`, `CURRENT_COMPLETE_INVENTORY_UNAVAILABLE` and `HOST_RISK_TRUST_COST_ASSEMBLY_UNAVAILABLE` blockers until a verified host adapter supplies complete current inputs. The typed `create_app(portfolio_source=...)` boundary permits that verified production assembly without changing the algorithm.

The offline LIVE_READ_ONLY contract probe uses explicitly labeled `OFFLINE_SCHEMA_PROBE` inputs in disposable stores. It verifies the same routing implementation and the unchanged `PRODUCTION_TRUST_GATE` rejection, with zero provider calls; it does not establish provider entitlement, real liquidity, current independent equity freshness or actual LIVE Trust evidence. Provider-route handoff tests likewise use `TEST_FIXTURE` responses. Evidence JSON marks all such financial fixtures synthetic and production-ineligible.

Remaining external work includes verified complete wallet inventory and fresh funding/price provenance; host assembly of independent equity, Trust, liquidity and cost evidence; actual provider route/build/simulation verification and transaction equivalence; and verified Agentic Wallet runtime/controls. Existing Phase 7 real-input assembly, Phase 8 live equivalence and Phase 9 wallet runtime remain PARTIAL. Existing production Trust historical/as-of requirements remain unchanged; this task adds no qualifying real historical episodes. There is no live rebalance scheduler, automatic signing or crypto provider integration.

## Validation

| Check | Result |
| --- | --- |
| Full backend `PYTHONPATH=backend:. .venv/bin/python -m pytest -q` | 1,212 passed; three existing warnings |
| Focused `test_portfolio.py` + `test_portfolio_api.py` | 94 passed |
| Targeted Phase 6–10 allowance, LLM transport, settlement, wallet quota and position regressions | 156 passed |
| Frontend `npm test` | 173 passed across nine files |
| `npm run build` | PASS; includes `tsc --noEmit` and Vite production build |
| Ruff check / format check | PASS |
| Project secret/bundle/ignore security audit | PASS |
| Python `pip check` and `npm ls --all` | PASS; dependency consistency checks, not a new CVE audit |
| Existing desktop/mobile browser scenarios | Six PASS; both full Information hero flows and stand-down scenarios preserved |
| Portfolio API browser smoke | Configuration succeeds; missing host inputs produce audited BLOCKED/null valuation, zero actions/broadcast |
| Git whitespace and safety-source invariants | PASS |

The inherited stderr-only wallet CLI timeout test failed intermittently during earlier full runs (`WALLET_READ_TIMEOUT` versus expected `CLI_READ_FAILED`). Both responses fail closed. Its isolated cases passed, and the full process-readiness probe passed all 1,212 tests; the probe did not reproduce a missed selector exit event. The final ordinary full-suite result is recorded in `PHASE_11_VERIFICATION.json`. No wallet client, wallet test, timeout, output limit or assertion was changed to conceal the issue. Three existing full-suite warnings concern Starlette TestClient deprecation and deliberately malformed allowance serialization cases.

Browser evidence records 43 local API requests, zero live provider/execution calls, unchanged Overview Trust (`INSUFFICIENT_EVIDENCE`), disabled production Opportunity navigation, visible synthetic-data labels and no desktop/mobile overflow. Disposable servers were stopped; the user's existing ports 8000/5173 were not terminated.

## Evidence and files

- `docs/evidence/PHASE_11_SYNTHETIC_PLANS.json`: exact BUY, SELL, within-band and missing-funding snapshots/plans, canonical fixture execution references, provider quote IDs, fingerprints and simulation/gateway outcomes. All fixture data is explicitly synthetic and production-ineligible.
- `docs/evidence/PHASE_11_BROWSER.json`: actual local desktop/mobile browser regression and portfolio API smoke results.
- `docs/evidence/PHASE_11_VERIFICATION.json`: validation results, log hashes, safety-source hashes, unchanged gates and readiness distinctions.

Exact files changed:

1. `backend/app/main.py`
2. `backend/app/models/position.py`
3. `backend/app/services/position.py`
4. `backend/tests/security/test_boundaries.py`
5. `backend/app/api/portfolio.py`
6. `backend/app/models/portfolio.py`
7. `backend/app/repositories/portfolio.py`
8. `backend/app/services/portfolio.py`
9. `backend/app/services/portfolio_sources.py`
10. `backend/tests/unit/test_portfolio.py`
11. `backend/tests/integration/test_portfolio_api.py`
12. `docs/PHASE_11_REPORT.md`
13. `docs/evidence/PHASE_11_SYNTHETIC_PLANS.json`
14. `docs/evidence/PHASE_11_BROWSER.json`
15. `docs/evidence/PHASE_11_VERIFICATION.json`

## Unchanged gates and stop condition

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

Phase 6 remains PASS for non-live scope; Phases 7–9 remain PARTIAL; Phase 10 remains PASS for non-live persistent positions. Phase 11 implementation is PASS for the specified non-live machinery, with the production dependencies above still blocked. No authenticated external provider, real signing, wallet mutation, order submission, transaction broadcast or funds movement occurred during this milestone. No production gates or thresholds were changed. No commit or push was made. Work stops after Phase 11; Phase 12 requires a separate instruction.
