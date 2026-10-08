# Master Phase 14 — Agent API / MCP

**PHASE_14_IMPLEMENTATION = PASS** for the bounded non-live interface. **PROVIDER-VERIFIED = PARTIAL**, **EXECUTION-VERIFIED = BLOCKED**, **LIVE-READY = BLOCKED**. Phase 15–18 were not started. No commit or push; no live signing, execution, broadcast, RFQ submission, wallet-setting change or funds movement.

## Authority and initial audit

All 5,321 lines of `docs/MASTER_SPEC.md` and the complete Phase 14 request were read before changes. Authoritative SHA-256: `f69a9bd01a622c001c3ec6cb654e00562f6b3d03a8310f9e5ccf68efe4b49c84`. Starting commit: `bb1d363f3cd673e2966da3584cb57f020e6027d9`; starting working tree clean.

The repository already had stock resolution/discovery/normalization and shared deterministic routing, canonical Trust assessments, full-universe/top-K Opportunity scans with bounded agents and Risk validation, host-only Phase 8–9 safety/execution controls, Phase 10 positions, Phase 11 portfolio authority, Phase 12 read projections, and Phase 13 append-only evaluation/audit. There was no external tool interface or MCP abstraction. Those services are reused; no parallel financial engine or execution state machine was introduced.

## Tool inventory and typed contracts

`GET /api/agent/tools` publishes all seven Pydantic-generated request schemas, the serialization response schema, annotations, interface version and backend availability. `POST /api/agent/tools/{name}` accepts only these seven names and a JSON object. The catalog is also the MCP tool inventory. Exact schemas are generated from `backend/app/models/agent_api.py`; focused tests validate real results against the published JSON schemas.

| Tool | Kind | Input | Existing authority / result |
| --- | --- | --- | --- |
| `buy_stock_exposure` | Proposal | ticker, decimal-string amount/risk budget, UUID idempotency key, optional mode | Canonical Trust + UI Exposure service and its shared router; persisted indicative proposal with explicit downstream blockers |
| `find_opportunity` | Proposal | decimal-string budget/risk budget, window, bounded universe filters, UUID key, optional mode/scenario | Existing source capture → deterministic universe/filter/top-K → agents → decision → existing Risk eligibility; public scan facts |
| `compare_stock_tokens` | Analytical | ticker, bounded limit/offset | Existing cached Terminal issuer board and normalization; source observations, independent reference, Trust, liquidity and unavailable fields |
| `get_stock_trust` | Analytical | ticker | Existing deterministic Trust assessment; classifications/confidence/features/regime/news/history/reasons and policy |
| `get_route` | Analytical | ticker, decimal-string amount | UI Exposure discovery/normalization and the **same** RoutingService, without persisting a proposal |
| `get_portfolio` | Analytical | optional expected data mode | Phase 11 `PortfolioService.state()`; config, latest/pending plan, original allocation/drift/action/funding inputs and Phase 10 active positions |
| `get_autopilot_status` | Analytical | optional expected data mode | The same Phase 11 state; inspection only, existing decisions/preparations/recovery/constraints, no configuration or action mutation |

All inputs forbid extra fields. Tickers use the existing format; pagination is strict integer, limit 1–100, offset 0–10,000. Monetary inputs must be positive decimal **strings**, bounded to 18 integer/18 fractional digits and USD 1 billion; existing stricter backend constraints remain authoritative. Floats, booleans, non-finite values, exponent-form requests and policy/execution/provider-URL fields are rejected. Investment and risk budgets remain separate. Optional input `data_mode` asserts the host mode; it cannot change it. Scenarios are accepted only by the existing isolated DEMO runtime. Request bodies are bounded to 16 KiB.

Responses are validated `ToolResult` JSON: tool/status/error, current request/correlation/run/invocation IDs, original request/correlation IDs, decision ID where available, original as-of/generated times, data mode/quality, source, reason codes and existing typed authority payloads. Decimal output strings may contain exponents emitted by existing backend serializers; the output schema accurately describes those lexemes. No financial calculation occurs in the adapter or React.

Raw agent responses/interpretation summaries are omitted from public scans. Portfolio projections preserve backend-computed quantities/share exposure/P&L and original plan values, while omitting raw execution/signing/transaction payloads. UNKNOWN/unconfirmed positions retain their actual state and zero unconfirmed filled/remaining quantity; they are never relabeled owned. Active position coverage retains the existing 100-row completeness flag. Original plan allocations/funding have their captured timestamp; these are not a fresh NAV or rebalance calculation. Closed positions are excluded by the existing active-position view, not converted into holdings.

## Transport and boundaries

The transport-independent `AgentAPI` adapter dispatches directly to the application’s existing service instances. No handler has a signing, broadcast, RFQ submission or wallet-mutation operation.

The minimal MCP implementation uses the **official Python SDK `mcp==2.3.0`**, installed as an optional transport extra and a development-test dependency. It implements **stdio** over SDK-provided framing, lifecycle, capabilities, version handling and cancellation; JSON `structuredContent` is accompanied by serialized JSON text. The SDK’s current protocol is **2026-07-28**, with its compatibility handling retained. No handwritten MCP protocol or Streamable HTTP endpoint was created. The frontend and base FastAPI runtime do not import or require the MCP runtime.

The stdio process forwards only these seven tools to a fixed `http://127.0.0.1:<port>` backend. It owns no provider client, wallet session, second database or financial service. The port is host-configured (1024–65535); callers cannot supply arbitrary URLs. Redirects, environment proxies and credential forwarding are disabled. There are no automatic transport retries.

The HTTP invocation endpoint permits loopback peers and literal localhost/loopback Host only. It rejects foreign/null Origin, forwarded headers, query overrides and non-JSON content. It does not trust `X-Forwarded-For`. This is a **local single-user authority boundary**, not multi-tenant RBAC or public OAuth. Remote/proxied invocation remains denied; authenticated remote MCP deployment is not implemented. The public catalog contains schemas and status only.

Verified primary sources: [current MCP transports](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports), [current tools/structured results](https://modelcontextprotocol.io/specification/2026-07-28/server/tools), [official Python SDK](https://github.com/modelcontextprotocol/python-sdk), [pinned release](https://pypi.org/project/mcp/2.3.0/). The installed SDK API was inspected and exercised, rather than assuming older decorators/API behavior.

## Safety and supported stop boundaries

All seven responses remain DRY_RUN / PROPOSE_ONLY / simulation-required / execution-not-ready / no-broadcast. A requested LIVE mode returns `EXECUTION_BLOCKED` before any business dispatch. Arbitrary execute/sign/broadcast/RFQ/wallet methods are absent. Agent claims, external text and metadata cannot alter policies, thresholds, modes, wallet limits or gates.

`buy_stock_exposure` calls canonical Trust and the current indicative Exposure flow. It can persist a reproducible issuer comparison/route estimate, but returns **DEFERRED** when an estimate exists and **REJECTED** when it does not. Its explicit risk budget is retained for audit; it is **not** called Risk-approved. Complete execution Risk/funding/inventory/wallet inputs are not assembled in this flow, so `RISK_INPUTS_UNAVAILABLE` remains explicit. Provider quote/build/simulation and approval/execution remain unavailable; no separate fabricated implementation fills the gap.

`find_opportunity` preserves the existing BUY, DEFER and NO_QUALIFYING_OPPORTUNITY outcomes. BUY is a DEMO proposal only when the existing scan’s deterministic filters, bound agents and Risk permit it. Production `OPPORTUNITY_GATE=BLOCKED_BY_TRUST` remains unchanged. Existing scan concurrency bounds and the five-LLM-call ceiling are retained. The adapter does not force investment or upgrade confidence.

`get_route` uses production-compatible discovery/profile/observation interfaces and the shared deterministic router; the new host-only `persist=False` option suppresses proposal/observation saves in that path. Default UI proposal behavior is unchanged. Current results are **indicative**, not a verified aggregator quote: provider execution mode and quote ID remain NULL. No issuer→SWAP/RFQ mapping, fake fee or synthetic LIVE fallback was introduced. Future provider preparation continues to require the existing quote → Risk → exact build/fingerprint → simulation → wallet controls → ExecutionGateway authority. This interface does not unlock that path.

Analytical tools perform no investment, portfolio configuration/evaluation/preparation/completion or wallet mutation. Trust assessments use the same analytical persistence/provider caching as the existing GET assessment; invocation audit is also recorded. Thus “read-only” refers to financial/control authority, not an absence of analytical cache/audit writes.

Errors are structured and sanitized. Caller failures use `INVALID_INPUT`; provider/authority failures use `DATA_UNAVAILABLE`; LIVE requests use `EXECUTION_BLOCKED`; changed-key payloads use `IDEMPOTENCY_CONFLICT`; interrupted claims use `RECONCILIATION_REQUIRED`. Categories distinguish caller, provider, product, safety and execution capability. Existing deterministic rejection reasons stay inside existing payloads; a valid stand-down is not recast as a successful trade. Exceptions/raw validation input are not returned. When an MCP backend response is unavailable, the transport returns **UNKNOWN** mode/quality with no financial payload and a no-resubmission policy, rather than inventing the backend mode.

## Idempotency and audit

The adapter adds a mode/tool/UUID-scoped retry receipt around existing non-idempotent Exposure proposal creation and existing deterministic scan persistence. It introduces **no execution intent/order/rebalance**. Existing Phase 7 scan identities and Phase 8–11 execution/action idempotency remain the authorities.

A SQLite unique claim is committed **before** dispatch. Equal completed input returns the original result/decision/as-of/expiration with `replayed=true`, current delivery IDs, and original operation IDs. Changing payload under that key is refused. Pending/lost/cancelled claims return `RECONCILIATION_REQUIRED`, including after restart; there is no automatic TTL reset or blind resubmission. Checksum, typed receipt and tool/mode bindings fail closed. Completion happens after required audit capture. An audit/capture failure can leave a pending receipt even if an indicative source proposal was already saved; retry does not duplicate it. Recovery/operator resolution is deliberately not exposed as a tool. A receipt is not a new quote or fresh execution permission.

Ordinary disk-backed receipts live beside the existing database under `agent-api/phase14/<mode>/tool-receipts.sqlite`. DEMO/test/memory receipts remain isolated in memory, consistent with earlier journals.

Phase 13’s `AuditEvent` gains an additive `OBSERVED_TOOL_INVOCATION` capture kind. Existing source projections retain their original capture kind/default and identifiers. Started/completed/replayed/refused invocations append bounded typed summaries, input/result digests, reason codes and actual request/correlation/decision references using the existing AuditService/ScorecardStore. Invalid raw inputs are not retained. Proposal/scan decisions are captured by the existing scorecard evaluator; invocation events augment their trace without rewriting immutable scorecards or original decision inputs. Analytical/error events without a scorecard are inspectable through `/api/audit`; mode/ticker/time/as-of/decision filters apply. The existing frontend audit parser accepts only the two verified capture kinds.

## Minimal frontend

`#agent-api` adds a visible Agent API navigation entry with seven read/proposal tool names, schemas, structured request example, stdio startup command, backend mode/status, unavailable/retry state and prominent non-live restrictions. It fetches **only GET `/api/agent/tools`**. It has no tool-execution button or frontend financial logic. Desktop/mobile schema expansion wraps within the page. Overview Trust, DEMO pipeline, Terminal, and locked production Opportunity/Autopilot navigation remain unchanged. Phase 15 integration was not started.

## Validation and evidence

| Check | Result |
| --- | --- |
| Focused Phase 14 | **81 passed** |
| Complete backend | **1,387 passed**, two inherited malformed-allowance warnings |
| Inherited regression, including every Phase 6–13 test | **1,306 passed**, included in the complete run |
| Complete frontend | **220 passed** across 12 files; nine Phase 14 cases |
| Typecheck/build | PASS (`npm run build`: `tsc --noEmit` + Vite) |
| Ruff / formatting | PASS |
| Security / secret / bundle / ignore checks | PASS |
| Python / Node dependency consistency | PASS (`pip check`, `npm ls --all`); no new CVE/entitlement claim |
| Actual MCP stdio subprocess | PASS; all seven tools plus same-key retry, eight calls through isolated synthetic backend |
| Browser | PASS; desktop 1440px/mobile 390px, catalog/schema/error recovery + all six DEMO scenarios, ordinary Trust/blocked portfolio and Terminal/Scorecard regression; **79 local requests**, zero live calls/runtime errors/page overflow |
| Master, gates, prior reports/evidence, real data and engine comparison | PASS; no gate/threshold/real-history changes, no commit/push |

Focused coverage includes contract/JSON-schema validation, numeric precision bounds, policy injection, malformed/bounded bodies, Host/Origin/proxy boundaries, LIVE refusal before dispatch, no arbitrary tools, shared production-compatible routing, no fake provider modes, explicit unavailable provider state, separate risk budget, existing full-universe/agent/Risk outcomes, authoritative portfolio/pending plan/UNKNOWN ownership projections, audit and historical filters, restart, conflict, concurrent retries, cancellation and MCP transport timeout/no-retry/no-secret behavior. Existing tests/assertions were not removed or weakened.

Two inherited CLI tests initially exceeded their original one-second child timeout under concurrent validation load, correctly failing closed with `WALLET_READ_TIMEOUT`. All 37 wallet contract cases subsequently passed in isolation with the original timeout; final complete runs passed. No timing assertion was loosened.

Browser fixture investigation also observed intermittent health 503s when its concurrent proxy calls shared a single in-memory SQLite connection; sequential direct health reads recovered. This is consistent with the [documented StaticPool shared-connection concurrency constraint](https://docs.sqlalchemy.org/en/21/dialects/sqlite.html) (inference, not a new production concurrency certification). The final synthetic browser harness serializes local forwarding, retains every assertion/timeout, and uses fresh ledgers. **Concurrent in-memory runtime health remains an inherited availability limitation; no database/workflow rewrite or production workaround was made.** Backend receipt/concurrency safety is independently tested. The final browser run does not certify concurrent memory-database throughput.

Final retry-correlation review corrected current-versus-origin request IDs and a field-placement mistake; final validation uses the corrected contracts. Owned local test services/disposable Chrome are stopped after verification; unrelated user services are untouched.

Evidence: [verification/invariants](evidence/PHASE_14_VERIFICATION.json), [MCP subprocess](evidence/PHASE_14_MCP.json), [browser](evidence/PHASE_14_BROWSER.json), [isolated API/audit examples](evidence/PHASE_14_API.json). Synthetic evidence is not provider, real-history, settlement or wallet-runtime verification.

## Readiness and remaining blockers

- **IMPLEMENTED: PASS** — seven bounded tools, typed schemas, shared backend dispatch, HTTP/local MCP transport, original/current retry correlation and Phase 13 audit integration.
- **PROVIDER-VERIFIED: PARTIAL, unchanged** — production-compatible routing is preserved and offline tested; no external provider verification occurred in Phase 14. Indicative routes do not become verified aggregator quotes.
- **EXECUTION-VERIFIED: BLOCKED** — no live execution/simulation equivalence, RFQ final-settlement safety or actual Agentic Wallet runtime verification added.
- **LIVE-READY: BLOCKED** — no signing/execution/broadcast/RFQ/funds movement or wallet mutation.

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

Remaining external/product blockers are unchanged: independent current-equity entitlement/alignment; relevant executable-market liquidity and news; historical ratio/as-of evidence and real 30/30/3 coverage; complete Phase 7 real-input/inventory/funding assembly; actual route/build/simulation equivalence; RFQ settlement safety; verified wallet runtime. Additional interface limits are local-only transport, unresolved retry receipt recovery, existing bounded catalogs/active position coverage, indicative direct proposals without complete Risk/preparation inputs, and inherited concurrent in-memory availability noted above. None was reclassified as passed.

## Exact file inventory

Existing files changed:

- `README.md` — local tool/transport/run/retry instructions and historical milestone framing.
- `pyproject.toml`, `requirements-dev.txt` — pinned optional MCP transport/development dependency.
- `backend/app/main.py` — adapter/receipt lifecycle and API router.
- `backend/app/services/exposure.py` — host-only read analysis option; default UI persistence unchanged.
- `backend/app/models/scorecard.py` — additive invocation capture kind.
- `backend/app/services/audit.py` — invocation adjuncts in existing decision traces.
- `backend/app/services/scorecard.py` — bounded/filterable invocation event inspection.
- `backend/app/api/scorecard.py` — existing audit query propagation.
- `backend/tests/security/test_boundaries.py` — exact catalog/invocation route allowlist additions.
- `frontend/src/App.tsx` — minimal Agent API navigation.
- `frontend/src/services/scorecard.ts` — typed acceptance of observed invocation events.
- `frontend/src/styles.css` — scoped schema wrapping/details styles.

New files:

- `backend/app/models/agent_api.py` — seven typed inputs, validated responses/public projections.
- `backend/app/services/agent_api.py` — shared-service adapter/catalog/audit orchestration.
- `backend/app/repositories/agent_api.py` — mode/tool/input-bound retry receipts.
- `backend/app/api/agent_api.py` — local-only invocation and public catalog.
- `backend/app/mcp_server.py` — official SDK stdio-to-backend bridge.
- `backend/tests/integration/test_agent_api.py` — 81 focused cases.
- `frontend/src/components/AgentApi.tsx` — inspection/examples only.
- `frontend/src/services/agentApi.ts` — GET catalog validation.
- `frontend/src/test/AgentApi.test.tsx` — nine frontend cases.
- `frontend/src/test/agentApiFixtures.json` — backend-generated schemas, common output schema factored once.
- `docs/PHASE_14_REPORT.md` — this report.
- `docs/evidence/PHASE_14_VERIFICATION.json` — counts/invariants/inventory.
- `docs/evidence/PHASE_14_MCP.json` — actual stdio results.
- `docs/evidence/PHASE_14_BROWSER.json` — actual desktop/mobile observations.
- `docs/evidence/PHASE_14_API.json` — isolated original/current retry IDs and connected audit evidence.

**Stop:** Phase 14 only. Phase 15 NOT started; no commit or push.
