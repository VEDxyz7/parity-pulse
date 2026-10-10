# PR #1 merge resolution — review pending

This prepares `feat/fix-swap-and-RFQ` for a normal merge of the verified current
`main`. It does not commit, push, merge on GitHub, enable execution, or advance a gate.

## Verified inputs and isolation

- PR: <https://github.com/VEDxyz7/parity-pulse/pull/1>.
- PR/source head: `223c204a77de2f5242767681fa60fcf8457abda0`.
- Target `main` and original local `main`/`origin/main`:
  `9b6368cda71ca3ee79ce8d5755255d80b29ea38d`.
- Merge base: `266c2cb922a093e790f3aef2e3b406f06dd7d60c`.
- GitHub reports open, `mergeable=false`, `mergeable_state=dirty`. Its PR base SHA
  and cached `refs/pull/1/merge` refer to older parents, so they were not used as
  the current merge result. Both actual remote branch tips were checked again
  after validation and remain the exact SHAs above.
- Isolated review clone:
  `/private/tmp/parity-pr1-review-20261011-v0o6hi1g/repo`.
  It has its own Git index, refs and merge state, with source HEAD at the PR head
  and `MERGE_HEAD` at the verified target. Objects are shared read-only with the
  original repository. Dependencies are reused through ignored local symlinks;
  no `.env`, credentials, production database or uncommitted replay dataset was copied.
- Original working tree remains on `main`; its 41 uncommitted paths, porcelain
  status, HEAD and SHA-256 hashes of all 568 tracked/untracked files are unchanged.
  No stash, reset, clean, source overwrite, commit or push occurred there.

## Exact conflict and semantic decisions

The only Git text conflict is **`frontend/src/App.tsx`**. Keep `main`'s newer
premium emerald header, responsive navigation, architecture image, MarketSnapshot,
DataContext, Research Lab and all existing views. Integrate the teammate's `#live`
entry as **Execution status**, a read-only view of blocked gates and allowlisted
journal records. No browser worker credential, execute/retire control, unverified
index parity request or protected raw capture request is retained.

The following automatic merges also required semantic reconciliation:

| Area / files | Resolution |
|---|---|
| `config.py`, `.env.example`, `main.py`, API schemas, frontend system parser/types | Preserve newer Alpaca/Finnhub configuration and strictly non-live application/status contracts. Carry the optional backend-only worker credential and journal runtime. Startup constructs no signer/write client. Worker routes mount only when configured; the default public API inventory remains unchanged. The credential grants no live capability. |
| `services/live_execution.py`, `live_wiring.py`, `execution_gates.py`, `clients/binance_trading.py`, `binance_web3.py`, `common.py`, `execution_gateway.py`, `bsc_rpc.py` | Carry the related audited local remediation: independent gates before writes, fresh risk and market revalidation, exact allowance and balance/chain reads, simulation effects, one-attempt uncached RFQ submission transport and no blind retry/fallback. Ordinary Binance read-only authorization/signing allowlists stay unchanged. Preserve sanitized provider business-code mapping. |
| `services/rfq_orders.py`, `protocol_definitions.py`, `eip712_validation.py`, `live_settlement.py` | Retain vendor-specific CoW, 1inch and Pancake order verification with exact canonical schemas/domains/deployments, hash/UID/witness binding, supported extensions and signed bounds. Signed bounds do not replace settlement simulation/equivalence. Raw on-chain transfer/transaction/event/order identity and canonical confirmation/reorg evidence are required. Pancake settlement allowlist remains empty by default. |
| `repositories/live_fills.py`, `models/live.py`, `api/live.py` | Durable atomic action/wallet claims, signed identity recorded before submission, uncertain submissions remain unresolved and locked, observation-only recovery, bounded sanitized unsigned captures and positive public response allowlists. Worker actions require loopback/Host/Origin policy, worker authentication, server-owned preparation and exact expiring single-use confirmation. |
| `services/live_signer.py`, `agentic_wallet_signer.py` | Preserve adapters behind independent route/wallet gates. EOA ownership/hash and real ERC-1271 RPC validation replace HTTP assertions. CLI previews use documented simulation/risk/authority fields. Unverified Altana user-operation and wallet gas/nonce execution paths remain blocked. |
| `services/portfolio.py`, `models/portfolio.py`, generated UI contracts | Keep teammate WALLET inventory buy/sell/drift math through the existing shared Router/Risk/Funding services, verified fresh holdings and explicit inventory provenance. Keep default POSITIONS behavior, mandatory Trust and unresolved-wallet guards. Reject Trust-disable and closed-market exemption options. Do not add an unaudited EXECUTED transition or live flags to plans. |
| `services/risk.py`, `routing.py`, `models/routing.py`, `repositories/portfolio.py`, `execution_builders.py`, execution-risk/RFQ schemas | Keep `main`'s strict controls. No Trust/liquidity bypass, weekend half-cap authorization, optional RFQ identity, mixed gas model or permissive unknown-field RFQ parsing. Harmless quote segment descriptors, bounded DEX labels and informational `isBest` are retained without changing canonical route fingerprints. |
| `models/data.py`, `providers/binance.py` | Preserve `offhours` as an explicit provider fact without admitting it as an open/tradable execution session. |
| `clients/binance_futures.py`, `services/equity_reference.py` | Preserve optional read-only index corroboration and conversion, with actual provider publication time preserved. `.reference()` explicitly refuses independent-equity admission; only `.corroboration()` returns non-admitted index context. No production reference selection changes. |
| `services/live_portfolio_source.py` | Keep an unwired read-only discovery/mark/raw wallet balance prototype. It returns explicit evidence blockers, no fabricated USD funding, liquidity, fees, slippage or risk template, and does not build/capture RFQ signing payloads automatically. It cannot authorize a rebalance. Existing admitted data/portfolio sources remain authoritative. |
| `sidecar/agent-studio/server.mjs`, `grant-session.mjs`, new `execution-gates.mjs` | Retain teammate SDK handlers behind an immutable blocked entry gate evaluated before SDK imports, session/private-key reads, wallet creation, permission grants, signatures, transfers, x402 payment settlement or listening sockets. No environment/CLI override. Correct BSC Permit2 constant in retained experimental code; suppress raw SDK errors. SDK/runtime compatibility remains unverified, not claimed by gate tests. |
| Historical teammate documents and sidecar README | Preserve original text with an explicit superseded notice; legacy enablement/runbook claims are historical, not instructions for this resolved state. |

The original 41 uncommitted remediation paths were individually selected because
all concern these execution defects, their tests/contracts/dependencies or evidence.
They are explicitly listed in the external `selected-remediation-files.json` and
`merge-audit.json`. They were copied into the isolated review only; unrelated local
files, secrets, databases and replay data were not staged. No code/test was taken
from a dirty tree indiscriminately with a blanket original-tree `git add`.

All newer `main` changes are present. Alpaca/Finnhub clients/adapters/events,
observational storage/ingestion/data-layer services, production Trust service,
shared Risk/Router, strict status parsers, dashboard stylesheet and master spec
are byte-for-byte equal to the verified target. Massive, Binance and Hyperliquid
paths remain present; their regression suite passes. No file is deleted relative
to either parent and each worker/journal/router/risk implementation has one class.

## Tests and evidence

Final validation in the isolated clone:

- Backend: **1,804 passed, 1 skipped**, two existing warnings from deliberately
  malformed allowance fixtures. Skip: `test_agent_evidence.py:122`, local real replay
  artifact not committed. No synthetic control is skipped or counted as real data.
- Frontend: **290 passed** in 16 files, including five merged execution-view tests.
- `npm run build`: TypeScript `tsc --noEmit` and Vite production build pass.
- Ruff lint and format: pass, **251 Python files** formatted.
- Pydantic-derived UI contract drift: pass, seven contracts.
- `pip check`: no broken requirements.
- Sidecar: two Node offline gate tests plus syntax checks pass. No SDK install,
  live runtime verification, session grant or payment execution was performed.
- Security: configured local secret leakage, Git ignore, Docker exclusion and
  frontend isolation pass, including sidecar files. Credentials were used only
  in memory for leakage comparison and never copied, printed or recorded.
- Browser/MCP: actual built UI with four credential-free disposable fixture
  backends; desktop/mobile/tablet, six scenario journeys, read-only execution
  status on desktop/mobile; **195 local API requests**, zero external browser
  requests, zero live execution calls, zero production Trust calls from Sandbox.
  All five owned servers stopped; unrelated processes untouched.
- Index: zero unresolved entries/markers; whitespace checks against both parents
  pass. Full diffs against PR head and `main`, selected-file hashes and per-file
  dispositions are saved for review. No commit/push/GitHub merge was performed.

Teammate regression intent is preserved without retaining unsafe success criteria:

- Wallet gap buys, at-target stand-down, held-balance sells and closed-session
  refusal remain in `test_portfolio.py`; Trust-disable assertions now require refusal.
- Every teammate RFQ verifier case is ported to canonical fixtures in
  `test_teammate_rfq_regressions.py`, alongside the audited protocol tests.
- Previous receipt-only, auto-sign/execute, expired-order release and blind-resubmit
  success expectations are superseded by the stronger worker/journal/settlement
  regressions: exact approvals and simulation effects, stale/fresh risk checks,
  pre-submit persistence, two-worker claims, lost response/crash recovery, raw
  identity/event/balance evidence, nonfill locks, reorgs, consent and independent gates.
- Legacy CLI preview/signature/dev-mode scenarios now prove zero CLI execution;
  documented preview/recovery-byte validation remains separately tested.
- New merge guards prove non-admitted index timestamps, blocked wallet captures,
  informational quote fingerprint stability and sidecar pre-import denial.
- Existing provider, Trust, routing, sandbox, position, portfolio, scorecard, API,
  MCP and dashboard tests were retained; no test is disabled to conceal a failure.

## Reproduction

Run from the isolated review clone (dependency symlinks currently point to the
original project; no credential file is required):

```sh
cd /private/tmp/parity-pr1-review-20261011-v0o6hi1g/repo
.venv/bin/python -m pytest -q
npm test
npm run build
.venv/bin/python -m ruff check backend scripts
.venv/bin/python -m ruff format --check backend scripts
PYTHONPATH=backend .venv/bin/python scripts/generate-ui-contracts.py --check
.venv/bin/python -m pip check
node --test sidecar/agent-studio/execution-gates.test.mjs
node --check sidecar/agent-studio/server.mjs
node --check sidecar/agent-studio/grant-session.mjs
.venv/bin/python scripts/check-security.py
.venv/bin/python scripts/verify-frontend-phase15.py
```

Browser checks require local Google Chrome and unused fixture ports
`8054–8057` and `5178`; the runner refuses occupied ports. It forwards no credentials,
loads no `.env`, uses temporary databases and terminates only its own processes.
Security checks additionally compared the review artifacts with original locally
configured credential values in memory; none are included in the evidence.

## Gate status and remaining blockers

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
EXECUTION_MODE=DRY_RUN
APPROVAL_MODE=PROPOSE_ONLY
LIVE_TRADING_ENABLED=false
REQUIRE_SIMULATION=true
```

Real admitted independent equity, authoritative liquidity, historical as-of ratios
and the 30/30/3 real evidence requirements remain external Trust blockers. Genuine
SWAP gas-sensitive simulation/equivalence, RFQ payload/deployment/hash/settlement
equivalence and verified wallet/runtime/confirmation compatibility are still
required. Offline mocks, index corroboration and this clean merge do not resolve them.

The only merge-workflow dependency is review and authorization of the staged diff,
followed by a normal merge commit and non-force source-branch push. GitHub still
shows the old conflicted head until that reviewed update is pushed. Do not merge
on GitHub as part of this task.

## Exact commands after review

The clone is intentionally in a fully resolved, staged merge with no commit yet.
Before committing, confirm remote tips still match the verified inputs; stop and
reconcile again if either has advanced. Do not run these commands in the original
dirty working tree and do not stage its unrelated work.

```sh
cd /private/tmp/parity-pr1-review-20261011-v0o6hi1g/repo
git ls-remote origin refs/heads/main refs/heads/feat/fix-swap-and-RFQ
git diff --cached --stat
git diff --cached origin/main
git diff --cached 223c204a77de2f5242767681fa60fcf8457abda0
git diff --cached --check
git ls-files --unmerged
# Only after review: creates a two-parent merge; rewrites no shared commit.
git commit -m "Merge main into feat/fix-swap-and-RFQ and preserve execution remediation"
git push origin HEAD:feat/fix-swap-and-RFQ
```

No `--force`, reset, stash, cleanup or GitHub merge is required.
