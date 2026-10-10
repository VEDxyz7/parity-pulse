> **Historical teammate proposal — superseded by the PR #1 merge resolution (2026-10-11).**
> The original text below is preserved as history, not as an operational runbook or
> verified capability evidence. LIVE flags, Trust-disable configuration, weekend
> exceptions, Binance-index independent references, signed-bounds-only RFQ admission,
> blind retries and Altana/x402/session grants described below are NOT enabled.
> Current gates, commands and limitations: [PR_1_MERGE_RESOLUTION.md](PR_1_MERGE_RESOLUTION.md).

# Implementation plan: weekend SWAP + RFQ execution

Status: IMPLEMENTED (2026-10-10) except the Monday rollout (§6). Nothing has been executed against
a wallet; no real RFQ payload has been captured yet.
Scope: live wallet rebalancing on BSC mainnet (`PORTFOLIO_INVENTORY=WALLET`). Opportunity mode and the
Phase 8/10 DRY_RUN machinery are out of scope and stay unchanged.

## 1. Background and constraints

**Facts measured on 2026-10-10 (Saturday):**
- Binance quotes for NVDAB and NVDAon currently return `executionMode=SWAP`, vendor LiquidMesh. A
  `/swap` build returns raw calldata that `/pre-transaction/simulate` accepts, so it can be simulated.
- No RFQ route was returned for any of 14 major tickers, at $10 or $1000, in either direction.
  Errors were 40374 (`RWA_INSUFFICIENT_LIQUIDITY`: neither LiquidMesh nor PcsXRfq quoted) and
  some rate limits.
- Ondo catalog status: 306 tokens `closed`, 23 in the weekend `offhours` session (including NVDA,
  AAPL and TSLA). BStock reports `marketStatus=null`, `openState=true`.
- NVDAon's next session opens Mon 2026-10-12 00:05 UTC, which is after the hackathon deadline
  (2026-10-11 12:00 UTC).
- Rate limit: the quote endpoint needs at least about 1.2 s between calls.

**What the Binance docs say** (Trading API integration flow, introduction and error codes):
- Ondo is "always" routed through 3 RFQ vendors: InchFusion, CowSwap and PcsXRfq. BStock gets one
  LiquidMesh SWAP route plus one PcsXRfq RFQ route. xStock gets AMM only.
- The RFQ flow is: `/quote`, then `/approve-transaction?vendor=<vendorName>` (when needed), then
  `/swap`, which returns `rfq.typedDataToSign`. You sign it with `eth_signTypedData_v4` using the
  quote's `userWalletAddress`, then POST `/order/submit` with `{userSignature, vendor,
  quoteId=rfq.orderId, requestId(UUID, reused on retry), signingScheme?}`, then poll
  `/order/{orderId}` until FILLED or FAILED.
- Relevant error codes:
  - 40366 Ondo per-order maker cap
  - 40367 Ondo market not tradable
  - 40369 BStock outside trading hours
  - 40374 no RWA liquidity
  - 40375 Ondo below minimum USD
  - 40401 quote expired
  - 40462 quote/params mismatch
- **Not documented:** the RFQ approval spender, the typed-data structure for each vendor, and any
  way to force a vendor.

**Consequences:**
1. RFQ market makers hedge in the real stock market, so RFQ only quotes during issuer sessions. On
   weekends only on-chain pools (SWAP) quote.
2. No real RFQ payload has been captured. The RFQ verifier is built from each vendor's published
   order format, must fail closed on anything unrecognised, and must capture raw payloads the first
   time it sees one so they can be confirmed when markets reopen.

## 2. Design principles

- **SWAP:** exact pre-trade simulation is required. This is already implemented.
- **RFQ:** the outcome is bounded by verifying the signed order. The EIP-712 order is the only
  authority the vendor receives, and the vendor's settlement contract enforces it on-chain (sell at
  most X, receive at least Y, at receiver R, before deadline D). Verifying the order exactly therefore
  bounds the worst case. Every RFQ leg is labelled `verification=SIGNED_ORDER_BOUND`, never
  "simulated".
- **Fail closed:** unknown vendor, primary type, domain, settlement contract, field or flag means
  refuse and capture the payload for review.
- **No silent fallbacks:** a refused RFQ leg is never retried through a different route without a
  fresh plan.
- **Caps:** closed-underlying legs get half the per-leg cap. All existing caps still apply (notional,
  slippage, daily trade count, daily loss, gas reserve).

## 3. Part A: weekend SWAP (closed-underlying trading)

### A1. Catalog accepts weekend states (bug fix)
- `backend/app/providers/binance.py`, wire `Status.marketStatus`: add `"offhours"`. **Done.**
- `backend/app/models/data.py`, `TokenMetadata.market_state` and `MarketStatus.state` (lines
  152 and 181): add `"offhours"`. **Pending; the earlier edit was rejected.**
- Without these, every Ondo token is rejected from the catalog on weekends.

### A2. Routing policy
- `RoutePolicy.allow_closed_underlying: bool = False`. It is refused for `purpose=OPPORTUNITY`.
  **Done.**
- `RoutingService`: `SESSION_STATES = {regular, premarket, postmarket, open}` and
  `CLOSED_STATES = {offhours, overnight, closed}`. Closed states count as tradable only when the
  policy allows them and the issuer reports `openState=true`, and the route gets the limitation
  `UNDERLYING_MARKET_CLOSED`. **Done.**

### A3. Portfolio and config
- `PortfolioService(allow_closed_underlying=...)`: allowed only with `inventory=WALLET` and passed
  into `RoutePolicy`. **Done.**
- `Settings.closed_market_swap: bool = True` (applies only in WALLET mode). **Done.**
- `main.py` wiring. **Done.**

### A4. Caps
- Live source: the per-ticker risk template uses `max_position_usd = cap/2` when the chosen
  representation is closed, and records the note `UNDERLYING_MARKET_CLOSED_<T>`. **Done.**
- Executor: per-leg cap is `cap/2` when the selected route's `market_state` is closed. **Done.**
- Executor: a closed-underlying leg may use SWAP routes only. Implemented as part of B4.

### A5. Freshness on weekends (open issue, to be measured)
- The live weekend plan for NVDAB failed `DATA_FRESHNESS`. The token price timestamp was about 37 s
  old at capture. The suspected cause is capture latency (several quotes at 1.2 s spacing) pushing
  the token, equity or evidence timestamps past 120 s by the time the plan is evaluated.
- Action:
  1. Log the token, equity and evidence timestamps against the plan time in a weekend run.
  2. If capture latency is the cause, take the RWA prices last (just before returning) and reduce the
     probe quotes to one per representation.
  3. Do **not** relax the 120 s rule.
- The equity index stays fresh on weekends, but its value reflects a closed market. The UI and
  parity output must label it `UNDERLYING_CLOSED_REFERENCE`.

### A6. Tests (A)
- Closed state is rejected when the policy is off. With the policy on, the closed state is accepted
  with the `UNDERLYING_MARKET_CLOSED` limitation.
- An `OPPORTUNITY` policy with `allow_closed_underlying` raises.
- The portfolio constructor raises if closed-underlying trading is enabled without WALLET inventory.
- Closed-route leg above `cap/2` gives `LIVE_NOTIONAL_CAP`.
- The catalog parses an `offhours` row; regression fixture from the 2026-10-10 NVDAon payload.

## 4. Part B: RFQ execution

### B1. Wire models (tolerant parsing, strict verification)
- `RFQPayload` in `models/execution.py`:
  - accept `typedDataToSign` as a JSON string **or** an object (normalise to a canonical JSON
    string);
  - `signingScheme`: accept the case-insensitive values `eip712`, `ethsign`, `eip1271`;
  - unknown extra fields are ignored but kept in the captured raw payload.
- `RFQSubmission.signingScheme`: the same set, optional. The signature may be 65 bytes (EOA) or
  variable length (EIP-1271, e.g. Altana's 98 bytes).
- `RFQStatus.status`: map the known statuses `PENDING_VENDOR`, `PENDING_ONCHAIN`, `FILLED`,
  `FAILED`, `EXPIRED`, `CANCELLED`. Anything else becomes `UNKNOWN` and is never success.

### B2. Order decoder and verifier: `backend/app/services/rfq_orders.py` (new)

Input: `typed` (EIP-712 dict), the expected leg `{side, sell_token, sell_amount_max, buy_token,
min_buy, wallet, now}`, and the settlement allowlist.
Output: `VerifiedOrder{vendor, order_hash, settlement, sell_token, sell_amount, buy_token,
min_buy_to_wallet, deadline, fees, warnings}` or `RFQRejected(code)`.

Common steps:
1. Run the existing structural check (`validate_typed_data`), with chainId = 56.
2. Compute the EIP-712 digest with `eth_account.messages.encode_typed_data`. This is journaled as
   `order_hash` and used for signature recovery.
3. Dispatch on `(domain.name, primaryType)`. Anything not in the table below is rejected with
   `RFQ_ORDER_TYPE_UNRECOGNIZED` and the payload is captured.

Vendor rules:

| Check | CowSwap: GPv2 `Order` | 1inch Fusion: LOP v4 `Order` | PancakeSwap X: Permit2 `PermitWitnessTransferFrom` |
|---|---|---|---|
| Domain / settlement | `name="Gnosis Protocol"`, `verifyingContract` in allowlist (default GPv2Settlement `0x9008D19f58AAbD9eD0D60971565AA8510560ab41`) | `name="1inch Aggregation Router"`, `verifyingContract` in allowlist (default router v6 `0x111111125421cA6dc452d289314280a0f8842A65`) | `name="Permit2"`, `verifyingContract=0x000000000022D473030F116dDEE9F6B43aC78BA3`; `message.spender` must equal `witness.info.reactor`, and that reactor must be in the allowlist (**no default; set after the first capture**) |
| Owner / receiver | `receiver` is 0x0 (means the owner) or the wallet | `maker` = wallet; `receiver` is 0x0 or the wallet | `witness.info.swapper` = wallet; every output to the buy token has `recipient` = wallet |
| Sell side | `sellToken` = plan sell token; `sellAmount + feeAmount` ≤ plan max | `makerAsset` = sell token; `makingAmount` ≤ plan max | `permitted.token` = sell token; `permitted.amount` ≤ plan max; input max(start, end) ≤ `permitted.amount` |
| Buy side minimum | `buyToken` = buy token; `buyAmount` ≥ plan min | `takerAsset` = buy token; `takingAmount` ≥ plan min (signed floor) | Sum of min(start, end) over outputs to the wallet in the buy token ≥ plan min. Outputs to others are fees, journaled, and must be ≤ 1% of output. |
| Kind / fill | `kind="sell"` (buy orders rejected); `partiallyFillable=false` | `makerTraits` NO_PARTIAL_FILLS bit set | n/a (single fill) |
| Deadline | `validTo` ≤ now + 600 s and > now | expiration (bits 80–119 of `makerTraits`) ≤ now + 600 s and nonzero | `deadline` and `witness.info.deadline` ≤ now + 600 s |
| Code paths | `sellTokenBalance=buyTokenBalance="erc20"`; `appData` journaled (hooks run from the HooksTrampoline and cannot spend the owner's funds beyond the order) | pre/post-interaction bits: journaled; allowed only with the extension present and receiver = wallet (Fusion uses them for the auction and resolver logic) | `additionalValidationContract` = 0x0 |
| Approval spender | GPv2VaultRelayer (allowlist, default `0xC92E8bdf79f0507f65a392b0ab4667716BFE0110`) | the router itself | Permit2 |

- The allowlist comes from config `RFQ_SETTLEMENT_ALLOWLIST` (comma-separated `vendor:address`),
  with the defaults above. An address missing from the list is rejected with
  `RFQ_SETTLEMENT_NOT_ALLOWLISTED` and the payload is captured. The operator verifies the address on
  BscScan and adds it; that's a one-time step for PcsXRfq on Monday.
- The addresses in the table are taken from the vendors' public deployments and must be re-checked
  on BscScan before the first live order. They are not assumed correct.

### B3. Payload capture (first-sight learning)
- New table `rfq_captures` in `live_fills.sqlite` with columns `captured_at, vendor, primary_type,
  domain, verifying_contract, typed_json, verdict, reason`.
- Every RFQ `/swap` response is captured whether or not it is accepted, and also in read-only mode
  (a planning-time capture). This guarantees real payloads on Monday even if execution refuses
  them.
- New endpoint `GET /api/live/rfq/captures`, read-only, last 50.

### B4. Executor: RFQ branch (`services/live_execution.py`)

Route choice per leg:
1. Get all quotes. Keep SWAP routes that have an `approveTarget`, and RFQ routes from known
   vendors.
2. If the underlying is closed, use SWAP only.
3. Otherwise pick the higher `toTokenAmount`. Ties go to SWAP, because exact simulation beats a
   bound.

RFQ leg steps:
1. **Bounds:** price impact ≤ cap; quoted output ≥ plan minimum. The same checks as SWAP.
2. **Approval:**
   - Call `GET /approve-transaction?vendor=<vendorName>&...`. The returned spender must equal the
     vendor's expected spender from B2.
   - Approve the **exact** amount only. Simulate, send, wait for the receipt, read back the
     allowance (the existing approval path).
   - For PcsXRfq, approving Permit2 for the token is enough; the signed permit authorises the
     transfer.
3. **Build:** `/swap` gives `rfq`. Capture it (B3), then verify it (B2) against the plan bounds.
4. **Sign:** `signer.sign_typed_data(typed)` returns the signature. For EOA signers, recover the
   signer from `order_hash` and require it equals the wallet.
5. **Submit:** create the `requestId` (UUIDv4) and journal it **before** the POST. Then POST
   `/order/submit`. A retry reuses the same `requestId`; the same leg never gets a new one.
6. **Poll:** call `/order/{orderId}` every 2 s, for up to 120 s.
   - FILLED: go to settle.
   - FAILED, EXPIRED or CANCELLED: the leg is `NOT_FILLED`. No funds moved. Reset the exact
     allowance to 0 (revoke) and stop the plan.
   - Timeout: the leg stays `SUBMITTED` and is reconciled later.
7. **Settle:**
   - Get the receipt for `txHash` (status 1) and diff the wallet's balances.
   - Require spent ≤ signed sell maximum and received ≥ signed minimum.
   - Best effort: decode the vendor's fill event (GPv2 `Trade`, LOP `OrderFilled`, reactor `Fill`)
     and match the order hash or UID.
   - Then mark `CONFIRMED`. Any mismatch gives `RECONCILIATION_REQUIRED`, and the plan halts.
8. **Journal fields:** `verification`, `vendor`, `order_hash`, `order_id`, `request_id`, the decoded
   order, fill event and amounts.

Reconcile path (rerun or restart):
- A journaled RFQ leg is never re-signed or re-submitted.
- If it has an `order_id`, poll its status.
- If it has a `request_id` but no `order_id` (crashed mid-submit), resubmit with the **same**
  `requestId`. The POST is idempotent for 30 minutes, which the docs state, so the same body is
  safe.
- Older than 30 minutes: mark `RECONCILIATION_REQUIRED`.

Plan-level rule: a plan with any RFQ leg in `SUBMITTED` / `PENDING` cannot be marked `EXECUTED`.

### B5. Binance client (`clients/binance_trading.py`, `clients/binance_web3.py`)
- Add `POST /api/v1/dex/aggregator/order/submit` to `SAFETY_PATHS`. That path is already a safety
  path, so request signing accepts it.
- `submit_rfq(submission)` replaces the stub that raises `RFQ_LIVE_GATE_BLOCKED`. It runs only when
  the client is constructed with `allow_submit=True`, which is set only by the live wiring under the
  full live opt-in. The response is validated.
- `rfq_approval(quote, vendor)` wraps `/approve-transaction` with the `vendor` parameter.
- Map Binance business codes to journal reasons (40366 / 40367 / 40369 / 40374 / 40375 / 40401 /
  40462).

### B6. Signers (`services/live_signer.py`, `agentic_wallet_signer.py`, sidecar)
- **LocalKeySigner.sign_typed_data:** `Account.sign_typed_data(full_message=typed)`, recovered and
  checked.
- **AgenticWalletSigner.sign_typed_data:** use the `baw` EIP-712 sign command documented in
  binance-skills-hub `references/external-sign.md`. **The exact command must be read from that doc
  before implementing.** If it can't be verified, the method raises
  `RFQ_SIGNING_UNSUPPORTED_BY_SIGNER` and the executor falls back to SWAP only. Never guess the CLI.
- **AltanaSigner.sign_typed_data:** new sidecar route `POST /altana/sign-typed-data` that calls
  `client.signOrderTypedData` and returns an EIP-1271 signature.
  - Requires that `approveSignatureChecker` was called once for the vendor's settlement contract.
    `grant-session.mjs` gains `--approve-checker <addr>`.
  - Submitted with `signingScheme=eip1271`.
  - Allowed for CowSwap only, because its EIP-1271 support is documented. Other vendors with Altana
    are rejected with `RFQ_VENDOR_REQUIRES_EOA`.

### B7. API and UI
- `GET /api/live/rfq/captures`.
- Each execute-response leg includes `verification` and a decoded order summary.
- Live page:
  - The journal gets columns for verification (`EXACT_SIMULATION` / `SIGNED_ORDER_BOUND`), vendor
    and order ID.
  - New "RFQ captures" panel: vendor, primary type, settlement contract, verdict and reason.
  - Before executing, a plan preview shows that RFQ legs are possible and that settlement is
    order-bound, not simulated.

### B8. Tests (B)

Fixtures are built from the vendors' published formats. They are synthetic and labelled as such.
- **Verifier, accepted:** a valid order per vendor, with the expected amounts and hash.
- **Verifier, rejected** (one test per rule):
  - wrong receiver, swapper or recipient;
  - output below the minimum;
  - sell amount above the maximum;
  - deadline too long or already expired;
  - partial fill allowed;
  - CoW buy order or non-erc20 balance;
  - PcsX non-zero `additionalValidationContract`;
  - Permit2 spender ≠ reactor;
  - settlement not on the allowlist;
  - wrong chain;
  - unknown primary type or domain;
  - fee output above 1%;
  - extra unknown message field.
- **Executor RFQ:**
  - happy path: approve, sign, submit, FILLED, CONFIRMED;
  - EXPIRED gives NOT_FILLED plus a revoke;
  - FILLED but received below the minimum gives `RECONCILIATION_REQUIRED`;
  - crash after the `requestId` is journaled: resubmit with the same `requestId`, never a new one;
  - closed underlying never uses RFQ;
  - tie goes to SWAP;
  - every refused payload is captured.
- **Signers:** local key recovers to the wallet; `baw` unsupported raises; the Altana route is
  CowSwap-only.
- **Client:** `submit_rfq` refused unless `allow_submit`; business codes are mapped.
- **Boundary test updates:** the new POST path (live only), and the live routes stay gated on
  WALLET.

## 5. Order of work and estimates

| Step | Work | Est. |
|---|---|---|
| 1 | A1 data enum fix, A5 freshness measurement and fix, A6 tests | 1.5 h |
| 2 | B1 wire models, B5 client (submit, approval, codes) | 1.5 h |
| 3 | B2 verifier, PcsXRfq first, then CowSwap, then 1inch, with B8 verifier tests | 4–5 h |
| 4 | B3 capture table and endpoint | 0.5 h |
| 5 | B4 executor RFQ branch, reconcile, B8 executor tests | 3 h |
| 6 | B6 signers: local key, then Altana; `baw` only if its doc confirms the command | 1.5 h |
| 7 | B7 API/UI, regenerate frontend contracts | 1.5 h |
| 8 | Full backend/frontend suites, graphify update, docs (`LIVE_REBALANCE.md`) | 1 h |
| **Total** | | **about 14–16 h** |

If time runs short, cut 1inch first, then CowSwap. PcsXRfq is the only RFQ vendor seen in Binance's
BSC error text, so it comes first. The executor refuses any vendor without a verifier
(`RFQ_VENDOR_VERIFIER_NOT_IMPLEMENTED`).

## 6. Rollout: Monday 2026-10-12 after 00:05 UTC
1. Start the backend in read-only WALLET mode and run a plan for an Ondo ticker. The RFQ `/swap`
   payloads land in `rfq_captures`.
2. Compare the captured payloads against the B2 table. Fix field mappings if they differ, and add
   real fixtures to the tests.
3. Verify each reported settlement or reactor address on BscScan and add it to
   `RFQ_SETTLEMENT_ALLOWLIST`.
4. Enable live execution with a small cap, e.g. $10, and execute one RFQ leg.
5. Confirm the order status, receipt, balance diff and fill event, then raise the cap.

## 7. Risks and open questions
- **Payload format unknown until Monday.** Mitigation: fail closed, capture on first sight, keep the
  verifier table data-driven.
- **PcsXRfq reactor address unknown.** It's operator-allowlisted after on-chain verification. There
  is no default.
- **Fusion auction semantics.** The signed `takingAmount` is assumed to be the floor. This must be
  confirmed against the LOP v4 and Fusion extension before 1inch is enabled.
- **`baw` EIP-712 signing command unverified.** The `AGENTIC_WALLET` signer is SWAP-only until it's
  confirmed.
- **Altana EIP-1271 acceptance** is assumed for CowSwap only. Unverified on BSC.
- **Weekend parity reference.** The index is fresh but the market is closed; the parity output
  labels it.
- **Deadline.** The submission (2026-10-11 12:00 UTC) can include the verifier, capture path, tests
  and the working weekend SWAP. A real RFQ fill can only happen after Ondo reopens.
- **Out of scope:** Opportunity RFQ, Phase 8/10 DRY_RUN RFQ, autonomous scheduling, and any change
  to the 120 s freshness or the Trust policy.
