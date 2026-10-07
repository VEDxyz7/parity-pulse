# Master Phase 8 — Safety and Execution

Date: 2026-10-08 (project timezone Asia/Kolkata).

**PHASE_8_IMPLEMENTATION=PASS. Live execution remains unavailable. Phase 9 was not started.**

The sole authoritative `docs/MASTER_SPEC.md` was read completely, lines 1–5321, before coding. SHA256: `f69a9bd01a622c001c3ec6cb654e00562f6b3d03a8310f9e5ccf68efe4b49c84`. Starting checkpoint: `e927501`, the pushed Phase 7 implementation. The working tree was clean. No commit was made.

## Audit and reuse

The existing deterministic RiskEngine already enforced synthetic position/cash/portfolio/liquidity/stress/daily-loss caps, confidence, fees, slippage, freshness and cooldown. Phase 7 had extracted shared `position_caps` and added neutral `OpportunityRiskContext`. Those rules, existing calls and calculations are preserved.

Existing QuoteService, TransactionBuilder and SimulationService describe the isolated DEMO request manifest and local constraints, not executable Binance transactions. Those services and the complete paper lifecycle remain unchanged. Existing issuer routing, Trust, research, candidate ranking, six agents, tools and production gates remain unchanged. Phase 8 adds distinct typed provider execution contracts to avoid falsely treating a DEMO manifest as an EVM transaction.

Missing before this phase: provider quote/build/simulation adapters; funding/base-unit checks; exact SWAP/RFQ and approval bindings; execution fingerprints; durable execution attempts and transition guards; confirmation handling; bounded status reconciliation; and the fail-closed gateway.

## Architecture and integration

```text
Existing discovered representation / Phase 7 scan
  → host-supplied validated execution evidence
  → existing RiskEngine + shared position_caps
  → FundingService
  → AggregatorQuoteService / BinanceSafetyClient
  → quote executionMode
  → ExecutionRouteBuilder
  → exact PreparedRoute fingerprint
  → provider ExecutionSimulationService
  → approval analysis / separate approval simulation if required
  → exact external allowance confirmation / rebuild and resimulate
  → explicit user confirmation when PROPOSE_ONLY
  → DryRunExecutionGateway → STOP
```

`SafetyExecutionService.prepare_scan` binds the existing Phase 7 mandate, decision identifier and proposed size. Current real scans cannot pass the blocked Trust/Opportunity prerequisites. Existing `demo:*` representations cannot be converted to real EVM addresses; they continue using the existing local DEMO flow. No second Trust, Opportunity, issuer router or agent engine was added.

FastAPI constructs the execution store and host-only safety service during its lifecycle. A Binance safety client is constructed **only in LIVE_READ_ONLY data mode**. DEMO startup creates no real client; its original pipeline stays offline. No public execution/confirmation endpoint, frontend change or execution agent tool was added. A future verified worker must provide authoritative wallet/evidence inputs; API callers cannot inject them today.

Normal applications persist the separate journal under `data/execution/phase8/execution.sqlite`. DEMO runtime, test configuration and in-memory applications use an isolated in-memory journal. This directory is ignored by Git. Production observations/baselines are not written by these services or tests.

## 1. Deterministic Risk hard controls

`RiskEngine.evaluate_execution` reuses existing `position_caps`; it does not infer user risk or scale size by confidence. It independently checks budget and cost-inclusive stress, position/portfolio limits, daily losses, trade count, cooldown, wallet/system restrictions, tradability, liquidity floor/p50/participation, confidence, slippage, Opportunity net edge, valid evidence, 120-second freshness and 30-second alignment. Direct Exposure does not require an expected speculative profit, but still requires applicable Trust, funding and execution safety controls.

Production Trust and Opportunity remain blocked for real execution preparation. DEMO Risk PASS is analytical fixture evidence only. The gateway recalculates Risk independently; agents cannot override it. Every decision carries `EX_ANTE_NOT_A_GUARANTEED_MAXIMUM_REALIZED_LOSS`. Existing risk methods and their outputs are preserved.

## 2. Funding checks

USD_NOTIONAL and ONCHAIN_FUNDING_ASSET are separate contracts. Default resolution is exact-symbol USDT/BSC through the existing market search/basic-info provider, optionally pinned to a verified contract. Zero, invented, ambiguous or conflicting contracts fail closed; no funding address is hardcoded.

Required sell units are `ceil(usd_notional / verified_funding_unit_price_usd × 10^decimals)`, using Decimal precision 256 and uint256 bounds. A stablecoin balance is not assumed to equal USD. Identity, token balance, timestamps, conversion verification/cost, native gas balance/reserve and independently supplied native price are required. Conversion cost is included in shared Risk caps and must match funding evidence.

Exact returned gas × gasPrice is converted with the supplied native price. Trade plus approval maximum gas must fit native balance **with the additional untouched native reserve** and the Risk cost reserve. No conversion trade, wallet balance fetch, signer or wallet integration was implemented. Missing authoritative state fails closed.

## 3. Quote contract and lifetime

[Current official Trading API](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/trading-api) and its [published schema](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/1.0.0/schema.json) were reviewed for quote, build, approval and status contracts. Verification is documentation plus synthetic MockTransport contract tests; no authenticated provider probes were made in this phase.

GET `/api/v1/dex/aggregator/quote` sends chain `"56"`, an integer-string smallest-unit sell `amount`, exact discovered sell/buy addresses and user wallet. Supported chains are checked. HTTP/business envelopes and endpoint-specific fields are separately validated. The sole existing signer and bounded/redacted transport are reused. No custom fee, auto-slippage, flash or Solana shortcut is enabled.

Quotes expire at request-start + at most30 seconds, conservatively including network latency. Missing/unknown mode, unknown spender, malformed amounts/metadata, conflicting token marks/decimals, unavailable network fee/price-impact or incompatible costs fail closed.

Vendor ranking is explicit: descending quoted output USD mark value less the documented USD network fee, then vendor/quote ID. It uses the same output-token mark/decimals across candidates. This ranks provider routes for an already selected representation; the existing issuer RoutingService is unchanged. A token mark is never substituted for an independent traditional-equity quote.

Expired quotes produce EXECUTION_EXPIRED. Explicit bounded `requote` revalidates Risk/funding, creates a new generation, clears old route/simulation/approval/consent, obtains a fresh quote, rebuilds, fingerprints and resimulates. It keeps the durable attempt/request ID. It never refreshes a submitted/unknown or already bound RFQ request into another order.

## 4. SWAP builder

GET `/api/v1/dex/aggregator/swap` uses the exact quote request, wallet and quoteId, with explicit slippagePercent and `autoSlippage=false`. Execution mode comes from the quote and must agree with the build response. No issuer→mode map exists.

Router data, amounts, token metadata, vendor, wallet, gas fields, calldata and minimum receive are bound. Exactly one SWAP tx is required; inconsistent RFQ/tx branches are rejected. The supported subset is BSC ERC-20 sells with zero native value and complete legacy fee fields. Mixed legacy/EIP1559 fees, undocumented extras, auxiliary payloads and unsupported spender/router binding fail closed.

The exact provider transaction is retained; calldata is never fabricated. Exact calldata/effect/ABI and gas-sensitive live equivalence still require verified runtime evidence. An adapter is not that evidence.

## 5. RFQ builder and requests

RFQ retains vendor, provider `orderId`, txType, signingScheme, typedDataToSign and exact route/wallet/amount context. The JSON EIP-712 validator checks domain chain/contract, types, fields, primitive values, widths, arrays, nested structures and bounded recursion. Valid opaque hex is retained as uninspectable; it is never called verified typed-data binding.

A host-verified vendor field map can inspect wallet/token/amount/minimum/deadline semantics without assuming vendor field names. This inspection does not prove settlement safety. Missing `rfq.orderId`, inconsistent vendor or unsupported payload blocks preparation. The published `/swap` properties omit orderId while `/order/submit` prose requires it; no replacement ID is invented.

The offline submission contract is exactly POST `/api/v1/dex/aggregator/order/submit`: requestId(UUIDv4), userSignature(65-byte hex), vendor, quoteId=`rfq.orderId`, signingScheme. The platform order ID subsequently used for polling is distinct from the vendor order ID and quote route ID.

A durable UUIDv4 belongs to the attempt. Retries require the same exact request digest, including a hash of the signature-bearing request and route; changed retry payloads are rejected. Actual signatures are not stored or logged. This formats supplied synthetic signatures in tests; it does not sign or verify ownership through a wallet. The transport's submit method always refuses before network I/O.

## 6. ERC-20 approvals

Fresh exact owner/token/spender allowances determine whether approval is needed. Unknown allowances block; sufficient allowances avoid unnecessary approvals. The approval endpoint sends exact token and required smallest-unit approveAmount; vendor is supplied for RFQ and omitted for ordinary SWAP.

Returned approve calldata is decoded and checked for selector, exact spender and exact amount. Infinite/mismatched approvals fail. Approval transactions use the funding token as destination, zero value, returned gas fields and their own route-bound fingerprint and simulation. No spender address or calldata is invented.

Successful approval simulation is not confirmation. A fresh matching external allowance is required. `observe_approval` then obtains a fresh trade quote/build/fingerprint/simulation, invalidating old consent and trade simulation. The previous approval stays in the audit journal. Approval failure/unavailability stops the flow. RFQ approval simulation can be inspected independently while final RFQ settlement remains unavailable and BLOCKED.

## 7. Fingerprint and simulation equivalence

SHA256 over canonical typed JSON covers the quote request/route/identifier/lifetime, chain, mode, token identities/decimals, amounts, wallet, route data, exact transaction bytes, minimum receive, slippage, gas-sensitive fields, RFQ vendor/order/typed payload and allowance context. Approval fingerprints additionally bind the trade fingerprint and exact token/spender/amount/transaction. Mutable copies are revalidated and fingerprints recomputed at boundaries. Any critical change invalidates simulation; timestamps also conservatively invalidate context.

[Current Transaction API](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/transaction-api) accepts chain `"56"` plus exactly one `evmTx{from,to,value,data}`. No Solana/Tron payload is sent. Simulation validates SUCCESS/FAILED, failReason, balance/allowance changes, receipts, mode and payload digest; contradictory, unavailable, expired or failed results cannot pass.

The official simulation body does **not** include returned gas fee/limit fields. Coverage is explicitly `EVM_FROM_TO_VALUE_DATA_ONLY`; `live_equivalence_verified=false` remains enforced even after fixture success. RFQ has `RFQ_SETTLEMENT_UNAVAILABLE` and never receives final-settlement PASS. Thus neither live gate is certified.

## 8. State, persistence and recovery

States distinguish PROPOSAL, RISK_APPROVED, QUOTE_CREATED, ROUTE_BUILT, SIMULATION_PASSED, APPROVAL_REQUIRED, APPROVAL_CONFIRMED, EXECUTION_SUBMITTED, EXECUTION_PENDING, EXECUTION_CONFIRMED, EXECUTION_FAILED, EXECUTION_EXPIRED, EXECUTION_CANCELLED, EXECUTION_UNKNOWN and BLOCKED.

Transition guards require current matching Risk/funding, unexpired quote, exact build/simulation and approval conditions. Illegal skips, clock regression and identity mutation are rejected. EXECUTION_SUBMITTED is unreachable through the Phase 8 state-machine/gateway boundary. PROPOSE_ONLY waits for fingerprint/decision/expiry-bound explicit host confirmation. AUTONOMOUS is modeled only in DRY_RUN and cannot bypass controls; application configuration still refuses autonomous/live startup.

The separate SQLAlchemy/SQLite journal has unique mode+decision ownership, persisted UUIDs, atomic compare-and-swap versions and chained immutable audit snapshots. A losing concurrent worker never calls providers. Snapshot reads validate the journal through the selected version so concurrent append cannot create a false corruption error. Corrupted audits fail closed. Pending/unknown recovered attempts block new preparation; no restart or retry creates a second order.

## 9. Status tracking

Bounded read-only polling supports `/aggregator/order/{platformOrderId}` and `/aggregator/history?binanceChainId=56&txHash=...`. Pending vendor/on-chain, unknown and timeouts remain non-terminal; no poll resubmits or invents an order.

RFQ FILLED requires matching order, sell amount, minimum receive, hash and valid settlement timestamps. FAILED/EXPIRED/CANCELLED retain their separate meanings. SWAP success requires matching chain/hash/sender/router, actual token identities/amounts, minimum receive and documented successful status; a hash, null result or partial/malformed settlement is UNKNOWN. Unknown external attempts cannot be cancelled/expired locally to bypass reconciliation.

Records retain mode/vendor via quote, order ID, tx hash, external status, received quantity in token base units, settlement time and native fee units where returned. Average USD price is left unavailable rather than fabricated. Imported external tracking records do not represent a Phase 8 submission, signature or funds movement; tests label these fixtures explicitly. Actual confirmation/finality mechanisms still need verified live gateway evidence.

## 10. ExecutionGateway and isolation

ExecutionGateway is an abstract boundary with only DryRunExecutionGateway implemented. It independently recalculates Risk, verifies funding/native gas, quote validity, route fingerprint, exact successful simulation, approval, confirmation and mode. It always returns DRY_RUN_STOP_NO_EXECUTION plus current gate blockers. It contains no signer or execution transport.

BinanceSafetyClient allows only explicit quote/build/simulation/approval-build/supported-chain/status reads. Arbitrary URLs, RFQ submit, broadcast, wallet settings, flash and Solana shortcuts are denied before HTTP. The centralized signer likewise refuses mutating/unreviewed/non-build paths. Agents retain their closed read-tool allowlist and cannot invoke the gateway. Existing public execution/approval URLs remain404; frontend cannot bypass the boundary. Secrets, signatures, provider bodies and wallet material never enter logs; only safe IDs/status are logged.

## Verification

Exact final counts and commands are recorded in [PHASE_8_VERIFICATION.json](evidence/PHASE_8_VERIFICATION.json). [Typed safety runs](evidence/PHASE_8_SAFETY_RUNS.json) contain three explicit synthetic protocol cases with durable round-trip checks. [Browser evidence](evidence/PHASE_8_BROWSER.json) proves unchanged desktop/mobile NORMAL, NOISE and INFORMATION paths, the complete paper lifecycle and ordinary Overview behavior. No prior tests were removed or weakened.

- Full backend suite: **846 passed**, including all 707 retained Phase 5/6/7, Trust, routing and paper tests; one existing Starlette/httpx deprecation warning.
- Phase 8 targeted suite: **139 passed**. Tests cover financial limits, funding conversion/native gas, contracts/API authentication signing, dynamic mode, expiry, mutation, simulation failures, RFQ typed data/binding/idempotency/polling, approvals, state skips, terminal semantics, concurrency/restart, prompt injection, secret redaction and mode isolation. No wallet signing occurred.
- Frontend: **173 passed /9 files**; TypeScript/Vite build PASS, unchanged CSS/JS bundle hashes.
- Ruff checks/format, established security audit, dependency compatibility and diff whitespace checks PASS.
- Six desktop/mobile scenarios,39 local API requests, zero DEMO production-Trust calls and zero live execution calls. Disposable backends use memory-only data; only owned test servers are stopped.
- 83 protected historical/spec/data/evidence artifacts remain byte-identical, including the sole master specification.

Two verification findings were corrected without weakening tests: DEMO startup initially constructed a real client (now forbidden by mode), and concurrent/journal reads needed canonical model serialization and version-bounded snapshot validation. A repeated browser run against an already consumed session ledger correctly rejected a duplicate paper lifecycle; the successful run used fresh disposable backends. No production financial or frontend workaround was added.

## Current gates and remaining blockers

```text
PHASE_8_IMPLEMENTATION=PASS
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

Implementation PASS certifies safety machinery and fail-closed contract behavior, **not** authenticated build/simulation entitlements, quote availability, wallet runtime, signing, broadcast, RFQ submission or live readiness. DRY_RUN_GATE retains its prior evidenced scope; fixture simulation is not a production certificate.

Unchanged external blockers: independent equity/live alignment verification, relevant authoritative liquidity, historical as-of ratios and0/30 qualifying baseline,0/30 opening-model,0/3 analogue episodes; verified actual funding/wallet limits; real quote/build/approval/simulation fixtures and permissions; RFQ orderId/schema/vendor semantic bindings and exact final-settlement safety; SWAP ABI/effect/gas/nonce equivalence and actual terminal/finality confirmation; a controlled verified wallet worker/runtime. Unsupported closed-reference preparation, custom/referral fees, taxed tokens, non-BSC/native sells, mixed EIP1559 fees and incomplete critical schemas fail closed rather than being approximated.

No Twelve Data alignment run, provider entitlement probe, history/backfill, signing, real order, broadcast, funds movement, wallet-setting change or live execution occurred. No Phase 9 `baw`, wallet or signing integration was added. The next separately authorized engineering phase is Master Phase 9 — Agentic Wallet, starting with verified read-only runtime/worker capabilities. STOP after Phase 8.

## Files changed

Existing files amended:

- `.gitignore`
- `backend/app/clients/binance_web3.py`
- `backend/app/main.py`
- `backend/app/services/risk.py`
- `backend/app/utils/logging.py`
- `README.md`
- `docs/API_MATRIX.md`
- `docs/ARCHITECTURE.md`
- `docs/EXECUTION_GATES.md`
- `docs/PHASE_MAP.md`

New files:

- `backend/app/clients/binance_trading.py`
- `backend/app/clients/execution_gateway.py`
- `backend/app/models/execution.py`
- `backend/app/repositories/execution.py`
- `backend/app/services/aggregator_quote.py`
- `backend/app/services/eip712_validation.py`
- `backend/app/services/execution.py`
- `backend/app/services/execution_builders.py`
- `backend/app/services/execution_simulation.py`
- `backend/app/services/execution_state_machine.py`
- `backend/app/services/execution_status.py`
- `backend/app/services/funding.py`
- `backend/tests/fixtures/execution_fixtures.py`
- `backend/tests/integration/test_execution_contracts.py`
- `backend/tests/unit/test_execution_safety.py`
- `docs/PHASE_8_REPORT.md`
- `docs/evidence/PHASE_8_SAFETY_RUNS.json`
- `docs/evidence/PHASE_8_BROWSER.json`
- `docs/evidence/PHASE_8_VERIFICATION.json`
