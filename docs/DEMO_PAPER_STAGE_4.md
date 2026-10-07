# Hackathon DEMO Stage 4 — Paper Execution, Position and Scorecard

Status: PASS, scoped to the isolated synthetic sandbox. No production phase or execution gate has advanced. No commit was made.

## Audit and integration

Stage 3B already provided deterministic Opportunity/Risk, synthetic quotes, unsigned logical request manifests and local simulation. There was no position, paper accounting or scorecard implementation to reuse. Stage 4 retains those services and their contracts; the preparation adapter now retains bounded server-generated simulation references. A DEMO-only `DemoPaperLedger` consumes those references and reuses the existing `RiskEngine` and `SimulationService` immediately before recording a fill.

The ordinary `RUNTIME_MODE=LIVE` path never constructs this ledger or registers its APIs. Global application configuration remains DRY_RUN/PROPOSE_ONLY, required simulation and disabled live trading. PAPER is a record label, not a new global execution configuration or permission.

## Ledger and idempotency

One DEMO backend owns one memory-only ledger. It has no database, provider, network, signing or wallet interface. Paper orders, fills, positions, events, observations, exits, P&L and scorecards carry `source=DEMO`, `execution_mode=PAPER`, `production_eligible=false`, synthetic fixture provenance and false signed/broadcast/funds-moved flags.

Records are serialized snapshots; returning a record does not expose mutable ledger internals. A lock covers lookup, current risk/local constraint verification and insertion. A prepared request ID maps to one position; deterministic paper order/fill/position IDs derive from its fingerprint. Repeating the same request/proof returns the existing lifecycle, including after quote expiry or position exit. Concurrent retries create one fill. A different proof on an existing request is rejected. A hard 64-position capacity refuses new fills rather than deleting idempotency or financial history.

For a new fill, the server requires its own cached SIMULATION_PASS, matching preparation/fingerprint and unexpired quote/request/proof, approved preparation/quote Risk, unchanged market/economic inputs and a fresh local simulation. Risk is recalculated from ledger-adjusted available cash, open exposure, realized daily losses, trade count and last entry/cooldown using the unchanged Risk engine and synthetic policy. Rejection writes no order, fill, position or event.

Restart clears this sandbox ledger and its references. This is session-state idempotency, not durable restart recovery or production position persistence. Use a fresh DEMO backend for another complete walkthrough of the fixed synthetic session; the ledger does not reset itself on scenario changes or bypass financial limits to permit repeated trades.

## Lifecycle, costs and scorecard

1. Fill creates one PAPER_FILLED order, an exact quote-bound synthetic fill, one OPEN position and ENTRY event. Quantity, slippage-adjusted entry price, notional, fees, gas and reserve come from the quote.
2. Explicit Monitor loads the captured `data/demo/paper/exit.json` fixture, advances synthetic time five minutes after entry, and records one MONITOR event. Repeating Monitor while OPEN returns the existing observation. This is an illustrative synthetic observation, not a real opening bar, provider read or calibrated forecast.
3. Exit requires that OPEN position and its recorded observation ID. It creates one synthetic exit, marks EXITED, records EXIT and calculates realized P&L. Exit before Monitor, a wrong observation, repeated Exit, or Monitor after EXITED is rejected.
4. Scorecard is available only after Exit and derives entry, exit, recalculated P&L, source IDs, classification, confidence, synthetic evidence quality, Risk, simulation and reasons from the stored lifecycle. There is no separate hardcoded scorecard object.

All arithmetic uses bounded Decimal inputs, precision256 intermediates and 18-decimal floor rounding for return percentage. With quantity `Q`, slippage-adjusted entry price `Pe`, slippage-adjusted synthetic SELL price `Px`:

```text
gross P&L = Q × (Px − Pe)
costs = entry fees + entry gas + exit fees + exit gas
net P&L = gross P&L − costs
entry cost basis = entry notional + entry fees + entry gas
return % = 100 × net P&L / entry cost basis
```

Slippage is embedded in the two prices and is not charged again. The entry execution buffer is held as a reserve while OPEN, released at Exit and excluded from paid costs. Available synthetic cash and realized loss are derived from the same records. Tests vary entry, exit, quantity and winning/losing outcomes; P&L is not stored as a fixed fixture outcome.

Default Information example (synthetic only):

| Field | Result |
|---|---|
| Entry quantity | 0.978435286290164768 tokens |
| Entry price | 51.10200 USD/token |
| Exit mark | 53 USD/token |
| Exit price with 20bps SELL slippage | 52.894 USD/token |
| Gross P&L | 1.75335603303197526425600 USD |
| Entry + exit costs | 0.30 USD |
| Net P&L | 1.45335603303197526425600 USD |
| Return on entry cost basis | 2.898018012027866929% |

## Scenario behavior

| Scenario | Analytical result | Paper result |
|---|---|---|
| NORMAL / steady | NO_OPPORTUNITY; Risk FAIL | No quote, order, fill, position or P&L |
| LIKELY_NOISE / thin-move | REJECTED_BY_TRUST; Risk FAIL | No quote, order, fill, position or P&L |
| LIKELY_INFORMATION / supported-move | ACTIONABLE; Risk PASS | QUOTED → PREPARED → SIMULATION_PASS → PAPER_FILLED → OPEN → Monitor → EXITED → P&L → Scorecard |

Information is an analytical classification supported by synthetic evidence. It is never represented as a passed production Trust gate.

## API and UI walkthrough

Only DEMO registers these endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/demo/paper/fills` | Request one paper fill by `transaction_id` and `simulation_id` only |
| GET | `/api/demo/paper/positions/{position_id}` | Retrieve a recorded lifecycle without analytical-cache TTL |
| POST | `/api/demo/paper/positions/{position_id}/monitor` | Explicitly load the marked synthetic observation; empty body |
| POST | `/api/demo/paper/positions/{position_id}/exit` | Close the paper position by recorded `observation_id` only |
| GET | `/api/demo/paper/positions/{position_id}/scorecard` | Derive the exited position's scorecard |

Unknown/expired references return410; rejected constraints/transitions return409; malformed or extra body fields return422; query flags are rejected404. No endpoint accepts arbitrary quantities, fills, prices, execution flags or client-generated simulation results.

From the repository root, start your DEMO backend and frontend in separate terminals. Use only an available port/your own stopped instance; do not terminate unrelated existing services.

```sh
RUNTIME_MODE=DEMO DATA_MODE=DEMO EXECUTION_MODE=DRY_RUN \
  APPROVAL_MODE=PROPOSE_ONLY LIVE_TRADING_ENABLED=false REQUIRE_SIMULATION=true \
  .venv/bin/python -m uvicorn app.main:create_app --factory \
  --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log

npm run dev
```

At localhost:5173 select supported-move and click: Run demo scenario → Analyze Opportunity → Analyze Risk → Generate DEMO Quote → Prepare DEMO Transaction → Run DEMO Simulation → Create Paper Fill → Monitor Synthetic Opening Observation → Exit Paper Position → View Paper Scorecard. Quote validity remains30 seconds; complete preparation/simulation/fill promptly. An already-filled paper position may be monitored/exited and its scorecard retrieved after analytical expiry. Retrieve Paper Fill reuses the same IDs. Upstream artifacts are locked after a fill so they cannot replace the displayed lifecycle.

UI extends the existing sandbox and shows DEMO SANDBOX, SIMULATED DATA — NOT LIVE TRADING, PAPER EXECUTION, NO REAL FUNDS MOVED, UNSIGNED DEMO PREPARATION, NOT BROADCAST, LOCAL DEMO SIMULATION and NOT ON-CHAIN EXECUTION. Default LIVE UI/navigation is unchanged. No downstream stage runs automatically.

## Verification and production boundary

- Backend: 467 tests pass, including25 new paper tests; existing442 tests retained.
- Frontend: 146 tests pass, including18 new paper tests; existing128 tests retained.
- TypeScript noEmit / Vite build: PASS.
- Ruff check and format: PASS.
- Established security scan and extended configured-secret scan: PASS.
- Actual built UI / actual DEMO APIs: desktop1440 and mobile390 widths, all three scenarios PASS; Information completes scorecard and repeated fill, no errors/overflow. Separate disposable DEMO backends ensure independent financial state for each viewport. 10 paper API calls; zero live provider or live execution calls.
- Automated lifecycle tests forbid provider construction, network transport/socket connections and verify empty production Trust tables. Default LIVE never constructs the ledger or exposes paper APIs.
- All eight existing database files and their table counts unchanged. Production core services, Trust policy/classifier, gate specifications/evidence, original fixtures, prior tests/reports and saved timestamp-alignment diagnostic unchanged.

See [machine verification](evidence/DEMO_PAPER_STAGE_4_VERIFICATION.json) and [browser evidence](evidence/DEMO_PAPER_STAGE_4_BROWSER.json).

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

No wallet, signing, order submission, broadcast, SWAP, RFQ, Agentic Wallet or other external execution occurred. Local simulation remains a deterministic constraint check, not on-chain simulation. No synthetic history entered production coverage; real 30/30/3 deficiencies remain unresolved.

## Files and remaining polish

Changed: `README.md`, `backend/app/main.py`, `backend/app/services/demo_preparation.py`, `frontend/src/components/DemoPreparationFlow.tsx`.

Added: `backend/app/models/demo_paper.py`, `backend/app/services/demo_paper.py`, `backend/app/api/demo_paper.py`, `data/demo/paper/exit.json`, `backend/tests/unit/test_demo_paper.py`, `backend/tests/integration/test_demo_paper_api.py`, `frontend/src/services/demoPaper.ts`, `frontend/src/components/DemoPaperFlow.tsx`, `frontend/src/test/DemoPaperFlow.test.tsx`, `frontend/src/test/demoPaperFixtures.json`, this report and the two evidence JSON files linked above.

Stage4 is complete. Before presenting, launch a fresh explicitly marked DEMO session and rehearse the manual30-second quote window. Optional later polish includes shorter display formatting, lifecycle navigation/export and durable isolated paper-session storage; these are not implemented here. Production Trust remediation and live execution remain separate blocked work. Stop at this milestone; no next phase was begun and no automatic commit was made.
