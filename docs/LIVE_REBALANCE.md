> **Historical teammate proposal — superseded by the PR #1 merge resolution (2026-10-11).**
> The original text below is preserved as history, not as an operational runbook or
> verified capability evidence. LIVE flags, Trust-disable configuration, weekend
> exceptions, Binance-index independent references, signed-bounds-only RFQ admission,
> blind retries and Altana/x402/session grants described below are NOT enabled.
> Current gates, commands and limitations: [PR_1_MERGE_RESOLUTION.md](PR_1_MERGE_RESOLUTION.md).

# Live wallet rebalancing on BSC mainnet

Parity Pulse rebalances a wallet of tokenized US stocks (Ondo Global Markets and bStocks on BSC)
toward configured target weights. Holdings are read from chain, and every leg is quoted, simulated,
capped and reconciled before it counts.

The Trust classifier is parked. Rebalancing plans on cost, liquidity, risk and freshness alone, and
each route is labelled `TRUST_NOT_EVALUATED`. The Opportunity path still requires Trust.

## What runs on a live leg

1. **Plan.** `POST /api/portfolio/plans` reads the inputs below.
   - Balances: on-chain `balanceOf` for USDT and each stock token, plus the native BNB balance (BSC RPC).
   - Marks: token prices and share ratios from Binance `rwa/tokens` and `rwa/price`.
   - Costs: a Binance aggregator quote at the trade-size cap.
   - Liquidity: Binance pool reserves when reported, otherwise executable depth proved by a quote
     several times the cap that stays within the slippage limit.
   - Parity: an independent equity reference from the Binance USD-M equity index (`fapi/v1/premiumIndex`,
     a multi-vendor index with a millisecond timestamp). Any representation that deviates more than
     3% from it blocks the plan.

   The existing `PortfolioService` computes drift, actions, `RiskEngine` checks and aggregate caps.
2. **Execute.** `POST /api/live/plans/{plan_id}/execute` runs each action in priority order, sales first.
   - Gets a fresh quote. Only `SWAP` routes are accepted, so RFQ is never signed.
   - Checks price impact against the slippage cap and checks the output against the plan minimum.
   - Approves the exact amount when needed, never unlimited. The approval is simulated by Binance,
     sent, confirmed, and the new allowance is read back.
   - Builds the swap. The sender, router and value must match, and `minReceiveAmount` must meet the
     plan minimum.
   - Requires a Binance `/pre-transaction/simulate` SUCCESS whose simulated receive amount meets the
     minimum.
   - Checks native gas plus a reserve, then signs and sends.
   - Waits for the receipt (`status=1`) and reconciles by diffing on-chain balances.
3. **Journal.** Each leg is one durable row in `live_fills.sqlite`, recording the quote, transaction
   hashes, simulated and actual amounts, and the realized cost against the plan mark. A journaled leg
   is never sent again; on a rerun it is only reconciled.
4. **Settle.** When every leg is `CONFIRMED`, the plan becomes `EXECUTED`. The next evaluation reads the
   new balances and should show the portfolio within its bands.

## Turning it on

Read-only planning against a real wallet sends nothing:

```
DATA_MODE=LIVE_READ_ONLY PORTFOLIO_INVENTORY=WALLET LIVE_WALLET_ADDRESS=0x...
TRUST_REQUIRED_FOR_REBALANCE=false
```

Live execution needs all of the following, or startup is refused:

```
EXECUTION_MODE=LIVE LIVE_TRADING_ENABLED=true RUNTIME_MODE=LIVE DATA_MODE=LIVE_READ_ONLY
PORTFOLIO_INVENTORY=WALLET LIVE_MAX_NOTIONAL_USD=25          # hard per-leg cap, <= 1000
LIVE_SIGNER=LOCAL_KEY LIVE_SIGNER_PRIVATE_KEY=0x...          # dev wallet only
```

Fund the wallet with USDT plus about 0.005 BNB for gas, set targets on the Autopilot page, then use
**Live rebalance** to plan and execute.

## Signers

| `LIVE_SIGNER` | Custody | Spending limits enforced by |
|---|---|---|
| `LOCAL_KEY` | Dev EOA key in `.env` | Parity Pulse caps only |
| `AGENTIC_WALLET` | Binance Agentic Wallet (MPC, `baw` CLI 1.10.0) | Daily limit, token allowlist and abnormal-transaction rules set in the Binance App, plus Parity Pulse caps |
| `ALTANA` | BNB Agent Studio Altana smart wallet session key | On-chain session permissions (router and approve allowlist, daily USDT and BNB caps, expiry), plus Parity Pulse caps |

`AGENTIC_WALLET` runs `baw contract-call preview`, which is the wallet-side simulation, and then
`contract-call execute`. Transactions that need App confirmation are refused rather than left
waiting. Setup is `npm i -g @binance/agentic-wallet@1.10.0`, then `baw auth signin`, then approve in
the App. The CLI output field names come from the skill docs and must be checked with
`baw cli-check` before a live run.

`ALTANA` goes through the sidecar in `sidecar/agent-studio` (see its README).

## Sidecar: BNB Agent Studio

`sidecar/agent-studio/server.mjs`, localhost only:

- `POST /altana/execute` runs one call through the scoped Altana session. It needs the
  `x-sidecar-token` header.
- `GET /x402/parity/:ticker` is a paid endpoint using the x402 (B402 v2) protocol, paid in U
  (EIP-3009) or USDT (Permit2) on BSC. Agent Studio buyers (`bag x402 buy`) and Altana
  `fetchWithX402` can pay it. It returns `/api/live/parity/{ticker}`: each representation's price per
  share and its deviation in basis points from the equity index.
- `grant-session.mjs` creates the Altana wallet and grants the session. With `--register-agent` it
  also mints an ERC-8004 identity whose card advertises the x402 endpoint.

## Weekend / off-hours

When the underlying market is closed (Ondo `offhours`/`closed`, `overnight`), rebalancing may still
swap on on-chain pools (`CLOSED_MARKET_SWAP=true`): SWAP routes only, half the per-leg cap, route
labelled `UNDERLYING_MARKET_CLOSED`. The equity index stays fresh but reflects a closed market.

## RFQ legs

RFQ (Ondo/bStock market makers: PancakeSwap X, CowSwap, 1inch Fusion) is used only when it beats
the best SWAP route and the underlying is in session. Settlement is relayed by the vendor and
cannot be simulated, so each order is verified instead (`services/rfq_orders.py`,
`verification=SIGNED_ORDER_BOUND`): receiver/swapper = wallet, sell ≤ plan, signed minimum output ≥
plan minimum, deadline ≤ 10 min, no partial fills, no extra validation hooks, settlement contract
on the allowlist. Then: exact approval to the vendor's known spender (cross-checked with Binance),
sign, recover, journal the `requestId` + signature, `/order/submit`, poll, and settle only if the
on-chain receipt and balance diff stay inside the signed bounds. Expired/failed orders revoke the
leftover allowance; a crash resubmits the identical idempotent request, never a new signature.

Every RFQ payload is captured (`GET /api/live/rfq/captures`), including in read-only planning,
because no live payload has been seen yet. Before the first live RFQ: compare captures with the
vendor table in `docs/WEEKEND_SWAP_AND_RFQ_PLAN.md`, verify the PancakeSwap X reactor on BscScan and
add it with `RFQ_SETTLEMENT_ALLOWLIST=PcsXRfq:0x...`.

Signers: `LOCAL_KEY` (EIP-712), `AGENTIC_WALLET` (`baw sign-message`, needs Developer Mode),
`ALTANA` (ERC-1271 via sidecar, CowSwap only, after `grant-session.mjs --approve-checker`).

## Known limits

- RFQ settlement is not previewable (G01); RFQ legs are bounded by order verification, not
  simulated. Vendor order formats are implemented from public specs until real captures confirm them.
- `priceImpactPercent` is read conservatively as a fraction: 0.0009 is treated as 9 bps.
- The equity index timestamp is its publication time. Outside US sessions the index can be fresh
  while the underlying stock is closed.
- Trust and historical baselines are not used for rebalancing.
