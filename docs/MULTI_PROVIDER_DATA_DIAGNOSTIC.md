# Multi-provider read-only data verification — October 10, 2026

## Outcome and scope

**PARTIAL: useful independent equity history, event context and secondary perpetual signals are accessible; current Trust eligibility is not established.** Authentication succeeded for the tested permitted Alpaca/Finnhub reads. Alpaca denied latest SIP and BOATS quotes, but supplied historical SIP and BOATS bars. Finnhub supplied quotes, news, earnings and calendar data, but denied historical candles. Hyperliquid dynamically exposed three active target markets on `xyz`, alongside eleven delisted target listings with empty books/history.

The combined run was **2026-10-10 07:37:54.298778–07:38:38.368314 UTC**, Saturday, or **13:07:54–13:08:38 IST**. Every returned cash-equity latest quote was stale against the existing 120-second requirement. This is closed-session evidence, not proof of how fresh the account's permitted quotes will be during a regular session. No current parity, forecast, executable opportunity or entitlement upgrade is inferred.

Evidence:

- [Combined observations and request ledger](evidence/MULTI_PROVIDER_DATA_20261010.json): 106 HTTP requests.
- [Existing Alpaca diagnostic, now with configured credentials](evidence/ALPACA_CONFIGURED_NVDA_20261010.json): three HTTP requests, 07:31:21–07:31:23 UTC.
- [Target Binance catalog schema audit](evidence/MULTI_PROVIDER_CATALOG_AUDIT_20261010.json): one HTTP request, receipt 07:44:17.297166 UTC.
- One preliminary public Hyperliquid `perpDexs` read also returned HTTP 200 and ten DEXs. Its exact receipt time was not retained; discovery was repeated and timestamped in the combined evidence. It is not used for freshness calculations.

**111 actual API HTTP requests total**, excluding official-documentation browsing. All were market-data reads. No retries, rate-limit load test, order, RFQ, swap, wallet, simulation or execution endpoint was called. No application startup or production database backfill occurred. The scheduled Twelve Data/Binance alignment diagnostic was not run or changed. Prior no-credential evidence remains historical and was not overwritten.

| Request group | Actual HTTP requests | HTTP 200 | HTTP 403 |
|---|---:|---:|---:|
| Alpaca, combined run | 45 | 39 | 6 |
| Finnhub | 12 | 11 | 1 |
| Hyperliquid, combined run | 39 | 39 | 0 |
| Binance, combined run | 10 | 10 | 0 |
| Existing Alpaca diagnostic | 3 | 3 | 0 |
| Hyperliquid discovery preflight | 1 | 1 | 0 |
| Binance target catalog audit | 1 | 1 | 0 |
| Total | 111 | 104 | 7 |

Status vocabulary: `PASS` means the specified capability was observed and validated; `PARTIAL` means bounded data with unresolved quality/coverage/identity limitations; `UNAVAILABLE` means denial, empty expected data or unusable values for that use; `NOT_CONFIGURED` means missing required local settings; `NOT_VERIFIED` means untested or insufficient evidence. A low-level request/check `PASS` in JSON can coexist with STALE quality, an empty nested result, delisting or unverified entitlement. It is not a Trust-gate decision.

## Configuration and repository reconnaissance

Started on branch `main`, HEAD `be34929` (`Merge glassmorphism dashboard UI`), with 19 pre-existing modified/untracked files from the Alpaca adapter increment. Those files were fingerprinted before this diagnostic and preserved. No reset, stash, branch switch, commit or push.

| Configuration | Local presence / actual consumption |
|---|---|
| `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | CONFIGURED; existing `Settings` and `AlpacaClient` consume these exact names through header authentication |
| `FINNHUB_API_KEY` | CONFIGURED; this isolated diagnostic consumes it; no production Finnhub adapter/settings integration |
| `HYPERLIQUID_API_URL` | Configured to the complete `https://api.hyperliquid.xyz/info` URL; diagnostic validates exact equality and never appends `/info` |
| `HYPERLIQUID_ENABLED` | true; consumed only by this diagnostic, not production `Settings` |
| `EQUITY_PROVIDER` | Effective default MASSIVE; unchanged |
| `ALPACA_FEED`, `ALPACA_DATA_QUALITY` | Effective defaults iex / UNKNOWN; diagnostic requests individual feeds explicitly without changing defaults |
| Binance Web3 / Massive credentials | Existing configuration preserved; Binance read client reused, Massive not retested |
| Execution settings | `EXECUTION_MODE=dry_run`, `LIVE_TRADING_ENABLED=false`, `REQUIRE_SIMULATION=true`; unchanged |

`.env` is excluded by Git (`git check-ignore .env` succeeds). No secret values, signatures, authentication headers or provider error bodies are retained. Alpaca/Finnhub credentials travel only in headers. The diagnostic uses bounded allowlists, Decimal JSON parsing, UTC timestamps, one attempt per request, secret-echo rejection and safe numeric rate-limit headers. It imports no application startup or repository/database writer. Hyperliquid POST requests target public `/info` market-data types only, never `/exchange` or user/wallet types.

The existing Binance and Massive implementations, DEMO isolation, Trust reference selection, scoring, thresholds and gate documents are unchanged by this increment. `HYPERLIQUID_ENABLED=true` does not enable a production integration or execution path.

## Actual endpoints and parameters

| Provider | Endpoint actually called | Parameters / payload |
|---|---|---|
| Alpaca | GET `https://data.alpaca.markets/v2/stocks/quotes/latest` | One of TSLA/NVDA/GOOGL per request; feeds iex, sip, delayed_sip, boats, overnight; currency USD |
| Alpaca | GET `https://data.alpaca.markets/v2/stocks/bars` | Each ticker; `timeframe=1Min` / `5Min`; feeds iex/sip/boats; start Oct 8 00:00Z, end Oct 10 00:00Z; `adjustment=raw`, `asof=-`, ascending order, bounded pagination (two pages maximum) |
| Alpaca | Same bars endpoint, depth probe | Each ticker, SIP 1Min; Jan 4, 2016 14:30–15:00Z, one page |
| Alpaca | Same bars endpoint, Saturday probe | Each ticker, IEX/BOATS 1Min; Oct 3 04:00Z–Oct 4 04:00Z, one page |
| Finnhub | GET `https://finnhub.io/api/v1/stock/market-status` | `exchange=US` |
| Finnhub | GET `/api/v1/stock/market-holiday` on the same host | `exchange=US` |
| Finnhub | GET `/api/v1/quote` | Each ticker as `symbol` |
| Finnhub | GET `/api/v1/company-news` | Each symbol, `from=2026-10-03`, `to=2026-10-10` |
| Finnhub | GET `/api/v1/calendar/earnings` | Each symbol, `from=2026-10-10`, `to=2027-01-08` |
| Finnhub | GET `/api/v1/stock/candle` | NVDA only, resolution 1, epoch-second bounds Oct 9 13:30–14:00Z |
| Hyperliquid | POST `https://api.hyperliquid.xyz/info` | `{"type":"perpDexs"}` |
| Hyperliquid | Same `/info` endpoint | `{"type":"metaAndAssetCtxs","dex":<discovered name>}` for all ten non-null DEXs |
| Hyperliquid | Same `/info` endpoint | `{"type":"l2Book","coin":<exact discovered target symbol>}` for all fourteen target listings |
| Hyperliquid | Same `/info` endpoint | `{"type":"candleSnapshot","req":{"coin":<symbol>,"interval":"5m","startTime":1791444900000,"endTime":1791617700000}}` for all fourteen listings |
| Binance | GET `https://web3.binance.com/build/api/v1/dex/market/rwa/tokens` | `binanceChainId=56`, combined run plus supplementary schema audit |
| Binance | GET `/build/api/v1/dex/market/rwa/underlying-profile` | Exact eligible BSC token identity for each target BStock representation |
| Binance | GET `/build/api/v1/dex/market/rwa/price` | Chain and exact contract through existing provider |
| Binance | POST `/build/api/v1/dex/market/price-info` | Existing read-only batched token identity body, each BStock representation |

Full actual Alpaca/Finnhub query parameters, opaque pagination tokens, Hyperliquid payloads, HTTP/business statuses and receipt timestamps are in the combined request ledger. Binance's existing safe ledger records endpoint/status/receipt, with public token identities in the corresponding result; signed wire URLs and headers are deliberately excluded. No other endpoint is claimed tested.

## Alpaca verification

**Authentication PASS; latest data PARTIAL; history PASS for the captured bounded windows; active-session freshness NOT_VERIFIED.** All history pages completed within the bound. Latest SIP/BOATS reads returned HTTP 403 for all three symbols; other reads returned 200. Their plan names are NOT_VERIFIED: successful authentication elsewhere plus feed-specific denials establish capability restrictions without identifying the exact subscription.

### Latest quote samples

All timestamps below are UTC on **October 9**; receipts are October 10. Price is bid/ask midpoint in USD, not a last trade or official close. All samples are STALE. Exact nanosecond strings, exchange codes, conditions, sizes, receipt times and uncertainty flags are retained in JSON; comparisons use microsecond datetime precision.

| Ticker | Requested feed | Midpoint USD | Bid / ask USD | Bid / ask size (raw) | Source UTC, Oct 9 | Receipt UTC, Oct 10 | Age seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TSLA | iex | 382.03 | 362.9 / 401.16 | 40 / 40 | 20:00:00.003294Z | 07:37:55.096708Z | 41875.093 |
| NVDA | iex | 231.505 | 222.06 / 240.95 | 100 / 100 | 20:00:00.003063Z | 07:37:56.238703Z | 41876.236 |
| GOOGL | iex | 351.285 | 333.62 / 368.95 | 40 / 40 | 20:00:00.013608Z | 07:37:57.470149Z | 41877.457 |
| TSLA | delayed_sip | 382.80 | 382.75 / 382.85 | 40 / 80 | 23:59:59.745923Z | 07:38:02.574526Z | 27482.829 |
| NVDA | delayed_sip | 229.315 | 229.3 / 229.33 | 800 / 900 | 23:59:58.763985Z | 07:38:02.944897Z | 27484.181 |
| GOOGL | delayed_sip | 351.605 | 351.6 / 351.61 | 80 / 40 | 23:59:47.989317Z | 07:38:03.237998Z | 27495.249 |
| TSLA | overnight | 386.71 | 378.12 / 395.3 | 1 / 25 | 08:00:00.669560Z | 07:38:06.432725Z | 85085.763 |
| NVDA | overnight | 233.56 | 232.96 / 234.16 | 19 / 19 | 08:00:00.675507Z | 07:38:06.746679Z | 85086.071 |
| GOOGL | overnight | 350.295 | 349.81 / 350.78 | 29 / 29 | 08:00:00.670728Z | 07:38:07.205278Z | 85086.535 |

IEX bid/ask venue codes were `V/V` for all three, corroborating the single-venue feed. Other successful responses did not echo a definitive feed identifier: requested-feed acceptance is not independent proof of delivery type or entitlement. The derived overnight sample uses `B/B` venue codes but that alone does not certify a real-time BOATS feed. IEX quotes are wide close-boundary quotes (`R` condition), unsuitable as official closing trades or consolidated NBBO.

Official Alpaca documentation distinguishes single-venue IEX, consolidated SIP, BOATS and its derived overnight feed; the latter's trades are delayed/adjusted. This diagnostic tested quotes rather than measuring that trade delay. No derived/delayed feed is promoted to a current reference. See [data sources](https://docs.alpaca.markets/us/docs/historical-stock-data-1) and [latest-access/history distinctions](https://docs.alpaca.markets/us/docs/market-data-faq).

### Historical depth, gaps and valid observations

Recent requested range: **Oct 8 00:00Z–Oct 10 00:00Z**. Counts are real validated completed bars per ticker/feed/interval, not independent episodes. No duplicates were found. Gaps include non-trading hours and absent eligible trade bars; they do not prove an outage. No missing slot is filled.

| Ticker | Requested feed | Interval | Validated bars | First bar UTC | Last bar UTC | Gaps > interval | Largest gap seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TSLA | iex | 1minute | 780 | 2026-10-08T13:30:00Z | 2026-10-09T20:36:00Z | 7 | 61440 |
| TSLA | iex | 5minute | 159 | 2026-10-08T13:30:00Z | 2026-10-09T20:35:00Z | 4 | 61500 |
| NVDA | iex | 1minute | 789 | 2026-10-08T13:30:00Z | 2026-10-09T20:11:00Z | 9 | 57600 |
| NVDA | iex | 5minute | 164 | 2026-10-08T13:30:00Z | 2026-10-09T20:10:00Z | 6 | 57600 |
| GOOGL | iex | 1minute | 781 | 2026-10-08T12:10:00Z | 2026-10-09T19:59:00Z | 4 | 61680 |
| GOOGL | iex | 5minute | 158 | 2026-10-08T12:10:00Z | 2026-10-09T19:55:00Z | 3 | 61800 |
| TSLA | sip | 1minute | 1792 | 2026-10-08T08:00:00Z | 2026-10-09T23:59:00Z | 95 | 28860 |
| TSLA | sip | 5minute | 384 | 2026-10-08T08:00:00Z | 2026-10-09T23:55:00Z | 1 | 29100 |
| NVDA | sip | 1minute | 1883 | 2026-10-08T08:00:00Z | 2026-10-09T23:59:00Z | 37 | 28860 |
| NVDA | sip | 5minute | 384 | 2026-10-08T08:00:00Z | 2026-10-09T23:55:00Z | 1 | 29100 |
| GOOGL | sip | 1minute | 1615 | 2026-10-08T08:00:00Z | 2026-10-09T23:59:00Z | 171 | 28860 |
| GOOGL | sip | 5minute | 378 | 2026-10-08T08:00:00Z | 2026-10-09T23:55:00Z | 6 | 29100 |
| TSLA | boats | 1minute | 407 | 2026-10-08T00:01:00Z | 2026-10-09T07:57:00Z | 190 | 57840 |
| TSLA | boats | 5minute | 167 | 2026-10-08T00:00:00Z | 2026-10-09T07:55:00Z | 22 | 57900 |
| NVDA | boats | 1minute | 568 | 2026-10-08T00:01:00Z | 2026-10-09T07:59:00Z | 186 | 57720 |
| NVDA | boats | 5minute | 186 | 2026-10-08T00:00:00Z | 2026-10-09T07:55:00Z | 7 | 57900 |
| GOOGL | boats | 1minute | 330 | 2026-10-08T00:01:00Z | 2026-10-09T07:59:00Z | 198 | 58200 |
| GOOGL | boats | 5minute | 162 | 2026-10-08T00:00:00Z | 2026-10-09T07:55:00Z | 28 | 58200 |

Every SIP 1m series contains **780/780 regular-session minutes** over two sessions; SIP 5m contains **156/156 regular slots**. IEX 1m regular counts are TSLA 777, NVDA 779, GOOGL 779; all IEX 5m regular counts are 156. Off-hours counts are below. Sparse IEX extended-hours observations do not establish comprehensive coverage.

| Ticker | Requested feed, 1m | Regular | Pre-market | Post-market | Legacy weekday overnight |
| --- | --- | --- | --- | --- | --- |
| TSLA | iex | 777 | 1 | 2 | 0 |
| NVDA | iex | 779 | 8 | 2 | 0 |
| GOOGL | iex | 779 | 2 | 0 | 0 |
| TSLA | sip | 780 | 298 | 423 | 291 |
| NVDA | sip | 780 | 300 | 464 | 339 |
| GOOGL | sip | 780 | 286 | 305 | 244 |
| TSLA | boats | 0 | 0 | 0 | 407 |
| NVDA | boats | 0 | 0 | 0 | 568 |
| GOOGL | boats | 0 | 0 | 0 | 330 |

These regime columns use the unchanged application calendar. **Important semantic gap:** its PREMARKET begins at 07:00 ET, so SIP data at 04:00–07:00 ET is classified `WEEKDAY_OVERNIGHT` by that calendar. The observed SIP range starts at 08:00Z = 04:00 ET and ends 23:59Z = 19:59 ET. It does not demonstrate true 20:00–04:00 ET overnight coverage. BOATS bars actually occur across the 20:00–04:00 ET overnight session, crossing UTC/New York dates. No calendar or Trust policy was modified to resolve this distinction.

Each ticker's SIP depth probe returned **31 real 1m bars, Jan 4, 2016 14:30–15:00Z**. This proves that specific old window is accessible, not uninterrupted ten-year retention. The current application calendar covers 2026–2028, so 2016 rows remain UNKNOWN for its regime classification. Each Saturday IEX and BOATS probe returned HTTP 200 with **zero bars**, consistent with closed cash-equity sessions. Delayed SIP/derived overnight historical endpoints were not tested through the adapter; it only allows IEX/SIP/BOATS history.

Historical feed identity is retained from the explicit request; the bar envelope does not independently echo it. Raw/unadjusted bars and disabled automatic ticker remapping preserve the requested convention but do not certify point-in-time corrections, corporate-action availability, historical official closes or liquidity. These sampled series are not persisted to the application.

Rate headers reported limit **200**, remaining **198–199** on captured responses. No 429, retry or load saturation was observed. Header values alone do not prove a daily quota, long-run throughput or contractual display/non-display rights. Actual active-session 120s freshness and 30s token alignment remain NOT_VERIFIED in this run.

## Finnhub verification

**Market status, event retrieval and bounded holiday/calendar retrieval PASS; complete event coverage PARTIAL; current-price eligibility UNAVAILABLE in this run; historical candles UNAVAILABLE.**

Market status: HTTP 200, `exchange=US`, timezone America/New_York, `isOpen=false`, `session=null`, `holiday=null`, source epoch `1791617890` (**Oct 10 07:38:10Z**), receipt **07:38:11.101987Z**. This describes the status query, not an equity-price timestamp. The holiday endpoint returned **62 rows**, Jan 2, 2023–Dec 24, 2027. 2026 Thanksgiving Nov 26 and Christmas Dec 25 were closures; Nov 27 and Dec 24 showed regular hours `09:30-13:00`. Their raw post-market string `13:00:17:00` has an ambiguous delimiter; it is retained, not silently parsed into an authoritative session. Calendar rows have no point-in-time publication ledger. No 2028 coverage was returned.

| Ticker | Price USD | Source UTC | Receipt UTC, Oct 10 | Age seconds | Quality |
| --- | --- | --- | --- | --- | --- |
| TSLA | 382.7 | 2026-10-09T20:00:00Z | 07:38:12.674400Z | 41892.674 | STALE |
| NVDA | 229.28 | 2026-10-09T20:00:00Z | 07:38:15.921804Z | 41895.922 | STALE |
| GOOGL | 351.66 | 2026-10-09T20:00:00Z | 07:38:19.243026Z | 41899.243 | STALE |

All three prices are stale October 9 close-time observations received Saturday. Their venue, quote-vs-trade details, live/delayed entitlement and independent NBBO status were not supplied/verified. The exact 20:00Z boundary is labelled POSTMARKET by the application calendar; it is not evidence of an actual post-market trade or a certified official closing auction.

News requests covered **Oct 3–10 inclusive**, with publication and ingestion stored separately and event IDs deduplicated within each response. Source attribution and first/last event URLs are retained without full article text.

| Ticker | Unique valid events | Earliest publication UTC | Latest publication UTC | Ingestion UTC |
| --- | --- | --- | --- | --- |
| TSLA | 244 | 2026-10-05T10:39:29Z | 2026-10-10T03:15:00Z | 2026-10-10T07:38:13.763582Z |
| NVDA | 249 | 2026-10-08T17:20:00Z | 2026-10-10T05:20:00Z | 2026-10-10T07:38:17.071998Z |
| GOOGL | 247 | 2026-10-07T11:38:56Z | 2026-10-10T06:02:32Z | 2026-10-10T07:38:20.412556Z |

No duplicates, invalid timestamps or out-of-window rows were found in these bounded responses. Counts near 250 and differing earliest dates do **not** establish exhaustive coverage of the requested week. Missing older events cannot be interpreted as “no news.” Deduplication is within symbol/response, not a claim that cross-ticker overlapping stories are independent. Today's ingestion must never be backdated to historical decision times.

Earnings requests Oct 10–Jan 8, 2027 returned one item each: **TSLA Oct 20, 2026; NVDA Nov 17, 2026; GOOGL Oct 27, 2026**, all `amc`. These are provider-reported upcoming dates, not independently confirmed issuer announcements or exact UTC release times. NVDA's `year=2027, quarter=3` is fiscal reporting metadata, not a claim the event occurs in calendar 2027. No historical publication/revision timestamp was exposed.

The optional NVDA 1m candle request returned **HTTP 403**; no historical candle observations were obtained. Finnhub is not a verified primary historical source on this account. Headers reported limit **60**, remaining **52–59**; no 429 or deliberate saturation. Account plan, effective news retention, actual quote delay and redistribution entitlements remain NOT_VERIFIED. Endpoint construction and header auth were checked against the [official SDK](https://github.com/Finnhub-Stock-API/finnhub-python/blob/master/finnhub/client.py) and [API documentation](https://finnhub.io/docs/api).

## Hyperliquid HIP-3 verification

**Public discovery and active order-book retrieval PASS; secondary price signals PARTIAL; official underlying equity reference UNAVAILABLE by design.** No wallet or credentials were used. Ten DEXs were dynamically returned: `xyz`, `flx`, `vntl`, `hyna`, `km`, `abcd`, `cash`, `para`, `mkts`, `io`. Metadata/context responses were index-matched before extracting exact `DEX:TSLA`, `DEX:NVDA`, `DEX:GOOGL` names; GOOG and similarly named instruments were not substituted.

Fourteen target listings were found. **Three xyz listings were not marked delisted and had non-empty books plus real historical candles.** Eleven were explicitly delisted: flx TSLA/NVDA; km TSLA/NVDA/GOOGL; cash TSLA/NVDA/GOOGL; mkts TSLA/NVDA/GOOGL. Those returned empty books and zero historical candles, despite HTTP 200 and frozen mark values. They are UNAVAILABLE for useful current signals. A current timestamp on an empty book does not imply recent trading.

| Exact instrument | Asset ID | Raw context mark | Raw funding | Book bid / ask | Best bid / ask size | Book UTC, Oct 10 | Book receipt UTC, Oct 10 | Book age seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| xyz:TSLA | 110001 | 382.78 | 0.0000049502 | 382.69 / 382.7 | 13.65 / 2.635 | 07:38:23.150000Z | 07:38:23.499069Z | 0.349069 |
| xyz:NVDA | 110002 | 230.11 | 0.0000054438 | 229.98 / 229.99 | 18.152 / 20.15 | 07:38:23.687000Z | 07:38:24.114658Z | 0.427658 |
| xyz:GOOGL | 110012 | 352.4 | -0.0000041581 | 352.24 / 352.27 | 5.53 / 3.04 | 07:38:24.225000Z | 07:38:24.738227Z | 0.513227 |

Asset IDs follow the documented `100000 + dex_index * 10000 + index_in_meta` formula. Metadata, size decimals, max leverage and growth flags are retained in JSON. The book bid/ask values above are positive and uncrossed, with positive best sizes; each side has 20 returned levels. Sizes and raw funding rates are kept in native API units without invented share equivalence, funding horizon, annualization or notional conversion.

All three context marks/funding values were **retrieved at 07:38:23.222651Z**, but `metaAndAssetCtxs` supplies no source timestamp. Their quote-age/alignment is therefore NOT_VERIFIED. The table's timestamps/ages apply **only to the subsequently fetched order books**, not marks, oracles, funding or last trades. Context midpoints and later book midpoints need not match because requests are separate.

Each active listing returned **577 5m candles**, of which **576 completed** within Oct 8 07:35Z–Oct 10 07:35Z; first bar starts Oct 8 07:35Z and last completed bar starts Oct 10 07:30Z. No duplicate timestamps or gaps over five minutes were found. The incomplete current bar was excluded. Coverage checks validated instrument/interval/time identity; this diagnostic did not independently certify every historical OHLC/volume value or point-in-time revision. Counts are temporal coverage, not Trust-ready price samples.

Per active listing, completed temporal counts under the existing calendar were **156 regular, 60 pre-market, 96 post-market, 221 weekday overnight, 43 weekend**. This demonstrates this sampled perpetual market spans weekend/off-hours; it does not prove continuous long-term operation. No earlier retention boundary or holiday-session execution behavior was probed.

Public metadata verifies exact exchange symbols and asset IDs but does not provide a legal/ISIN-level underlying-stock mapping. That mapping remains NOT_VERIFIED beyond explicit ticker names. Marks, oracles, funding and derivative basis may differ from cash equity. These instruments cannot replace an independent underlying quote, Binance RWA candles, RWA liquidity or economic token/share ratios. No 429 or numeric rate-limit headers were observed; maximum capacity was not tested. API methods, timestamp fields and asset IDs follow official [info endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint), [perpetual metadata](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals), [asset IDs](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/asset-ids) and [rate limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits).

## Existing Binance cross-check and independent reference integrity

The current catalog yielded **three eligible BStock target representations** after existing validation, with **34 quarantined catalog rows across the full universe**. A supplementary raw-target audit found six target records: BStock and Ondo for each ticker. The three Ondo records fail `statusInfo.marketStatus` literal validation. They are present upstream, not absent assets; this diagnostic neither repairs undocumented values nor bypasses quarantine. This is a current API/schema compatibility blocker, separate from earlier successful Ondo evidence.

| Ticker | Token / issuer BStock | Current token/share ratio | Token USD | Token source UTC, Oct 10 | Receipt UTC, Oct 10 | Age seconds | Reported 24h volume USD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TSLA | TSLAB | 1.000000000000000000 | 382.92000000 | 07:37:33.632000Z | 07:38:36.268207Z | 62.636207 | 14069674118 |
| GOOGL | GOOGLB | 1.000478058978107511 | 352.64000000 | 07:38:36.667000Z | 07:38:37.412276Z | 0.745276 | 5103912817 |
| NVDA | NVDAB | 1.000778223752807865 | 230.26000000 | 07:38:34.630000Z | 07:38:38.096739Z | 3.466739 | 17054711459 |

All Binance reads returned HTTP 200/business 0. Exact BSC contracts are retained in JSON. Ratios are current profile values only: no historical effective-date claim or backfill. Each price-info result still has `liquidity=null`; market status in the accepted metadata remains UNKNOWN. Reported 24h volume is preserved with the existing provider's USD-unit provenance, but is not a liquidity measurement, executable depth or historical activity ledger. The underlying-market endpoint was not called in this run; UNKNOWN metadata does not prove issuer trading is currently open or closed.

**Binance RWA `referencePrice` is excluded as an independent reference.** It is token-derived; see [official RWA documentation](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/rwa-data). No provider fallback, token-derived comparison or live parity was calculated. Equity is hours old while token observations are current; token/share normalization alone cannot correct that timestamp mismatch. Perpetual marks have different product identity and no source timestamp. Small numerical differences across these samples are not verified stock-premium or forecast signals.

## Session-aware responsibilities and proposed priorities

These are recommendations subject to validation and a separately authorized implementation, **not changes to current production selection**.

| Session | Candidate independent-equity role | What the evidence permits / still blocks |
|---|---|---|
| Regular | Alpaca explicitly identified feed; SIP if actually entitled, otherwise explicitly disclosed IEX | Old SIP history is accessible; latest SIP denied. IEX access/venue verified but active-session freshness, spread quality, reference admissibility and 30s alignment still need proof |
| Pre-market | Explicit eligible Alpaca feed plus proper venue/session mapping | SIP bars observed from 04:00 ET; current calendar's 07:00 ET pre-market boundary needs a separately scoped semantic review. Sparse IEX history is not consolidated coverage |
| Post-market | Explicit eligible extended-hours equity feed | SIP history observed to 19:59 ET; stale delayed quotes cannot be promoted to current LIVE references |
| Weekday overnight | Eligible real BOATS observations with actual delay/quality evidence | BOATS historical bars exist; latest BOATS denied. Derived overnight quote is stale and not verified real-time. Prior official close can be contextual only under an explicit close-reference policy |
| Weekend / cash-equity holiday | Verified previous official regular close, explicitly labelled closed-session reference | No current cash-equity quote demonstrated. Current HIP-3 books are optional secondary derivatives, never replacement cash quotes. Previous official close was not newly certified here |
| Early close / DST | Authoritative exchange calendar plus venue-specific session definitions | Existing calendar/DST/early-close tests pass; Finnhub rows are useful corroboration, with malformed post-market strings and finite coverage. Do not infer halts or full venue schedules |

Binance remains the tokenized-asset source; Alpaca is the proposed independent cash-equity source after validation; Finnhub contributes attributed event/session context and optional secondary quotes; Hyperliquid contributes separately typed derivative signals. Massive remains configured as production equity source and its prior current entitlement denial is not bypassed. No provider's HTTP success establishes public redisplay rights or removes the need for separately verified source policy.

## Historical 30/30/3 readiness and remaining blockers

**NOT_VERIFIED for new qualifying counts; existing measured qualifying evidence remains 0/30 baseline, 0/30 opening-model, 0/3 real analogues.** No production sample/episode builder was run on these diagnostic captures and no observations were inserted into production history. A few thousand bars are not independent eligible episodes.

The preserved [historical investigation](TRUST_BLOCKER_HISTORICAL_REPORT.md) found 48 full-span representation/reopening windows (43 in the 180-day scope), 31 distinct opening targets, but zero complete eligible samples. Missing historical as-of features, rather than a demonstrated loss of eligible rows at a join, remained the dominant blocker. This run's two recent cash-equity sessions add no completed new weekend/reopening episode: the Oct 10 weekend has not yet reopened. The 2016 probe is outside the existing calendar/lookback. Hyperliquid weekend bars are derivatives, not substitute tokenized-equity episodes.

Remaining requirements:

1. Regular-session independent equity freshness ≤120s and actual token/equity observation alignment ≤30s; no substitution of request receipt or candle start for quote time. This Saturday run cannot certify either.
2. Explicit source/feed/delay/quality and official-close/extended-hours policy, with exact session semantics. Existing production Trust still admits Massive equity sources only; Alpaca's UNKNOWN entitlement and the lack of reference-policy integration are intentional unresolved boundaries.
3. Historical effective-dated token/share ratios for exact contracts. Today's ratios cannot normalize old observations. Cash-equity history and HIP-3 metadata do not solve this.
4. Authoritative time-stamped current/historical token liquidity, activity units and required dense token feature windows. Binance null price-info liquidity remains unresolved; a perpetual book measures a different market.
5. Point-in-time feature/revision/corporate-action availability and complete decision-time event coverage. Newly ingested news/history cannot be treated as known at old decision times. A retrospective bar is not automatically an official close or live historical quote.
6. Enough genuine eligible completed episodes in each ticker/representation/regime/ratio/reference-policy partition to establish the unchanged 30/30/3 minima. No pooling of different assets, duplicated issuer outcomes, synthetic rows or regimes.
7. Current Ondo market-status schema mismatch must be verified against its official contract before a separately authorized compatibility change; no quarantine bypass here.

The combined sources **partially solve raw data access**, not the complete production Trust requirements. Exact SWAP/RFQ transaction/simulation/settlement equivalence and wallet runtime blockers are independent and untouched.

## Reproduction and validation

Run from the repository root, with configured secrets in ignored `.env` or the process environment. Do not put secrets in command arguments or enable HTTP debug logging. Finnhub and Hyperliquid settings are consumed directly by this diagnostic; changing them does not integrate a provider into production. Each run requires a new output path, explicit read-only flag and at most two days for the recent Alpaca history range. Recent/event/Hyperliquid retrieval timestamps naturally differ on repeat runs; the recorded date windows and statuses above belong to this run.

```sh
PYTHONPATH=backend .venv/bin/python scripts/verify-alpaca-readonly.py --live \
  --start 2026-10-09T00:00:00Z --end 2026-10-10T00:00:00Z \
  --output docs/evidence/ALPACA_CONFIGURED_NVDA_NEXT.json
PYTHONPATH=backend .venv/bin/python scripts/diagnose-multi-provider.py --live-read-only \
  --start 2026-10-08T00:00:00Z --end 2026-10-10T00:00:00Z \
  --output docs/evidence/MULTI_PROVIDER_DATA_NEXT.json
PYTHONPATH=backend .venv/bin/python scripts/diagnose-multi-provider.py --live-read-only \
  --catalog-audit-only --output docs/evidence/MULTI_PROVIDER_CATALOG_AUDIT_NEXT.json
.venv/bin/python -m pytest backend/tests/integration/test_alpaca.py backend/tests/unit/test_multi_provider_diagnostic.py -q
.venv/bin/python -m pytest -q
npm test
npm run build
.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
PYTHONPATH=backend .venv/bin/python scripts/generate-ui-contracts.py --check
.venv/bin/python scripts/check-security.py
git diff --check
```

Final backend regression: **1,486 passed**, including **21 new diagnostic tests**. Two existing Pydantic serializer warnings come from deliberately malformed allowance fixtures. Relevant Alpaca/diagnostic subset: **68 passed**. Frontend: **273 passed, 14 files**. TypeScript/Vite build, Ruff lint, Ruff format check (216 Python files), seven generated frontend contracts, configured-secret/security audit and `git diff --check` passed. The security audit verified configured-secret leakage, Git `.env` exclusion, Docker `.env` exclusion and frontend secret isolation.

All 19 pre-existing working-file SHA-256 fingerprints matched their before-run values. `docs/MASTER_SPEC.md` retained SHA-256 `f69a9bd01a622c001c3ec6cb654e00562f6b3d03a8310f9e5ccf68efe4b49c84`. This is preservation evidence, not a new production gate certification.

No browser recheck was necessary for a diagnostic-only increment with no frontend/application changes. Unit tests use synthetic responses solely to verify allowlists, safe evidence, denial/429 handling, calendar/DST/early-close semantics, missing/duplicate coverage, explicit authorization and catalog quarantine. They do not count as real provider data or entitlement evidence.

## Files introduced by this increment

- `scripts/diagnose-multi-provider.py`: isolated bounded diagnostic and optional catalog schema audit.
- `backend/tests/unit/test_multi_provider_diagnostic.py`: offline safety/measurement tests.
- `docs/MULTI_PROVIDER_DATA_DIAGNOSTIC.md`: this report.
- `docs/evidence/ALPACA_CONFIGURED_NVDA_20261010.json`: existing Alpaca command's authenticated read results.
- `docs/evidence/MULTI_PROVIDER_DATA_20261010.json`: combined read-only measurements/ledger.
- `docs/evidence/MULTI_PROVIDER_CATALOG_AUDIT_20261010.json`: raw-target catalog rejection explanation.

No existing file was edited by this increment. All 19 prior working-tree files retain their starting byte fingerprints, including application code, `.env.example`, prior README/API/architecture/gate changes and the previous Alpaca diagnostic/report. The authoritative master remains unchanged. Local frontend build output is ignored/generated.

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

**Next smallest implementation increment:** a separately authorized typed Finnhub read-only event/status/calendar adapter using the existing transport, publication/ingestion provenance and explicit coverage/format uncertainty, without changing Trust reference selection. Before a session-aware equity reference engine is implemented, perform a bounded regular-session Alpaca IEX freshness/spread and Binance source-timestamp alignment check, then resolve single-venue reference eligibility and session boundaries. Optional HIP-3 signal integration remains later scoped work. None of these steps begins here.
