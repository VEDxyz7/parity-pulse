# Agentic readiness tests during the paused rebase

**Historical reconciliation report:** the three failures below describe the state
before the separately authorized settlement remediation. Its implementation and
passing validation are recorded in the final section; the original evidence is
preserved here. No live-readiness gate has passed.

The replay of `e51e817` onto `081388c` combined an incoming readiness test with
already-resolved remote execution files. This reconciliation changes tests and this
report only. It preserves the four earlier conflict resolutions, remote production
execution code, historical reports and independent gate statuses.

The import incompatibility is resolved. This is **not a live-readiness PASS**.
Three ordinary, unskipped settlement assertions expose missing protections in the
retained implementation. No compatibility shim or production execution change was
introduced to make the suite green.

## Interface mapping and capability limits

Repository-wide search and inspection of both commit versions establish the
following distinctions. Incoming interfaces existed on the UI commit's execution
branch; their absence from the retained remote code does not by itself mean their
safety requirements are obsolete.

| Incoming dependency or expectation | Retained interface / classification | Reconciled verification and remaining limitation |
| --- | --- | --- |
| `LiveReconciler` | Reconciliation is implemented by `LiveRebalanceExecutor.reconcile`. | A worker with production gates and no signer methods recovers a persisted submission identity using synthetic read-only RPC evidence. Missing transfer evidence retains the wallet lock; complete evidence confirms. No separate reconciler is invented. |
| `ENABLED_RUNTIME`, `authorization_for` imports from another test | Incorrect dependencies on absent branch-specific test helpers. | Construct the real `RuntimeExecutionPolicy` directly to verify each control. Real production gates still reject a nominal policy. Do not manufacture a successful authorization helper. |
| `TransactionAuthorization` wired into the worker/signer/RPC | Genuinely incomplete integration. The incoming standalone helper exists, but retained transports do not consume it, and `LiveFillStore.require_consumed_consent` does not exist. | Exact-envelope mutation tests remain. Real journal consent recording/consumption tests cover expiry, digest and single use across restart. No test claims successful end-to-end transaction authorization. |
| Worker `check_gas` | Shared `FundingService.check_gas` already validates maximum gas cost, USD budget, native reserve and price freshness. | Exercise this real service. The live worker does not integrate the shared USD-cost check; this remains an execution blocker. |
| RPC `estimate_gas` and runtime/authorization arguments | Missing production capabilities in the retained client. | `eth_estimateGas` is outside its read allowlist and is rejected before transport. Actual raw-send methods reject under real production gates even with `allow_send=True`. No RPC estimation, final-envelope budget enforcement or independent transport runtime authorization is claimed. |
| `LiveRuntime.attach_readonly` | Missing convenience/runtime wiring, not needed to call the existing reconciliation method offline. | Verify real `LiveRuntime.attach` rejects all supported signer kinds and both routes under production gates; startup never attaches a worker. Automatic host recovery wiring remains unavailable. |
| `AgenticWalletSigner.preview(route)` | No such signer orchestration interface. Existing primitives are `BawPreviewClient`, command validation, `validate_preview`, `AgenticWalletAdapter.snapshot` and `WalletSafetyChecks.evaluate`. | Test exact preview arguments, denied execute/auth/gas/nonce arguments, version requirements, disconnected/changed sessions, wrong-chain preflight and DEMO/LIVE isolation. Valid synthetic reads retain fixture provenance and never satisfy production readiness. An integrated final-envelope preview/execute lifecycle remains unverified. |
| `PreparedApprovalLeg`, worker `after_approval` | Missing live-worker approval lifecycle. The proposal service has `SafetyExecutionService.observe_approval`. | The real proposal service requires verified allowance and obtains a new quote, route and simulation. This is a synthetic non-executable proposal test, not proof of an on-chain approval. |
| `verify_approval(rpc, hash, ...)` | Missing on-chain approval receipt verifier. `ApprovalService.confirmed` verifies a fresh exact allowance, not receipt/calldata/nonce/finality. | Test supported owner/token/spender/amount/mode/freshness/quote-expiry checks. Exact approval receipt and allowance lifecycle remain blockers; neither a hash nor an allowance is relabelled as full receipt verification. |
| Settlement prepared minimum and nonce | Genuine missing protections, not obsolete test expectations. | Preserve active rejection assertions, detailed below. |
| Rechecking quote/consent immediately before and after signer preparation | Missing final-boundary integration. Current quote/builder and journal checks exist earlier. | Verify supported quote-expiry and consent-expiry boundaries, plus real gates rejecting the worker before signer access. Do not claim these tests prove time-of-signing or time-of-broadcast expiry revalidation. |

## Preserved failing security expectations

`verify_swap` enforces `expected["minimum_out"]`, which the live worker journals
from `PreparedLeg.minimum_out`. It does not enforce the potentially stronger
`expected["transaction"]["minReceiveAmount"]`, require that field, or compare the
actual transaction nonce with the durable submission nonce.

The following tests must remain red until these production protections are
substantively implemented and verified in a separately scoped change:

- `test_settlement_enforces_prepared_minimum_even_if_plan_is_weaker`: a synthetic
  fill below the exact prepared minimum is incorrectly confirmed when the weaker
  journal minimum is satisfied. The original rejection expectation is retained.
- `test_settlement_requires_exact_prepared_minimum`: missing prepared-minimum
  evidence is incorrectly accepted. The original rejection expectation is retained.
- `test_settlement_rejects_changed_journaled_nonce`: synthetic actual nonce 7 and
  journaled nonce 8 are incorrectly accepted. The fixture now explicitly supplies
  both values, and the original nonce-rejection expectation is retained.

No `skip`, `xfail`, module exclusion, permissive production gate injection or fake
authorization success is used in the reconciled module. Its autouse guard rejects
network connects, subprocess launches and transaction/typed-data signing. Fixture
CLI responses keep their synthetic identity. Existing tests outside this module
remain unchanged.

## Gate invariants

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

Settings continue to refuse LIVE execution, live trading, autonomous approval or
disabled simulation. Production gates reject worker attachment, signing and raw
send paths. Passing supported-interface tests cannot enable these capabilities.

## Reproduction

Actual verification on 11 October 2026:

| Check | Result |
| --- | --- |
| Reconciled readiness module | 74 passed, 3 failed; no collection errors |
| Full backend suite, no exclusions | 1,929 passed, 3 failed, 2 pre-existing malformed-fixture serializer warnings |
| Focused execution/wallet/readiness/security suites | 430 passed, the same 3 settlement failures |
| Frontend suite | 329 passed |
| Type checking and production build | PASS; existing large-bundle warning |
| Ruff, schema verification, security audit and diff whitespace | PASS |
| Official wallet diagnostic | CLI absent; authentication/session/equivalence NOT_VERIFIED; zero signing/approval/broadcast calls |

Backend validation remains **BLOCKED** by the three genuine settlement defects.
The original four resolved files and all unrelated original index entries are
unchanged. Stored-data hashes are unchanged. The previous browser evidence is
preserved; browser checks were not rerun for this tests/documentation-only change.

From the repository root:

```sh
.venv/bin/python -m pytest -q backend/tests/unit/test_agentic_execution_readiness.py
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q backend/tests/unit/test_agentic_execution_readiness.py backend/tests/unit/test_live_execution.py backend/tests/unit/test_live_settlement.py backend/tests/unit/test_wallet_signer_remediation.py backend/tests/unit/test_agentic_wallet_signer.py backend/tests/unit/test_agentic_wallet.py backend/tests/unit/test_execution_safety.py backend/tests/integration/test_live_remediation_api.py backend/tests/integration/test_wallet_contracts.py backend/tests/integration/test_wallet_quota_remediation.py backend/tests/security
.venv/bin/ruff check backend scripts
PYTHONPATH=backend .venv/bin/python scripts/generate-ui-contracts.py --check
npm test
npm run build
.venv/bin/python scripts/check-security.py
PYTHONPATH=backend .venv/bin/python scripts/check-agentic-wallet-readiness.py
git diff --check
git diff --cached --check
```

The first two commands are expected to exit nonzero for the three preserved
settlement defects, without any collection errors. The wallet diagnostic performs
bounded version/help/status reads only when an official CLI is present; it never
authenticates, previews, signs or executes. The rebase is deliberately not continued.

## Settlement remediation — 11 October 2026

The partially edited command completed despite its reported tool error: all five
initial edits were present when work resumed. The original three failing tests
were run first and all three passed. Subsequent review completed recovery checks
and added regression coverage without discarding the existing implementation.

### Root causes and enforced invariants

1. Settlement previously used only `PreparedLeg.minimum_out` from the plan. It now
   validates both that value and the exact prepared `minReceiveAmount` as positive
   canonical uint256 strings, then enforces their maximum in output-token base
   units. There is no float conversion, decimals conversion or zero fallback.
   Missing, malformed or inconsistent preparation/envelope evidence is rejected.
2. The durable signed submission previously supplied only a hash to recovery.
   Recovery now verifies that hash against `swap_tx`, the receipt and raw RPC
   transaction; the submission payload digest against the validated prepared
   transaction; and the sender transaction nonce against the actual RPC nonce.
   If a bound envelope is present, its transaction, nonce, minimum, recipient,
   spender, tokens, amount and route fingerprint must agree with preparation.
   The existing worker persists this envelope before the durable submission
   boundary. This binds metadata and bytes; it does not decode opaque calldata or
   establish live simulation equivalence.
3. Confirmed/reverted SWAP recovery now rechecks those immutable commitments,
   canonical receipt, finality and applicable transfers against the stored
   settlement. It uses the original verification result rather than today's
   mutable wallet balances. Initial successful settlement still requires the
   existing balance/log consistency check. Incomplete/conflicting evidence keeps
   a pending wallet claim or restores a terminal claim and leaves the action
   `RECONCILIATION_REQUIRED`. Missing evidence is not permission to resubmit.

SWAP nonces are strict nonnegative integers; SQLite journaling rejects values
outside its exact signed 64-bit storage range. RFQ submission identities continue
to use a request UUID and `nonce=None`; protocol order nonces remain verified in
their own RFQ events and are never compared with the relayer's transaction nonce.
Existing gate checks, mandatory simulation, Trust/risk admission, consent checks,
exact allowances, transfer limits and duplicate prevention remain intact.

### Files changed in this remediation

- `backend/app/services/live_settlement.py`: strongest minimum, prepared payload,
  durable signed identity, nonce and optional envelope verification.
- `backend/app/services/live_execution.py`: persist envelope and use durable
  submission evidence during settlement/restart; revalidate terminal commitments
  and reject missing/conflicting evidence or route domains.
- `backend/app/repositories/live_fills.py`: validate transaction/RFQ nonce domains
  before journaling; retain the existing atomic re-lock operation with an accurate
  evidence-failure reason when recovery fails.
- `backend/tests/unit/test_live_settlement.py`: valid nonce/minimum fixtures and
  exact large-integer, malformed-evidence, signed-identity, envelope and RFQ-domain
  regressions.
- `backend/tests/unit/test_live_execution.py`: real payload fingerprints in
  recovery fixtures; restart corruption, claim retention/re-lock, terminal
  idempotency and mock-only envelope persistence regressions.
- `backend/tests/unit/test_agentic_execution_readiness.py`: explicitly remove the
  prepared minimum for its missing-evidence test; use the actual fixture payload
  digest for durable recovery. Original rejection assertions remain intact.
- `docs/AGENTIC_READINESS_TEST_RECONCILIATION.md`: preserve the historical failures
  and record this remediation and its verification.

### Actual validation after remediation

| Check | Result |
| --- | --- |
| Three originally failing settlement tests, run first | 3 passed |
| Settlement/execution/readiness suites | 259 passed, included in the focused run |
| Readiness module separately | 77 passed |
| Focused execution/wallet/readiness/security suites | 530 passed |
| Full backend suite, no exclusions | 2,029 passed; 2 existing malformed-fixture serializer warnings |
| Frontend suite | 329 passed |
| Type checking and production build | PASS; existing large-bundle warning |
| Ruff and 12 generated UI contracts | PASS |
| Secret scanning, Git/environment and Docker exclusions | PASS |
| Staged and unstaged diff whitespace | PASS |

The full backend suite used `.venv/bin/python -m pytest -q` without exclusions;
the reproduction commands in the historical section remain applicable. Detailed
backend/frontend logs are in `/tmp/parity-settlement-remediation/`. The original
249 staged paths, including all four conflict resolutions, were preserved exactly;
this remediation is left unstaged for review. Stored data is unchanged. No new
public API/model contract or frontend workflow was introduced, so browser checks
were not repeated for the settlement changes.

### Remaining live blockers and stop state

Backend validation is now PASS. Live execution remains BLOCKED. The final-boundary
quote/consent authorization integration, independently enforced runtime controls,
RPC gas estimation and USD budget enforcement, on-chain approval-receipt lifecycle,
Agentic Wallet runtime integration, calldata semantics and exact final-envelope
simulation equivalence still require separate implementation/evidence. The
existing production Trust/risk and 30/30/3 requirements are unchanged.

No configured wallet signing, approval, submission or broadcast was performed;
the regression suite uses synthetic keys, mock transports and isolated journals.
All seven gate values above remain unchanged. No commit, push or rebase continuation
was performed; the interactive rebase remains paused for review.
