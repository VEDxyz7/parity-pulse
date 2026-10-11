# Agentic Wallet BSC remediation — 2026-10-11

## Readiness conclusion

**Not ready for a real swap.** Non-capital implementation defects were repaired and
tested, but installed-wallet, deployed-route, calldata and exact simulation/execution
evidence remains missing. No gate is advanced. No user-wallet signing, approval,
broadcast, authentication or wallet-setting operation was performed. Offline tests use
synthetic identities and mocked transports; some existing tests exercise fixture-only
cryptography. No production observations were backfilled. No commit or push was made.

The working tree already contained substantial uncommitted execution remediation,
provider and frontend work. This increment preserves it and extends the existing
worker, journal, clients, builder, simulation and funding services rather than replacing
them. The older execution-remediation reports remain historical evidence.

## Phase A: actual runtime evidence

At `2026-10-11T02:04:41.676212+00:00`, the bounded diagnostic found no `baw` on PATH.
Standard Homebrew, `/usr/local/bin`, user-local/npm and local/global Node installation
locations were also inspected without finding a supported alternate runtime. No binary
was installed. Installed version, command help, authentication, user control of a BSC
address, Developer Mode and transaction preview are therefore **NOT_VERIFIED**.
Absence of the executable is not proof that the user's Binance account has no wallet.

The official Binance documentation inspected on this date declares CLI `1.10.0`
(`SKILL.md` version `1.12.0`) and npm package `@binance/agentic-wallet`:

- [Official preflight/install instructions](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/preflight.md).
- [Official authentication instructions](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/authentication.md).
- [Official external-call preview/execution contract](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/external-sign.md).
- [Official wallet reads](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/wallet-view.md).

Documentation supports BSC chain identifier `56`, ownership-checked contract-call
preview, request-ID execution and transaction history/lock reads. This is documentation
evidence, not proof of this machine's operational capability. Preview accepts
from/to/value/inputData; an optional user-specified gas limit is documented, but gas
price and nonce controls are not. The new preview client deliberately omits gas
overrides and cannot execute. A returned request ID never passes a gate or proves
exact-envelope equivalence. The existing conservative rejection of risk/authority
changes and `requireConfirmation=true` is preserved. App-confirmation order lifecycle
is not yet supported by the worker.

### User-controlled installation and authentication (not run)

In the user's own terminal, follow the official instructions:

```sh
npm install -g @binance/agentic-wallet@1.10.0
baw cli-check --required-version 1.10.0 --json
baw contract-call --help
baw wallet status --json
```

If disconnected, run `baw auth signin --json` locally. Open the exact official URL it
returns, compare the pairing code with the Binance App, and confirm the login in the
App. Then run `baw auth verify --qrCodeId <locally-returned-id> --json` and keep it
running until completion. Recheck `baw wallet status --json`; App success alone does
not prove local connection. Do not paste QR URLs, pairing/session artifacts, access
tokens or other credentials into chat, logs or repository files. Developer Mode and
security settings can only be configured through the user's official App interface;
this increment does not change them.

## Phase B: implementation and limits

| Finding | Implemented correction | Remaining limitation |
|---|---|---|
| Settlement used the weaker plan minimum | Require the prepared transaction minimum and enforce the greater of prepared/plan bounds; missing prepared minimum rejects; verify submitted nonce | Actual deployed swap settlement remains untested |
| Quote/consent could expire during preflight | Check current quote, action/payload binding and consumed durable consent before signing, after preparation and at final transport boundary; RFQ callbacks repeat expiry/deadline checks | No actual wallet signing/broadcast attempted |
| Gas estimation/budget missing | Read-only `eth_estimateGas` with exact prepared call/gas fields, chain 56, bounded estimate; enforce maximum gas-price × gas-limit against existing approved USD cost reserve, fresh native price and on-chain native balance/reserve | CLI cannot yet be shown to preserve these fields; no gas-sensitive simulation proof |
| Incomplete approved identity | Immutable envelope binds chain, wallet/recipient, destination, calldata, native value, input/output tokens, input amount, prepared minimum, spender, gas fields, nonce and route fingerprint; local signer validates signed RLP/recovered wallet against it | Opaque calldata metadata is not an ABI proof; `calldata_semantics_verified` stays false |
| Simulation could be mistaken for authorization | Final production authorization independently requires exact simulation match and live equivalence, plus calldata verification | `live_equivalence_verified` remains false; existing provider only simulates from/to/value/data |
| Approval lifecycle incomplete | Reuse exact scoped unsigned approval builder; require gas check and simulation. Read-only canonical receipt/event/nonce/allowance verification precedes fresh quote/build/simulation/nonce preparation | No approval signing/submission; reset/unlimited and wallet execution lifecycle remain unsupported. Fresh swap consent still required |
| Restart/unknown recovery depended on a live worker | Separate read-only reconciler, available with live flags disabled; durable action/wallet claim, submission hash/nonce/envelope and existing terminal verification retained | Unknown outcomes stay locked; never automatically resubmit or infer absence from missing receipt |
| Gates alone were insufficient | Default-disabled host runtime policy checked independently at worker, signer, raw RPC and RFQ client boundaries; transaction authorization mandatory | External CLI cannot be assumed to know application flags; verified controlled execution bridge remains absent |
| HTTP gate differed from actual signer | HTTP and status use the same signer-kind policy: local EOA needs route gate; Agentic/Altana additionally need wallet gate; unknown kinds reject | All production gates still blocked |
| Preview path absent | Extend existing bounded CLI reader with a closed preview-only grammar; verified version/session/address/chain/Developer Mode/lock/pending state, preview expiry and unchanged post-preview session required | Actual preview not run; returns `execution_ready=false`; no execute command accepted |

Read-only preparation reuses `FundingService`, `AggregatorQuoteService`,
`ExecutionRouteBuilder`, `ApprovalService` and `ExecutionSimulationService`.
Trust/risk admission, closed-market rules, source separation and 30/30/3 are unchanged.
The Agentic signer still refuses sending and typed-data execution. It does not expose
a working swap `prepare/broadcast` implementation or a verified live worker attachment.
Startup attaches a read-only recovery transport only in `LIVE_READ_ONLY`, never a signer
or write-capable Binance client. Recovery is explicitly invoked, not an automatic retry.

## Phase C: acceptance evidence

- Full backend: **1816 passed**, two existing malformed-fixture Pydantic serializer warnings.
- Targeted execution/readiness/API suites: **157 passed**.
- Frontend: **304 passed** across 17 files.
- TypeScript typecheck and Vite production build: **PASS**; existing large-chunk warning.
- Ruff: **PASS**. Security scanner: **PASS** (configured-secret leakage, ignored env,
  Docker env exclusion, frontend secret isolation).
- Generated frontend contracts: **PASS**, 11 contracts unchanged.
- Python dependency consistency: **PASS**. `git diff --check`: **PASS**.

Regressions cover prepared-minimum settlement, missing minimum/nonce, every runtime
control, altered chain/recipient/spender/input/minimum/destination/calldata/value/gas,
expiry before and during preparation, gas estimate/budget failures, closed CLI grammar,
wallet disconnect/session switch/expired preview, approval receipt and fresh reprepare,
HTTP signer-gate consistency and read-only restart reconciliation. Existing concurrent
claims, duplicate/uncertain submissions, durable identities, reorg and fixture-crypto
tests remain. New readiness tests prohibit sockets and cryptographic signing.
Fixture-only open policies do not modify production gate definitions or provide live evidence.

Reproduce from the repository root:

```sh
PYTHONPATH=backend .venv/bin/python scripts/check-agentic-wallet-readiness.py
.venv/bin/python -m pytest -q backend/tests/unit/test_agentic_execution_readiness.py backend/tests/unit/test_live_execution.py backend/tests/unit/test_live_settlement.py backend/tests/unit/test_wallet_signer_remediation.py backend/tests/integration/test_live_remediation_api.py
.venv/bin/python -m pytest -q
npm test
npm run build
.venv/bin/ruff check backend scripts
.venv/bin/python scripts/check-security.py
PYTHONPATH=backend .venv/bin/python scripts/generate-ui-contracts.py --check
.venv/bin/python -m pip check
git diff --check
```

Use `python -m pytest` from the root: the console-script invocation does not make the
repository's `backend.tests` fixture namespace importable in this environment. The
readiness script reports only sanitized capability states and never authenticates,
previews, signs or executes. With a CLI present, bounded help/status/session reads run.

## Configuration and entitlement prerequisites

Existing application variable names: `DATA_MODE`, `RUNTIME_MODE`, `EXECUTION_MODE`,
`LIVE_TRADING_ENABLED`, `APPROVAL_MODE`, `REQUIRE_SIMULATION`, `EXECUTION_WORKER_TOKEN`,
`BINANCE_WEB3_API_KEY`, `BINANCE_WEB3_SECRET_KEY`, `DATABASE_URL`, `EQUITY_PROVIDER`,
`MASSIVE_API_KEY`, `MASSIVE_DATA_QUALITY`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`,
`ALPACA_FEED`, `ALPACA_DATA_QUALITY`. Independent-equity provider choice remains unchanged.
No environment values or secret presence checks are exposed in this report.

There is no implemented `BAW_PRIVATE_KEY` or `BSC_RPC_URL` setting. Wallet access uses
the official local CLI session. RPC uses the existing HTTPS constructor/default endpoint;
startup read-only recovery uses that default. A future deployment needs controlled RPC
configuration and adequate chain/read/simulation access. Binance quote/build/simulation,
actual pair/vendor/route permissions and verified tradability must be checked independently;
an indicative quote or an RFQ response must never be presented as a SWAP capability.
Live RFQ additionally needs its own verified settlement-equivalence/deployment evidence.

## Exact blockers and separate live-task order

1. Install the official CLI and establish user-controlled local authentication. Run
   sanitized version/help/session/BSC checks; verify owned address, token permissions,
   spending/developer limits, active session and clear pending/lock state.
2. Verify an actual executable SWAP route for the intended pair/amount and supported
   provider entitlement. Verify destination/spender deployed contracts, decoded calldata,
   recipient, input amount, minimum output and deadlines. Fail if provider returns RFQ.
3. Obtain documented and non-capital proof that the wallet preserves the approved final
   gas/nonce envelope and exact simulated payload. Implement the controlled request-ID,
   expiry/App-confirmation and ambiguous-result reconciliation bridge only from verified
   runtime behavior. Current CLI docs and provider simulation do not establish this.
4. Satisfy production Trust/risk admission with real permitted references, liquidity,
   historical as-of ratios and required 30/30/3 evidence. DEMO results cannot satisfy this.
5. Re-run gate-specific acceptance and security/recovery tests, then independently assess
   the relevant live gates against `EXECUTION_GATES.md`. Current literal guards and
   `Settings` reject live execution; changing environment variables cannot enable it.
   Any later live configuration/wiring change must follow verified gate evidence.
6. In a separate explicitly authorized task, establish funded wallet state and native gas
   reserve; obtain a fresh bounded quote/build/simulation and transaction-specific consent.
   If exact allowance is absent, the separately confirmed approval must use an equally
   verified execution path, followed by confirmed receipt/allowance and fresh swap
   quote/build/simulation/consent. Do not reuse the pre-approval preparation.
7. Only after all applicable gates and controls pass, execute the separately authorized
   operation once using durable identity. Reconcile canonical receipt, exact transaction,
   transfers/minimum output and journal; keep ambiguous/reorg outcomes locked.

**Within one hour: not realistically supported by current evidence.** CLI installation
and authentication may be quick, but missing provider/wallet envelope semantics, deployed
route proof and blocked production Trust are independent prerequisites. The recorded
0/30 baseline, 0/30 opening-model and 0/3 analogue evidence cannot be supplied by a
smaller transaction or offline tests. No credible one-hour execution estimate can be
made before those dependencies are resolved.

## Gates (unchanged)

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

Files changed by this increment (including extensions of pre-existing uncommitted files):

- `backend/app/clients/{baw_cli,baw_preview,bsc_rpc,binance_trading}.py`
- `backend/app/models/execution_envelope.py`
- `backend/app/repositories/live_fills.py`
- `backend/app/services/{execution_authorization,live_execution,live_settlement,live_signer,live_wiring,agentic_wallet_signer}.py`
- `backend/app/api/live.py`, `backend/app/main.py`
- `backend/tests/unit/{test_agentic_execution_readiness,test_live_execution,test_live_settlement,test_wallet_signer_remediation}.py`
- `backend/tests/integration/test_live_remediation_api.py`
- `scripts/check-agentic-wallet-readiness.py`
- This report. No frontend, Trust, risk, gate-definition or credential file changes in this increment.
