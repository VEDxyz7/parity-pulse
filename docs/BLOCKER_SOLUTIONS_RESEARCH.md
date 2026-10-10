> **Historical teammate proposal — superseded by the PR #1 merge resolution (2026-10-11).**
> The original text below is preserved as history, not as an operational runbook or
> verified capability evidence. LIVE flags, Trust-disable configuration, weekend
> exceptions, Binance-index independent references, signed-bounds-only RFQ admission,
> blind retries and Altana/x402/session grants described below are NOT enabled.
> Current gates, commands and limitations: [PR_1_MERGE_RESOLUTION.md](PR_1_MERGE_RESOLUTION.md).

# Blocker solutions research — 2026-10-09

Web research across Binance Web3 / Agentic Wallet docs, binance-skills-hub, BNB Chain docs, Ondo docs, Pyth/Chainlink docs and live read-only probes. Tags: [DOC] quoted from docs, [LIVE] verified by a read-only call, [INF] inference. Nothing here was executed against a wallet; no funds moved.

## Hackathon context [DOC]

"BNB Hack: Tokenized Stocks Edition" (BNB Chain + Binance Web3 Wallet) — https://www.bnbchain.org/en/hackathons/tokenized-stocks

- Submission closes 2026-10-11 12:00 UTC; judging 2026-10-15..23.
- BSC mainnet only; spot only; bStocks/Ondo/xStocks central.
- Judging: Technical 30%, Creativity 25%, Developer Experience Report 25% (mandatory, AI-generated reports not accepted), Product/UX 20%.
- Side prizes: Best Use of Agentic Wallet/Wallet Skills ($2k), Best Use of BNB Agent Studio ($2k).
- Free Binance Web3 API access with elevated limits: https://web3.binance.com/en/dev-portal

## Blocker → solution

| Gap | Verdict | Solution |
|---|---|---|
| G02 Agentic Wallet runtime | SOLVABLE (setup) | `npm i -g @binance/agentic-wallet@1.10.0`; `baw auth signin --json` → `baw auth verify --qrCodeId <id>` (App approval); `baw wallet status`, `baw cli-check` |
| G12 Autonomous execution | SOLVABLE within limits | App-side `dailyLimit`, `tradeAllTokens` allowlist, `abnormalTxnHandling=AutoReject`, `devMode.dailyLimit/expiresAt`; `requireConfirmation=false` executes without App tap. Read via `baw wallet settings --json`. Settings not CLI-mutable. Alt: BNB Agent Studio v2 "Altana" session keys (spend limits, allowlists, time bounds) |
| SWAP simulation equivalence | SOLVABLE | `POST /api/v1/dex/pre-transaction/simulate` {binanceChainId, evmTx{from,to,value,data}} → status, failReason, balanceChanges, allowanceChanges. CLI: `baw contract-call preview` → simulationResult + requireConfirmation, then `contract-call execute --requestId` |
| G01 RFQ settlement preview | PARTIAL (vendor limit) | No settlement-tx preview documented. Stock tokens return `executionMode=RFQ`; vendors `InchFusion | CowSwap | PcsXRfq`. Mitigation [INF]: decode `rfq.typedDataToSign` per vendor order struct (receiver, min out, deadline), check `domain.verifyingContract` vs published settlement address, reconcile `GET /order/{orderId}` toAmount/txHash after fill. Possible alt [INF, untested]: `quote-and-swap` with `vendor=LiquidMesh` returns SWAP calldata → simulate |
| G10/G13 RWA metadata/eligibility | SOLVED (current) | `GET /api/v1/dex/market/rwa/tokens` (tokenToShareRatio, statusInfo{openState, marketStatus, reasonCode, nextOpenTime, nextCloseTime}, referencePrice, volume24H); `/rwa/platforms`, `/rwa/price`, `/rwa/underlying-market`; corporate-action status (`ASSET_LIMITED`) |
| G03 Fresh independent equity | SOLVABLE (free) | Binance perp index `GET https://fapi.binance.com/fapi/v1/premiumIndex?symbol=NVDAUSDT` (indexPrice, ms `time`, no key) [LIVE]; constituents via `/fapi/v1/constituents` (databento, dxfeed, kaiko, massive, pyth_pro). USDT-denominated. Alt: Pyth `Equity.US.NVDA/USD` (needs API key since 2026-08-26, regular hours only); Chainlink Data Streams RWA v11 |
| Historical ratio (Ondo) | SOLVED on-chain | `SyntheticSharesOracle` BSC `0xF4Fd8a1B412633e10527454137A29Db7Aa35F15e`: `getSValue(token)→(sValue, paused)`, `assetData(token)`; events `SValueUpdated`, `CorporateActionApplied` [DOC+LIVE]. NVDAon `0xa9ee28c80f960b889dfbd1902055218cba016f75` sValue≈1.0017 (1e18). REST alt needs key (onboarding@ondo.finance) |
| Historical ratio (BStock) | SOLVED on-chain [INF semantics] | NVDAB `0x02fca66c1d1afb4e2a7884261eb00f63598a7436`: `uiMultiplier()`, `pendingMultiplier()`, `effectiveAt()`; event `UIMultiplierUpdated(old,new,effectiveAt)` |
| Ondo pause/status | SOLVED on-chain | GMTokenManager `0x91f8Aff3738825e8eB16FC6f6b1A7A4647bDB299`: `globalMintingPaused()`, `gmTokenMintingPaused(token)`, `gmTokenRedemptionsPaused(token)`; pause manager `isTokenPaused(token)` |
| Current liquidity | SOLVABLE | `/api/v1/dex/market/token/top-liquidity` (pool liquidityUsd); executable depth via KyberSwap `GET https://aggregator-api.kyberswap.com/bsc/api/v1/routes?tokenIn&tokenOut&amountIn` (no key) [LIVE] |
| Historical liquidity | PARTIAL (market limit) | Archive `eth_call` at block (NodeReal free 10M CU/mo, archive included): v3 `slot0`/`liquidity`/`balanceOf`, v2 `getReserves`, v4/Infinity `StateView`. Covers AMM reserves only — RFQ/PMM depth invisible |
| 30 episodes / 3 analogues | NOT ACHIEVABLE as specified | NVDAB oldest pool 2026-06-18 (~16 weekends). NVDAon ~45 weekends but on-chain pools ~$10k; real depth is Ondo RFQ/mint-redeem |

## Market facts [LIVE]

- NVDAB: PancakeSwap v3 NVDAB/USDT 0.25% ~$6.1M reserve, ~$3.7M 24h vol. ~$234k Kyber sell ≈ −0.1%.
- NVDAon: largest pool PCS v3 1% ~$9.7k. ~$234k Kyber sell ≈ −34%. Ondo hours: 24/5; weekend Off-Hours only for select assets.

## Data providers

- Dune `dex.trades` (BSC, block_time) — free tier view-only, no API export.
- GeckoTerminal OHLCV — free tier last 180 days only.
- Bitquery — trades archive yes; liquidity/slippage realtime only.
- The Graph PCS v3 BSC — stale, avoid.
- Public dataseed RPC: no archive, getLogs disabled.

## Low-value for this project

- `bnb-chain/bnbchain-mcp`: no swap/simulate tools.
- BNBAgent SDK: identity (ERC-8004)/payments only.
- opBNB: hackathon is BSC mainnet only.
