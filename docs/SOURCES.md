# Official source register and reconnaissance coverage

Checked 2026-10-06, user timezone Asia/Kolkata. Links identify actual official sources inspected. DOC means documentation evidence; RUNTIME would mean first-hand business response evidence. No RUNTIME provider integration evidence exists.

## Binance

| Source | Evidence inspected | Coverage limit |
|---|---|---|
| [Web3 authentication](https://web3.binance.com/en/dev-docs/authentication) | Signing, headers, /build, timestamp, replay, rate dimensions | No actual signature or permission test |
| [RWA](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/rwa-data) | Six mandatory methods, search nesting, derived reference price, ratios/platforms | No dynamic inventory or user entitlement tested |
| [General market](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/general-data) | Mandatory methods, query/body distinction, batching/trades | Not every extra market endpoint selected |
| [Trading](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/trading-api) | Quote/build, conditional slippage, modes, approvals, identifiers, submit/status | Final RFQ safety not established |
| [Transaction](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/transaction-api) | Gas/simulation/broadcast/orders, chain-payload exception | No simulation result measured |
| [Wallet REST](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/wallet-api) | Chain/balance/history/detail, raw versus scaled units | Read APIs do not authenticate Agentic Wallet |
| [Published schema](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/1.0.0/schema.json) | OpenAPI3.0.2, info.version1.0.0, mandatory path families; detailed RFQ submit and gas-limit sections | Partial browser inspection; no complete machine diff/snapshot hash |
| [Agentic Wallet overview](https://developers.binance.com/en/docs/products/agentic-wallet/welcome) | CLI/skills model, policy, BSC support | Page modified October5,2026; overview not full command authority |
| [Skills reference](https://developers.binance.com/en/docs/products/agentic-wallet/reference/skills) | Official skills entry point | Current GitHub references used for syntax |
| [Wallet skill](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/SKILL.md) | Version1.12.0, CLI1.10.0, command routing and confirmation | Mutable main branch; local installation absent |
| [Wallet view](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/wallet-view.md) | Status/address/balance/history/lock | Examples are not current wallet responses |
| [Wallet settings](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/wallet-setting.md) | Read-only policy and separate operation quotas | No actual settings read |
| [Market order](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/market-order.md) | Quote/swap/list, human units, terminal status | External quote/calldata equivalence not documented |
| [Limit order](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/limit-order.md) | Buy/sell/list/cancel | Not selected as execution substitute |
| [External sign](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/external-sign.md) | Developer Mode EVM preview/execute and EIP712 message preview/execute/result | No proof of final vendor-relayed RFQ simulation |
| [Securities-info skill](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-tokenized-securities-info/SKILL.md) | Version1.1; six public API operations, ratios, volumes and statuses | Ondo-focused; not signed REST/full issuer universe |

## Independent equity and calendar

[REST quickstart](https://massive.com/docs/rest), [stocks overview](https://massive.com/docs/rest/stocks/overview), [single snapshot](https://massive.com/docs/rest/stocks/snapshots/single-ticker-snapshot), [full snapshot](https://massive.com/docs/rest/stocks/snapshots/full-market-snapshot), [custom bars](https://massive.com/docs/rest/stocks/aggregates/custom-bars), [last quote](https://massive.com/docs/rest/stocks/trades-quotes/last-quote), [market status](https://massive.com/docs/rest/stocks/market-operations/market-status), [holidays](https://massive.com/docs/rest/stocks/market-operations/market-holidays), [news](https://massive.com/docs/rest/stocks/news), [splits](https://massive.com/docs/rest/stocks/corporate-actions/splits), [dividends](https://massive.com/docs/rest/stocks/corporate-actions/dividends), [rate policy](https://massive.com/knowledge-base/article/what-is-the-request-limit-for-massives-restful-apis), [NYSE schedule](https://www.nyse.com/trade/hours-calendars).

Coverage: public contracts, update/plan descriptions, current corporate-action routes. Actual account entitlements, licensing, current observations and historical schedule dataset not established.

## Research and software

Research links/versions and access limitations: [RESEARCH_NOTES.md](RESEARCH_NOTES.md). Official software references: [DEPENDENCIES.md](DEPENDENCIES.md). No named paper's latest status is inferred from a third-party summary alone; no library documentation page is treated as package compatibility evidence.

## Retrieval limitations and evidence preservation

The official schema was readable through the documentation browser. Direct approved curl retrieval produced HTTP202 with empty body and WAF challenge. It was not saved to the project as a valid schema. No upload snapshot comparison, complete live-schema checksum or exhaustive programmatic diff is claimed.

Some docs are mutable or have stale examples. Authentication examples illustrate serialization and must not override actual endpoint methods. In particular, the authentication page's sample GET market/price is not evidence that the general price operation is GET; endpoint docs/schema specify POST.

All citations are readable URLs rather than transient tool reference IDs. The specification file remains unmodified.
