# Master Phase 9 — Agentic Wallet

Date: October 8, 2026 (Asia/Kolkata).

**PHASE_9_IMPLEMENTATION=PASS; actual wallet runtime UNAVAILABLE; all production gates unchanged.**

The sole authority `docs/MASTER_SPEC.md` was read completely, lines 1–5321, before coding.
Its SHA256 remains `f69a9bd01a622c001c3ec6cb654e00562f6b3d03a8310f9e5ccf68efe4b49c84`.
Starting checkpoint was committed Phase 8 `9202eb8`; the working tree was clean.
No Phase 10 position-management work or automatic commit was performed.

## Continuation audit and completion

The continuation resumed the existing 22 uncommitted Phase 9 files at the same Phase 8
checkpoint. It read the entire sole master specification again before further changes,
inspected the current diff, source, tests, reports and Phase 8 gateway, and reused the
implementation. No source-code acceptance gap was found. No source, fixture, dependency,
frontend or application behavior was changed in this continuation.

Already implemented: the closed read-only CLI client, immutable wallet contracts, adapter,
wallet hard-control checks, Phase 8 gateway integration, read-only reconciliation, diagnostic,
116 tests and capability documentation. Remaining completion work was the explicit checklist,
fresh regression/browser verification and finalizing two pending security/whitespace evidence
fields. Those checks now PASS. Earlier diagnostic and verification results are retained;
the verification JSON records the fresh continuation and its previous result summary.

| # | Continuation checklist | Audit status | Evidence / actual-access limitation |
|---|---|---|---|
| 1 | Official capability reconnaissance | COMPLETE | Official manifest and references inspected; current manifest/preflight rechecked |
| 2 | Exact integration mechanism | COMPLETE | Official Skills Hub `baw` CLI documented; local authenticated runtime UNVERIFIED |
| 3 | Agentic Wallet adapter | COMPLETE | Strict normalized read boundary and explicit unavailable results tested |
| 4 | Wallet status | UNVERIFIED | Read contract/fixture tests complete; actual runtime UNAVAILABLE |
| 5 | Wallet address | UNVERIFIED | Exact BSC identity contract tested; no real wallet address observed |
| 6 | Supported chains | UNVERIFIED | Runtime-list contract and unsupported-chain tests complete; real chain support unknown |
| 7 | Balances | UNVERIFIED | Human-unit and exact base-unit checks tested; actual holdings unavailable |
| 8 | Security settings / limits | UNVERIFIED | Settings and independent quotas tested; actual account controls unavailable |
| 9 | Token scope | PARTIAL | `tradeAllTokens` read contract tested; restricted allowlist not exposed, so it blocks |
| 10 | Confirmation requirements | PARTIAL | Policy and fingerprint-bound host checks tested; transaction-specific App confirmation unknown |
| 11 | Transaction history | UNVERIFIED | Bounded history/binding contract tested; no actual history read succeeded |
| 12 | Supported order/quote capability | PARTIAL | Documented market-order status/indicative quote reads tested; actual access and exact binding unknown; writes disabled |
| 13 | DRY_RUN integration | COMPLETE | Fixture-verified typed checks; all results explicitly non-executable |
| 14 | ExecutionGateway integration | COMPLETE | Existing Phase 8 hard controls reused; no parallel execution transport |
| 15 | Reconciliation | COMPLETE | Exact Phase 8 settlement evidence required; conflicts/timeouts stay UNKNOWN |
| 16 | Idempotency | COMPLETE | Existing IDs, decision ownership and CAS journal reused; no resubmission |
| 17 | Mode isolation | COMPLETE | DEMO fixtures rejected in LIVE_READ_ONLY before any call |
| 18 | Secret handling | COMPLETE | Restricted child environment; configured-secret and bundle scans PASS |
| 19 | Error sanitization | COMPLETE | Raw CLI/error bodies withheld; bounded generic reason codes tested |
| 20 | Capability matrix/report | COMPLETE | Documentation, fixtures and actual access distinguished for each capability |
| 21 | Tests | COMPLETE | Fresh Phase 9 suite: 116 passed, 0 failed |
| 22 | Regression tests | COMPLETE | Fresh full backend: 962 passed; frontend: 173 passed; six browser scenarios PASS |
| 23 | Documentation/evidence | COMPLETE | Report, capability evidence and verification evidence finalized |

UNVERIFIED/PARTIAL above describe external account capabilities; they do not imply synthetic
data is a replacement. The authorized unavailable-state adapter and non-executable DRY_RUN
architecture satisfy the Phase 9 implementation gate without certifying live readiness.

Fresh full backend duration was 22.58s; targeted Phase 9 duration was 3.88s. Build/typecheck,
Ruff lint/format (165 files), dependency compatibility, security (383 artifacts), expanded
credential scans and diff checks passed. The new browser run again made 39 loopback API
requests, with no production Trust calls from DEMO and no live execution calls. Only its four
owned disposable servers were stopped; user services were untouched. No real wallet CLI
process or authenticated account read occurred. This continuation changed only this report
and the three Phase 9 evidence files, including refreshed browser evidence.

## Reconnaissance and actual capabilities

Current official Binance Skills Hub defines the wallet CLI mechanism, required version and
read schemas. The official wallet skill is 1.12.0, required CLI 1.10.0. Local PATH and npm
inventory found no `baw`/matching package. The read-only runtime diagnostic actually returned
`BAW_UNAVAILABLE`. No installed official CLI command, authenticated wallet state, chain support,
account balance, token permission, quote, order or transaction was successfully observed.

[Capability matrix](AGENTIC_WALLET_CAPABILITIES.md) distinguishes DOC verification, synthetic
contract verification and actual access. [Capability evidence](evidence/PHASE_9_CAPABILITIES.json)
records source-document hashes, bounded local inventory, actual sanitized diagnostic and fixture
checks. Documentation and fixtures never become real wallet capability PASS.

No installation or App pairing was attempted. The requested unavailable-state path is complete;
public DEMO/DRY_RUN operation needs no wallet credentials. Ordinary Web3 Wallet REST APIs are
not used as Agentic Wallet APIs. No invented remote interface or new token discovery source exists.

## Architecture and reuse

```text
Controlled local worker / existing CLI-owned session
  → BawReadOnlyClient (closed read grammar, exact-version check)
  → AgenticWalletAdapter (strict normalized contracts)
  → WalletSafetyChecks (wallet controls only)
  → AgenticWalletCliGateway
      → existing DryRunExecutionGateway
      → existing Risk / Funding / Quote / Fingerprint / Simulation / Approval checks
      → STOP, no execution transport

Existing external execution identifiers
  → WalletReconciler (read-only corroboration)
  → existing Phase 8 ExecutionStatusTracker / ExecutionStore / StateMachine
  → exact terminal evidence or UNKNOWN; never a new order
```

Trust, research, routing, six agents, Opportunity/Risk arithmetic, the original DEMO paper
pipeline and frontend are unchanged. Phase 8 persistence and ExecutionAttempt serialization
remain unchanged, preserving old journal fingerprints. Wallet snapshots are transient; no raw
CLI output or wallet credentials enter persistence. Results retain IDs, mode, hashes and safe
reason codes. There is no new wallet database, public API, scheduler, signing or executor.

FastAPI injects a client-less adapter into the existing safety service. It does not discover,
spawn or authenticate a CLI in the public process. A controlled host can explicitly inject a
read client; the standalone `scripts/inspect-wallet.py --read-only` is the opt-in diagnostic.
DEMO accepts only explicit fixture clients. LIVE_READ_ONLY rejects fixtures before any call.

## Read contracts and runtime safety

Strict immutable wallet contracts normalize connection, supported chains, BSC address, balances,
security settings, quotas, lock/pending state, orders, history and indicative quotes. They retain
source, mode, capability level, UTC request/receipt times, limitations and sanitized errors.

The client builds commands as argument arrays without a shell; even its private subprocess
boundary validates the closed grammar. Version checks precede wallet reads. No auth, transfer,
swap, signing, contract preview, cancellation, settings update or approval mutation is permitted.
Child stdin is closed; stderr is discarded; stdout is bounded to 1 MiB and execution to 10s.
Only an explicit environment subset reaches the CLI; project/API secrets and NODE_OPTIONS do not.
Timeouts terminate the owned process group. There is no retry-to-trade or installation fallback.

Duplicate JSON fields, invalid envelopes, excessive output, malformed critical data and unknown
statuses fail safely. Untrusted display metadata is discarded; it cannot supply limits, token
permission or safety instructions. Unknown statuses normalize to UNKNOWN. No raw error text,
secret, authentication token, private key or signature is logged or exposed publicly.

## Wallet hard controls / DRY_RUN

Wallet preflight verifies available connected state, source/mode, a bounded current read window,
BSC support, exact quote/funding wallet identity, lock and pending-state resolution, session and
inactivity expiry, spending quotas, Developer Mode status/quota/expiry, token scope, confirmation
policy and exact funding/native balance consistency.

Funding quantities are human token units. The adapter converts them with verified existing token
decimals using Decimal precision 256, exact integer boundaries and uint256 bounds. It never treats
a stablecoin quantity as USD or rounds available balance upward. Spending checks use actual
rounded quote funding units × the independently supplied funding price, plus costs/conversion;
theoretical USD notional alone would miss the smallest-unit round-up at a limit boundary.

Snapshot identity/connection are rechecked after all reads, including pending records. Omitted
balances, incomplete pending pages, stale reads or unknown policy block preflight. A restricted
token scope without its actual allowlist blocks; foreign `allowedTokens` metadata cannot override
settings. `NeedConfirmation` remains unresolved until actual App/transaction evidence exists.
PROPOSE_ONLY still needs existing fingerprint-bound explicit host confirmation. AUTONOMOUS can
be tested only as non-executable DRY_RUN and cannot bypass either layer; application startup
continues refusing autonomous/live configuration.

The gateway reuses Phase 8 risk/funding/gas/quote/fingerprint/simulation/approval checks, then
always returns live gate and wallet-execution blockers. Wallet-only preflight PASS certifies
read checks on synthetic inputs, never execution readiness. Unknown reset timezone, non-atomic
reads, actual preview/confirmation and full execution equivalence remain explicit limitations.
Existing CLI quote information is indicative and has no external Phase 8 route-binding proof.

## Reconciliation / idempotency

Wallet reconciliation loads the existing mode-scoped execution/version from Phase 8 storage.
It rejects stale callers and needs an existing externally tracked order/hash. It retains decision,
execution and UUID request IDs; it creates no attempt, order, transaction or position.

Pending, missing, timeout, malformed, unbound, conflicting or unknown wallet state stays UNKNOWN.
History and wallet order results corroborate identities/amounts; wallet FINISHED alone never
becomes ExecutionAttempt CONFIRMED. The existing Phase 8 tracker supplies the exact documented
terminal settlement evidence. Its new optional corroboration guard leaves conflicting terminal
results UNKNOWN before any terminal journal update. All old callers retain their existing behavior.

Restart reads existing pending/unknown attempts with the same IDs and bounded recovery batches.
Pending records continue blocking new Phase 8 preparation. No poll or timeout creates another
order; read reconciliation is not persistent position management or a Phase 10 exit engine.

## Verification

[Exact commands/results](evidence/PHASE_9_VERIFICATION.json) record the full backend and Phase 9
counts, frontend checks, build/typecheck, Ruff/format, established credential/security audit,
dependency compatibility and diff checks. No existing tests were removed or weakened.

- Full backend: **962 passed**, including all **846 retained** tests; one existing Starlette/httpx deprecation warning.
- Phase 9 targeted suite: **116 passed**.
- Frontend: **173 passed /9 test files**; TypeScript/Vite build PASS.
- Ruff lint/format: PASS, **165 Python files**; security/credential scans, dependency compatibility and diff whitespace checks PASS.
- Browser: **six desktop/mobile scenarios PASS,39 loopback API requests, zero real provider/execution calls**.

Phase 9 tests cover official command syntax, unavailable/version-mismatched runtime, real bounded
subprocess mechanics with fake executables, malformed/schema/error responses, injection, secret
isolation, BSC/identity/balances/units, limits/scope/confirmation, expiry/pending state, mutation
denial, gateway control reuse, reconciliation/terminal conflicts/restart/idempotency and mode isolation.
Protocol fixtures are explicitly synthetic and are not real account or live gate evidence.

[Browser evidence](evidence/PHASE_9_BROWSER.json) verifies six desktop/mobile NORMAL/NOISE/
INFORMATION scenarios, full synthetic paper entry→monitor→exit→P&L→scorecard, ordinary Overview
INSUFFICIENT_EVIDENCE and locked production Opportunity navigation. Frontend source and bundle
names are unchanged. Temporary test backends use memory-only data; only owned test servers are
stopped. All 86 protected specification/historical/data/evidence artifacts remain byte-identical.

## Gates and remaining blockers

```text
PHASE_9_IMPLEMENTATION=PASS
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

Implementation PASS verifies the read adapter, unavailable-state handling, strict contracts,
DRY_RUN architecture and fail-closed reconciliation without capital. It does not certify actual
runtime authentication, permissions, wallet availability, BSC/token support, signatures or execution.

External prerequisites: compatible official CLI/skill on a controlled worker, user-owned authenticated
session and actual read/schema/security/chain/token tests; verified quota reset/allowlist/transaction
confirmation and wallet session/worker trust; exact SWAP gas/nonce/ABI effects and wallet execution
equivalence; RFQ payload/vendor bindings and final-settlement safety; authoritative real wallet/funding
state and terminal/finality evidence. Existing independent-equity/alignment/liquidity/as-of ratio and
0/30 baseline, 0/30 opening-model, 0/3 analogue Trust blockers remain unchanged.

No real wallet read command was successfully executed because `baw` is absent. No real quote, order,
signature, broadcast, transaction, funds movement, security-setting change or production history write
occurred. No Twelve Data alignment/backfill was run. **Phase 10 was NOT started. No commit was made.**
Stop after this Phase 9 report; later engineering work requires separate authorization.

## Files changed

Existing: `backend/app/clients/execution_gateway.py`, `backend/app/main.py`,
`backend/app/services/execution.py`, `backend/app/services/execution_status.py`, `README.md`,
`docs/API_MATRIX.md`, `docs/ARCHITECTURE.md`, `docs/EXECUTION_GATES.md`, `docs/PHASE_MAP.md`.

New: `backend/app/clients/baw_cli.py`, `backend/app/models/wallet.py`,
`backend/app/services/agentic_wallet.py`, `backend/app/services/wallet_reconciliation.py`,
`backend/tests/fixtures/wallet_fixtures.py`, `backend/tests/unit/test_agentic_wallet.py`,
`backend/tests/integration/test_wallet_contracts.py`, `scripts/inspect-wallet.py`,
`docs/AGENTIC_WALLET_CAPABILITIES.md`, `docs/PHASE_9_REPORT.md`,
`docs/evidence/PHASE_9_CAPABILITIES.json`, `docs/evidence/PHASE_9_VERIFICATION.json`,
`docs/evidence/PHASE_9_BROWSER.json`.
