# Free alternative provider feasibility — read-only diagnostic

Measured2026-10-06 UTC (2026-10-07 after00:00 Asia/Kolkata). **No production change, production observation write, gate modification, purchase, execution call or synthetic data.** Current Trust thresholds30/30/3, freshness120s, skew30s, mode partition and first-availability rules are unchanged. Existing databases, source, historical evidence and formal Trust gate remain byte-identical.

## Result and scope

| Required result | Status | Evidence / limitation |
|---|---|---|
| TWELVE_DATA_CURRENT_EQUITY | FAIL — runtime NOT_TESTED | TWELVE_DATA_API_KEY absent from shell/project.env; no authenticated call, HTTP status, actual price, timestamp or history can be claimed |
| FINNHUB_CURRENT_EQUITY | FAIL — runtime NOT_TESTED | FINNHUB_API_KEY absent from shell/project.env; no authenticated quote or candle entitlement/freshness cross-check |
| GECKOTERMINAL_LIQUIDITY | FAIL for unchanged Trust requirement | Pool reserve data retrieval PASS; token-market equivalence, measurement asof and historical liquidity are not verified |
| REAL_HISTORICAL_EPISODE_FEASIBILITY | FAIL |0 qualifying baseline/opening-model episodes and0 eligible analogues; no new free equity bars available |

FAIL for missing keys means verification could not pass, **not an observed provider API failure or proof that its free plan is incapable**. A location/configuration question was sent; values were never requested. Only.env and.env.example exist in the repository. No substitute/demo credential was used. Preliminary and recovered actual captures are retained separately; the final pairing audit below supersedes the preliminary window counts.

Recommendation **2 — Free replacement partially solves blockers**, limited to verified raw pool reserves and historical price coverage. No complete Trust blocker is closed. Twelve Data is a plausible independent internal-use candidate pending credentials, observed recency/provenance and licensing verification. There is insufficient evidence for recommendation1, and missing credentials do not justify claiming recommendation3 that all free alternatives are impossible.

## Twelve Data official contract and licensing

Current [individual pricing](https://twelvedata.com/pricing) advertises Basic at no charge,8 API credits/minute and800/day, real-time US equities/ETFs and internal non-display usage. Endpoint weights count credits; these are not800 arbitrary weighted requests. Individual terms specify personal/internal/noncommercial scope. The [US equity source/licensing guide](https://support.twelvedata.com/en/articles/9935903-us-equities-market-data) describes default real-time venue coverage of approximately5% of US trading volume and separately licensed broader coverage/redistribution. This is not consolidated SIP/NBBO coverage. Basic is **not assumed to authorize public Parity Pulse price redisplay**. No paid subscription or add-on was obtained.

Official [API documentation](https://twelvedata.com/docs) was retrieved directly over HTTP200 when the browser text fetch exceeded its size limit. Reviewed sections: market-data/real-time-price, quote, time-series, markets/market-state, authentication. Header authentication is `Authorization: apikey <protected value>`; no key enters query strings, logs or diagnostic output.

| Planned NVDA read | What must be verified | Actual local result |
|---|---|---|
| GET /price | Positive latest price plus independently supported price asof | NOT_TESTED_CREDENTIAL_ABSENT |
| GET /quote, interval=1min, timezone=UTC | Identity/currency/exchange, close, timestamp and last_quote_at semantics, actual age/skew | NOT_TESTED_CREDENTIAL_ABSENT |
| GET /time_series, interval=1min, UTC, Oct2–5, max5000 | Actual range, previous regular close, gaps, adjustments, completed bar timing | NOT_TESTED_CREDENTIAL_ABSENT |
| GET /time_series, interval=5min, same bounded range | Exact first13:30Z opening bar completing13:35Z; never synthesize absent bar | NOT_TESTED_CREDENTIAL_ABSENT |
| GET /market_state, NASDAQ | Actual exchange status with existing schedule cross-check | NOT_TESTED_CREDENTIAL_ABSENT |

`/price` documents only a price field, with no guaranteed source timestamp: response receipt alone cannot prove freshness. Quote `timestamp` is the selected interval's **opening time**, and `last_quote_at` is the last minute candle time; neither is silently labeled an exact last-trade timestamp. Historical `datetime` uses the requested UTC intraday timezone; adjusted prices default to split adjustment, and pre/postmarket support is plan-restricted. The source guide says historical/EOD becomes available after midnight Eastern on the next trading day, including Basic access; actual one-minute/five-minute retention and account entitlement remain unmeasured. A pricing promise or HTTP200 alone would not pass current-reference rules.

No actual current price, observation timestamp, freshness, earliest/latest equity range, interval availability, runtime rate-limit response or account-plan identity is available. The diagnostic spaces Twelve Data requests at8seconds and retains only safe rate headers/business categories when run with an actual key; it does not deliberately exhaust a quota.

## Finnhub optional cross-check

Reviewed official [quote](https://finnhub.io/docs/api/quote), [stock candles](https://finnhub.io/docs/api/stock-candles), [pricing](https://finnhub.io/pricing) and [official Python client](https://github.com/Finnhub-Stock-API/finnhub-python/blob/master/finnhub/client.py). Dynamic pricing/endpoint pages did not yield readable current plan details, so no precise free candle entitlement or rate-limit number is asserted from third-party descriptions. Official client confirms GET `/quote?symbol=NVDA` and `/stock/candle` with resolution1/5 and Unix from/to parameters; protected key uses documented `X-Finnhub-Token` header.

Latest quote and both historical intervals are NOT_TESTED_CREDENTIAL_ABSENT. HTTP status, actual price/timestamp/freshness, historical date coverage, quota behavior and entitlement are UNKNOWN. **No measured Twelve Data–Finnhub price comparison exists.** Public redisplay authorization is not established. No production provider was integrated.

## GeckoTerminal: indexed pools and explicit selection

Public keyless GETs use `https://api.geckoterminal.com/api/v2`; [official public Swagger](https://api.geckoterminal.com/docs/v2/swagger.json) was retrieved HTTP200 and inspected for exact free endpoint parameters/schema. Network `bsc` and contracts come from prior verified Binance discovery, not symbol-only search:

- BStock NVDAB: `0x02fca66c1d1afb4e2a7884261eb00f63598a7436`.
- Ondo NVDAon: `0xa9ee28c80f960b889dfbd1902055218cba016f75`.

GET `/networks/bsc/tokens/{contract}/pools?include=base_token,quote_token,dex&page=...` retrieved60 unique BStock pools over3 pages; Ondo20 from1 page before pagination was rate-limited. **Neither enumeration is exhaustive.** Actual pool addresses, DEX identifiers and exact base/quote token relationships are retained in the captures. Some returned identifiers are64hex pool IDs or manager-address/index strings; they are not invented42-character EVM contract addresses.

For history diagnostics, select the largest reported reserve **among enumerated exact-token pools with a recognized USDT/USDC counterasset and nonzero24hour activity**. This is a reproducible sampling rule, not routing, risk selection or a claim of complete token-market liquidity. It avoids equating a dormant reserve-rich pool with a current active market.

| Selected diagnostic pool | Verified relationship / DEX | Reported reserve USD | Token price USD |24h pool volume USD | Receipt UTC |
|---|---|---|---|---|---|
| `0x8fb4243b553ac29ba088acf00b9b7da24bd6690c` | NVDAB base / USDT quote; PancakeSwapV3 |5667691.3273 |240.824925860477 |4568044.04070757 |Oct6 18:28:33.252737 |
| `0xb90bdbfbdffd4af5a636b5805539edeafb969308` | NVDAon base / USDT quote; PancakeSwapV3 |9730.2089 |244.153170465569 |492.4915163367 |Oct6 18:29:20.802406 |

USDT counterasset contract is `0x55d398326f99059ff775485246999027b3197955`. Both prices use the actual base-token field; an inverted quote-side pool cannot be read the same way. Public [reserve semantics](https://docs.coingecko.com/changelog/update-frequency-improvements-for-selected-pro-api-endpoints) define `reserve_in_usd` as total pool liquidity/reserve in USD. It is **not token-wide liquidity, executable price impact, concentrated-liquidity depth at the current tick, or an independent equity reference**. No reserve sum or token-market substitution was made.

Neither current detail response supplies a verified reserve measurement timestamp/block nor `last_trade_timestamp`. Receipt/cache time is not liquidity asof. OHLCV lacks historical reserve values. Pool-wide reserve semantics differ from the existing token liquidity feature; complete venue coverage, applicable source scope and matching history would still require verification before any production proposal. Therefore **raw pool-data availability PASS; authoritative Trust liquidity replacement FAIL**.

Initial diagnostic selected Ondo pool ID `0xafc43fae32302d725fc4d448525c44c522a9a1b9-40` with reported reserve14408.2354, zero24hour activity, token price181.330621061 and only sparse February–March minute history. It was explicitly rejected as the current-data candidate. Its captured rows are preserved but excluded from the final active-pool pairing audit. Highest reserve alone was insufficient.

Initial reads encountered429 (`Retry-After: 0`) despite bounded pacing. Slower8second requests recovered BStock history, but one Ondo hourly request still returned429; the diagnostic imposed a30second cooldown. A later isolated hourly retry returned200. These failures remain in evidence. No stable quota/freshness SLA is inferred. The provider's [public API guide](https://www.coingecko.com/learn/dex-data-api) describes historical OHLCV support; paid CoinGecko plan/cache limits are not silently transplanted to the free GeckoTerminal surface.

## Real historical coverage and dry-run pairing

Requests explicitly set `currency=usd`, exact token address, aggregate1, limit1000 and `include_empty_intervals=false`. Public Swagger defines `[Unix-seconds bar start, open, high, low, close, volume]`; completed bars only enter the audit. Empty intervals, source gaps and incomplete bars were not fabricated or filled. Zero-volume and invalid-OHLC checks on the selected recovered histories found none. These are provider-captured historical rows, not proof of immutable revisions or first publication availability at their historical dates.

| Active pool history | First observed bar start UTC | Last completed bar start UTC | Rows / observed gaps |
|---|---|---|---|
| BStock daily |Jul29 00:00 |Oct5 00:00 |69; maximum1day gap |
| BStock hourly |Jul29 07:00 |Oct6 17:00 |1667; maximum1hour gap |
| BStock recent minute |Oct6 01:42 |Oct6 18:27 |999;7 gaps>1minute, max120s |
| BStock preopen minute |Oct4 19:26 |Oct5 13:29 |999;69 gaps>1minute, max240s over entire capture |
| Ondo daily |Apr6 00:00 |Oct5 00:00 |182;1 gap>1day, max2days |
| Ondo hourly, recovered |Aug19 12:00 |Oct6 17:00 |998 completed;114 gaps>1hour, max8hours |
| Ondo recent minute |Sep26 01:53 |Oct6 18:26 |647;534 gaps>1minute, max22380s |
| Ondo preopen minute |Sep24 22:09 |Oct5 13:28 |610;505 gaps>1minute, max22380s |

All dates are2026. Ondo pool creationNov26 2025 is metadata, **not a claim of captured history starting then**. Historical retrieval is bounded; earliest returned bar is not proof of earliest available token data. No claim of complete six-month minute coverage. Binance persisted122 token observations remain read-only:23 BStock/99 Ondo. The new diagnostic candles are not persisted as application observations.

An in-memory audit uses the existing published exchange calendar and actual token captures. Date-span potential windows are separated from windows containing intraday observations. New Twelve Data/Finnhub bars are0 because credentials are absent. Existing Massive2083 BAR rows spanningOct2 08:00→Oct5 23:59 are used **only as a previously captured real control**, never mislabeled as a free-provider success or current reference.

| Pairing metric | BStock | Ondo | Total / qualification |
|---|---|---|---|
| Potential weekend/holiday reopening representation-windows |10 |27 |37 representation-windows;27 distinct opening dates, not37 independent stock events |
| Windows with actual closed-window intraday token data |10 |7 |17 |
| Newly paired episodes with free equity captures |0 |0 |0 |
| Raw pairs using pre-existing Massive close/first5m target |1 |1 |2 issuer-scoped pairs for the **same Oct5 stock opening**, not2 independent outcomes |
| Qualifying baseline episodes |0 |0 |0/30 |
| Qualifying opening-model episodes |0 |0 |0/30 |
| Eligible real analogues |0 |0 |0/3 |
| Rejected potential representation-windows |10 |27 |37 |

Existing-control opening target remains `(237.376−234)/234`, approximately+1.442735%, Decimal precision retained. It completesOct5 13:35Z after13:30Z decision and is kept outside features. BStock's final30minute window now has30 actual minute bars with60s maximum gap: **density alone passes**, unlike the previous sparse Binance minute sample. Ondo has3 bars and1560s maximum gap in that window: density fails. Neither becomes a Trust episode without the other mandatory facts.

Rejections identify missing free equity captures; historical asof ratio; historical pool liquidity; point-in-time feature/revision availability; time-aligned historical news; and absent/sparse end-window coverage. Twenty potential Ondo date windows have only coarse daily span coverage, with no captured intraday closed-window observations. No target, ratio, feature, missing interval or news availability was invented. New historical receipts were not backdated. Normalized historical exposure remains null when the ratio is unverified.

## Historical token/share ratio investigation

Binance [underlying profile](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/rwa-data) documents `tokenToShareRatio` for the current representation, without a historical asof parameter/version ledger in the reviewed contract. Previously captured ratios have actual October6 receipt provenance; they are not evidence that those ratios applied earlier.

Ondo's current official [shares-multiplier history endpoint](https://docs.ondo.finance/api-reference/assets/get-shares-multiplier-history-for-an-asset) **does exist**: GET `/v1/assets/NVDAon/shares-multiplier?range=all`. It documents earliest change timestamps/values and requires an Ondo API key. Two anonymous diagnostic reads returned403; no historical ratio records were obtained and no key/access was requested or purchased. A retrieved event ledger would still need exact contract identity, effective-time and correction/availability validation before matching any observation. API existence is not verified free entitlement.

For BStock, official [Binance bStocks documentation](https://www.binance.com/en/academy/articles/what-are-bstocks-a-guide-to-tokenized-stocks-on-binance) describes dividend/split multiplier changes. [BEP-677](https://github.com/bnb-chain/BEPs/blob/master/BEPs/BEP-677.md) defines scaled UI amount and scheduled-change/overwrite events. Those are potential onchain reconstruction inputs; no actual deployed-contract event/archive history or equivalence to Binance's raw-token/share ratio was verified here. General1:1 backing prose does not override the captured non-unit raw-token ratio. UI display multipliers must not be treated as economic ratios without that mapping.

**For every evaluated historical window, historical economic ratio remains UNAVAILABLE.** Today's ratio was not backfilled. This alone prevents historical Trust qualification even where raw prices/opening targets/density exist.

## Evidence, verification and stop

- [Skipped equity probes / missing credentials](evidence/FREE_PROVIDER_EQUITY_FEASIBILITY.json).
- [Initial actual pools/history and retained rate limits](evidence/FREE_PROVIDER_GECKOTERMINAL_FEASIBILITY.json).
- [Active-pool recovered capture](evidence/FREE_PROVIDER_GECKOTERMINAL_REVERIFIED.json).
- [Isolated Ondo hourly recovery](evidence/FREE_PROVIDER_GECKOTERMINAL_HOURLY_RECOVERY.json).
- [Final real in-memory pairing and per-window rejection ledger](evidence/FREE_PROVIDER_FEASIBILITY_PAIRING.json).
- Throwaway [read-only diagnostic](../scripts/diagnose-free-providers.py); refuses existing output overwrite, uses reviewed GET-only paths and protected header credentials, suppresses bodies on denial and scans output for configured secret values.

Verification: all311 existing backend tests PASS; existing upstream Starlette/httpx deprecation remains. Ruff lint/format PASS for69 Python files. Existing security scan and extended two-provider-key scan PASS. Pre-task SHA256 manifest confirms every179 existing source/doc/data artifact unchanged, including production databases and the formal Trust gate. Only this report, the new diagnostic and its five evidence files were created; no package/dependency/configuration change. Raw source/API documentation captures reside under/private/tmp.

**TRUST_GATE remains BLOCKED and was not modified.** Opportunity remains BLOCKED_BY_TRUST; all three LIVE gates remain BLOCKED. No free provider was added to production. Stop after this feasibility task. Next prerequisite for completing the omitted equity runtime checks is locally configured credentials or their location identifiers; no secret values should be shared.
