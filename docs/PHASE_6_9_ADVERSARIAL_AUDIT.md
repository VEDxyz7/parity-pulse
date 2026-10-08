# Independent adversarial audit — Master Phases 6–9

Audit date: October 8, 2026 (Asia/Kolkata). Audited checkpoint: `d8ba445e37243ab5581d060f160360fbedaf7c40`, initially clean.

**Recommendation: fix and audit further before Phase 10.** The deterministic analytical implementation is substantial and the no-execution boundary holds. The four unrestricted implementation PASS labels are too broad: functional LLM interpretation is missing, and exact settlement confirmation has reproducible defects. No application code, existing tests, gates, thresholds, historical reports or data were changed during this audit. No Phase 10 work, wallet authentication, order submission, transaction broadcast or commit occurred.

## Authority, scope and evidence

The entire sole authoritative [MASTER_SPEC.md](MASTER_SPEC.md), lines 1–5321, was reread. Its SHA256 is `f69a9bd01a622c001c3ec6cb654e00562f6b3d03a8310f9e5ccf68efe4b49c84`. Requirements below include sections 28–39A, funding/quote/approval/simulation/execution controls, provider boundaries, testing requirements and the exact Phase 6–9 build/gate lists at lines 4664–4747. Older specifications were not substituted.

Evidence levels are deliberately separate:

- **A:** prior actual provider/runtime observations, with timestamps and limitations. This audit did not renew authenticated market/provider reads.
- **B-captured:** sanitized captured provider fixtures; useful contract regression, not a fresh entitlement test.
- **B-synthetic:** explicitly constructed protocol/market fixtures, fake subprocess executables or echo/error LLM transports. These are not sanitized real transactions or actual wallet access.
- **C:** deterministic local logic, real local database/HTTP/subprocess/browser integration.
- **D:** unavailable or not independently verified. Public documentation alone does not become A.

[Machine-readable audit evidence](evidence/PHASE_6_9_ADVERSARIAL_AUDIT.json) contains probe inputs/results, full reproducible isolated probe and mutation-plugin source, commands, browser observations, checksums and preservation results. [Keyword inventory](evidence/PHASE_6_9_HOLLOW_INVENTORY.json) records every match in the stated repository-text scope, with path, line, column and classification. Earlier reports remain historical evidence, not overwritten conclusions.

All adversarial probes used synthetic addresses, fixed fixture timestamps and memory-only stores. Those timestamps are test inputs, not current market observations. The private workspace was `/private/tmp/parity-adversarial-audit`.

## Independent phase assessment

Confidence here means confidence in the assessment, not external readiness.

| Phase | Implementation status | Confidence | Reason |
|---|---|---|---|
| 6 — Multi-Agent Intelligence | **PARTIAL** | HIGH | Six bounded deterministic agents, structured evidence, memory and safe abstention work. The optional LLM accepts only an exact echo; configured provider/model transport is not connected to application startup. The master interpretation/provider scope is incomplete. |
| 7 — Opportunity Mode | **PARTIAL** | HIGH | Full-universe deterministic filtering, ranking, top-K, ex-ante sizing, no-op and API/audit boundaries work. The required stage-2 LLM interpretation inherits Phase 6's gap; real costs/routes/risk/research inputs are not assembled by the default real source. |
| 8 — Safety and Execution | **PARTIAL** | HIGH | DRY_RUN, PROPOSE_ONLY, quote/fingerprint/approval checks and unconditional live blocks work. RFQ reconciliation changes a known hash; the state machine can confirm without complete settlement evidence. Successful simulation does not validate its economic effects. |
| 9 — Agentic Wallet | **PARTIAL** | HIGH | Correct CLI read abstraction, explicit BAW_UNAVAILABLE, strict isolation and disabled writes. Wallet reconciliation can corroborate one hash and persist confirmation of another through Phase 8. Real runtime/account capabilities remain D, accurately disclosed. |

This does **not** erase narrower achievements: the Phase 6 deterministic explain/abstain exercise passes; the Phase 7 `$100 / risk $10 / no preference` non-forced outcome exercise passes; Phase 8's current no-live-execution gate passes. Phase 9's documented read/DRY_RUN contracts are testable without capital, but exact reconciliation is not yet reliable. Missing live entitlement is not itself a bug or a reason to invent functionality.

## Phase 6 requirement audit

Paths below are relative to `backend/` unless prefixed otherwise. Test names refer to existing, unchanged tests.

| Requirement | Implemented? | Evidence/file | Test covering it? | Evidence level | Risk/gap |
|---|---|---|---|---|---|
| Six real agent responsibilities | YES, deterministic | `app/agents/{intent,market,news,research,opportunity,decision}_agent.py` | `unit/test_agents.py::test_existing_demo_pipeline_same_financial_services` and role-specific tests | C / B-synthetic | Real service calls and distinct typed outputs; not empty classes. LLM intelligence is a separate missing capability. |
| Structured mandate; explicit user budget/risk | YES for supported grammar | `intent_agent.py`, `schemas.py` | `test_intent_explicit_finance_only`, `test_explicit_master_opportunity_wording_and_other_verified_stock` | C | Unsupported/ambiguous language abstains; no financial limit inferred. Broader natural-language interpretation not verified. |
| Strict schemas; malformed output fails | YES | `schemas.py`, `orchestrator.py:236` | `test_strict_schema_rejects_float_extra_fields_unsafe_modes_and_confidence`, malformed/retry tests | C / B-synthetic | Unknown fields/floats/authority are rejected; real vendor schema behavior D. |
| Financial facts immutable | YES | `orchestrator.py:239`, `OpportunityOutput`, candidate contracts | hallucination/invented-edge tests | C / B-synthetic | Equality is safe but also rejects legitimate interpretation-only changes: F1. |
| Market/news interpretation with source time | YES, constrained | `market_agent.py`, `news_agent.py` | stale-equity and publication/look-ahead tests | C / B-synthetic / B-captured | News is bounded headline evidence, not verified causality; confidence remains LOW. |
| Existing Phase 5 retrieval/model reused | YES | `research_agent.py`, `HistoricalRetrieval`, `RollingOpeningModel` | `integration/test_agent_evidence.py` | C / B-synthetic; prior real replay A | Tests demonstrate actual calls, not calibrated real predictive power; real 30/30/3 remains unsatisfied. |
| Summary/strengths/weaknesses/conflicts | PARTIAL | `schemas.py:202`, `opportunity_agent.py:56` | ranking/rejection tests | C | Bounded code conclusions exist. No independent LLM explanation is accepted; no separate opportunity reasoning-summary field. F1. |
| Bounded calls, retries, timeout, tool depth | YES | `AgentPolicy`, `orchestrator.py`, `tools.py` | budget, retry, timeout, depth tests | C / B-synthetic | Generation cap includes retries; timeout does not retry unknown work. No hostile external Python transport sandbox promised. |
| Closed tool registry | YES | `tools.py::ALLOWLIST`, `ToolRegistry` | `test_agent_tools_have_only_allowlisted_readers`; network-denial test | C | No model-selected URL/SQL/wallet/sign/execute tool. |
| Default K=4, mode/stock/regime-scoped memory | YES | `memory.py::AgentStore`, policy defaults | K4/future-outcome/scorecard and durable restart tests | C, actual SQLite | K is configurable 1–10, as master default allows; not an unconditional exactly-four rule. |
| No private chain-of-thought stored | YES for supported contracts | `MemoryEpisode`, `AgentStore` | `test_memory_no_chain_of_thought_or_raw_credentials_contract` | C | Codes/features/evidence IDs only; no arbitrary raw provider prose persisted by these contracts. |
| Risk/disagreement/failure cannot grant execution | YES | `decision_agent.py`, bound risk preview, literal false fields | risk failure, missing route, user risk, disagreement, execution-denial tests | C / B-synthetic | BUY is an analytical DEMO recommendation. Production candidates defer. |
| Configurable usable LLMProvider/model | PARTIAL | `provider.py`, `orchestrator.py:209–251`, `app/main.py:115` | Echo/configuration/error tests only | B-synthetic / D | Protocol and configuration exist, no application transport wiring; exact-echo constraint prevents interpretation. F1. |

### F1 — LLM path is an exact-echo verifier, not the specified interpreter

**Severity: MEDIUM; confirmed functionality gap, not an execution bypass.** The orchestrator first computes each deterministic response. It sends both that complete canonical response and its schema to the optional provider, then rejects `parsed != response`. No change to strengths, weaknesses, explanation or conflicts is admissible, even if all prices, eligibility, risk, selected candidate and authority are identical. `OpportunityOutput` has no separate reasoning-summary field. `main.py` constructs `AgentOrchestrator(store=agent_store)` without a provider or configured transport.

The audit provider echoed all responses except it removed one optional Opportunity strength code, keeping `DETERMINISTICALLY_ELIGIBLE`. `OpportunityResponse.model_validate` accepted the alternative. The workflow nevertheless produced Opportunity `UNAVAILABLE`, final `DEFER`, and `AGENT_FAILED_CLOSED`. Five calls were consumed. Thus model transport/echo tests cannot establish genuine interpretation. The existing Phase 6 report accurately discloses deterministic defaults and unverified entitlement; that disclosure does not complete master section 39A's LLM interpretation stage.

## Phase 7 requirement audit

| Requirement | Implemented? | Evidence/file | Test covering it? | Evidence level | Risk/gap |
|---|---|---|---|---|---|
| Configurable discovered universe | YES within explicit supported bounds | `models/opportunity_scan.py`, `opportunity_sources.py`, asset discovery | dynamic discovery/quarantine API contract test; universe tests | C / B-captured | Refuses oversized universes rather than choosing a favorable prefix; no claim of arbitrary unbounded coverage. |
| Actual full-universe deterministic scan | YES | `OpportunityScanService.scan/generate`, full audit rows | multi-stock benchmark/top-K/order tests | C / B-synthetic | Current DEMO source supplies one representation; 10/25/50/100 benchmarks clone synthetic inputs, not actual stock coverage or provider throughput. |
| Filtering before agent/LLM calls | YES | `opportunity_scan.py` | rejected-candidate/no-LLM and top-K tests | C / B-synthetic | Rejected catalog rows and filter reasons remain in audit. |
| Rejected candidates retain reasons | YES | `CandidateAudit`, quarantine and rejection counters | filter matrix/quarantine tests | C / B-captured / B-synthetic | Not a winner-only table. |
| Default top-K=5, may tighten | YES | `ScanPolicy`, schema and ranking | top5/tightened3/schema tests | C / B-synthetic | Provider sees reduced candidate table; full universe retained separately. |
| Deterministic economics/ranking | YES | shared `agents/opportunity_agent.py::ranked`, `RoutingService` | reversed ordering, changed economics, issuer comparison tests | C / B-synthetic | Explicit lexicographic priorities; no opaque weights. |
| Missing cost never becomes favorable zero | YES | cost/route filters, `ScanCosts` | missing/stale cost, size mismatch and net-edge tests | C / B-synthetic | Real costs absent means rejection, not manufactured estimates. |
| Authoritative candidate table; no invented numbers | YES locally | `Candidate`, immutable references, orchestrator equality | schema and hallucination tests | C / B-synthetic | Data provenance/runtime truth remains external D where unavailable. |
| Ex-ante risk budget, no forced BUY | YES | `RiskEngine.size`, shared `position_caps`, request-bound final risk | caps/sizing and master mandate tests | C / B-synthetic | Risk budget is stress-based, not guaranteed realized loss. `$100/risk$10` exceeds unchanged DEMO $5 platform cap and safely gives NO_QUALIFYING_OPPORTUNITY. |
| Trust-blocked cannot be promoted by agent | YES | hard filters, final decision, literal production gates | real-unavailable/API injection and agent tests | C | `PRODUCTION_OPPORTUNITY_GATE_BLOCKED_BY_TRUST` remains enforced, including real hypothetical ready inputs. |
| Batched LLM interpretation | PARTIAL | Phase 6 orchestrator | echo-only five-call tests | B-synthetic / D | F1; numeric immutability verified, actual interpretation absent. |
| Real provider/service boundary integration | PARTIAL | `DataLayerScanSource`, API/main lifecycle | dynamic discovery/real-unavailable adapter tests | C / B-captured | Discovery/Trust connected; default research/cost/route/risk preview assembly missing. F5. |
| Final Risk after Decision | YES against supplied snapshot | `opportunity_scan.py:387`, risk preview | `test_final_risk_after_agents_cannot_be_bypassed` | C / B-synthetic | Test patches the third Risk call. It does not prove fresh real account-state acquisition; current real output cannot BUY. |
| Immutable audit, retrieval, restart, isolation | YES | `repositories/opportunity_scan.py`, `api/opportunity_scan.py` | API roundtrip/store integrity/mode tests | C, real local DB/HTTP | Public caller cannot provide economics, policies, candidate table or LIVE mode. |

### F5 — Real scan integration stops before required preview inputs

**Severity: MEDIUM; documented operational gap.** `DataLayerScanSource.capture` actually discovers representations and invokes the existing Trust service. It returns a `ScanSnapshot` without cost mappings, executable-route previews or an authoritative risk context. Research inputs are only supplied if a host `research_loader` was injected; `main.py` does not inject one. Separately, real scans intentionally remain blocked by the production Opportunity Gate. Removing a data blocker later will therefore not make the existing application a ready production Opportunity pipeline; host integration work remains. This is not a suggestion to remove the global block or use DEMO values.

## Phase 8 requirement audit and bypass analysis

“No bypass found” below is scoped to the examined repository paths and current configuration, not a mathematical proof or authorization for LIVE. Host-only model constructors are not public API authentication boundaries.

| Safety control | Implemented? | Evidence/file | Existing test | Evidence level | Alternate-path/bypass assessment |
|---|---|---|---|---|---|
| Current Risk and ex-ante hard caps | YES | `risk.py::evaluate_execution`, gateway recalculation | hard rejection matrix; user-risk and autonomous tests | C / B-synthetic | No caller/agent can submit through a separate executable gateway. Analytical inputs still require authoritative host provenance. |
| Funding identity, decimals, balances, conversion, gas reserve | YES locally | `funding.py`, gateway checks | funding/base-unit/gas/precision tests | C / B-synthetic; resolution adapter B-captured | Actual balances/prices not verified A. Unknowns block; source fields are not independently signed attestations. |
| Exact quote binding/lifetime | YES | `aggregator_quote.py`, `current_quote`, quote contracts | quote/mode/expiry/ranking tests | C / B-synthetic | Expired quote cannot be used by preparation/gateway. Requote clears old artifacts and consent. |
| Dynamic executionMode | YES | provider quote/build contracts, `execution_builders.py` | dynamic-mode and branch tests | C / B-synthetic | No issuer-mode hardcoding. Unknown/contradictory mode blocks. |
| SWAP transaction builder | PARTIAL live semantics | `ExecutionRouteBuilder`, `BinanceSafetyClient.build` | wire and field mutation tests | C / B-synthetic / D | Metadata/bytes bound; opaque calldata economics not decoded/verified. No real built transaction was tested. |
| RFQ payload/field binding | PARTIAL explicitly | RFQ schema, EIP712 validator, binding inspector | structured/opaque RFQ tests | C / B-synthetic / D | Opaque typed payload remains unverified; settlement simulation unavailable. RFQ live stays blocked. |
| ERC-20 approval flow | YES for non-executing preparation | `ApprovalService`, observe/rebuild/resimulate | exact calldata, amount, spender, failed approval tests | C / B-synthetic | Decode restricts actual approve bytes; no infinite approval permitted. External allowance confirmation is distinct from simulation. |
| Critical transaction fingerprint | YES | typed canonical SHA256 and boundary revalidation | field/payload mutation tests | C / B-synthetic | Changed bytes/metadata cannot reuse old simulation. A fingerprint establishes identity, not economic correctness. |
| Simulation status, exact payload and receipt | YES narrowly | `execution_simulation.py` | failure/conflict/expiry/provider isolation tests | C / B-synthetic | RFQ unavailable; failed simulation blocks; matches binds payload/fingerprint. |
| Simulation economic effects/equivalence | PARTIAL | `execution_simulation.py:52`, `ExecutionSimulation` | No adverse-success effect test; audit probe F4 | B-synthetic / D | Unexpected unlimited allowance can still get analytical PASS. Gas-sensitive/effect equivalence remains false and blocks LIVE. |
| Legal state transitions/current artifacts | YES for preparation | `execution_state_machine.py` | illegal skips, stale/funding/approval tests | C / B-synthetic | Submission is refused unconditionally. Terminal-confirmation proof is insufficient: F3. |
| Exact terminal status reconciliation | PARTIAL | `execution_status.py:35–74`, wallet downstream | terminal/missing-field tests; audit probes | C / B-synthetic / D | Known RFQ hash overwritten; wallet corroboration not preserved: F2. |
| Durable identity/idempotency/recovery | YES locally | `ExecutionStore`, CAS/unique decision/chain journal | actual restart/two-worker/journal tests | C, real SQLite | UNKNOWN/pending cannot trigger preparation/requote/new order. Journal integrity records the bad confirmation accurately; it does not cure it. |
| PROPOSE_ONLY confirmation binding | YES locally | `UserConfirmation`, gateway validation | exact decision/fingerprint/expiry tests | C / B-synthetic / D | No public confirmation endpoint; actual App transaction confirmation D. Model source labels alone are host assertions. |
| Single gateway, DRY_RUN cannot broadcast | YES | `DryRunExecutionGateway`, literal controls, client allowlists | pre-network denied paths, sockets, 404 endpoints | C / B-synthetic | No executable transport/signer present. This safety invariant holds despite F2/F3/F4. |
| Unknown status cannot authorize retry/order | YES | tracker/recovery/refresh guards | UNKNOWN, restart, RFQ retry-digest tests | C / B-synthetic | Read retry only; mutating submit/broadcast methods always refuse. |

### F2 — Known RFQ hash can be replaced; wallet corroboration confirms another transaction

**Severity: HIGH for settlement integrity; confirmed.** `ExecutionStatusTracker.reconcile` compares the RFQ order ID, sell amount and minimum receive, but only requires returned `txHash` to be non-null. It does not compare a previously known `attempt.tx_hash`. It overwrites the journal hash at lines 71–74. By contrast, SWAP reconciliation explicitly compares hashes.

Reproduction used an existing synthetic external RFQ attempt with known hash `0x555…555`, order `platform-order`, and a schema-valid FILLED response with matching amounts but hash `0x666…666`. Result: `EXECUTION_CONFIRMED`, recorded hash `0x666…666`.

The stronger end-to-end probe supplied wallet order `FINISHED` and wallet history `confirmed`, both for `0x555…555`, then supplied the RFQ tracker response for `0x666…666`. Result: wallet state FINISHED, execution CONFIRMED, final hash `0x666…666`, reason `PHASE8_EXACT_SETTLEMENT_RECONCILIATION`. The exact same transaction was not corroborated. Existing successful wallet tests start with no attempt hash or agree on all hashes, so they miss this case.

The chronology probe also accepted a FILLED timestamp of October 6 against a quote/attempt timestamp of October 8. It checks `createdAt <= filledAt <= receipt`, but does not bind external order chronology to the imported quote/attempt context. **This is a policy/binding gap to investigate, not a blanket assertion that an old fill is invalid:** an imported journal can legitimately be created after the external order. The intended external order creation/quote relationship must be explicitly verified rather than imposing an incorrect import-time lower bound.

These probes cannot submit anything. The immediate defect is false terminal bookkeeping; Phase 10 position/reconciliation must not consume that bookkeeping as exact evidence.

### F3 — Host state-machine path confirms without complete settlement evidence

**Severity: HIGH for future confirmation consumers; confirmed host-boundary weakness.** Calling `ExecutionStateMachine.transition` on an imported pending attempt with target CONFIRMED, `external_status="FILLED"` and `settled_at=NOW` succeeds. It requires no filled quantity or exact settled transfer evidence and invokes no provider tracker. The result has `filled_quantity_base_units=null` and `EXECUTION_CONFIRMED`. `ExecutionAttempt` likewise validates terminal success from a supported label and a non-null settlement time.

The state machine accepts trusted host updates; it is not presently reachable from a public execution API or an agent tool. Thus this is **not a demonstrated network exploit or live-execution bypass**. It means exact settlement is not an invariant of every confirmation path, despite the stronger tracker-based claims. A later position consumer cannot trust the enum alone. The store can persist such validated records; hash chaining proves consistency, not provenance.

### F4 — Successful simulation can contain unauthorized effects

**Severity: MEDIUM now; high-priority prerequisite for any later LIVE work.** A syntactically valid SUCCESS simulation containing an unrelated token's allowance change to an unrelated spender for `2^256−1` was accepted as simulation PASS, and preparation reached `APPROVAL_CONFIRMED`. The response schema validates field types, and SUCCESS/failReason consistency, but the service does not validate expected versus unexpected balance/allowance effects. Most happy fixtures have empty effect arrays and a synthetic four-byte swap payload, which proves binding/status handling rather than actual economically correct settlement.

`live_equivalence_verified=false` remains enforced, and the gateway also returns live-gate/DRY_RUN blockers. The earlier report correctly limits coverage to from/to/value/data. Nevertheless, analytical PASS is weaker than verified transaction safety; it must not be reused as such when extending the gateway. This finding concerns simulation effects, not the separate approval builder, whose approval amount/spender decoding is implemented.

### Alternate-path search

The complete targeted outbound/call inventory is retained in the audit evidence. Reviewed paths:

| Possible alternate path | Result |
|---|---|
| `ReadTransport` / centralized Binance signer | Bound endpoints and methods; no arbitrary URL; redacted transport; bounded retries. |
| `BinanceSafetyClient.submit_rfq` / `broadcast` | Always raise before HTTP; no network submission implementation. |
| quote/build/approval/simulation APIs | Preparation/read operations only; no order created. Semantic gaps above remain explicitly separate. |
| `BawReadOnlyClient` subprocess | Closed argv grammar, no shell, bounded output/timeout, constrained environment; mutation function denied. |
| `ExecutionGateway` subclasses | Only non-executing DryRun gateway and its wallet wrapper; no second live transport. |
| Agent tools/provider | No execution/wallet mutation reader; raw output is untrusted. Provider is a host-injected Python transport, not a security sandbox. |
| Public API/frontend | Ask/Trust/analysis and isolated DEMO paper writes; real execution/approval endpoints absent. Production Opportunity navigation remains locked. |
| Diagnostic scripts | Explicit market/history/equity readers, not automatically scheduled/trading workers. The pending alignment diagnostic was not run. |
| Direct model/state/store host calls | Cannot broadcast; can create inadequate terminal records (F3). Do not confuse host-only access with a public execution grant. |

## Phase 9 requirement audit

| Requirement | Implemented? | Evidence/file | Test covering it? | Evidence level | Risk/gap |
|---|---|---|---|---|---|
| Actual official mechanism, no invented REST | YES as documented abstraction | `clients/baw_cli.py`, [capability report](AGENTIC_WALLET_CAPABILITIES.md) | exact command/flag tests | C / B-synthetic; runtime D | Uses documented `baw`; public Web3 REST not mislabeled Agentic Wallet. |
| Explicit BAW_UNAVAILABLE | YES, observed again | `AgenticWalletAdapter`, local executable inventory | unavailable/disabled tests plus fresh audit read | A for runtime absence only | PATH has no `baw`; fresh capability UNAVAILABLE, source UNAVAILABLE, errors BAW_UNAVAILABLE, no observed address. This is not authenticated wallet access. |
| Status/address/chains | YES adapter; actual access D | wallet snapshot contracts | malformed/disconnected/chain/address tests | B-synthetic / D | No invented real address or supported-chain claim. |
| Balances/units/gas funding matching | YES adapter; actual access D | `human_base_units`, normalized balances/preflight | exact amounts/mismatch/roundup tests | C / B-synthetic / D | CLI balance mark has no authoritative price timestamp; not independent market data. |
| Security settings and independent quotas | YES locally | `WalletSafetyChecks.evaluate` | restriction/developer/cooldown tests | C / B-synthetic / D | Current code checks both quota dates. Developer date removal survives all tests: Q1. |
| Token restrictions/confirmation policy | PARTIAL safely | settings/limit checks | restricted token / NeedConfirmation rejection tests | C / B-synthetic / D | Restricted list not exposed and App transaction confirmation unverified; blocks rather than bypasses. |
| Quote/order/history reads | YES contract; actual access D | `read_records`, closed commands | args/malformed/binding tests | C / B-synthetic / D | Indicative quote lacks exact executable transaction binding. Unknown order statuses stay UNKNOWN. |
| CLI gateway preserves Phase 8 | YES non-executing | `AgenticWalletCliGateway` | gateway mode/no-execution tests | C / B-synthetic | All Phase 8 live blockers remain. Some tests assert a constant false result rather than a particular safeguard: Q6. |
| Exact settlement reconciliation | PARTIAL | `WalletReconciler` → tracker | FINISHED-alone/conflict/restart tests; audit F2 | C / B-synthetic / D | Can corroborate old hash and confirm another. Earlier “exact” completion claim needs correction. |
| DEMO cannot enter LIVE_READ_ONLY | YES | source/mode checks before calls | mode isolation/API tests | C / B-synthetic | Rejected before CLI/provider calls, not relabeled real data. |
| DRY_RUN/agents cannot change settings or funds | YES | mutation denial and closed agent tools | no-execution/injection/allowlist tests | C / B-synthetic | No signing, submit, settings mutation or real transaction. |
| Secrets and bounded errors | YES in tested scope | restricted child env, decoder, error sanitization | fake executable/env/timeout/overflow tests; security audit | C / B-synthetic | Real CLI session/security behavior unverified; static scan is not a full security assessment. |
| Durable recovery/idempotency | YES locally with confirmation caveat | shared Phase 8 store/CAS/recover | restart/unknown/no-new-order tests | C | Idempotent erroneous confirmation is still erroneous; F2/F3. |

Official public references were rechecked in this audit: [wallet manifest](https://raw.githubusercontent.com/binance/binance-skills-hub/main/skills/binance-web3/binance-agentic-wallet/SKILL.md), [preflight](https://raw.githubusercontent.com/binance/binance-skills-hub/main/skills/binance-web3/binance-agentic-wallet/references/preflight.md), [Trading API](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/trading-api) and [Transaction API](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/transaction-api). They describe the CLI/preflight mechanism and separate preparation, status and execution operations. Document access does not verify local installation, permissions or account access.

## Test-quality findings

**Would these phases still appear to pass if the test suite were weaker than it should be? YES.** More strongly, the present complete suite still passes with one real hard-control check removed in memory. Passing counts alone do not justify the original broad PASS labels.

| ID | Suspicious existing test/fixture | What it really proves | What it misses / audit result |
|---|---|---|---|
| Q1 | `unit/test_agentic_wallet.py::test_actual_wallet_restrictions_are_hard_stops` | Market quota-date rejection and several independent limits | No stale developer quota-date case. Audit removed only `and s.developer_quota_date == now.date()` in process memory: all **962 backend tests** still passed; stale developer date changed BLOCKED → PASS. All 116 wallet tests also passed separately. On-disk control stayed intact. |
| Q2 | `test_five_batched_provider_calls_metadata_and_deterministic_confidence`, `test_configured_provider_metadata_not_secrets_reaches_agents` | Echo call counts, metadata isolation, serialization | Transport returns the supplied expected response. Does not prove independent interpretation; legitimate schema-valid alternative fails F1. |
| Q3 | `test_provider_http_failure_sanitized_fail_closed` | RuntimeError sanitization/defer | “429”/“500” are strings in a thrown RuntimeError, not actual LLM HTTP responses, retry headers or an implemented HTTP adapter. Binance HTTP MockTransport tests are stronger, but do not supply an LLM transport. |
| Q4 | `test_news_external_prompt_is_data_only`, line 187 | Other assertions check direction/publication handling | `decision != BUY or not execution_authorized` is vacuous when execution_authorized is a schema literal false. It does not require no analytical BUY. Not every assertion in this test is weak. |
| Q5 | `test_recursion_denied` | Directly set `_running=True` is denied | Does not exercise overlapping asynchronous workflows/cancellation race. Current bound check exists; no race was established by this audit. |
| Q6 | `test_gateway_preserves_all_phase8_checks_and_no_execution_in_any_approval_mode` | Wrapper refuses execution and records baseline reasons | The missing-simulation branch asserts only `execution_ready is False`, which is always false. This does not prove that particular simulation guard survives removal. More specific reason tests elsewhere retain value. |
| Q7 | `test_unknown_partial_or_mismatched_rfq_settlement_never_confirms`, RFQ terminal tests | Missing hash/amount/order fields and minimum receive fail | No differing non-null previously known hash, no wallet/hash disagreement, no imported order chronology policy. F2 still confirms. |
| Q8 | `test_exact_phase8_tracker_required_for_wallet_reconciliation` | Tracker called; matching synthetic terminal labels map correctly | Agreeing/no-known-hash fixtures cannot expose cross-provider transaction identity mismatch. End-to-end adverse probe F2 exposes it. |
| Q9 | `FixtureProvider.simulate`, integration `Wire`, `build` | Typed serialization, fingerprints, branching | SUCCESS with empty changes and `0x12345678`; opaque RFQ `0x1901abcd` is not a verified settlement. These are explicitly synthetic, not wrong for contract tests, but cannot certify effects/equivalence. F4. |
| Q10 | `test_phase5_retrieval_and_model_are_called_without_reimplementation` | Actual Phase 5 reuse and sensible counts | Expected outputs computed using the same retrieval/model classes are integration oracles, not independent statistical validation. Synthetic sample count is not real 30-sample sufficiency. |
| Q11 | `test_captured_real_replay_has_no_synthetic_fallback_or_production_mutation` | Captured artifact reruns safely when present | Skips when ignored local artifact absent. It ran here; CI without that file does not prove real replay regression. |
| Q12 | `test_final_risk_after_agents_cannot_be_bypassed` | Injected final Risk FAIL suppresses prior agent BUY | Third-call patch is coupled to implementation order; it does not test real account changes or authoritative recapture. |
| Q13 | fake executable subprocess tests / exact official argv tests | Genuine process timeout/output/env/argument boundaries locally | Synthetic local executable is not official installed CLI compatibility or authenticated permission. B-synthetic, not A. |
| Q14 | 10/25/50/100 benchmark universes | Deterministic local scalability and top-K reduction | Repeated synthetic representations, not 100 distinct verified real stock datasets, runtime throughput or real LLM latency. |

The suite also contains meaningful adversarial tests: exact approval calldata, tiny gas reserve failures, canonical uint256 units, fingerprint mutation, actual SQLite CAS/restart/corruption, malformed schemas, point-in-time future data exclusion, endpoint denial before HTTP and process injection denial. The audit does not dismiss these because they use fixtures. No existing test was weakened or removed.

### Mutation experiment reproducibility

The isolated plugin imported `app.services.agentic_wallet`, compiled a source-string copy with **one conjunction removed**, and replaced only that module's in-memory definitions before collection. It never wrote the application file. Commands:

```sh
PYTHONPATH=/private/tmp/parity-adversarial-audit:backend .venv/bin/python -m pytest -q -p mutation_plugin backend/tests/unit/test_agentic_wallet.py backend/tests/integration/test_wallet_contracts.py
PYTHONPATH=/private/tmp/parity-adversarial-audit:backend .venv/bin/python -m pytest -q -p mutation_plugin
```

The unmodified run gave 962 PASS; the mutant run also gave 962 PASS. Baseline adversarial preflight rejected yesterday's developer quota date; mutant preflight passed. This is a demonstrated coverage omission, **not an application change or discovery that the intact current check is absent**. Reproducible source is embedded in the evidence JSON; ordinary tests run without this plugin retain original behavior.

## External-integration capability matrix

| Major capability | A: actual observed | B: fixtures | C: local implementation | D: still unavailable/unverified |
|---|---|---|---|---|
| Binance asset/issuer/representation discovery | Prior Oct 6 HTTP200/business0 reads, `PHASE_2_BINANCE_READS.json` | B-captured catalog/market fixtures with provenance README/manifest | Discovery/quarantine/current candidate mapping | Fresh complete cross-stock coverage/entitlements not renewed here |
| Token prices/candles/trades | Prior actual read evidence | B-captured, plus synthetic temporal edge cases | Normalization, as-of validation, filtering | Historically known token/share ratios and authoritative relevant-market liquidity |
| Independent equity/calendar/news | Prior historical/calendar/news HTTP200; Massive current Snapshot/NBBO403 | B-captured successful data; synthetic quote tests | Source identity/freshness/publication checks | Entitled fresh Massive equity; Twelve Data production integration/alignment remains separate |
| Phase 5 histories/replay | Captured real replay: 7336 unique primary raw bars, 2143 equity bars, 48 posthoc outcomes | Synthetic model/retrieval histories separate | Point-in-time retrieval/model/replay artifacts | 0 qualifying baseline / 0 opening-model / 0 analogues; historical as-of ratio/calendar/features missing |
| Six-agent interpretation | None for external LLM | B-synthetic echo/error provider | Six roles, strict schemas/memory/budgets | Functional configured LLM interpretation/transport, external entitlement |
| Opportunity universe/rank/risk | Underlying real discovery A; no actual eligible real BUY | B-captured discovery; B-synthetic multi-stock/cost/risk tables | Full deterministic scan/API/store/no-op | Real preview/research assembly; eligible Trust/history |
| Quote/SWAP/RFQ/approval build | No authenticated Phase 8 execution-contract probe | **B-synthetic** `execution_fixtures.py` / MockTransport Wire | Typed build branches, approval decode, fingerprints | Actual quote/build schemas for entitled RWA pair and exact live equivalence |
| Transaction simulation | No actual Phase 8 runtime simulation probe | B-synthetic SUCCESS/FAILED arrays | Exact payload/fingerprint/receipt/status checks | Verified economic effects, gas-sensitive equivalence, RFQ final settlement |
| RFQ/SWAP terminal status | No actual order/transaction tracked in this audit | B-synthetic status/transfer payloads | Tracker/state/store integration | Real settlement/finality; F2/F3 integrity gaps |
| Agentic Wallet | **A-negative:** fresh local BAW_UNAVAILABLE | **B-synthetic** WalletWire/fake executable | Read CLI grammar/normalization/preflight/reconciliation wrapper | Installed authenticated CLI, status/address/balances/settings/quote/history and exact App preview |
| Risk/Routing/Funding arithmetic | No runtime wallet attestation | B-synthetic fixture policy/context | Shared deterministic economics/constraints/precision | Authoritative current real wallet/cost/liquidity inputs |
| DEMO paper lifecycle/UI | Actual local HTTP/browser operation, synthetic market inputs | B-synthetic fixtures clearly labeled | Real local position/exit/P&L/scorecard services | Not evidence of real settlement, profit or market calibration |
| LIVE execution | None | No fixture can unlock gates | Explicit refusal/absence of live transport | SWAP, RFQ and wallet LIVE gates blocked |

Public documentation was checked, but does not establish A capability. Some captured fixtures convert Decimal money lexemes to strings and remove authenticated pagination URLs; they are documented transformations, not byte-identical raw HTTP archives. Phase 8/9 constructed protocol fixtures must not be called “sanitized real provider captures.”

## Hollow/stub search

The inventory scanned 370 repository nonignored text files and classified **22,427 literal-substring matches**: 22,425 SAFE/INTENTIONAL, 2 POTENTIAL PRODUCTION GAP (simulation PASS promotion, F4). Counts: synthetic 9,818; demo 6,514; pass 4,358; unavailable 1,341; mock 183; disabled 137; stub 41; fake 30; placeholder 5. TODO/FIXME/NotImplemented counts were zero in this scope. Substring matching intentionally includes identifiers and ordinary words; a mention is not an implementation defect.

The machine inventory contains every matching position, including test/doc/fixture occurrences, and a per-row classification/reason legend. Excluded: `.git`, dependencies, builds, credential files, ignored private/runtime files and binary artifacts. Runtime data preservation was checked separately. No credential contents were copied into the search report.

Bare executable `pass` statements were inspected individually:

| Location | Classification | Reason |
|---|---|---|
| `backend/app/models/base.py:6` | SAFE/INTENTIONAL | SQLAlchemy DeclarativeBase subclass. |
| `backend/app/models/demo_paper.py:191` | SAFE/INTENTIONAL | Marker schema subclass inherits implementation. |
| `backend/app/clients/baw_cli.py:247` | SAFE/INTENTIONAL | ProcessLookupError cleanup; already exited process. |
| `backend/app/services/agentic_wallet.py:401` | SAFE/INTENTIONAL | Unit conversion error leaves balance checks false, then blocks. |
| `scripts/verify-trust-remediation.py:175` | SAFE/INTENTIONAL | Optional diagnostic provider failure handled; no trade fallback. |

No empty core risk/router/quote/wallet implementation was found. The abstract gateway signature is intentional and has a concrete non-executing implementation. Most unavailable/disabled/DEMO occurrences enforce the authorized scope. **F1/F2/F3/F5 do not need a TODO or stub keyword to be real gaps.** Keyword totals are not a confidence score; functional inspection and probes found them.

## Regression and preservation

- Full unmodified backend suite: **962 PASS**, 23.96s. One existing Starlette/httpx TestClient deprecation warning.
- Frontend: **173 PASS / 9 files**. TypeScript `tsc --noEmit` and Vite build via `npm run build`: PASS.
- Ruff lint: PASS; Ruff formatting: **165 files already formatted**. Established security check: PASS. `pip check`: no broken requirements; benign cache-permission warning.
- Fresh desktop/mobile browser: **6 scenarios PASS, 39 successful actual loopback API requests**, no runtime errors or horizontal overflow. NORMAL/noise stand down; INFORMATION completes Trust → Opportunity → Risk → Routing → Quote → Prepare → Simulate → Paper Fill → Position Monitor → Exit → P&L → Scorecard. No production Trust call from DEMO, no real provider or live execution call. Ordinary Overview remains INSUFFICIENT_EVIDENCE, ordinary-runtime sandbox disabled, production Opportunity navigation locked.
- Browser runs used three disposable memory-only backends and a built-frontend server, `_env_file=None`, test environment and DEMO data. Loopback sandbox binding required approved local-process access; the final successful run used no account APIs. Only the four recorded audit servers were terminated after command-line identity checks. User services were untouched.
- Historical comparison against pre-Phase-6 `85e7a1ba7847fc2633329e3dd3abf2649a17fe57` shows no changes to Trust service/classifier/evidence/history, research replay, routing or existing DEMO lifecycle/frontend source. Shared Risk gained separate methods; retained suites pass. This is regression evidence, not proof of economic calibration.
- The initial 371-file source/test/docs/data/config SHA baseline is checked at completion. Original master, historical fixtures/evidence/data and original gate documents remain byte-identical during the audit. Fresh audit artifacts are separate files. No production observation or historical sample was added.

## Five highest-risk assumptions

1. **“A documented FILLED/FINISHED status means the same exact transaction was settled.”** False under F2: corroborated wallet hash can differ from confirmed journal hash.
2. **“Every CONFIRMED record has passed exact settlement reconciliation.”** False under F3; a trusted host state transition can confirm with no filled quantity/provider proof. Order/quote chronology policy also needs explicit investigation.
3. **“SUCCESS simulation plus a fingerprint proves the authorized economic effects.”** False under F4; bytes are bound, adverse effects not validated. Global live-equivalence blocking currently contains it.
4. **“Five structured calls and six agent classes prove the master LLM interpretation stage.”** False under F1; exact echoes pass, legitimate alternative interpretation fails, application transport is absent. Phase 7 inherits the gap.
5. **“Passing all tests means individual wallet hard controls are tested.”** False under Q1: removal of developer quota-date validation still passes all 962 tests. F5 also shows real preview inputs must be integrated before fixture success becomes operational capability.

## Unchanged production gates and stop

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

These are the existing runtime/documented gates, not rewritten by the audit. The corrected PARTIAL labels above are this independent assessment; earlier dated PASS reports are preserved.

Before Phase 10, prioritize exact terminal identity/confirmation invariants and adversarial regression coverage (F2/F3/Q1). Separately resolve the required LLM interpretation boundary/transport and real preview integration (F1/F5), and retain F4 as a mandatory safety/equivalence blocker. Define legitimate imported-order chronology instead of guessing. Require a new targeted audit after authorized fixes. **No automatic fixes, live enablement or Phase 10 advancement. STOP.**
