# Master Phase 12 — Terminal + Analytics

PHASE_12_IMPLEMENTATION = PASS for the backend-authoritative, read-only analytical surface. Provider verification remains PARTIAL and live execution remains BLOCKED. No Phase 13–18 work was performed, and no commit or push was made.

## Authority and scope

The complete authoritative `docs/MASTER_SPEC.md` was read before coding: 5,321 lines, SHA-256 `f69a9bd01a622c001c3ec6cb654e00562f6b3d03a8310f9e5ccf68efe4b49c84`. Baseline commit: `e4bdaeeab4d7c080a1ae79a115a11277c8d48c68`. Existing discovery, normalization, Trust, agents/retrieval, routing, quotes, execution journals, research replay, positions and portfolio services were inspected and retained.

This milestone adds an observation surface, not a financial decision or execution engine. Existing Trust thresholds, 30/30/3 safeguards, Risk rules, routing ranking, execution invariants, wallet controls, position transitions and portfolio state semantics are unchanged. Historical reports, production observations and the master specification remain unchanged.

## Architecture and authoritative values

`TerminalService` composes existing mode-scoped repositories and deterministic services. It never refreshes a provider, assesses Trust, invokes agents, requests quotes, builds transactions, simulates, reconciles positions or evaluates portfolio plans. Repository additions are read-only catalog/latest methods using existing schema/checksum validation. The application exposes the existing Phase 5 research store by default and permits a host-supplied isolated research store for tests.

The frontend adds **Terminal** navigation at `#terminal`. It requests the backend overview, verifies its mode and safety envelope, and renders exact decimal strings, identifiers, timestamps, reasons and provenance. Financial arithmetic stays on the backend. React only adds display labels and controls filtering/pagination. Loading and API errors clear previously displayed values; there are no financial fallback fixtures in the production component. DEMO and LIVE_READ_ONLY responses are checked separately; embedded synthetic evidence is refused in a LIVE_READ_ONLY frontend response.

### Issuer board and normalized prices

Each cached representation is identified by ticker, chain and contract. Metadata and prices are selected deterministically by their actual availability/observation times with explicit conflict detection. Existing `effective_price_per_share` and `comparable_economics` compute normalized cost and deviation using Decimal; the backend projects percentage deviation and signed USD/share spread. For the isolated test example, $10.2/token divided by 0.1 shares/token yields $102/share against an independent $100/share reference, with $2/share spread and 2.00% deviation. These are synthetic acceptance inputs, not current market prices.

Independent references use existing Trust reference validation: source identity, regime/calendar, freshness, actual provider timestamp alignment and the previous regular close when appropriate. Binance `referencePrice` is never used as an independent reference. Missing/stale/conflicting references suppress comparison values; valid token-only normalization can remain available with the independent-reference limitation. Unverified issuer mappings or normalization inputs suppress normalized values. Liquidity uses existing verified-unit evidence validation. Provenance includes source/provider identifiers, record digest, observed time, available time, ratio timing and normalization version.

### Trust and agent evidence

The monitor loads existing persisted deterministic Trust assessments. Absent or stale assessments show `INSUFFICIENT_EVIDENCE`; stale original classifications remain explicitly historical. The projection includes confidence, reference/deviation/liquidity, regime, news coverage, baseline/analogue counts and missing-input reasons. It does not manufacture a new assessment or override the production gate.

Agent views retain the existing typed Phase 6 outputs, confidence tiers, evidence references, conflicts, decision/rejection reasons, model/provider identity and timestamps. Retrieved recent memory uses the existing decision-time retrieval boundary. Responses, evidence and memory are bounded. Hidden reasoning/chain-of-thought, private keys, signing data and transaction payloads are excluded; a forbidden projection or configured credential value fails closed.

### Execution, position and portfolio analytics

Execution analytics read canonical Phase 8 journals and Phase 10 position links. They distinguish `PROPOSED`, `DRY_RUN`, `SIMULATED`, `SUBMITTED`, `CONFIRMED`, `FAILED`, `UNKNOWN`, `RECONCILIATION_REQUIRED` and `BLOCKED`. A simulated/quoted/submitted quantity is never counted as a fill or completed trade. `TEST_FIXTURE` confirmations are labeled synthetic and never treated as real trades.

The view preserves actual stored quote ID, provider/vendor, execution mode, fingerprint, simulation result, Risk/Funding status and recorded quote latency. Confirmed fill price/quantity/actual fees come only from persisted settlement. Gas provider units remain separate from USD network-fee estimates. Remaining ownership and realized P&L come from Phase 10, with stale embedded execution snapshots marked reconciliation-required rather than used as current holdings. Unknown or unconfirmed values remain null.

Portfolio context displays existing configuration version, pending plan and reasons. It does not calculate a new NAV or trigger a rebalance. Execution ticker filtering requires a verified linked position; unlinked proposals remain visible in the unfiltered view rather than receiving an invented ticker.

### Historical episodes

The Terminal reads existing checksum-validated Phase 5 replay runs without recomputing models, analogues or decisions. It exposes original decision time, feature availability, regime, eligibility, Trust state, prediction, retrieved analogue references, dataset/implementation digests and provenance. Opening outcomes are separate from decision inputs and appear only when their recorded availability is within the requested as-of cutoff. Advancing the cutoff does not alter the original features, prediction or retrieval. Future training/retrieval bindings and corrupt records fail closed. Post-hoc/unscorable targets are labeled and not presented as available decision-time outcomes. This milestone adds no qualifying real historical evidence.

## APIs and operational bounds

All seven new endpoints are GET-only, typed and non-executable:

| Path | Projection |
| --- | --- |
| `/api/terminal` | Combined analytical overview and portfolio context |
| `/api/terminal/issuers` | Issuer spread board |
| `/api/terminal/prices` | Same authoritative normalized-price projection |
| `/api/terminal/trust` | Persisted deterministic Trust evidence |
| `/api/terminal/agents` | Structured agent evidence and retrieval |
| `/api/terminal/executions` | Canonical execution/position analytics |
| `/api/terminal/episodes` | Point-in-time research episodes |

Responses include schema version, UTC generation/as-of timestamps, run/request/correlation IDs and the unchanged safety envelope. Query parameters are `ticker`, `limit` (default 25, maximum 100) and `offset` (maximum 10,000). Episodes additionally accept timezone-aware `as_of`; future cutoffs are refused. Extra mode/authorization/execution fields are rejected. Pagination reports `has_more`; it does not claim an invented total.

This initial implementation deliberately has bounded catalog inspection: fewer than 1,000 cached records per queried type, at most 100 agent/execution records, 1,000 inspected positions, 50 replay files of at most 2 MB each, and 5,000 episodes per replay. Exceeding these bounds fails explicitly with unavailable evidence rather than silently presenting a truncated complete catalog. Large-catalog server-side pagination/indexing is a remaining operational extension. Overview sections share an offset; dedicated endpoints permit independent pagination. No external data refresh is implied by **Refresh Terminal**.

## Routing and readiness

**IMPLEMENTED: PASS.** The Terminal consumes real provider-compatible cached contracts and canonical persisted quote/execution records. Existing production asset discovery, `RoutingService`, provider quote selection, Risk, build/fingerprint/simulation, wallet controls and ExecutionGateway remain the shared architecture. No DemoRouter, hardcoded issuer choice or parallel routing engine was introduced. A representation without an actual quote is explicitly `NOT_QUOTED`; analytics never fabricate a provider route to populate the board. Persisted quotes retain their real route/provider provenance.

**PROVIDER-VERIFIED: PARTIAL.** This milestone makes no external provider calls and does not repeat or supersede previous entitlement investigations. The LIVE_READ_ONLY contract test is an offline, production-ineligible schema probe, not proof of provider availability or real market coverage. Existing current independent-equity entitlement/alignment, verified relevant-market liquidity, historical ratio/as-of evidence, complete news coverage and qualifying 30/30/3 historical evidence remain external Trust blockers. Phase 7 real-input assembly and portfolio complete inventory/funding/host assembly remain partial.

**LIVE-EXECUTION-READY: BLOCKED.** Exact provider execution/simulation equivalence, RFQ settlement safety and the actual Agentic Wallet runtime remain unverified. There are no Terminal trading controls. No live signing, execution, broadcast, wallet mutation or funds movement occurred.

## Validation and evidence

| Check | Result |
| --- | --- |
| Full backend suite | **1,255 passed**, three existing warnings, 36.91 seconds |
| Focused Phase 12 integration suite | **43 passed**, 2.51 seconds |
| Targeted Phase 6–11 safety/position/portfolio regressions | **250 passed**, 9.05 seconds; also included in the full suite |
| Full frontend suite | **189 passed** across ten files, including 16 Terminal tests |
| Typecheck and production build | PASS (`npm run build`, includes `tsc --noEmit`) |
| Ruff / formatting | PASS |
| Project secret, bundle, Git-ignore and Docker-exclusion security audit | PASS |
| Python `pip check` / `npm ls --all` | PASS; dependency consistency checks, not a new CVE audit |
| Terminal browser E2E | PASS at desktop 1440px and mobile 390px: six sections, exact backend values, stale/insufficient evidence, empty filter, error clearing, recovery, disabled production actions and no page overflow |
| Existing demo browser regressions | Six PASS: NORMAL, NOISE and complete INFORMATION hero flows on desktop/mobile |
| Ordinary Overview / portfolio browser regression | Trust remains `INSUFFICIENT_EVIDENCE`; missing portfolio host inputs remain BLOCKED with null valuation, zero actions/broadcast |
| Safety-source hashes / Git whitespace | PASS; only additive integration/repository reads and Terminal UI changes |

Focused coverage includes normalization, multiple issuers, reference freshness/skew, missing/conflicting inputs, ratio validation, closed-session reference, stored Trust freshness, bounded agent evidence, canonical settlement/position reconciliation, synthetic labels, historical outcome cutoff, corrupt catalogs, pagination/filtering, GET-only API validation and no provider/state mutation. Existing tests were retained; only the exact route allowlist was extended for the seven GET endpoints. Three full-suite warnings are inherited Starlette TestClient deprecation and intentionally malformed allowance serialization warnings. No inherited wallet timing failure occurred in this full run; no timeout or assertion was relaxed.

Browser verification used the built frontend and actual isolated local backends with disposable synthetic stores. The 55 local API requests include eight Terminal reads and two deliberate 503 UI-error injections. Live provider/execution calls were zero. Screenshots were visually checked on desktop/mobile. An initial harness runtime-mode assertion and a startup race were corrected in the disposable harness; application assertions were retained. Owned browser/test servers were stopped; the user's services on ports 8000/5173 were untouched.

Evidence:

- `docs/evidence/PHASE_12_SYNTHETIC_API.json`: exact isolated analytical API response, explicitly synthetic and production-ineligible.
- `docs/evidence/PHASE_12_BROWSER.json`: local browser results, safety checks and request log.
- `docs/evidence/PHASE_12_VERIFICATION.json`: test commands/results, log hashes, inventory, baseline/safety hashes, readiness and gate status.

## Complete file inventory

1. `backend/app/main.py` — existing-service composition and GET-router registration.
2. `backend/app/agents/memory.py` — read-only validated run catalog.
3. `backend/app/repositories/execution.py` — read-only canonical execution catalog.
4. `backend/app/repositories/research.py` — bounded checksum-validated replay catalog.
5. `backend/app/repositories/trust.py` — read-only latest assessment at cutoff.
6. `backend/app/api/terminal.py` — seven GET APIs and safe projection boundary.
7. `backend/app/models/terminal.py` — typed bounded analytical contracts.
8. `backend/app/services/terminal.py` — composition over existing authorities.
9. `backend/tests/integration/test_terminal.py` — 43 focused cases.
10. `backend/tests/security/test_boundaries.py` — exact added GET-route allowlist.
11. `frontend/src/App.tsx` — `#terminal` route/navigation.
12. `frontend/src/styles.css` — minimal analytical layout and bounded table scrolling.
13. `frontend/src/components/Terminal.tsx` — backend-value rendering and safe states.
14. `frontend/src/services/terminal.ts` — typed mode/safety validation and GET transport.
15. `frontend/src/test/Terminal.test.tsx` — 16 frontend cases.
16. `frontend/src/test/terminalFixtures.json` — isolated synthetic API fixture.
17. `docs/PHASE_12_REPORT.md` — this report.
18. `docs/evidence/PHASE_12_SYNTHETIC_API.json` — synthetic contract evidence.
19. `docs/evidence/PHASE_12_BROWSER.json` — browser evidence.
20. `docs/evidence/PHASE_12_VERIFICATION.json` — verification evidence.

## Gates and stop

```text
PHASE_12_IMPLEMENTATION=PASS
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

The Phase 12 gate passes for the verified analytical implementation: authoritative values come from backend APIs, no frontend financial calculator was added, missing/stale inputs abstain, and simulations/proposals remain distinct from confirmed settlement. Provider coverage and live readiness are not certified. Phase 13 was NOT started. Stop after Phase 12.
