# Execution audit remediation — 11 October 2026

Implemented local regression fixes; **not ready for LIVE execution**. All seven gate states
and every existing Trust/source-admission threshold remain unchanged. This is an execution
remediation increment, not phase advancement. Authority: `docs/MASTER_SPEC.md`, read in full,
and the user's Complete Audit Remediation and Implementation request.

## Repository and preservation

- Branch: `main`; starting working tree clean, synchronized with `origin/main`.
- Starting and ending HEAD: `9b6368cda71ca3ee79ce8d5755255d80b29ea38d`.
- Audited teammate tip: `223c204a77de2f5242767681fa60fcf8457abda0` (`feat: weekend pool swaps and verified RFQ execution`).
- Tip parent: `2832a070761e9872a2777bfdd0611b243152c3a5`; merge base: `266c2cb922a093e790f3aef2e3b406f06dd7d60c`.
- Target was not integrated. Selected execution components were imported using Git object
  reads and remediated in the current tree; no whole-branch integration or Git mutation.
- No merge, reset, clean, checkout, rebase, commit or push. Ending tree contains the local
  files enumerated below and in `evidence/EXECUTION_REMEDIATION.json`.
- Alpaca/Finnhub/Massive/Binance/Hyperliquid data logic, Trust/Risk/Opportunity engines,
  source admission, original frontend components/styles and historical evidence preserved.
  The teammate's perpetual-index equity fallback, Trust-disable option, closed-market
  execution exemption and browser live controls were not imported.
- Existing tests were not removed or weakened. Default API inventory remains identical;
  protected worker routes mount only with an explicitly configured backend worker token.

## Finding-to-fix matrix

FIXED denotes a reproduced local defect resolved within the stated scope. It is never a
claim that a live capability gate passed. PARTIALLY FIXED means local regression defects
are repaired but the named integration/protocol/runtime evidence remains outstanding.
All tests below were executed; all passed in the final complete suite.

| # / status | Defect and implementation | Files | Regression evidence |
|---|---|---|---|
| 1 **FIXED** | Environment/config flags could authorize execution. Server-owned gate policy is checked at gateway, worker, signer, RPC send, RFQ submission/raw request signing and authenticated API. No flag/HTTP gate override; route and wallet gates independent. Startup has no write client/signer. | `services/execution_gates.py`, `clients/execution_gateway.py`, `clients/bsc_rpc.py`, `clients/binance_trading.py`, `services/live_execution.py`, `services/live_signer.py`, `services/agentic_wallet_signer.py`, `services/live_wiring.py`, `api/live.py` | `test_all_production_gates_block_even_direct_internal_calls`, `test_raw_rpc_and_signer_cannot_bypass_gate`, `test_wallet_gate_and_route_gates_remain_independent`, API blocked transport/execute tests |
| 2 **FIXED** within constrained verifier | Fusion getters could change takingAmount. Exact canonical types/domain, order digest and low-160-bit extension hash binding. Only absent extension or a hash-bound 32-byte empty offset table is supported; getters, suffixes, predicates, permits, interactions, custom bytes and unreviewed traits reject. No auction floor inferred. | `services/rfq_orders.py`, `services/protocol_definitions.py` | `unit/test_rfq_orders.py`: empty supported extension, wrong hash, malformed offsets, getter-dependent amount, hooks/unsupported traits, wrong schema/domain/hash |
| 3 **PARTIALLY FIXED** | Empty/mismatched simulation, zero output, overspend and receipt-only recovery rejected. Reuse unchanged builder comparison and exact simulation fingerprint including gas. Enforce bounded wallet token effects, minimum output, exact allowance, fresh quote/risk/market status and native gas/value reserve. Settlement checks signed hash, transaction fields, raw transfers and pre-balance corroboration, with identical recovery checks. | `services/live_execution.py`, `services/live_settlement.py`, `services/live_signer.py`, `clients/bsc_rpc.py`; existing builder/simulation reused | `test_simulation_original_failure_cases_rejected`, `test_swap_original_false_confirmations_rejected`, `test_receipt_only_recovery_fails_then_complete_evidence_recovers`, malformed RPC/ABI tests. **Still missing:** actual provider gas-sensitive execution/simulation equivalence; `live_equivalence_verified` remains false. |
| 4 **FIXED** | Executor-local lock allowed duplicates. SQLite BEGIN IMMEDIATE + unique action, active-wallet and submission identities; no INSERT OR REPLACE. Stable intent conflicts reject; wallet stream remains locked across crashes. Unknown actions cannot transition back to preparation. | `repositories/live_fills.py`, `services/live_execution.py` | `test_two_executor_instances_claim_before_any_submission` (separate executors/connections, one mock submission), `test_atomic_claim_across_connections_and_wallet_nonce_stream`, crash/transition tests |
| 5 **FIXED** for ambiguity handling | Lost response was incorrectly rejected. Signed hash/nonce/fingerprint durable before RPC; RFQ request identity durable before POST. Any error after submission boundary remains SUBMISSION_UNKNOWN. Read-only recovery observes the original identity and never re-signs/resends. RFQ HTTP writes get one attempt and no read-cache retention. | `repositories/live_fills.py`, `services/live_signer.py`, `services/live_execution.py`, `clients/common.py`, `clients/binance_web3.py`, `clients/binance_trading.py` | `test_accepted_broadcast_lost_response_persists_hash_nonce_unknown`, `test_crash_after_durable_identity_before_presentation_update_recovers`, `test_rfq_transport_one_attempt_no_signature_cache_or_echo`. Replacement transactions/unknown platform IDs remain manual unresolved cases, not definite failures. |
| 6 **PARTIALLY FIXED** | Unrelated RFQ receipt/provider amounts accepted. Raw vendor-specific Trade/OrderFilled/Fill decoding plus exact UID/hash/witness/nonce, settlement contract, wallet, tokens and bounded/full-fill amounts; pre-balances mandatory, no provider amount fallback. FAILED/EXPIRED/CANCELLED never automatically imply NOT_FILLED. Canonical-block checks and explicit terminal reorganization recheck. | `services/live_settlement.py`, `services/live_execution.py`, `repositories/live_fills.py` | All three vendors' wrong-order/contract/wallet/token/amount/receipt-only cases, missing pre-balances, malformed ABI, nonfill states and `test_canonical_settlement_reorg_relocks_wallet`. **Still missing:** genuine vendor payloads/receipts, authoritative deployment/hash and pre-execution settlement safety evidence. |
| 7 **FIXED** | Signature exposure and unauthorized/unbound execution. PublicFill positive allowlist even for legacy raw rows; signing artifacts memory-only. Loopback/Host/Origin/no-forwarding controls plus backend worker token. HTTP accepts exact expiring single-use consent for server-owned prepared objects; fingerprint includes route, risk, simulation, minimum and order. Signer digest/owner and recovered EOA identity checked. | `models/live.py`, `api/live.py`, `repositories/live_fills.py`, `services/live_execution.py`, `config.py`, `main.py` | Legacy synthetic signature/key sentinel API tests; expired/changed/consumed confirmation; absent/mismatched worker authorization, null/cross-origin/forwarded request, default route inventory; signature echo/cache regression |
| 8 **PARTIALLY FIXED** | Incomplete types/domain/deployment and Permit2/witness binding. Central exact definitions; PCS BNB deployment addresses corrected from official repository; outer nonce/deadline/amount/spender bind to witness. CoW UID/domain/version and Inch traits/extensions bind to the signed digest. | `services/protocol_definitions.py`, `services/rfq_orders.py`, `services/eip712_validation.py` | Wrong chain/address/version/types/nonce/deadline/digest and independent local ABI CoW hash/UID vector tests. **Still missing:** deployed bytecode and actual contract-computed hash calls; local definitions do not prove deployment compatibility. PCS allowlist remains empty by default. |
| 9 **PARTIALLY FIXED** | Missing preview accepted; HTTP signature trusted. Required documented preview simulationCode/precheck/risk/authority/confirmation fields validated, separate recovery byte assembled. Contract-wallet signature requires exact chain/wallet/digest ERC-1271 eth_call magic result. Agentic and Altana sending refuse unverified gas/nonce/preview equivalence. | `services/agentic_wallet_signer.py`, `services/live_signer.py` | `unit/test_wallet_signer_remediation.py`: missing/ambiguous preview, errors/risks/authority changes, recovery byte, wrong digest/wallet/chain/magic, HTTP-only signature. **Still missing:** installed `baw` runtime and real preview/confirmation/request binding; Altana user-operation and RFQ submission compatibility. |
| 10 **FIXED** within current worker scope | Reconciliation-required legs could retire and stale risk approval reused. All unresolved states block both internal PortfolioService and API retirement/replanning/preparation. Each leg reruns unchanged RiskEngine, checks exact risk digest and 120-second evidence/market lifetime plus quote expiry; allowance/balance/chain reread before submission. No 600-second stale approval reuse. | `services/portfolio.py`, `services/live_execution.py`, `repositories/live_fills.py`, `api/live.py`, `models/portfolio.py` | `test_no_trust_disable_and_unresolved_guard_cannot_be_bypassed_internally`, `test_execution_risk_revalidates_expired_evidence_and_production_admission`, consent/quote expiry, failed reconciliation and invalid transition cases |

## Capture infrastructure

Unsigned RFQ build capture occurs before local builder validation so rejection does not
silently lose the evidence needed to understand real formats. Captures remain explicitly
unverified. Store schema version 2, UTC capture time, provider identity, chain, protocol,
order identifier, verdict/gap reason, canonical JSON size and SHA-256. Only unsigned
protocol fields survive; configured secrets and signing artifacts are removed recursively.

Each payload is capped at 256 KiB, at most 128 rows and 8 MiB of payload plus stored text
metadata. Oversized evidence becomes a valid omission/gap object with a digest, never
truncated JSON. Metadata is bounded too. Public diagnostics return metadata/integrity;
host-internal access returns only intact unsigned payloads. The digest authenticates the
stored sanitized canonical representation, **not** the original wire bytes or deployment.
`unit/test_live_evidence.py` verifies redaction, malformed data/domain, size/count/total
retention, parseability and corruption detection. No genuine payload was fabricated.

## Protocol-specific evidence and limits

- **PancakeSwap X:** exact PermitWitnessTransferFrom/flat ExclusiveDutchOrder schema,
  Permit2 domain, constant-input constraint, recipient floor, deadline/nonce/amount binding,
  local EIP-712 and witness hashes; Fill(witness hash, filler, swapper, nonce) decoding.
  Official BNB addresses: Permit2 `0x31c2f6fcff4f8759b3bd5bf0e1084a055615c768`, reactor
  `0xdb9d365b50e62fce747a90515d2bd1254a16ebb9`. Default PCS settlement allowlist is empty.
  These addresses are documented identities, not a verified current deployment. See
  [official deployments](https://github.com/pancakeswap/pancake-x-contracts#deployment-addresses),
  [witness library](https://github.com/pancakeswap/pancake-x-contracts/blob/main/src/lib/ExclusiveDutchOrderLib.sol),
  [permit construction](https://github.com/pancakeswap/pancake-x-contracts/blob/main/src/lib/Permit2Lib.sol)
  and [Fill event](https://github.com/pancakeswap/pancake-x-contracts/blob/main/src/base/ReactorEvents.sol).
- **CoW:** exact GPv2 Order, Gnosis Protocol/v2 domain, local digest and 56-byte UID
  construction; kind=sell, ERC20, no partial fills. Trade UID/owner/tokens/amounts/fee
  must match raw transfers. GPv2 Trade sell amount already includes fee; do not double
  count it. Independent local ABI reconstruction cross-checks the Python hash; this was
  not an on-chain contract call. See [Order library](https://github.com/cowprotocol/contracts/blob/main/src/contracts/libraries/GPv2Order.sol)
  and [Settlement](https://github.com/cowprotocol/contracts/blob/main/src/contracts/GPv2Settlement.sol).
- **1inch Fusion:** exact LOP v4 Order / Aggregation Router version 6 domain and local
  digest, static price/full-fill constraints, low-160 extension hash binding, raw
  OrderFilled hash/remaining matching. Real auction amount getters/interactions remain
  unsupported and reject. No guaranteed floor is claimed for them. See
  [OrderLib](https://github.com/1inch/limit-order-protocol/blob/master/contracts/OrderLib.sol),
  [ExtensionLib](https://github.com/1inch/limit-order-protocol/blob/master/contracts/libraries/ExtensionLib.sol),
  [MakerTraits](https://github.com/1inch/limit-order-protocol/blob/master/contracts/libraries/MakerTraitsLib.sol)
  and [events](https://github.com/1inch/limit-order-protocol/blob/master/contracts/interfaces/IOrderMixin.sol).

All signature and settlement vectors used here are synthetic and offline. No deployed
protocol compatibility, RFQ entitlement or real settlement is inferred. Current provider
simulation covers from/to/value/data only and cannot satisfy the unchanged live gas-sensitive
or RFQ final-settlement equivalence requirements.

## Wallet/runtime evidence

`baw` and `forge` were not present on PATH. No wallet CLI execution/sign-message or sidecar
call was performed. Preview validation follows the documented `simulationCode` fields,
not an invented status alias, and rejects missing inspection/confirmation prerequisites.
The [official external-sign reference](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/external-sign.md)
does not establish this machine's installed runtime or exact gas/nonce behavior. BAW and
Altana execution remain explicitly unsupported. ERC-1271 tests use synthetic RPC responses;
actual contract wallet, digest, chain and runtime must still be independently verified.

## Verification and reproduction

Run from the repository root; tests load no developer credentials and use fixtures/temp
stores. Baseline before changes: **1562 backend passed**. Final: **1738 backend passed**
(including **176 new remediation tests**), **285 frontend passed**, no remaining failures.
Two pre-existing Pydantic warnings exercise deliberately malformed allowance fields.

```sh
.venv/bin/python -m pytest -q
npm test
npm run build
.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
PYTHONPATH=backend .venv/bin/python scripts/generate-ui-contracts.py --check
.venv/bin/python scripts/check-security.py
.venv/bin/python -m pip check
git diff --check
.venv/bin/python scripts/verify-frontend-phase15.py
```

Executed Ruff lint/format, TypeScript (`tsc --noEmit` within build), Vite build, seven
Pydantic-derived frontend contract comparisons, configured-secret/source/bundle/ignore
checks, installed dependency consistency and diff whitespace checks: **PASS**. No Python
static type checker is configured; no additional type-checking pass is claimed.

The browser runner uses credential-free disposable local fixture servers, temporary
profiles/databases, built React, desktop/mobile/tablet journeys and actual MCP stdio. It
refuses occupied ports and stops only its own processes. The sandbox initially denied
loopback binding; the established runner was then approved and executed outside that
restriction. No production/provider credentials were forwarded. Browser evidence location
is recorded in the companion JSON; all journeys, six demo cases and MCP checks passed.

Intermediate failures were diagnosed, not omitted: two new protocol-test vectors were
incorrect and corrected; a duplicate funding fixture was rejected earlier by the existing
model as intended; two default route-inventory regressions were fixed by conditional worker
route registration without changing existing tests; capture gap-reason precedence was
corrected. Final complete suites above include the resulting fixes.

`eth-account==0.13.7` matches the audited branch pin. Its installation into `.venv` was
explicitly approved after the initial automatic review applied stale read-only scope.
Resolved transitive dependencies are pinned in requirements.txt; pip check passes. No
runtime dependency remains missing for the executed offline tests.

Not executed: genuine RFQ quote/build captures, contract-computed hash/bytecode checks,
real RPC settlement, installed BAW/Altana execution, approval/broadcast/order submission,
or capital tests. They need genuine external evidence and were outside this offline task.

## Independent gates (unchanged)

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

DATA/DRY_RUN retain their prior admitted evidence scope. Regression success adds no
Trust calibration, authoritative liquidity, historical ratio or real 30/30/3 evidence.
Current RiskEngine still refuses production Trust approval. All live gates remain blocked
by their original acceptance criteria; code, fixtures, valid signatures and receipts alone
cannot pass them. Defaults are DRY_RUN/false/PROPOSE_ONLY/required simulation.

## Remaining blockers and next action

| Missing evidence/capability | Technical impact | Specific next action |
|---|---|---|
| Genuine unsigned Binance RFQ payloads for each vendor and supported chain | Local definitions may reject actual provider shapes; format and order identity are not empirically established | Read-only quote/build capture, safely redact to versioned fixtures, compare exact domain/types/order/extension/permit fields |
| Deployed bytecode, chain-specific domain and contract-computed hashes | Documented addresses and local hash agreement cannot establish current contract behavior | Read-only RPC code/domain/hash verification against reviewed contract versions and the captured payloads |
| Gas/nonce-sensitive SWAP and final RFQ settlement simulation/equivalence | Existing simulation coverage is insufficient under unchanged master rules | Obtain documented exact provider/runtime mechanism and non-capital equivalence evidence; do not flip literal coverage flags |
| Installed BAW runtime and Altana preview/user-operation/ERC-1271/RFQ submission compatibility | CLI docs or HTTP signature alone do not prove worker execution capability | Verify installed versions/read-only access, exact preview/confirmation expiry, gas/nonce identity and contract-signature validation; no funds required |
| Production Trust and admitted reference/liquidity/as-of historical evidence | Risk/Opportunity cannot authorize production decisions | Continue existing data-admission investigations without changing thresholds, reference selection or 30/30/3 requirements |
| Scoped approval workflow, uncertain RFQ ID/nonce replacement, automatic reorg monitoring | No auto approval/revoke, resubmission, cancellation/no-fill proof or absolute finality is claimed | Reuse ApprovalService under independently verified gates; provide read-only authoritative reconciliation/protocol invalidation evidence and monitor canonical history before any live rollout |

**Highest-priority next step:** obtain bounded read-only unsigned RFQ quote/build payloads
for all three vendors, then verify those exact payload hashes/domains against deployed
contracts. This supplies evidence the offline regression suite cannot manufacture. Stop
here; no live enablement, phase advancement or Git publication.

## Files changed

- `.env.example`
- `backend/app/api/live.py`
- `backend/app/clients/binance_trading.py`
- `backend/app/clients/binance_web3.py`
- `backend/app/clients/bsc_rpc.py`
- `backend/app/clients/common.py`
- `backend/app/clients/execution_gateway.py`
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/app/models/live.py`
- `backend/app/models/portfolio.py`
- `backend/app/repositories/live_fills.py`
- `backend/app/services/agentic_wallet_signer.py`
- `backend/app/services/eip712_validation.py`
- `backend/app/services/execution_gates.py`
- `backend/app/services/live_execution.py`
- `backend/app/services/live_settlement.py`
- `backend/app/services/live_signer.py`
- `backend/app/services/live_wiring.py`
- `backend/app/services/portfolio.py`
- `backend/app/services/protocol_definitions.py`
- `backend/app/services/rfq_orders.py`
- `backend/tests/fixtures/rfq_orders.py`
- `backend/tests/integration/test_live_remediation_api.py`
- `backend/tests/unit/test_live_evidence.py`
- `backend/tests/unit/test_live_execution.py`
- `backend/tests/unit/test_live_settlement.py`
- `backend/tests/unit/test_rfq_orders.py`
- `backend/tests/unit/test_wallet_portfolio_remediation.py`
- `backend/tests/unit/test_wallet_signer_remediation.py`
- `docs/API_MATRIX.md`
- `docs/ARCHITECTURE.md`
- `docs/EXECUTION_GATES.md`
- `docs/EXECUTION_REMEDIATION.md`
- `docs/EXECUTION_REMEDIATION_CHECKLIST.md`
- `docs/evidence/EXECUTION_REMEDIATION.json`
- `frontend/src/services/backendSchemas.json`
- `frontend/src/types/backend.generated.ts`
- `pyproject.toml`
- `requirements.txt`
- `scripts/check-security.py`
