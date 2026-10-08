# Master Phases 6–9 remediation and follow-up adversarial audit

Verified October 8, 2026. All five requested remediation findings are **CLOSED in the tested non-live implementation**. This is a new follow-up assessment; the original [adversarial audit](PHASE_6_9_ADVERSARIAL_AUDIT.md), its evidence and inventory are preserved byte-for-byte.

The complete 5,321-line [MASTER_SPEC.md](MASTER_SPEC.md) was reread before changes. SHA256: `f69a9bd01a622c001c3ec6cb654e00562f6b3d03a8310f9e5ccf68efe4b49c84`. Starting HEAD: `d8ba445e37243ab5581d060f160360fbedaf7c40`. No commit was created. No Phase 10 code, positions, restart-position recovery or post-open exit logic was added.

The reviewer is the same coding agent that implemented the fixes. This follow-up uses adversarial boundary probes, the original reproducible attacks, an in-memory mutation experiment and the complete existing suite; it is not a separate human or independent-agent certification. [Machine-readable evidence](evidence/PHASE_6_9_REMEDIATION_AUDIT.json) contains results, source hashes, reproducible harnesses and preservation checks.

## Findings, roots, fixes and regressions

Numbers here match the **remediation request**. The earlier audit numbered its LLM gap F1, hash gap F2, force-confirm gap F3, simulation gap F4 and quota coverage gap Q1. Its separate F5 real scan assembly gap remains open below.

| Requested finding | Root cause | Exact remediation | Regression boundary and result |
|---|---|---|---|
| 1. RFQ can confirm a different transaction | Tracker overwrote a known hash; wallet corroboration did not survive delegation; journal did not lock the external quote/order binding. | Capture a `SettlementIdentity` binding execution/request/decision IDs, mode, source, quote ID, vendor, wallet, order ID and route fingerprint. State machine and journal retain external bindings and the known hash. Different hashes produce UNKNOWN and persistent contradiction evidence. Wallet hash is passed into the shared predicate. | `test_settlement_remediation.py`: same hash/complete fill confirms; differing hash under FILLED, pending and failed responses stays UNKNOWN; wallet-order and wallet/tracker disagreement preserve the original hash; order/quote/vendor/identity changes cannot confirm or rewrite the journal. **PASS**. |
| 2. Host can force CONFIRMED | Enum, status label and timestamp could substitute for complete terminal evidence. | One `execution_confirmation.settlement_values` predicate derives confirmation fields from revalidated captured evidence. `ExecutionAttempt` validation invokes it, so model construction, state transitions and durable writes share the requirement. Exact fills, transfer identities, minimum receive, chronology, known/corroborated hashes and unresolved conflicts are checked. | Pending/SUBMITTED/UNKNOWN direct confirmation is rejected by model, state and store without proof. Complete matching RFQ/SWAP evidence confirms. Wrong binding, absent fills, future or pre-quote records, altered hash and conflict erasure fail closed. **PASS**. |
| 3. SUCCESS accepts unsafe allowance effects | Simulator success and payload fingerprint were checked, but predicted allowance effects were not. | Approval records bind the observed pre-allowance. A bounded approval requires exactly one matching token/owner/spender effect, exact pre-value and exact approved post-value. SWAP allows no effect or bounded consumption of its existing allowance, never an increase. Unlimited new approvals are prohibited. The same envelope is checked again by `matches`, state and gateway. | `test_allowance_remediation.py`: unlimited, missing, duplicate, wrong token/owner/spender, negative/noncanonical/overflow amount, unexpected increase and excessive consumption all FAIL. Correct bounded approval and bounded consumption PASS. A forged PASS still produces `EXACT_SIMULATION_REQUIRED`. Re-fingerprinted mismatched calldata and a rebound approval wallet are rejected. **PASS**. |
| 4. LLM only accepts echoes; no app transport | Whole-response equality disallowed useful interpretation, and startup did not inject a configured transport. | Add bounded grounded `reasoning_summary` claims using existing evidence IDs and a controlled conclusion vocabulary. Allow selection/order of existing Opportunity strengths/weaknesses. All authoritative status, numbers, tickers, confidence, decisions, policies and correlation remain fixed. Wire an explicit configurable Chat Completions transport through application startup. | `test_llm_transport_remediation.py`: real HTTP request/response mechanics via MockTransport, valid **non-echo** summaries, app scan wiring, persistence, JSON-schema/JSON-object modes and shutdown. Malformed/missing/duplicate JSON, invented ticker/number/reference, invalid enum, contradictory output, correlation change, authority injection, timeout, HTTP 429/500, unavailable provider, empty/oversized output, refusal/tool calls and secret echo all safely DEFER. **PASS locally; external provider runtime UNVERIFIED**. |
| 5. Developer quota date has no test protection | Existing tests changed the market quota date or merely checked a constant non-executable result; no gateway test isolated the developer date. | Keep the existing hard requirement that both dates agree with UTC as-of date. Normalize the injected clock to UTC; require exact ISO date metadata. Add CLI fixture → adapter → actual `AgenticWalletCliGateway.dry_run` tests. | `test_wallet_quota_remediation.py`: valid, yesterday, tomorrow, missing/malformed, UTC midnight, different local date and unavailable metadata. The identical prior in-memory deletion mutation now causes **4 failures** in the full suite. **PASS; mutant killed**. |

### Settlement details and limits

Confirmation requires exact captured branch-specific terminal evidence, not just a terminal enum. RFQ needs FILLED, the bound platform order ID, hash, exact sell quantity, minimum acceptable received quantity and completed fill time. SWAP needs success without an error, positive height, Swap type, exact wallet/router, one matching sell and buy transfer, minimum receive, fee and transaction time. Derived fields must agree with this evidence. Evidence is revalidated even when the host used `model_construct` or `model_copy`.

RFQ creation must fall inside the **original bound quote** lifetime; completion may be later. SWAP settlement cannot predate that quote. This does not impose an incorrect lower bound on journal import time: an imported record may be created after its external order, but must retain the actual original quote/context. A newly created quote cannot establish a historical order's identity. No historical context is invented.

Contradictions remain sticky: conflicting hashes, latest conflicting hash and a settlement-conflict flag cannot be erased to obtain confirmation. Ten distinct hashes are kept in the bounded current list; the latest observed conflict is also kept separately on every update. The append-only, hash-linked journal therefore retains later conflicts even after the list fills. Terminal external records are immutable. Repeated terminal reads return the same record without another provider read. Duplicate/concurrent journal writes remain rejected by version/CAS rules.

The status wire response does **not** independently attest every local identity field. Binance's documented RFQ status contains order/status/hash/amount/time fields, not quote ID, vendor, wallet or request ID. These fields are immutable host request context, not invented provider response fields or a cryptographic proof. Actual settlement identity/finality and entitlement remain unverified. [Official Binance Trading API](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/trading-api).

No public API accepts settlement proof, changes controls, imports an executable attempt or exposes a submit/force-confirm operation. Host model constructors are not an authentication boundary: a trusted host can construct fictional complete evidence. Fixtures demonstrate contract enforcement, not real-chain truth.

### Allowance envelope

New unlimited approvals are never permitted by this implementation. For exact approval amount `A` and observed pre-allowance `P`, the required change is precisely the bound token/owner/spender with `pre=P`, `post=A` and `0 <= P < A < 2^256-1`. Approval calldata must encode that token, spender and amount, with zero native value. A fresh external allowance must equal `A`, not merely exceed it, before this approval can be considered confirmed.

For a SWAP with existing allowance `P` and sell quantity `S`, no allowance change is acceptable, or one matching effect must satisfy `pre=P` and `max(0,P-S) <= post <= P`. Unknown, unrelated, duplicate or increasing effects fail. An existing allowance is not a new approval policy grant. Matching simulation success is still **not live equivalence**. The envelope uses the documented `tokenAddress`, `owner`, `spender`, `preAmount` and `postAmount` fields. [Official Binance Transaction API](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/transaction-api).

Balance effects, economic decoding of opaque SWAP calldata, gas/nonce-sensitive equivalence and RFQ final settlement simulation remain separate unresolved capabilities. They are not certified by an allowance PASS, and all LIVE gates remain blocked.

### LLM configuration, authority and limits

Default `LLM_ENABLED=false` retains the deterministic fallback and makes no LLM calls. Explicit opt-in requires `LLM_PROVIDER`, `LLM_MODEL` and `LLM_BASE_URL`; `LLM_API_KEY` is host-only. The base URL is a credential-free HTTPS versioned root; the transport appends `/chat/completions`. It does not infer a model/vendor or enable execution. `.env.example` documents the configuration; no local credential file was edited.

Defaults: timeout 5 seconds, maximum output 50,000 UTF-8 bytes, token request cap 4,096, request body cap 200,000 bytes. Configuration bounds are 1–30 seconds, 1,024–50,000 output bytes and 128–8,192 tokens. The existing orchestrator also limits each call by its own timeout, total LLM generations to five, safe validation retries to one and total agent/tool budgets. Intent remains deterministic. Transport retry cap is zero: only the orchestrator owns retries. Timed-out/HTTP-failed work is not silently reissued. Redirects, provider tools, refusal/unfinished output and unbounded streamed output are rejected; stream reading is bounded even though generation requests use `stream=false`.

`LLM_STRUCTURED_OUTPUT=true` requests a strict JSON schema. `false` requests a JSON object while retaining identical local strict validation. Server support must be tested for the explicitly configured model. The protocol and schema-mode design were checked against [vLLM online serving](https://docs.vllm.ai/en/latest/serving/online_serving/) and [structured outputs](https://docs.vllm.ai/en/latest/features/structured_outputs/); documentation is not runtime verification.

Interpretation can choose which supplied evidence claims to emphasize and which existing strengths/weaknesses to present. It cannot introduce free-form financial claims, calculate economic values, raise confidence, choose a different trade or alter execution status. Unknown fields and changed authoritative values are rejected. Logs/persistence contain sanitized failure codes, never raw provider failures or credentials. Repeated identical point-in-time LLM inputs reuse their immutable persisted interpretation instead of allowing stochastic output to rewrite a record or spend another generation. The interpretation contract has its own identity namespace; fresh evidence/correlation produces a different run.

No live paid provider was invoked. **LLM_RUNTIME_CAPABILITY=UNVERIFIED**. This is not a dependency of the non-live Phase 6 gate; the deterministic explain/abstain path remains functional.

### Quota-date semantics

Both market and developer quota dates must match the injected **UTC** as-of date. Missing, invalid, future or yesterday's developer metadata blocks the gateway even when the market quota date is correct. The test changes developer metadata alone and verifies the failed `WALLET_QUOTA_DATE_CURRENT` check and reason through the actual gateway. Boundary fixtures use explicit future as-of instants; assertions never depend on the machine's current date.

The wallet provider's actual reset timezone remains unverified. UTC agreement is a conservative prerequisite, not proof of real daily reset behavior. `WALLET_QUOTA_RESET_TIMEZONE_NOT_VERIFIED` remains a LIVE blocker. Valid synthetic quota checks cannot create an execution grant.

## Related bypass review

Searched implementation and tests for RFQ/order reconciliation, hashes, CONFIRMED/force-confirm, allowance/approval/simulation SUCCESS, LLM provider/transport and quota dates. Inspected model validators, state transitions, durable store writes, gateway revalidation, wallet delegation, app startup and public APIs.

Related variants fixed and independently probed:

- Clearing a known hash, external binding or recorded conflict through state/store update.
- Wallet order containing another hash before tracker delegation; terminal wallet/history disagreement; later standalone tracker attempting to forget that conflict.
- Complete-looking evidence for another request/quote/vendor/wallet/mode/order; `model_construct` or `model_copy` bypassing initial construction.
- Old fills tied to a newly created quote; conflicting hashes after the bounded current list fills.
- Forged simulation PASS, missing expected approval, re-fingerprinted incompatible approve calldata, observed unlimited approval and a rebound approval wallet.
- Duplicate LLM JSON keys, contradictory/correlated output, unsafe provider URL, hidden HTTP retry, oversized output and repeated non-identical interpretation against one immutable run.
- Developer date alone invalid while market date remains valid; date coercion from integer/timestamp; UTC/local-midnight disagreement.

No alternate real executor, signer, RFQ submit, wallet mutation or broadcast path was added. The existing provider mutation-denial, public API denial, tool allowlist, mode isolation, funding/Risk controls, fingerprint/requote/resimulation, gateway and CAS/restart tests remain passing. This is a scoped audit, not a proof against every possible future integration.

## Full validation

| Check | Actual result |
|---|---|
| Full backend `.venv/bin/python -m pytest -q` | **1,061 passed**; original 962 retained, 99 new regression cases. No skips or xfails in the final result. |
| Full frontend `npm test` | **173 passed**, 9 files. |
| `npm run build` | **PASS**, includes `tsc --noEmit` and Vite build. |
| `.venv/bin/ruff check backend scripts` | **PASS**. |
| `.venv/bin/ruff format --check backend scripts` | **PASS**, 172 Python files. |
| `scripts/check-security.py` | **PASS**; configured-secret leakage, Git/Docker env exclusion and frontend isolation. |
| Additional configured-provider secret scan | **PASS**, including Twelve Data/Finnhub/Polygon names; values only held in memory. |
| `.venv/bin/python -m pip check` / `npm ls --all` | **PASS**, no broken Python requirements or Node dependency-tree errors. |
| `git diff --check` | **PASS**. |
| Built-UI disposable Chrome, desktop/mobile | **PASS**: six NORMAL/NOISE/INFORMATION scenarios, full existing paper hero flow, 39 local requests, no page overflow/runtime errors. Ordinary Overview retains INSUFFICIENT_EVIDENCE; production Opportunity navigation stays disabled. Zero live execution calls and zero production Trust calls from Demo Sandbox. |
| Original adversarial probe replay | Hash change → UNKNOWN/original hash retained; pre-quote fill → UNKNOWN; enum-only confirmation rejected; wallet hash disagreement → UNKNOWN; unrelated unlimited allowance SUCCESS → FAIL/BLOCKED; valid alternative interpretation → analytical BUY with execution unauthorized; stale developer date → BLOCKED. |
| Identical original quota deletion mutation, full suite | **4 failed, 1,057 passed**: stale, future, UTC-midnight and local-date gateway tests catch it. Expected experiment failure proves the missing control is detected; disk source was not altered. |
| Fresh isolated app contract | Health/status HTTP 200, DRY_RUN, submit/settings endpoints HTTP 404; master `$100 / risk $10 / no preference` safely returns NO_QUALIFYING_OPPORTUNITY under unchanged platform limits. |

Warnings: the existing FastAPI/Starlette `httpx` TestClient deprecation and two Pydantic serializer warnings intentionally caused by malformed constructed allowance test values. No warning was suppressed to conceal a failure. Dependencies were not upgraded during this safety remediation.

The exact scripts for the original attack replay, mutation and browser harness are embedded in the evidence JSON. Ordinary suites run without the mutation plugin. Local private logs are in `/private/tmp/parity-remediation`; durable evidence is in this report and the JSON. Browser servers used only verified-unused ports 8011–8013 and 5174, synthetic providers and in-memory databases; temporary servers/profiles were stopped after verification.

## Independent phase reassessment

These labels assess master requirements individually and do not overwrite historical narrower PASS reports or any production gate.

| Master phase | Follow-up status | Confidence | Requirements covered and actual integration | Remaining gaps |
|---|---|---|---|---|
| 6 — Multi-Agent Intelligence | **PASS for implemented non-live acceptance scope** | HIGH | Six structured agents, bounded calls/tools, top-K, memory, deterministic authority, grounded non-echo interpretation, actual transport/app wiring, schema/provenance/correlation validation, persistence and safe fallback/abstention. HTTP and paid-provider behavior tested with explicit synthetic MockTransport; real local HTTP/DB boundaries are exercised. | Configured external model availability, entitlement, server schema support, latency and output quality remain **UNVERIFIED**. No paid-provider dependency is added to this phase gate. |
| 7 — Opportunity Mode | **PARTIAL** | HIGH | Discovered/configurable universe, full deterministic filtering, rejection audit, top-K, candidate table, common ranking/Routing/Risk, ex-ante sizing, non-forced master mandate, final Risk and now usable bounded interpretation. Existing full-universe/API/isolation tests rerun. | Default real `DataLayerScanSource` still does not assemble authoritative costs/routes/risk context; the optional research loader is not wired by `main.py`. This is an **implementation/host-integration gap**, not merely entitlement. Real Trust is also blocked. No synthetic preview is substituted. |
| 8 — Safety and Execution | **PARTIAL overall; non-live safety gate PASS** | HIGH | Risk/funding/quote/dynamic SWAP-RFQ/approval/fingerprint/simulation/state/journal/gateway contracts; evidence-derived exact settlement; immutable hashes/conflicts; enforced allowance envelope. Positive/negative protocol tests and real local persistence/CAS/recovery pass. | Actual provider execution/economic effects, opaque SWAP decoding, gas/nonce equivalence and real finality remain D/unverified. RFQ exact final settlement simulation/equivalence unavailable. Full LIVE mechanism is not certified. |
| 9 — Agentic Wallet | **PARTIAL overall; read/DRY_RUN contract PASS** | HIGH | Strict CLI reads/arguments/schema/subprocess limits, capability/session/security/quota checks, mode isolation, actual gateway composition and exact tracker corroboration. Synthetic CLI and local fake executable tests; app has no connected CLI worker or wallet writer. | Installed/authenticated current official runtime, exact preview/execution mechanism, restrictions/App confirmation, reset timezone and authoritative state remain unverified. No real wallet command or authentication/session mutation was issued in this run. |

Evidence levels remain distinct: repository inspection/algorithms are C; HTTP/CLI protocol tests are **B-synthetic**; pre-existing captured real data remains B-captured; absent actual authenticated provider/runtime proofs remain D. A strict schema or successful synthetic fixture is not A evidence. The old audit's weaker-oracle cautions still apply to tests not remedied here; existing statistical fixtures do not become real 30/30/3 evidence.

## Production gates and protected artifacts

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

All gate semantics, 30/30/3 safeguards, 120-second freshness, 30-second alignment, production Trust/Risk/Routing economics, DEMO isolation and public no-execution boundary remain unchanged. No Twelve Data integration or live alignment diagnostic was run. Real historical coverage/ratio/liquidity blockers remain, with no backfill or synthetic real-evidence count.

The 378-artifact before-hash inventory was retained without reducing its scope: **360 original artifacts unchanged**, **18 explicitly authorized originals changed**, no deletion. The three earlier audit artifacts, master, all original docs, all frontend sources, production Trust/research/Routing/DEMO/scan services and data files are byte-identical. Existing tests retain their assertions; only two original test files had synthetic setup/positive-observation inputs corrected for the stricter contracts. The synthetic approval provider now reports the actual bounded approve effect instead of an empty SUCCESS array. No captured real provider or historical fixture was edited. No production database or local `.env` was modified.

Compatibility is deliberately fail-closed: old CONFIRMED execution records without complete bound settlement evidence and old prepared approvals without the observed pre-allowance cannot be reinterpreted as verified under the new contract. No production store was migrated or rewritten. Preserve such evidence for manual/read-only review; rebuild only non-submitted preparation from verified current inputs. Imported external attempts are never automatically resubmitted.

## Files changed

Existing implementation:

- `.env.example`
- `backend/app/agents/orchestrator.py`, `provider.py`, `schemas.py`
- `backend/app/config.py`, `main.py`
- `backend/app/models/execution.py`, `wallet.py`
- `backend/app/repositories/execution.py`
- `backend/app/services/agentic_wallet.py`, `execution_builders.py`, `execution_simulation.py`, `execution_state_machine.py`, `execution_status.py`, `wallet_reconciliation.py`

New implementation:

- `backend/app/agents/interpretation.py`
- `backend/app/clients/llm.py`
- `backend/app/services/execution_confirmation.py`

Existing synthetic tests/fixture:

- `backend/tests/fixtures/execution_fixtures.py`
- `backend/tests/unit/test_agentic_wallet.py`
- `backend/tests/unit/test_execution_safety.py`

New regressions:

- `backend/tests/integration/test_settlement_remediation.py`
- `backend/tests/integration/test_allowance_remediation.py`
- `backend/tests/integration/test_llm_transport_remediation.py`
- `backend/tests/integration/test_wallet_quota_remediation.py`

New documentation/evidence:

- `docs/PHASE_6_9_REMEDIATION_AUDIT.md`
- `docs/evidence/PHASE_6_9_REMEDIATION_AUDIT.json`

## Advancement recommendation

**SAFE_TO_ADVANCE_TO_PHASE_10=YES_FOR_NON_LIVE_DEVELOPMENT_ONLY, under a separate future task authorization.** The five requested safety/functional defects are closed, the no-execution boundary holds, and existing fixtures permit isolated non-live position work. This does not assert complete production Phase 7–9 integration or authorize trading. The development/execution gate separation remains in force: unresolved external LIVE capabilities do not block safe DEMO/DRY_RUN development.

Before real production Opportunity can operate, finish authoritative host input assembly and resolve the existing Trust evidence blockers. Before any live execution, independently verify and pass the relevant unchanged LIVE gate. No unconditional production-readiness PASS is issued by this audit.

**PHASE_10_STARTED=false. No wallet signing, SWAP execution, RFQ submission, transaction broadcast, settings mutation or funds movement occurred. Work stops after this remediation audit.**
