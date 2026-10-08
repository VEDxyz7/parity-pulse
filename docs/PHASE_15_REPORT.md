# Master Phase 15 — Frontend Integration

**PHASE_15_IMPLEMENTATION = PASS** for the non-live frontend integration gate.
Critical React journeys pass through the actual backend and back. This does not establish provider entitlement, live settlement equivalence or wallet-runtime readiness. Phase 16 is **NOT started**. No commit or push.

## Continuation audit

The interrupted implementation was preserved, not rebuilt. Before further edits, the complete 5,321-line `docs/MASTER_SPEC.md`, continuation request, working-tree diff, API/client/components/tests, and saved baseline results were inspected. The specification SHA-256 remains `f69a9bd01a622c001c3ec6cb654e00562f6b3d03a8310f9e5ccf68efe4b49c84`.

Already implemented: analytical navigation; typed Opportunity, Portfolio/Autopilot, wallet/system and audit views; Direct proposal review; bounded shared HTTP transport; seven Pydantic-derived display contracts; read inspection API; shared portfolio projection; polling; responsive styles; 31 new frontend tests and 10 backend cases. Saved baseline verification was 1,387 backend / 220 frontend tests; the interrupted changes passed 251 frontend / 95 focused backend tests. Production-facing pages read APIs, never the test fixture JSON.

This continuation fixed a real lifecycle gap: workspace refresh unmounted Autopilot controls and discarded reviewed inputs/retry identity. Controls now survive refresh, cannot submit with unavailable state, retain the planning key, and cancel on navigation. Six lifecycle tests prove reviewed version checks, preserved inputs, uncertain retries, cancellation, persisted-scan retrieval and GET-only refresh. Two additional tests prove reviewed Trust expiry and API-failure blocking. Review evidence expires using the existing 120-second display window; no Trust threshold changed. Historical scan snapshots are labelled explicitly, route tables are keyboard-scrollable, and Home explicitly marks unavailable current calendar summary values. Reproducible isolated browser coverage, final regression validation and this evidence were completed.

## Pages and contracts

| Surface | Navigation and actual backend authority | Behavior |
|---|---|---|
| Home | `#overview`; `/api/health`, `/api/system-status` | Backend health/modes/gates and three primary analytical actions. Current US market/next-open summary is explicitly unavailable here; Terminal exposes available per-asset observations. No invented overview quotes/charts/calendar. |
| Buy a Stock / Route Comparison | `#ask`; `POST /api/exposure/quote` | Existing resolution/discovery/normalization/shared router; exact backend strings, indicative cost, source, unknown fees/liquidity, expired estimates and no-broadcast status. |
| Confirm Trade review | Explicit review within Ask; `GET /api/assets/{ticker}/trust` | Separate canonical evidence; insufficient/stale/error states. Does not mutate the stored estimate or become execution approval. Risk/preparation/simulation remain unavailable for the indicative proposal. |
| Opportunity / Detail | `#opportunity`, `#opportunity/<run_id>`; existing scan POST and persisted-scan GET | Explicit budget/risk/window/universe, optional synthetic scenario only in configured DEMO, backend candidate order/rank, evidence, costs, Risk/action/rejections, NO_QUALIFYING_OPPORTUNITY, route, safe retry identity and audit link. No frontend ranking or forced investment. |
| Autopilot / Portfolio | `#autopilot`, `#portfolio`; `GET /api/workspace`, existing `POST /api/autopilot`, `POST /api/portfolio/plans` | Phase 11 config/targets/caps, original allocation/drift snapshot/funding, plan actions/routes/Risk/preparations and Phase 10 positions/P&L. Reviewed writes only; expected-version conflict remains backend-owned. No arbitrary execute/approve endpoint. |
| Terminal | `#terminal`; existing `/api/terminal` | Reused Phase 12 normalized issuer spreads, stale/missing Trust, agent evidence, execution analytics, historical episodes, portfolio context and filtering. |
| Scorecard / Audit | `#audit`, `#audit/<decision_id>`; existing `/api/scorecard`, `/api/audit`, `/api/audit/decisions/{id}` | Reused Phase 13 evaluations/trace, bounded event pagination, decision crosslinks and correlation/provenance. Unrecorded stages remain unavailable; paper outcomes are distinct from real execution. |
| Agent API | `#agent-api`; existing `GET /api/agent/tools` | Reused Phase 14 seven tool descriptions, request examples/response schemas and safe status boundaries. No automatic tool invocation, remote authentication or MCP redesign. |
| Settings / System Health | `#settings`; `GET /api/workspace` | Backend capability/gate projection, wallet unavailable/unknown, approval unavailable, unverified exact simulation, all live gates blocked; no credentials or editable gates. |
| DEMO Sandbox | `#demo-sandbox`; existing `/api/demo/*` and `/api/demo/paper/*` | Existing three scenarios and complete synthetic quote/preparation/simulation/paper lifecycle retained; canonical Overview Trust remains unchanged. |

`GET /api/workspace` is the only additive public endpoint. It projects existing services, exposes at most 100 position records with coverage status, and never refreshes providers, captures a portfolio evaluation, operates a CLI worker or prepares a transaction. Query overrides return 422; mutation methods return 405. Known projection failures return sanitized 503. The exact pre-existing Phase 14 portfolio projection was extracted into a shared pure helper; financial engines were not redesigned.

Wallet capability is **WALLET_UNAVAILABLE** without a host client; an injected host client is **UNKNOWN**, not connected/authorized. Address/balance remain null and no host worker is probed. Public approval remains `PUBLIC_APPROVAL_UNAVAILABLE`. The UI offers review and inspection, not a pretend approval. UNKNOWN, RECONCILIATION_REQUIRED, FAILED, OPENING and PROPOSED positions are not presented as confirmed ownership. Existing OPEN, EXIT_PENDING, EXITING and CLOSED states and backend-filled amounts remain distinct.

Seven generated schema roots: WorkspaceState, OpportunityScan, OpportunityRequest, ConfigRequest, RebalancePlan, PortfolioConfig and AuditPage. `scripts/generate-ui-contracts.py --check` detects contract drift. Runtime validation covers the known emitted Pydantic subset, exact decimal strings, enums, UTC timestamps, required/null/extra fields and nested mode isolation; it is not a general JSON Schema engine or replacement for backend Risk validation. Existing quote/Trust/route/DEMO/Terminal/Scorecard validators remain in use. HTTP statuses/correlation identifiers survive sanitized errors; raw provider errors/secrets are not rendered. No automatic HTTP or mutation retry.

## Updates, states and accessibility

Workspace observers share a TanStack query key. Workspace, Terminal, Scorecard and audit inspection use a 30-second GET refresh, disabled in the background, with bounded timeouts, cancellation, deduplication, no automatic retries and safe reconnect reads. Immutable persisted Opportunity scans are retrieved without rerunning the scan. Proposals/configuration/plans are submitted only by explicit user actions. Uncertain planning retries keep their identity while the reviewed page remains mounted; cancelling transport cannot undo a backend record, which can be inspected through workspace/audit APIs.

Loading/error states hide cached financial success. Empty inventories, unavailable balances/equity/fees, insufficient evidence, expired proposals/Trust, historical snapshots, blocked execution, unknown ownership and reconciliation are explicit; errors do not become zero holdings. Backend-owned timestamps/provenance and source-quality labels are displayed. Rendered external text is React-escaped; hidden agent reasoning/raw responses are not shown.

Responsive forms, panel/table wrapping and local table scrolling preserve the existing design. Labels, semantic headings/captions, keyboard-focusable table regions, visible focus styles, status/alert messages and keyboard skip navigation are present. Desktop 1440px, mobile 390px and tablet 768px new journeys passed with no page overflow. Existing Terminal/Scorecard/Agent API and DEMO journeys passed on desktop/mobile. Screenshots were reviewed. This is accessibility basics verification, not a full WCAG certification.

Polling follows the installed library's [official guidance](https://tanstack.com/query/latest/docs/framework/react/guides/polling) and [query options](https://tanstack.com/query/latest/docs/framework/react/reference/functions/useQuery). Schema handling is bounded against emitted contracts, with [object](https://json-schema.org/understanding-json-schema/reference/object) and [type](https://json-schema.org/understanding-json-schema/reference/type) semantics checked. No dependency was added or upgraded.

## Verification

| Check | Final result |
|---|---|
| Focused Phase 15 frontend | **39 passed**; plus 19 existing routing cases passed in the earlier focused combined run |
| Focused Phase 15 backend | **10 passed**; interrupted combined workspace/Phase 14/security check also **95 passed** |
| Complete frontend | **259 passed**, 13 files; all 220 inherited tests retained |
| Complete backend | **1,397 passed**, including all 1,387 inherited tests; two inherited intentional malformed-allowance serializer warnings |
| Phase 6–14 regression | **734 designated cases**, passed within the complete backend suite; exact collection list in verification evidence. Additional inherited remediation tests also pass in the full suite. |
| Typecheck / production build | PASS; `npm run build` runs `tsc --noEmit`; lazy analytical chunks preserve bounded initial bundle (~392 kB, ~115 kB gzip). |
| Ruff / formatting / Python compile | PASS across backend/scripts; no separate backend mypy framework is configured. |
| Contracts / whitespace | PASS; seven generated schemas exact; `git diff --check` clean. |
| Security | PASS; configured-secret artifact scan, frontend isolation, Git/Docker exclusions, existing backend security tests, negative contract/mode checks and frontend XSS text test. |
| Dependencies | PASS; `pip check`, root `npm ls --all`; consistency checks, not a new CVE certification. |
| Built browser ↔ actual fixture backend | **35 new workspace journeys**, **12 existing DEMO/Terminal/Scorecard/Agent API journeys**, ordinary-runtime canonical Trust/disabled sandbox check; **176 local API requests**, no runtime exceptions/live calls. |
| Desktop / mobile / tablet | PASS for recorded surfaces; no page overflow, keyboard skip and accessible form/table structure verified. |

Browser verification uses disposable credential-free backends with actual existing services, temporary research/ledgers, built React, disposable Chrome, an exact API-method allowlist and no provider/wallet runtime. Synthetic Risk inputs are changed only in the test factory to make the unchanged simulation service return SIMULATION_FAIL; UI records rejection and exposes no paper-fill action. Direct-exposure browser time matches the existing frozen test clock; timestamps/data are never labelled LIVE. No synthetic observation is written into real historical coverage.

Initial browser failures were harness issues: the frozen backend estimate was correctly expired relative to wall-clock browser time, two selectors were incorrect, direct audit renders stage evidence rather than a DIRECT label, and simulation failure correctly uses the existing `rejected` pipeline status. Assertions now match those actual contracts and independently require indicative audit evidence and SIMULATION_FAIL/Risk rejection/no paper fill. No application safety behavior or inherited test assertion was weakened. No inherited flaky test failed in the final complete run.

The inherited single-connection in-memory SQLite availability constraint remains: local browser forwarding is serialized, as in Phase 14. This run does not certify concurrent memory-database throughput. Backend concurrency/idempotency safety tests pass separately in the complete suite. All five owned test servers and disposable Chrome are stopped; unrelated user services are untouched.

Evidence: [verification/invariants/files](evidence/PHASE_15_VERIFICATION.json), [browser requests/journeys](evidence/PHASE_15_BROWSER.json), [contracts and isolated examples](evidence/PHASE_15_CONTRACTS.json).

## Readiness and unchanged production gates

- **IMPLEMENTED: PASS** — required non-live React integration and safe states.
- **BACKEND-VERIFIED: PASS** — actual existing services/APIs, exact contracts and complete regressions.
- **Routing production-capable: YES** — same backend router; financial/route authority remains server-side.
- **PROVIDER-VERIFIED: PARTIAL, unchanged** — no external entitlement, market or routing verification added.
- **EXECUTION-VERIFIED: BLOCKED** — no live simulation/equivalence or settlement/runtime evidence added.
- **LIVE-READY: NO** — no signing, broadcast, real RFQ, wallet execution/settings mutation or funds movement.

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

Remaining blockers: independent current-equity entitlement/alignment; authoritative executable-market liquidity/news; historical ratio/as-of evidence and real 30/30/3 coverage; Phase 7 complete real-input/funding assembly; SWAP exact transaction equivalence; RFQ final-settlement safety; verified Agentic Wallet runtime/controlled worker. Indicative Direct proposals have no public executable Risk/preparation/simulation/approval path. Public current wallet balances and a verified Home market-summary/chart API are not fabricated. These are explicit boundaries, not passed capabilities. Prior reports, gate documents, real data and Master specification remain unchanged.

## Exact file inventory

Existing files changed:

- `README.md`
- `backend/app/main.py`
- `backend/app/models/agent_api.py`
- `backend/app/services/agent_api.py`
- `backend/tests/security/test_boundaries.py`
- `frontend/src/App.tsx`
- `frontend/src/components/AskFlow.tsx`
- `frontend/src/components/RouteComparison.tsx`
- `frontend/src/components/ScorecardAudit.tsx`
- `frontend/src/components/Terminal.tsx`
- `frontend/src/services/agentApi.ts`
- `frontend/src/services/demoOpportunity.ts`
- `frontend/src/services/demoPaper.ts`
- `frontend/src/services/demoPreparation.ts`
- `frontend/src/services/demoSandbox.ts`
- `frontend/src/services/exposure.ts`
- `frontend/src/services/scorecard.ts`
- `frontend/src/services/system.ts`
- `frontend/src/services/terminal.ts`
- `frontend/src/services/trust.ts`
- `frontend/src/styles.css`

New files:

- `backend/app/api/workspace.py`
- `backend/tests/fixtures/frontend_phase15.py`
- `backend/tests/integration/test_workspace_ui.py`
- `docs/PHASE_15_REPORT.md`
- `docs/evidence/PHASE_15_BROWSER.json`
- `docs/evidence/PHASE_15_CONTRACTS.json`
- `docs/evidence/PHASE_15_VERIFICATION.json`
- `frontend/src/components/OpportunityView.tsx`
- `frontend/src/components/ProposalReview.tsx`
- `frontend/src/components/WorkspaceViews.tsx`
- `frontend/src/hooks/readRefresh.ts`
- `frontend/src/services/api.ts`
- `frontend/src/services/backendSchemas.json`
- `frontend/src/services/contracts.ts`
- `frontend/src/services/workspace.ts`
- `frontend/src/test/Phase15.test.tsx`
- `frontend/src/test/workspaceFixtures.json`
- `frontend/src/types/backend.generated.ts`
- `scripts/check-frontend-phase15.mjs`
- `scripts/generate-ui-contracts.py`
- `scripts/verify-frontend-phase15.py`

**Stop:** Master Phase 15 only. Phase 16/17/18 NOT started. No commit or push.
