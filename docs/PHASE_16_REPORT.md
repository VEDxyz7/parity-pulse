# Master Phase 16 — Hardening + Release Candidate

**PHASE_16_IMPLEMENTATION = PASS** for the verified **non-live hardening scope**. All mandatory suites ran and passed. Five reproduced defects were fixed; no critical execution-safety failure remains in the tested non-live paths. Provider verification remains **PARTIAL**, actual execution verification **BLOCKED**, and **LIVE-READY = NO**. This is a development release candidate, not approval to deploy or trade. Phase 17/18 were not started; no commit or push.

## Authority and reconnaissance

The entire authoritative `docs/MASTER_SPEC.md` was reread: **5,321 lines**, SHA-256 `f69a9bd01a622c001c3ec6cb654e00562f6b3d03a8310f9e5ccf68efe4b49c84`. The full Phase 16 request and Phase 6–9 remediation audit / Phase 10–15 reports were read. Starting HEAD: `3f983a5dc0dab7301f852809e80c76b066a80ffe`, clean working tree. Baseline: 1,397 backend / 259 frontend cases. No existing architecture was rebuilt.

The hardening plan prioritized reproduced data-integrity/concurrency defects, immutable persistence, adversarial contracts, interruption recovery, independent replay and measured performance. Test counts were treated as inventory, not proof. Existing adapters, router, agents, Risk, execution controls, journals and browser fixtures were reused. **77 tracked protected files**—master, gates, prior reports/evidence and tracked data—retain their baseline hashes. No production observations were written by this task.

## Findings and fixes

| Reproduced finding | Fix and verification |
|---|---|
| A concurrent in-memory health connection could roll back an ORM writer's uncommitted transaction; the committed row disappeared. | Exclusive checkout of the single memory connection using a bounded one-connection QueuePool. Health waits for the transaction owner; commit and rollback remain correct. File-backed pooling is unchanged. This serializes connection ownership, not requests or the application. |
| Identical simultaneous scan saves from separate file-backed stores raised a uniqueness error. Shared memory connections also lacked repository coordination. | Atomic SQLite insert-on-conflict followed by immutable payload/digest/mode validation; repository-local lock for shared-memory reads/writes. Concurrent identical input is idempotent, conflicting input still fails. |
| Position monitoring and manual exit preparation raced between reading and saving a lifecycle version. | Monitor transitions now use the position service's existing lock and reload the current row. Database CAS and persisted leases continue to arbitrate separate workers. Due-time, lease, unresolved-position and ownership rules remain intact. |
| JavaScript normalized impossible dates/24:00/noncanonical timestamps into usable display values. | Generated-contract validation now checks calendar dates and canonical timezone-aware timestamp components without coercion. Valid leap dates and fractional/offset timestamps remain accepted. |
| The shared client accepted traversal/backslash/fragment/noncanonical API paths. | Refuse these paths before fetch. Preserve supported dotted and encoded-colon audit identifiers; positive compatibility cases were added. |

Pre-fix probes recorded **two backend failures** and **ten frontend failures**; the monitor/manual race was subsequently reproduced. New test-development errors (incorrect workspace field, preparation field and benchmark count names, plus a mock's TypeScript signature) were corrected against actual contracts. They did not justify changing product behavior. The final browser audit drill uses the filtered persisted-decision catalog: the unfiltered first audit page held older historical events. It verifies a real encoded-colon agent/scan deep link, with no invented identifier or product change. No inherited test was deleted or loosened.

Preventive improvement: artifact/bundle secret checks now include Polygon, Twelve Data and Finnhub credential names in addition to existing Binance/Massive/LLM names. Values are read only into memory and never printed. An inherited existence-only portfolio assertion now checks the retained plan/action/execution identity and unchanged owned-position count after rejected completion.

## Test matrix

Final full runs: **1,418 backend passed**, **273 frontend passed across 14 files**. All 1,397 inherited backend and 259 inherited frontend tests remain. **35 new focused cases = 21 backend + 14 frontend**, plus one strengthened inherited case. Zero actual skips, xfails, failures or errors. Two inherited Pydantic warnings deliberately serialize malformed allowance fixtures that must fail validation.

The following are **overlapping subsets of the full run**, not additional tests:

| Suite | Passed |
|---|---:|
| Backend unit | 859 |
| Backend integration | 555 |
| Dedicated security boundaries | 4 |
| Broader security/adversarial subset, including those boundaries | 78 |
| Actual concurrency cases | 21 |
| Restart/recovery | 40 |
| Replay/backtest/point-in-time controls | 81 |
| Schema/provider/agent/frontend boundary contracts | 221 |
| Simulation equivalence, execution and settlement safety | 223 |

Exact node IDs and selection scope are retained in [verification evidence](evidence/PHASE_16_VERIFICATION.json). Unit/integration tests exercise resolution, discovery, Decimal/base-unit normalization, missing/stale sources, Trust, bounded schema-grounded agents, deterministic filtering/top-K, Risk/funding, shared routing, quote expiry, builders, exact simulation fingerprints, approval effects, immutable settlement identities, partial fills, unknown exposure, portfolio claims, scorecards/audit and tool boundaries. Synthetic success is explicitly distinct from real-provider verification.

Additional checks passed: seven Pydantic-derived frontend contracts; `npm run build` (TypeScript + Vite); Ruff and formatting across **210 Python files**; Python compilation; configured-secret/bundle/Git-ignore/Docker-exclusion checks; `pip check`; root `npm ls --all`; JSON evidence parsing; whitespace checks. No separate mypy/ESLint framework is configured. Dependency checks establish consistency, not a new CVE certification. No dependencies were added or upgraded.

Reproduce from the repository root:

```sh
.venv/bin/python -m pytest -q
npm test
npm run build
.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
PYTHONPATH=backend .venv/bin/python scripts/generate-ui-contracts.py --check
.venv/bin/python scripts/check-security.py
.venv/bin/python -m pip check
npm ls --all
.venv/bin/python scripts/verify-frontend-phase15.py
.venv/bin/python scripts/benchmark-hardening.py --evidence /tmp/parity-phase16-performance.json
```

The benchmark refuses an existing output file. Browser verification requires Chrome and free ports 8054–8057/5178; it starts credential-free disposable fixtures and stops only owned processes. The retained Phase 15 runner is extended rather than duplicated.

## Concurrency and recovery

Concurrent tests cover identical buys, duplicate Opportunity requests, four rebalance workers, monitor/scheduler plus manual exits, repeated explicit confirmations, repeated verified allowance observations, quote refresh plus duplicate preparation, active leased-job recovery, multiple MCP calls, status polling and cross-worker scan/scorecard writes.

Only one original proposal/scan/plan/intent is retained where idempotency applies. Pending tool claims refuse duplicate dispatch. Eight simultaneous confirmation/allowance deliveries accept one current generation, reject stale deliveries, and never submit. Refreshed routes have a new matching simulation fingerprint and no inherited confirmation. Two concurrent manual exits plus monitoring retain one exit intent, one quote and unchanged ownership. Twelve workers successfully poll 48 health/system/workspace/catalog requests for each of file-backed and memory runtimes. Browser forwarding is now **concurrent**, removing the earlier serialized-harness limitation.

Recovery tests inject interruption during data refresh; scan/agent orchestration; quote/build/simulation/approval preparation; entry/monitor/exit/scheduler work; portfolio planning; scorecard/audit append; and tool receipt handling. Existing fresh-process portfolio and actual MCP subprocess checks complement close/reopen journal tests. A mid-refresh transaction rolls back without advancing its checkpoint. Mid-scorecard interruption rolls back both cards and audit events. Interrupted scans/agents leave durable reconciliation-required receipts and cannot be blindly retried.

Pre-submission preparation retains its inert original identity/state, not an invented submitted transaction. Unknown submitted execution stays unknown/reconciliation-required, retains immutable hashes and cannot erase exposure. Leases and retry bounds survive restart; no order is resubmitted. DEMO memory/paper ledgers remain intentionally session-only. This is transaction/coroutine/fresh-process recovery evidence, **not an OS power-loss or multi-host deployment certification**. Exact scenario references: [hardening matrix](evidence/PHASE_16_HARDENING_MATRIX.json).

## Replay and real evidence

The existing offline research pipeline ran twice in fresh processes, writing only a temporary research store. Both complete outputs—including dataset/implementation/run identities and the saved artifact—were identical.

- **122** existing real token records; **7,336** unique primary raw bars.
- Ondo: 4,546 historical candles, March 3–October 5, 2026; BStock: 2,805, June 12–October 6. Counts include retained source coverage; experimental secondary data is not promoted to primary authority.
- **2,143 equity bars**: 1,921 one-minute and 222 five-minute, March 6–October 5.
- **48 candidate episodes / 31 candidate openings**; 48 post-hoc outcomes available.
- **0 qualifying baseline / 0 qualifying opening-model / 0 analogues / 0 predictions**.

All 48 candidates fail required as-of ratio, calendar-version, known prior-close/token-metadata and feature checks. Overlapping rejection counts are not independent episodes. Historical chart availability does not prove information was known at decision time; today's ratio was never backfilled. Synthetic controls test future prices/opens/news/corporate-action proofs/analogues/scorecards/outcomes exclusion and deterministic replay, but are not real calibration samples. **30/30/3 remains blocked**, with no predictive-quality claim. [Real replay evidence](evidence/PHASE_16_REPLAY.json).

## Contracts, simulation and security

Current official [RWA documentation](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/rwa-data) was checked for `keyword` search and GET price parameters. [Market documentation](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/general-data) confirms POST price arrays and GET candle/trade parameters. [Trading documentation](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/trading-api) was checked for smallest-unit amounts, provider execution mode, short quote lifetime, actual vendor/typed-data binding, immutable UUID retries and terminal RFQ status. [Transaction documentation](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/transaction-api) requires the matching chain-specific payload; BSC simulation binds chain 56 and exact EVM fields. No supported-scope contract change was needed. This was targeted current-document review, not an exhaustive OpenAPI diff or authenticated entitlement test. [Contract evidence](evidence/PHASE_16_CONTRACTS.json).

The documented SQLite shared-connection behavior informed the narrowly scoped ownership fix; concurrent transaction interference was demonstrated locally, not inferred solely from [SQLAlchemy documentation](https://docs.sqlalchemy.org/en/21/dialects/sqlite.html).

Tests reject changed destination/calldata/value/sender/chain/token/amount/route/quote/vendor/fingerprint, unsafe allowances/effects, malformed/partial inputs, stale quotes and mismatched approvals. Requote requires rebuild/resimulation. RFQ known identities cannot be replaced by wallet evidence; complete bound terminal settlement is required. Contradictions remain UNKNOWN, provider/runtime failures cannot create confirmation, and partial/unknown fills cannot incorrectly reduce exposure.

Actual SWAP economic decoding/gas/nonce/state equivalence, RFQ final-settlement simulation and Agentic Wallet runtime remain unverified and **live gates remain blocked**. Synthetic PASS does not certify them. Failure injection covers HTTP 401/403/404/429/500/503, timeouts, malformed JSON/schema drift/missing fields, stale/unavailable sources, simulation failure, quote expiry and contradictory settlement. Failures produce refusal/unavailable/unknown states rather than financial zeroes or invented success.

Security verification includes log/secret isolation, external text/prompt injection, strict agent outputs/call bounds, Host/Origin/proxy/local MCP restrictions, no arbitrary tools/routes/chains/wallet methods, LIVE activation refusal, React text escaping and safe backend response rendering. External content remains data; neither LLM nor caller controls hard policy.

## Performance and browser evidence

Seven warm measured samples per deterministic path, monotonic clock, nearest-rank p95; with seven samples, p95 is the maximum, not an SLA. Synthetic temporary inputs; no provider/network latency or speculative optimization/caching.

| Path | Median / p95, ms |
|---|---:|
| Asset discovery | 0.007 / 0.011 |
| Issuer comparison | 1.383 / 1.720 |
| Trust calculation | 14.589 / 15.791 |
| Shared route evaluation | 0.180 / 0.208 |
| Portfolio evaluation | 5.165 / 5.231 |
| Scorecard query | 163.886 / 185.544 |
| Audit query | 165.507 / 187.525 |
| Terminal API | 22.953 / 44.112 |
| Agent API tool | 9.038 / 9.220 |
| Opportunity universe 10 | 32.273 / 55.734 |
| Opportunity universe 25 | 76.960 / 103.217 |
| Opportunity universe 50 | 207.050 / 231.324 |
| Opportunity universe 100 | 706.271 / 711.515 |

Repeated scorecard/audit projection and large-universe preparation are the main local costs. No arbitrary performance gate was invented. Existing HTTP/provider/agent timeouts and cardinality limits remain enforced. [Performance evidence](evidence/PHASE_16_PERFORMANCE.json).

Built Chrome verification passes **36 workspace journeys** at desktop 1440px, mobile 390px and tablet 768px, all six desktop/mobile DEMO scenarios, existing Terminal/Scorecard/Agent API flows, ordinary Overview and blocked-plan smoke. **180 local API requests**, zero external browser requests, zero runtime exceptions/page overflow, no real execution. The separate actual SDK stdio subprocess passes all seven tools and original-decision retry (**8 calls**). [Browser](evidence/PHASE_16_BROWSER.json), [MCP](evidence/PHASE_16_MCP.json).

Across 24 navigations, backend-connected readiness median/p95 is **215.244/229.372 ms**. Across 36 workspace marks, cumulative journey median/p95 is **797.898/1,591.706 ms**. These local measurements include automation waits and a deliberate 150ms workspace loading-state delay; they are not isolated operation or production latency promises. Browser navigation event timings are retained separately.

## Test-quality findings

No broad `pytest.raises(Exception/BaseException)` assertions, xfails or new skipped tests were found. One inherited real-artifact test conditionally skips on a portable checkout lacking its uncommitted local artifact; that artifact was present here, so the test ran and **actual skips = 0**. It remains conditional rather than being mislabeled universally available.

Important tests assert persisted identities/quantities, generation/fingerprint changes, absence of dispatch/execution calls and exact rejection reasons. Before/after failing probes demonstrate that the new safeguards are exercised. Existing generic ValueError assertions and extensive offline fixtures are still present; this is not exhaustive mutation testing or provider certification. Synthetic execution/CLI/settlement fixtures remain explicitly synthetic and cannot unlock a gate.

## Release-candidate checklist

Statuses describe current capability and verified scope, not merely test results:

| Item | Status | Scope / limitation |
|---|---|---|
| Startup / configuration | PASS | Local startup and fail-closed settings |
| Data | PARTIAL | Adapters pass; real entitlement/alignment/as-of gaps |
| Trust | BLOCKED | Required real evidence unavailable |
| Agents | PASS | Bounded non-live interpretation only |
| Opportunity | BLOCKED | Production blocked by Trust and input assembly |
| Routing | PARTIAL | Production-capable architecture; provider partial |
| Risk | PARTIAL | Guards pass; complete real funding/inventory unavailable |
| Quote | PARTIAL | Offline contracts/expiry; real verification incomplete |
| Simulation / wallet / execution | BLOCKED | Actual equivalence/runtime unverified; no execution |
| Positions | PASS | Tested durable non-live lifecycle/recovery |
| Portfolio | PARTIAL | Non-live planning passes; real inputs/execution blocked |
| Scorecard / audit | PASS | Existing recorded scope; missing truth withheld |
| Agent API/MCP | PASS | Local-only seven tools; no remote auth claim |
| Frontend / security / concurrency / restart | PASS | Recorded test scope and explicit operational limits |
| Replay | PARTIAL | Determinism passes; qualifying real coverage blocked |
| Performance | PASS | Required local measurements, no SLA claim |
| Deployment readiness | BLOCKED | No deployment/Phase 17/18; non-live development RC only |

The [machine-readable checklist](evidence/PHASE_16_HARDENING_MATRIX.json) lists each of the 24 required items separately.

## Unchanged gates and remaining blockers

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

**Routing architecture = PRODUCTION-CAPABLE; provider verification = PARTIAL; live execution = BLOCKED.** Remaining blockers: independent current-equity entitlement/alignment; authoritative executable-market liquidity and complete news; historical ratio/as-of/calendar evidence and real 30/30/3 coverage; complete real-input/funding/host assembly; actual SWAP/RFQ simulation/settlement equivalence; verified Agentic Wallet runtime/session/quotas. Operational limits include local-only MCP, operator resolution of pending receipts, bounded catalogs, session-only DEMO ledgers and a host-invoked monitor rather than an installed continuous scheduler. These were preserved, not fabricated away.

No live signing/execution/broadcast, real RFQ submission, wallet mutation or funds movement occurred. No production financial logic/threshold/gate was changed. No deployment, commit, push or Phase 17/18 work. **Stop after Phase 16.**

## Exact files changed

- `README.md`
- `backend/app/database.py`
- `backend/app/repositories/opportunity_scan.py`
- `backend/app/services/position.py`
- `backend/tests/integration/test_hardening.py`
- `backend/tests/unit/test_portfolio.py`
- `frontend/src/services/api.ts`
- `frontend/src/services/contracts.ts`
- `frontend/src/test/Hardening.test.ts`
- `scripts/benchmark-hardening.py`
- `scripts/check-frontend-phase15.mjs`
- `scripts/check-mcp-hardening.py`
- `scripts/check-security.py`
- `scripts/verify-frontend-phase15.py`
- `docs/PHASE_16_REPORT.md`
- `docs/evidence/PHASE_16_VERIFICATION.json`
- `docs/evidence/PHASE_16_BROWSER.json`
- `docs/evidence/PHASE_16_MCP.json`
- `docs/evidence/PHASE_16_PERFORMANCE.json`
- `docs/evidence/PHASE_16_REPLAY.json`
- `docs/evidence/PHASE_16_CONTRACTS.json`
- `docs/evidence/PHASE_16_HARDENING_MATRIX.json`
