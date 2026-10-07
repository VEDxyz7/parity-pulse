# Master Phase 6 — Multi-Agent Intelligence

Verified October 7, 2026. **PHASE 6 IMPLEMENTATION=PASS; PHASE 6 DATA DEPENDENCY=BLOCKED.**
Scope is reusable, bounded, non-executable interpretation. Phase 7 has NOT started. No commit.

## Authority and pre-code audit

The entire 5,321-line `docs/MASTER_SPEC.md` was read before implementation and is the current
user-designated authority. SHA-256:
`f69a9bd01a622c001c3ec6cb654e00562f6b3d03a8310f9e5ccf68efe4b49c84`.
It remains byte-identical to the supplied file. Neither Downloads nor an older/root-level master
was substituted. Starting commit: `85e7a1ba7847fc2633329e3dd3abf2649a17fe57`.
The only initial untracked file was the user-supplied authoritative specification.

Before coding, the existing 558 backend/173 frontend tests, build/typecheck, Ruff and security
checks passed. The audit found the Phase 5 point-in-time research contracts, feature vectors,
retrieval, rolling Decimal model and replay already implemented. Trust, news alignment,
Opportunity, Risk, Routing and the complete DEMO UI/paper flow were also present. An agent layer,
controlled tool registry, workflow budgets and agent memory were absent. Existing financial
services were reused, not rebuilt. All prior source/data/evidence/fixture hashes are preserved.

## Six contracts and responsibilities

Every response is an immutable, extra-forbidden Pydantic contract with a discriminated agent name,
version, run/decision/correlation IDs, data mode, UTC decision timestamp, evidence references,
status, typed output, server-calculated confidence factors, limitations and conflicts.
Statuses are `OK`, `ABSTAIN`, `INSUFFICIENT_EVIDENCE`, `UNAVAILABLE`, `CONFLICT`.
Financial inputs reject floats/nonfinite values; derived evidence has an explicit 256-digit bound.
Outputs contain bounded enums, identifiers and reason codes, not private reasoning or arbitrary prose.

| Agent | Input boundary | Structured output / abstention |
|---|---|---|
| Intent | Bounded explicit grammar plus approved, mode-scoped stock metadata | DIRECT_EXPOSURE / OPPORTUNITY / AUTOPILOT mandate; ticker, budget, separately supplied risk budget, window, strategy/allocation and PROPOSE_ONLY. Ambiguity or missing required fields asks for clarification; no financial inference |
| Market | Existing deterministic Trust/features/baselines/liquidity/reference evidence | Existing classification, direction and risk flags. Missing, stale, misaligned or contradictory evidence abstains; no feature/price/Trust calculation |
| News | Existing publication-time news service, stock metadata and approved news records | Relevance, directional corroboration, article IDs/publication times, HEADLINE_EVIDENCE event type, explicit no-causality flag. Missing/stale/partial news abstains; contradictory corroboration conflicts |
| Research | Existing Phase 5 retrieval/model, supplied Trust analogues, typed priors and projected memory | Actual episode IDs, continuation/reversal/mixed from completed token episodes, separately labeled equity opening direction/model status/counts, RESEARCH_PRIOR tags, memory IDs. Insufficient real Phase 5 evidence remains explicit |
| Opportunity | Only a bounded deterministic candidate table | Eligible/rejected IDs, deterministic selection, strengths/weaknesses and BUY / DEFER / NO_QUALIFYING_OPPORTUNITY recommendation. No new candidates or invented economics |
| Decision | Validated prior interpretations, candidate Trust state and existing route/risk preview | BUY / DEFER / NO_QUALIFYING_OPPORTUNITY, issuer/ticker, reasons, conflicts and risk status. BUY is a DEMO analytical recommendation only, always execution_authorized=false |

Intent reuses the existing USD-budget grammar and resolves against supplied discovered assets.
It supports the master examples, including Apple when Apple is actually in the supplied catalog;
it does not hardcode company→ticker mappings. A missing Direct Exposure risk budget remains null
and cannot authorize a BUY recommendation. Opportunity mandates require separate budget, risk
budget and window. Allocation parsing grants no Autopilot implementation or autonomous authority.
The existing Ask/API behavior remains unchanged.

Market independently checks source observation freshness and regular-session 30-second alignment,
so an incorrectly marked AVAILABLE reference cannot hide staleness. News relevance uses publication
time, with first availability as an additional safeguard; its conservative one-hour interpretation
window does not modify the Trust service. No news is not proof of no information.

Research calls `HistoricalRetrieval` and `RollingOpeningModel` with the existing recorded policy.
Opening UP/DOWN is not renamed to token continuation/reversal. Those patterns use actual completed
30-minute Trust analogue outcomes. In the existing regular-session DEMO fixtures, the supplied
synthetic token history can be explained even though the opening model is NOT_READY/0 samples;
that limitation is explicit. A real insufficient Phase 5 gate cannot become a positive result.
Research priors are typed and labeled, without applying paper coefficients.

## Orchestration and decision boundary

```text
Intent
  → existing backend deterministic evidence snapshot
  → Market → News → Research (bounded interpretations)
  → Opportunity (already reduced candidate table)
  → Decision + existing Risk/Route preview
  → structured audit/memory
  → STOP
```

The orchestrator validates/clones inputs, removes future publications/first-seen records and future
or unavailable historical outcomes before calculating workflow identity or invoking tools, enforces
ordering, validates responses, propagates provenance/conflicts and persists the final trace.
It does not calculate financial economics, size positions or execute trades. A workflow failure
produces six ordered, typed records with unavailable downstream stages and a final DEFER.
No recursive/concurrent workflow on the same orchestrator instance is permitted.

Selected DEMO recommendations must match the user's **actual** budget/risk budget and the existing
Risk Engine result, route identity, expiry, Opportunity economics, slippage, liquidity and Trust.
A fabricated candidate edge, failed risk, unavailable route or mismatch cannot pass the preview.
Material disagreement or insufficient required evidence prevents BUY. Every LIVE_READ_ONLY decision
continues to respect BLOCKED_BY_TRUST; no DEMO risk contract can enter that mode.
No quote, preparation, simulation, paper ledger, wallet or execution behavior is added or changed.

## Controlled tools

| Agent | Allowlisted structured readers |
|---|---|
| Intent | stock_resolver, mandate_validator |
| Market | market_evidence |
| News | news_evidence |
| Research | historical_retrieval, recent_memory |
| Opportunity | candidate_table |
| Decision | constraints (existing Risk/Route/Opportunity preview) |

The registry uses closed typed snapshots and bound agent capabilities, with no arbitrary tool
registration or callable/SQL/URL supplied by a model. Readers return copies. Opportunity has no
news/market reader; only Decision receives prior agents' complete responses. No agent gets raw
DB access, secrets, arbitrary HTTP, wallet mutation, signing or execution tools. Memory writes
belong to the orchestrator/store, not agent capabilities.

## Configurable bounds and optional LLM boundary

| Bound | Default / enforced range |
|---|---|
| Total agent invocations, including retry | 12 / 6–24 |
| Invocations per agent | 2 / 1–3 |
| LLM generations, including retries | 5 / 0–5 |
| Timeout per interpretation/generation | 5 seconds / 1–30 |
| Structured validation retries | 1 / 0–2, also constrained by the other budgets |
| Candidate context / top-K | 5 / 1–5; excess is rejected before agent calls |
| Total tool reads | 24 / 6–48 |
| Reads per agent | 6 / 1–12 |
| Tool depth | 1; configurable down to 0, never above 1 |
| Relevant memory episodes per stock/regime/mode | K=4 / 1–10 |

Timeout and transport failure stop the workflow without retrying potentially running work.
Malformed structured responses can retry within all budgets. A retry consumes the five-generation
budget; it cannot silently add a sixth generation. Phase 5 CPU work is offloaded, read-only and
bounded to 500 supplied historical episodes per research context; cancellation grants no new tool
or write authority. Adapters/transports must honor asynchronous cancellation; this is not a sandbox
for arbitrary third-party Python code.

The default is deterministic interpretation with **zero LLM/network calls**. `LLMProvider` and
`StructuredLLMProvider` expose a vendor-independent, explicitly injected async structured transport.
`LLMConfiguration` supports LLM_PROVIDER, LLM_MODEL, protected LLM_API_KEY and LLM_BASE_URL;
configuration/secrets remain with the host transport and are never provided to agents. Provider/model
identifiers are recorded per response and bound to workflow identity. No vendor SDK, endpoint or
entitlement is assumed, and no external LLM provider was called or verified in this milestone.

The optional transport receives structured interpretations; Opportunity receives only the reduced
candidate table as evidence, never a raw universe. The accompanying canonical response/schema
sets the deterministic facts/confidence/authority boundary. Conflicting, invented or malformed
returned fields are rejected; confidence is always recalculated server-side. Synthetic echo/error
transports verify this boundary, not a claim of production LLM entitlement. Deterministic parsing
handles supported language; unsupported ambiguous language safely abstains rather than guessing.

## Memory and persistence

`AgentStore` uses separate SQLite/SQLAlchemy tables: agent_runs, agent_evidence, decisions,
agent_memory. Default CLI storage is Git-ignored `data/agents/phase6/agent-memory.sqlite`.
A directory containing application `.db` files is rejected. It never opens production history,
execution or scorecard tables. Writes are transactional, immutable and integrity-checked;
repeating identical input/policy/projected memory reproduces the same result and is idempotent.

Memory contains timestamp/first availability, mode, stock/regime, bounded deterministic feature
summary and quality, Trust state, LOW confidence, six ordered conclusion statuses, action/no-action,
evidence IDs, optional eventual outcome/scorecard reference and their separate availability times.
Readers return only K relevant known prior episodes. Future outcomes/scorecards are independently
removed from the projection even when their earlier episode is known. Unknown outcomes remain
UNAVAILABLE; no paper outcomes are automatically imported. Corrupt/mixed-mode records stop.
No raw user request, private chain-of-thought, hidden reasoning, credential or raw headline is stored
by this layer. Audit output retains the candidate table and timestamped source/digest references.
Reference timestamps describe the evaluated analytical view; provider observation times remain
separate in the existing source evidence/candidate rows and are not replaced by receipt time.

## Confidence and real data dependency

Confidence traces data quality/freshness, baseline count, analogue count, feature agreement,
news corroboration, persistence, model samples, regime certainty and agent disagreement.
The existing uncalibrated LOW cap is preserved. Insufficient data produces INSUFFICIENT confidence
status; disagreement produces CONFLICTING status and DEFER. No LLM probability, synthetic sample,
paper prior or agent label upgrades production Trust.

Captured real replay yields DEFER: baseline/model/analogue qualifying counts remain **0/30, 0/30,
0/3**. Its absent historical Trust representation is explicitly unavailable, not reconstructed using
today's ratio. Current Massive entitlement, authoritative liquidity/units, historical as-of ratios,
calendar/revision/first-availability/news and observation density remain external data blockers.
Twelve Data is not admitted to production Trust; the scheduled alignment diagnostic was not run.
No new read-only provider request, historical backfill or production observation write occurred.

## Verification and acceptance

- 628 backend tests PASS: all 558 existing tests retained, plus 70 Phase 6 synthetic/isolated controls.
- 173 frontend tests PASS; TypeScript noEmit and production build PASS.
- Ruff lint/format and dependency consistency PASS; security and expanded credential isolation PASS.
- Six desktop/mobile DEMO scenarios PASS, 39 local HTTP200 requests, no runtime errors/overflow.
  Information retains the full paper execution/position/exit/P&L/scorecard flow; NORMAL/noise stand down.
- Ordinary Overview still returns INSUFFICIENT_EVIDENCE and production Opportunity navigation stays disabled.
- Real captured replay returns six typed responses and DEFER/INSUFFICIENT_EVIDENCE with no fake fallback.
- All previous evidence, databases, fixtures, financial services and master bytes are preserved.

[Agent runs](evidence/PHASE_6_AGENT_RUNS.json), [browser regression](evidence/PHASE_6_BROWSER.json),
and [verification record](evidence/PHASE_6_VERIFICATION.json) supply the measured evidence.
The implementation gate passes because every required component and boundary is implemented and
verified, not because real Trust readiness is asserted. Live LLM/provider entitlement remains unverified.
The existing upstream Starlette/httpx TestClient deprecation warning remains.

```text
PHASE 6 IMPLEMENTATION=PASS
PHASE 6 DATA DEPENDENCY=BLOCKED
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

Changed files:

- `backend/app/agents/__init__.py`, `schemas.py`, `confidence.py`, `tools.py`, `provider.py`,
  `intent_agent.py`, `market_agent.py`, `news_agent.py`, `research_agent.py`, `opportunity_agent.py`,
  `decision_agent.py`, `orchestrator.py`, `memory.py`, `adapters.py`.
- `backend/tests/unit/test_agents.py`, `backend/tests/integration/test_agent_evidence.py`.
- `scripts/analyze-agents.py`, `.gitignore`, `README.md`.
- `docs/PHASE_6_REPORT.md`, `docs/ARCHITECTURE.md`, `docs/EXECUTION_GATES.md`, `docs/PHASE_MAP.md`.
- `docs/evidence/PHASE_6_AGENT_RUNS.json`, `PHASE_6_BROWSER.json`, `PHASE_6_VERIFICATION.json`.

The user-supplied untracked `docs/MASTER_SPEC.md` is an unchanged input, not an agent edit.
No application endpoint, frontend component, financial rule, Trust threshold, 30/30/3 safeguard,
production gate, paper behavior or LIVE integration changed. Temporary test servers were stopped;
existing user services were not altered. No automatic commit.

**Exact next engineering phase: MASTER PHASE 7 — OPPORTUNITY MODE**, only on separate authorization
and with the unchanged real Trust/Opportunity dependencies. Phase 7 has NOT started. STOP after Phase 6.
