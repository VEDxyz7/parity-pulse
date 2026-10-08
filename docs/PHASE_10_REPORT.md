# Master Phase 10 — Position Management

Authority: `docs/MASTER_SPEC.md`, October 7 VERIFIED_v2. All 5,321 lines were read before coding. Starting commit: `28f2f408b2ac40ff400e0bc173ae5e3d2a9b1a18`; initial working tree was clean. Scope is persistent non-live lifecycle machinery only. Accepted Phase 6 non-live PASS and Phase 7/8/9 PARTIAL scopes are preserved.

**PHASE_10_IMPLEMENTATION=PASS** — persistent non-live lifecycle acceptance only.

This is not a live position-management readiness claim. Automated execution evidence is explicitly synthetic; no actual account trade/position was created or imported during this task. No provider, wallet execution, RFQ submission or broadcast endpoint was called.

## Audit and integration

The existing `DemoPaperLedger` implements the judge-facing synthetic paper lifecycle in memory. It remains unchanged, separate from canonical positions and incapable of populating production history. Phase 8/9 already provide durable immutable execution IDs, settlement proofs, bounded read-only status tracking and hard-blocked execution gateways. Phase 10 adds one canonical `PositionService` and `PositionStore` around those contracts, rather than duplicating the paper engine or execution services.

The app initializes the position service after the execution journal, makes one bounded startup recovery pass, and closes both stores on shutdown. Two new API operations are inspection only: `GET /api/positions?limit=100` and `GET /api/positions/{position_id}`. No public endpoint accepts position facts, imported execution proofs, lifecycle mutations or exit requests. Evidence ingestion and exit preparation are trusted-host methods; client/agent output is not an authority for them.

## Durable model and provenance

One local account scope and the existing active wallet context are retained; no multi-tenant or multi-wallet system was added. The SQLite position payload includes:

- Position UUID, fixed local account scope, ticker/company, discovered representation, token/contract/chain, issuer/platform and decimals.
- Positive shares-per-token ratio, observation/availability timestamps and source. The ratio must have been available by the entry quote request, match the token identity and retain its original mode; today's ratio cannot be backfilled into an older entry.
- Requested quantity as the **original quoted output estimate**, actual confirmed received quantity, and confirmed remaining holding in canonical uint256 base-unit strings. Decimal token quantities, original and remaining normalized share exposure are derived from those persisted values.
- Full Phase 8/9 entry and exit snapshots, execution/request/decision IDs, wallet, platform order ID, immutable transaction hash, route/build fingerprint, risk/funding/quote/simulation metadata and actual settlement timestamps where available.
- Intended post-open holding policy, NYSE calendar version, regular opening and exit due timestamps, current/close state, append-only applied exits and optional as-of settlement valuations.
- Created/updated timestamps, lifecycle version, reasons, one stable linked monitor job, retry count, next check, lease identity/expiry and durable exit intent/decision.

Financial arithmetic uses integer base units and Decimal with an explicit 160-digit context. Floats are not accepted as financial quantities. Ratios and financial inputs retain the existing precision bounds. Fee/gas estimates in the stored quote remain estimates; they are never promoted to actual costs.

Storage is under the configured database file's parent: `positions/phase10/<DATA_MODE>/positions.sqlite`, alongside the existing `execution/phase8/execution.sqlite`. Position changes and corresponding history events commit in one SQLite transaction. Unique entry-execution ownership prevents duplicate positions; version compare-and-swap prevents stale writes and duplicate job claims. Payload hashes, row bindings, complete event history, legal transitions and exact historical execution-journal snapshots are checked on load/write. Hash checks detect accidental corruption; they are not a cryptographic proof against a privileged actor rewriting the database.

Production canonical runtime refuses `sqlite:///:memory:`. Tests and the explicit DEMO runtime can use memory. DEMO runtime never touches these on-disk canonical stores. `DEMO` and `LIVE_READ_ONLY` position directories and queries are separate, and fixture proof cannot be relabelled as real-provider evidence.

## State machine and reconciliation

| Current state | Allowed different states |
|---|---|
| PROPOSED | OPENING, OPEN, FAILED, UNKNOWN, RECONCILIATION_REQUIRED |
| OPENING | OPEN, FAILED, UNKNOWN, RECONCILIATION_REQUIRED |
| OPEN | EXIT_PENDING, UNKNOWN, RECONCILIATION_REQUIRED |
| EXIT_PENDING | EXITING, OPEN, CLOSED, UNKNOWN, RECONCILIATION_REQUIRED |
| EXITING | OPEN, CLOSED, UNKNOWN, RECONCILIATION_REQUIRED |
| UNKNOWN | OPENING, OPEN, EXIT_PENDING, EXITING, CLOSED, FAILED, RECONCILIATION_REQUIRED |
| CLOSED / FAILED / RECONCILIATION_REQUIRED | No reopening or automatic escape |

Same-state audited updates are allowed for jobs/evidence/valuations, with version checks. Every transition also has quantity, identity and evidence prerequisites; the table does not authorize transitions by itself. CLOSED may receive append-only valuation inputs, but cannot reopen.

Only an execution journal snapshot that passes the unchanged Phase 8/9 `EXECUTION_CONFIRMED` settlement validation can supply entry timestamp/filled quantity and establish OPEN. A quote, successful simulation, pending order or unknown status creates no holding. OPEN additionally requires a persisted deterministic schedule. A known confirmed entry stays linked to its exact immutable proof on restart; quote/route/request identities cannot be rebound.

Pending entries use the existing `ExecutionStatusTracker` on the exact known order/hash. Complete matching terminal success opens the recorded quantity; terminal failure makes entry FAILED; missing provider/unknown status becomes UNKNOWN. Conflicting hashes and settlement identities become sticky RECONCILIATION_REQUIRED without replacing the known hash. Reconciliation never creates a replacement order. A valid external pending exit is EXITING; uncertainty does not subtract any holding. Only matching confirmed exit evidence subtracts the proven sold token units. CLOSED requires complete confirmed disposition and its settlement timestamp.

The application execution service now has a restrictive position interlock for preparation and requote. Unfinished recovery, pending/unknown/reconciliation-required positions, leased monitoring or an unlinked exit intent block new dependent preparation. The owning deterministic exit decision can resume its own persisted intent; other decisions cannot consume it. Existing Risk, Funding, simulation, confirmation, wallet quota and LIVE gate rules are unchanged.

## Restart recovery and bounded scheduler

`PositionService.recover()` restores a bounded batch (default 100, host maximum 1,000), checks existing journal evidence and restores the persisted job without inventing identities. If the batch is incomplete, dependent preparation remains blocked. Closed/failed historical records do not displace active positions from the monitor batch.

Each position has exactly one monitor job in its atomic payload. A compare-and-swap claim establishes a 30-second lease. Another worker cannot poll that job while the lease is active. An interrupted worker's expired lease can be reclaimed. Status reads are bounded to one per pending leg per pass, spaced by persisted checks at least 60 seconds apart during ordinary monitoring. Three unresolved automatic attempts block the job and preserve UNKNOWN; restart does not reset the cap. Explicit host reconciliation may inspect existing evidence again, but never retries an order. Confirmed OPEN holdings wait until their stored due time; no aggressive background polling loop was added.

One-shot host command from the repository root:

```sh
.venv/bin/python scripts/monitor-positions.py --limit 100
```

It uses the current configured mode/database and one bounded lifespan recovery pass. It only reads existing status and records due exits; it does not prepare quotes or invoke wallet commands. A host scheduler can invoke it once per minute. Installing such a scheduler or enabling a trading daemon was not part of this milestone. Without that host invocation, recovery runs at app startup and monitoring is available through the internal service; no continuously running worker is implied.

Restart tests cover OPENING, OPEN, EXIT_PENDING, EXITING, UNKNOWN, interrupted monitor leases, a crash after a terminal execution poll was persisted, and a crash after exit preparation but before linking its execution to the position. A separate Python process also reads the same durable position/execution/job identities. There is no duplicate entry/exit, no timeout resubmission and no new identity invented during recovery.

## Deterministic exit and partial holdings

`POSTOPEN_EXIT_MINUTES=10` is configurable as integer minutes 1–120. Calendar calculations use the existing verified NYSE schedule in America/New_York and persist UTC. The exit is due after the first verified regular opening at or after entry settlement; weekends, holidays, early closes and DST use that same calendar. This policy does not guess an opening outside verified calendar coverage. Calendar/version disagreement requires reconciliation rather than silently rescheduling. Exit preparation is rejected before due time, after that scheduled regular session, or without current safety evidence. An overdue holding stays recorded; there is no next-day automatic exit policy or direct liquidation fallback.

`prepare_exit()` first checks proven OPEN exposure, known execution/hash, immutable schedule, due window, mode/wallet/token identity and a positive quantity not exceeding the holding. It persists an exit intent with a deterministic decision ID based on position, exit ordinal and requested sold units **before** calling the existing Phase 8 service. Crash recovery finds that same decision in the execution journal. A different size/decision cannot replace an unresolved intent.

The existing flow is reused: Risk → Funding → Quote → Build/fingerprint → exact Simulation → wallet controls/ExecutionGateway. Fresh host-supplied risk evidence, held-token funding balance/price/native gas state and allowance are required. No equity/Trust evidence or expected edge is invented for an exit. If those existing services reject the evidence, the exit remains blocked. Prepared exits are EXIT_PENDING with DRY_RUN reasons, retain the holding and never become CLOSED merely because simulation passed. The app uses the existing Phase 9 gateway, whose disconnected/unverified wallet and unchanged LIVE gates remain blocking.

Requested and received entry output can differ; they are not collapsed into one value. Confirmed sales of only a portion of a holding keep the remainder OPEN, preserve the completed exit and require a new deterministic intent for any later reduction. A pending/unknown partial exit is not presumed filled. Published [Binance Trading API](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/trading-api) status contracts provide terminal amounts, but the currently verified RFQ contract does not provide a usable intermediate partial-fill state. The tests distinguish smaller-than-quoted confirmed entry output from a claimed unfinished partial RFQ fill. Real intermediate partial-fill support remains an external evidence limitation, not a fabricated provider capability.

## P&L inputs, not Phase 13

Raw entry sell units, actual received units, confirmed exit sell/receive units, decimals, ratio/as-of data, timestamps, route/execution metadata and native fee units are durable. Entry notional and average per-token/per-share cost are derived only from matching fresh as-of funding evidence or an explicit host-verified settlement valuation. An exit cash-to-USD valuation must bind the exact confirmed execution, cash contract, mode and an available-as-of reference within 120 seconds. No stablecoin parity is assumed.

When those inputs exist, gross P&L uses actual received exit cash and the proportional entry cost of the confirmed sold quantity. Net P&L additionally requires explicit actual fee and gas USD inputs for every included execution; unknown costs stay null, not zero. Optional valuation/cost receipts are trusted-host evidence and append-only. No new production fee/reference provider was integrated. Holding duration, original/remaining share exposure and unavailable cost fields remain explicit. No Phase 13 scorecard, ranking, attribution or new DEMO financial engine was implemented; the existing DEMO scorecard remains unchanged.

## Validation and evidence

Final exact results are recorded in `docs/evidence/PHASE_10_VERIFICATION.json`; desktop/mobile regression evidence is in `docs/evidence/PHASE_10_BROWSER.json`.

| Check | Final result |
|---|---|
| Complete backend suite | 1,118 passed, 0 failed; 3 existing warnings |
| New Phase 10 lifecycle tests (included above) | 57 passed |
| Separate Phase 6–9 remediation regressions | 99 passed, 0 failed; 3 existing warnings |
| Frontend suite | 173 passed in 9 files |
| Typecheck and Vite build | PASS |
| Ruff / format | PASS; 179 Python files formatted |
| Established security check | PASS |
| Python/Node dependency consistency | PASS |
| Desktop/mobile browser regression | 6 scenarios PASS; 39 local API requests; 0 live-execution calls |
| Preservation baseline | 378 of 384 original artifacts byte-identical; only the 6 explicitly listed existing files changed |

The initial 70-test baseline covered existing paper endpoints and settlement/quota remediation. New tests cover creation, strict/invalid transitions, quantities, malformed/forged evidence, mode/as-of isolation, terminal failure, hash conflict, deterministic/DST/holiday exit timing, premature/late/oversized exits, downstream preparation/wallet controls, current safety evidence failure, partial exits, P&L availability, persistence, process restart, poll/preparation crash windows, simultaneous job claims, retry exhaustion and unchanged production gates. Existing security allowlist assertions were extended by the two GET routes and explicit POST-denial assertions; no existing endpoint restrictions or tests were removed.

Established dependency checks are `pip check` and `npm ls --all` (dependency consistency, not a new vulnerability scan). Security audit covers configured-secret leakage, environment ignore/exclusion and frontend isolation. Validation performs no real provider/wallet execution. Existing warning limitations are the Starlette/httpx deprecation and two Pydantic serializer warnings from deliberate malformed allowance fixtures.

## Current gates and remaining blockers

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

These are unchanged. The authoritative master, prior gate files, Trust thresholds/30–30–3 safeguards, Risk rules, wallet restrictions, settlement confirmation contracts, DEMO fixtures and production historical data are preserved.

Remaining blockers: authoritative production Trust/input coverage and Phase 7 host assembly; real route/simulation/gas/effect equivalence and independently passing LIVE gates; RFQ settlement equivalence; verified current Agentic Wallet runtime/preview/controls; authoritative intermediate partial-fill and complete actual cost/USD evidence. The machinery supports verified external observation through trusted host methods, but this run did not verify a real externally open position or perform live entry/exit. No automatic import guesses missing representation ratios, route facts or IDs. Unknown or corrupted records require host review.

## Files changed and stop condition

- `backend/app/models/position.py` — durable contracts and exact derived financial inputs.
- `backend/app/repositories/position.py` — SQLite lifecycle/job/event persistence and identity/CAS checks.
- `backend/app/services/position.py` — reconciliation, restart monitoring, deterministic exit intents and existing preparation adapter.
- `backend/app/api/positions.py` — two read-only inspection operations.
- `backend/app/main.py` — startup recovery, stores/service/interlock and shutdown.
- `backend/app/config.py`, `.env.example` — exit timer and production durable-storage requirement.
- `backend/app/services/execution.py` — restrictive unresolved-position preparation/requote interlock only.
- `scripts/monitor-positions.py` — bounded one-shot read-only monitor.
- `backend/tests/unit/test_position.py`, `backend/tests/integration/test_position_api.py` — lifecycle and adversarial/restart coverage.
- `backend/tests/security/test_boundaries.py` — exact GET allowlist extension with POST denial.
- `README.md` — Phase 10 storage/API/monitor runbook.
- `docs/PHASE_10_REPORT.md`, `docs/evidence/PHASE_10_VERIFICATION.json`, `docs/evidence/PHASE_10_BROWSER.json` — report and fresh evidence.

**PHASE_11_STARTED=false.** No Autopilot, portfolio allocation, drift bands, rebalancing or BTC/ETH feature was implemented. No automatic commit or push. Work stops after Phase 10.
