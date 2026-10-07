# Specification and external-contract discrepancies

Date: 2026-10-06. Product behavior remains authoritative in the master prompt; current official syntax wins. No master file was edited.

| ID | Comparison | Finding | Resolution for future work |
|---|---|---|---|
| D01 | User path / workspace | Initially docs master absent; exact copy created in Phase 0.1 | RESOLVED: raw-byte equality and identical SHA-256; no spec edits |
| D02 | Prompt / uploads | Proposal and uploaded schema mentioned but unavailable | Mark comparisons NOT AVAILABLE |
| D03 | Section 11.4 / current Trading API | Core build inputs omit conditional slippage requirement | Supply slippagePercent or autoSlippage=true; platform risk must cap it |
| D04 | Section 11.5 / official submit docs and schema | submit quoteId specifically takes rfq.orderId from swap, not automatically route quoteId | Persist separate identifiers and assert binding |
| D05 | General wallet assumptions / current official skill | Current skill 1.12.0 requires CLI 1.10.0 and documents Developer Mode external calls/EIP712 | Document concrete preview/execute path; still require runtime and settlement safety proof |
| D06 | Wallet controls / current settings | Developer Mode daily quota is separate from general dailyLimit | Check active operation's quota plus stricter application limits |
| D07 | “Wallet Skills” / signed Web3 REST | Securities-info skill uses public BAPI, different field names/envelope and currently describes Ondo | Separate adapters; signed RWA discovery remains issuer-universe authority |
| D08 | Schema required arrays / live transaction prose | gas-limit and simulate schema mark evmTx, solTx, tronTx all required for rendering; prose says exactly one | Validate chain-discriminated payload; BSC only evmTx |
| D09 | Prompt independent-price rule / docs | Confirmed: referencePrice derived from token economics | Never use it as independent equity observation |
| D10 | Section 15/calendar needs / Massive holidays | Upcoming endpoint is forward-looking, not historical schedule database | Add verified historical schedule provenance before replay |
| D11 | Section 79/79A | Scientific packages are float-oriented; all financial arithmetic prescribed as Decimal | Record unresolved boundary, do not silently relax precision |
| D12 | UI examples / final overrides | “max loss” phrasing and trust=HIGH example conflate risk guarantee/classification/confidence | Risk budget, explicit stress assumptions; separate classification and confidence |
| D13 | DRY_RUN simulation wording / RFQ override | RFQ final settlement cannot be marked simulated merely from approval or message preview | State RFQ settlement safety UNVERIFIED, LIVE disabled |
| D14 | Quote TTL / human approval | ~30-second quote cannot be presumed valid after approval transaction or user review | Confirm approvals, fresh quote/build/simulation; fingerprint changes re-approved |
| D15 | Generic market-order capability / exact transaction requirement | CLI market-order swap takes pair/quantity; no documented external quoteId or calldata binding | Do not use it to execute an independently simulated aggregator payload |
| D16 | Idempotency wording / official submit | Provider duplicate suppression documented for 30 minutes | Application persistence/reconciliation beyond that window |
| D17 | Research version / search index | v3 is June 16, 2026; older abstracts discuss a different crypto population/period | Use v3 full text, not v1/v2 abstract summaries |
| D18 | Current software / unspecified versions | No lockfile; current docs alone do not prove a compatible installed stack | Resolve/pin and test in Phase 1 only |
| D19 | Tokenized-info field names / economic semantics | Public dynamic tokenInfo.volume24h is stock USD volume; public K-line slot5 is reserved, unlike signed market candles | Never use public skill volume/reserved slot as on-chain liquidity evidence |
| D20 | Prompt / current candle contract | Signed candles order is OHLC,volume,timestamp,tradeCount; after=end and before=start, both exclusive | Separate positional schemas and pagination rules |
| D21 | Standard RFQ flow / optional Flash API | Flash enableRFQ may embed settlement calldata with short deadline | Defer Flash; do not infer an approved alternative settlement path |
| D22 | Authentication sample / endpoint contract | Auth page illustrates GET market/price although endpoint docs/schema specify POST | Use sample only for signing mechanics; real contract wins |

Verified alignments: signed /build prefix; RWA keyword search; RWA GET price versus general POST price arrays; POST basic-info with query parameters; response-envelope validation; dynamic SWAP/RFQ branching; RFQ terminal states; vendor-aware ERC20 approval; Solana-only swap-instruction excluded; issuer examples ondo/bstock not a permanent runtime inventory.

The published [schema](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/1.0.0/schema.json) and [live Trading documentation](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/trading-api) agree on D04. The [Transaction documentation](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/transaction-api) explicitly explains D08. A complete machine-level schema diff was not performed.
