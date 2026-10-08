# Master Phase 13 — Scorecard + Audit

**PHASE_13_IMPLEMENTATION = PASS** for deterministic evaluation of existing non-live decisions and their recorded outcomes. Provider verification remains **PARTIAL**; execution verification and live readiness remain **BLOCKED**. Phase 14–18 were not started. No commit or push was made.

## Authority and scope

The entire authoritative `docs/MASTER_SPEC.md` was read before coding: 5,321 lines, SHA-256 `f69a9bd01a622c001c3ec6cb654e00562f6b3d03a8310f9e5ccf68efe4b49c84`. Baseline: `31d438de8cfc16b2a3e722417062ecc70998448d`. The master, previous reports/evidence, production observations, Trust thresholds/30–30–3 safeguards, Risk, routing, quotes, execution controls, wallet controls, position transitions and portfolio/autopilot decisions are unchanged.

The initial audit found an established DEMO paper scorecard and validated decision/execution/position/portfolio/replay journals, but no consolidated Scorecard/Audit API or Terminal evaluation surface. Existing accounting, engines and journals were reused. Phase 13 adds evaluation and source projections; it does not make investment decisions or authorize execution.

## Architecture and persistence

`ScorecardService` reads original Exposure proposals, immutable Opportunity scans, structured agent runs, point-in-time research replay, Phase 11 plans, existing DEMO artifacts/paper accounting, and Phase 12's validated canonical execution/position analytics. Read-only repository additions retain existing validation. There are no provider refreshes, agent invocations, Trust assessments, quotes, builds, simulations, reconciliations or financial mutations initiated by evaluation.

`AuditService` creates bounded typed summaries and SHA-256 source references to these authorities. Existing Phase 11 audit and Phase 8–10 journals remain the underlying authorities. Consolidated events are explicitly `PERSISTED_SOURCE_PROJECTION`: their source timestamp is distinguished from their capture time. `DATA_FETCH`, `QUOTE`, `SIMULATION`, etc. describe existing recorded source artifacts, not a newly performed provider operation.

The mode-scoped `ScorecardStore` appends scorecards and their audit references atomically. Checksum, semantic identifier, mode/decision binding, original-input consistency and immutable conflict validation fail closed. Later outcomes append an evaluation version; they never overwrite the original decision or its evaluation. Same-source retries and concurrent workers retain the first capture. Invalid/missing/cross-decision event references roll back the transaction. Restart, concurrency, conflict and tamper cases are tested.

Ordinary disk-backed operation stores `scorecard-audit.sqlite` beneath the database directory's `scorecard/phase13/<data mode>/`. DEMO sandbox and test/memory runtimes remain session-only and isolated, consistent with the earlier phases. Existing real observations are not amended or seeded with DEMO data. Bounded DEMO quote/preparation attempt snapshots also retain typed BLOCKED returns; the audit shows the actual stop reason without claiming an artifact was created or execution occurred.

Successful existing decision-producing HTTP operations trigger capture after their authoritative result has been stored. Capture failure logs only `SCORECARD_CAPTURE_UNAVAILABLE`, never changes a previously produced decision or grants authority; read APIs retry validation and return unavailable if it still fails. Host-created journal records are also captured by the read APIs. This is a derived projection, not a new durable execution outbox.

## Scorecards and supported meanings

| Type | Authoritative inputs | Evaluation |
| --- | --- | --- |
| Opportunity | Scan/candidate/agent evidence, existing DEMO Opportunity output or historical replay | Decision/action, confidence, Trust, net-edge inputs, recorded route, Risk/abstention reasons, available prediction target and subsequent canonical outcome |
| Direct Exposure | Original user-intent proposal, discovered representations, normalization and recorded RouteDecision | Requested USD, selected issuer, estimated share exposure, token price/share ratio/normalized cost, eligible alternative route costs, proposal/rejection, downstream evidence where genuinely linked |
| Autopilot | Phase 11 frozen config/snapshot/allocation rows/actions/routes and canonical child execution IDs | Original target/current weights, drift/band decisions, BUY/SELL/notional, preparation state, Risk, resulting positions and validated completion |

A proposal is `PROPOSED`; a successful local simulation is `SIMULATED`; paper fills/exits are `PAPER_FILLED`/`PAPER_EXITED`. Submitted, failed, unknown and reconciliation-required execution categories come from existing Terminal/canonical journal semantics. `CONFIRMED` is possible only from already validated settlement evidence. A confirmed synthetic fixture is still labeled synthetic and has `actual_completed_trade=false`. A quote, submission, simulation or filled-looking request never establishes real ownership. Requested, quoted, filled and remaining units remain separate.

Autopilot child execution identifiers are retained under the original plan decision, with correlation and execution references in the trace. Completion requires the plan's canonical settled execution links. Allocation values are explicitly **decision-time** values; Phase 13 does not recalculate NAV, drift or a new rebalance. Missing earlier execution/position state is withheld, not reconstructed from a newer snapshot.

Prediction quality uses existing direction semantics and only opening targets whose recorded availability is within the requested cutoff. Direction matches, absolute predicted-versus-actual error and descriptive accuracy fractions use Decimal. Forecasts/original-input digests remain unchanged when later targets become available. Replay remains hypothetical/non-executable. Metrics count recorded evaluations, not independent market episodes; no statistical validity or profitability is claimed.

Independent classification truth is absent from the current authorities. Classification correctness, correctly ignored noise outcome, classification accuracy and abstention **outcome** accuracy therefore remain NULL. `noise_suppressed` records procedural suppression without asserting it was economically correct. Composite `score` is NULL with `NO_COMPOSITE_SCORE_FORMULA_DEFINED`. No score formula or label was invented.

### Correct abstention

`CORRECT_ACTION`, `INCORRECT_ACTION`, `CORRECT_ABSTENTION`, `INCORRECT_ABSTENTION` and `UNSCORABLE` are explicit **existing-policy consistency** evaluations, not profitable-trade labels. Proposal permission never imposes a duty to buy. Blocked/no-qualifying decisions are valid abstentions; unblocked discretionary deferral remains unscorable without additional truth. An existing explicit outside-band rebalance requirement supports the incorrect-abstention predicate. Tests cover all four classifications and unknown/discretionary cases.

Decision and execution abstention scopes remain distinct. Trust/data/Risk/simulation/unknown-state reasons are preserved from the existing vocabulary. A supported proposal followed by blocked execution does not become a failed investment or erase its original decision inputs.

### Route cost efficiency

The existing `RouteDecision` is evaluated, never rerun or replaced. The chosen persisted ranking cost is compared with the minimum among eligible recorded candidates on that decision's existing ranking basis. Excess cost and minimum-selection flags use exact Decimal arithmetic. Rejected routes never become the comparison minimum. Raw token price/share ratio, normalized share cost, liquidity state/source, Trust, tradability and available estimated fee/gas/slippage inputs are retained.

Token-price-only ranking is distinguishable from an all-in estimate. Estimated costs are distinct from simulated and realized costs. Actual total USD cost, actual slippage and simulated USD cost stay NULL without sufficient authority. Existing canonical actual native fee units and average execution prices can be displayed without fabricating a USD conversion. Existing paper P&L is reused exactly; no new P&L calculation is added. Binance `referencePrice` is never substituted for independent equity data.

## Audit trace

Starting from an original decision returns ordered, correlated source records for input, available data/discovery/normalization/features/Trust/agents/candidates, decision or explicit NO_ACTION, route, Risk, quote, build, simulation, approval, execution, position/exit, outcome and scorecard.

Stages actually recorded are labeled `RECORDED`; others are `UNAVAILABLE_OR_NOT_APPLICABLE`. `complete_for_recorded_scope` requires connected INPUT → DECISION/NO_ACTION → OUTCOME → SCORECARD evidence and all referenced events. It does **not** claim absent stages ran successfully. Standalone execution records retain actual risk/input evidence and explicitly flag an unavailable upstream catalog link.

Audit projections contain concise scalar summaries, reason codes and digests rather than raw provider/transaction payloads, wallet signing material or agent reasoning summaries. Configured secrets, credential-like values, private material and hidden-reasoning keys are refused. Source records are never treated as instructions. Hashes detect accidental/tampered journal inconsistencies; this is not an externally signed audit attestation.

## API and Terminal surface

All new endpoints are typed, GET-only and non-executable:

| Endpoint | Result |
| --- | --- |
| `/api/scorecard` | Current mode-scoped evaluations and descriptive metrics |
| `/api/scorecard/{evaluation_id}` | Retained immutable evaluation, explicitly historical rather than current state |
| `/api/audit` | Ordered audit events referenced by the selected evaluations |
| `/api/audit/decisions/{decision_id}` | Decision trace with stage availability and connected evaluations |

Filters: decision, ticker, data mode, scorecard type, outcome, execution status, timezone-aware after/before/as-of, offset and limit. Cross-mode requests, future cutoffs, inverted date ranges and extra authorization/execution parameters fail closed. Default page size 25, maximum 100, maximum offset 10,000. Original Exposure proposals are read without the earlier API's current-time expiry projection.

Operational inspection limits are explicit: 100 original proposals/scans/plans/agent runs/execution rows, 500 evaluation cards per capture, 100 projected historical episodes, 500 execution journal versions, 2,000 events per scorecard and 20,000 events per capture/stored catalog inspection. Existing Terminal/replay limits also apply. Exceeding a bound returns unavailable rather than silently claiming completeness. A latest execution updated after a historical cutoff is withheld; earlier execution/position snapshots are not reconstructed. Retained immutable evaluation IDs preserve previously captured views. Unrecorded evicted DEMO artifacts and very large catalogs require a later operational extension.

At `#terminal`, **Scorecard & audit** opens the existing analytical surface's new evaluation panel. Type/ticker/outcome filters, independent pagination and per-decision trace buttons use backend APIs. Exact decimal strings, source/correlation IDs, timestamps, route estimates, unknown metrics, abstention and synthetic/no-execution distinctions are rendered. Loading, empty, stale/historical labeling, unavailable, API-error clearing and recovery are supported. React performs no authoritative score, route, cost or P&L arithmetic. Existing Overview Trust behavior and locked production navigation are unchanged.

## Validation

| Check | Result |
| --- | --- |
| Full backend suite | **1,306 passed**, three inherited warnings |
| Focused Phase 13 suite | **51 passed** |
| Complete inherited backend regression, including Phases 6–12 | **1,255 passed**; also included in the full suite |
| Full frontend suite | **211 passed** across 11 files, including **22 Phase 13 tests** |
| Typecheck/build | PASS; `npm run build` includes `tsc --noEmit` |
| Ruff/format | PASS |
| Secret/bundle/Git-ignore/Docker-exclusion checks | PASS |
| Python/Node dependency consistency | PASS: `pip check`, `npm ls --all`; no new CVE/entitlement claim |
| Browser | PASS: desktop 1440px/mobile 390px, Scorecard/Audit plus six existing DEMO scenarios, ordinary Overview and blocked portfolio smoke; 65 local requests, no live calls/runtime errors/page overflow |
| Source/gate/history comparison and whitespace | PASS; authoritative safety engines, master, gates and production data unchanged |

Focused coverage includes all scorecard types, explicit policy-quality predicates, safe unsupported requests, valid Direct Exposure normalization, route comparison and unknown actual costs, agent-only decisions, canonical simulated/submitted/unknown/confirmed/reconciliation states, actual existing portfolio completion/ownership bindings, paper accounting reuse, original-input immutability, atomic references, restart/concurrency/tamper protection, point-in-time targets, exact Decimal metrics, missing truth, filters, GET-only APIs, provider/mutation prohibition, LIVE_READ_ONLY separation, no secrets/hidden reasoning and unavailable-source behavior.

Existing tests were not removed or weakened. Only the exact security route allowlist was extended for the four GET endpoints. The full suite's warnings are inherited Starlette TestClient deprecation and two intentional malformed-allowance serialization warnings. No inherited timing assertion or timeout was relaxed. Browser harness development corrected an option-versus-record wait, reset an already-used isolated paper ledger after its risk rejection, and waited for server readiness; the final successful run retained every product safety control. All four owned test servers and the disposable Chrome instance were stopped; unrelated services were untouched.

Evidence: [verification](evidence/PHASE_13_VERIFICATION.json), [browser](evidence/PHASE_13_BROWSER.json), [isolated synthetic API/point-in-time examples](evidence/PHASE_13_SYNTHETIC_API.json). Synthetic examples are not provider, market-history or live-settlement verification.

## Production readiness and gates

- **IMPLEMENTED: PASS** — deterministic three-type evaluation, append-only audit, original-input protection, current/historical APIs and backend-authoritative Terminal presentation.
- **PROVIDER-VERIFIED: PARTIAL, unchanged** — no external provider calls in Phase 13. Existing production-compatible discovery/routing/quote interfaces are preserved. Missing provider data stays unavailable.
- **EXECUTION-VERIFIED: BLOCKED for live operation** — validated synthetic contracts and canonical settlement handling are tested; actual provider simulation/execution equivalence, RFQ settlement and Agentic Wallet runtime verification remain absent.
- **LIVE-READY: BLOCKED** — no signing, swap/RFQ execution, broadcasts, wallet changes or funds movement occurred.

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

Remaining external blockers: independent equity entitlement/current alignment verification; relevant executable-market liquidity and complete news evidence; historical share-ratio/as-of evidence and qualifying real 30/30/3 samples; Phase 7 real-input/complete inventory/funding/host assembly; actual route/build/simulation equivalence; RFQ settlement safety; actual Agentic Wallet runtime. Evaluation limitations additionally include unavailable independent classification truth/realized costs, no composite score formula, bounded catalogs and unreconstructed earlier execution/position snapshots. None was bypassed or reclassified as passed.

## Complete file inventory

Existing files changed additively:

- `backend/app/api/middleware.py` — post-decision evaluation capture.
- `backend/app/main.py` — mode-isolated store/service lifecycle and GET routers.
- `backend/app/repositories/execution.py` — validated read-only execution history.
- `backend/app/repositories/exposure.py` — original immutable proposal catalog.
- `backend/app/repositories/opportunity_scan.py` — validated scan catalog.
- `backend/app/repositories/portfolio.py` — validated plan catalog.
- `backend/app/services/demo_opportunity.py` — bounded read-only DEMO analysis snapshots.
- `backend/app/services/demo_paper.py` — bounded validated existing ledger inspection.
- `backend/app/services/demo_preparation.py` — read-only artifact snapshots and typed quote/preparation attempt retention.
- `backend/tests/security/test_boundaries.py` — four GET route allowlist entries.
- `frontend/src/components/Terminal.tsx` — explicit evaluation entry.
- `frontend/src/styles.css` — scoped evaluation controls/mobile wrapping.

New files:

- `backend/app/models/scorecard.py` — typed evaluation, audit, query, page and trace contracts.
- `backend/app/repositories/scorecard.py` — immutable atomic evaluation/audit storage.
- `backend/app/services/audit.py` — structured safe source projections and trace assembly.
- `backend/app/services/scorecard.py` — deterministic evaluation of existing authorities.
- `backend/app/api/scorecard.py` — four non-executable GET endpoints.
- `backend/tests/integration/test_scorecard.py` — 51 focused cases.
- `frontend/src/components/ScorecardAudit.tsx` — evaluation and trace presentation.
- `frontend/src/services/scorecard.ts` — read-only API and mode/safety/exact-string validation.
- `frontend/src/test/ScorecardAudit.test.tsx` — 22 frontend cases.
- `frontend/src/test/scorecardFixtures.json` — isolated existing-API synthetic fixtures.
- `docs/PHASE_13_REPORT.md` — this report.
- `docs/evidence/PHASE_13_VERIFICATION.json` — validation, invariants and exact inventory.
- `docs/evidence/PHASE_13_BROWSER.json` — actual isolated browser results.
- `docs/evidence/PHASE_13_SYNTHETIC_API.json` — source-derived examples for all three types and immutable point-in-time targets.

**Stop:** Phase 13 only. Phase 14 was not started; no commit or push.
