# Trust blockers — historical data investigation and isolated backfill

Measured **October 6, 2026, 21:47:07–22:04:38 UTC**, or **October 7, 03:17:07–03:34:38 IST**. The regular US session was closed. This task investigated data and appended only isolated raw diagnostic history. Production code, databases, Trust requirements, gates, configuration and prior reports were preserved.

```text
HISTORICAL_RATIO_UNAVAILABLE
QUALIFYING_BASELINE_EPISODES=0/30
QUALIFYING_OPENING_MODEL_EPISODES=0/30
REAL_ANALOGUES=0/3
LIQUIDITY_AUTHORITY=UNVERIFIED
TRUST_GATE=BLOCKED (unchanged)
```

## Data availability versus pipeline

**The dominant qualification blocker is missing historical as-of feature evidence. Raw price capture was also incomplete and has now been substantially expanded.** No otherwise eligible real episode was found being lost by a timestamp join.

The existing databases contain 122 distinct LIVE token records, 2,083 historical equity BAR records and one REGULAR_CLOSE record referring to an already captured minute. Thus the SQL inventory has 2,084 equity records, not 2,084 distinct bars. Existing LIVE Trust samples and Trust episodes are both zero. The previous 122/2,083 evidence remains valid for its captured scope; it was not the limit of provider historical availability.

The bounded initial capture obtained 4,437 Binance bars. Deeper official pagination recovered another 2,899, for **7,336 newly captured real Binance bars**. Combining these with existing candles and deduplicating source/contract/interval/event timestamps gives **7,351 distinct official historical candles**. The first isolated audit is archived alongside the final audit; old evidence is not replaced.

Pipeline findings:

- `HistoricalIngestion` paginates toward older Binance timestamps. Inclusive upper-bound returns and ignored lower bounds are quarantined by existing validation. This diagnostic likewise records exclusions and requires advancing cursors. The initial 20-page hourly cap left older available data uncaptured; deepening removed that cap as the explanation for the reported earliest hourly dates. Empty responses remain bounded observations, not absolute retention guarantees.
- `DataRepository.list` has a 1,000-record limit. This investigation uses direct read-only SQL for the full inventory and file captures for the backfill, so this limit does not hide equity rows. `TrustRepository` has a separate 5,000-history bound; zero real samples/episodes never reach it.
- `TrustService` constructs eligible samples from verified references and PRICE_INFO liquidity, then persists samples only with complete bounded news coverage. `EpisodeBuilder` consumes these samples, not raw candles. Historical CANDLE rows are not silently converted to fresh PRICE_INFO inputs. Missing required evidence prevents sample construction before baseline/analogue joins.
- The existing Binance candle adapter attaches the currently supplied metadata ratio to historical observations. That attached number is **not a historical effective-time ledger** and is not accepted here as normalization evidence. Existing records remain untouched. Every new raw candle has `historical_ratio=null`, unknown volume units, null historical liquidity and actual first-seen time.
- Baseline/analogue eligibility partitions by stock, issuer, chain, contract, regime, ratio, reference kind and policy. Summing different issuers, ratio versions or regimes cannot satisfy one scope's minimum. A raw reopening candidate also is not an `EpisodeBuilder` episode: the latter requires actual eligible features throughout a completed 30-minute bucket.

This identifies an incomplete raw collection stage and missing as-of inputs, rather than proving a faulty join on a complete eligible feature dataset. A production historical-replay integration is not introduced by this task.

## Official token history by representation

Times are UTC **bar starts**, not receipt times or exact last-trade timestamps. New Binance timestamps are explicitly milliseconds; GeckoTerminal OHLCV timestamps are seconds. Counts below deduplicate historical candle events by interval.

| Official Binance candle coverage | BStock NVDAB | Ondo NVDAon |
|---|---|---|
| Existing application token records | 23: 3 candles, 15 price/info records, 5 unit-unverified trades | 99: 77 candles, 17 price/info records, 5 unit-unverified trades |
| Earliest retained official historical observation | Jun 12 00:00 | Mar 3 07:00 |
| Latest official historical candle start | Oct 6 10:00 | Oct 5 23:00 |
| Distinct official candles, old plus new | 2,805 | 4,546 |
| Daily candles | 107, Jun 12–Oct 5 | 174, Mar 4–Oct 5 |
| Hourly candles | 2,388, Jun 12 03:00–Oct 6 10:00 | 4,102, Mar 3 07:00–Oct 5 23:00 |
| Captured minute candles | 310, Jun 15 13:01–Oct 5 13:29 | 270, Apr 13 13:05–Oct 5 13:27 |
| Largest hourly gap | 612,000s: Sep 13 23:00 → Sep 21 01:00 | Same 612,000s gap |
| Largest daily gap | 691,200s, 8 days | 777,600s, 9 days |
| Historical economic ratio | Unavailable | Unavailable |

Minute retrieval targeted the final 30 minutes before the 26 in-window reopenings, not continuous months of minute history. Large gaps between requested minute windows therefore must not be interpreted as exchange outages. Within-window insufficiency is measured separately below. Hourly/daily gaps are actual absent timestamps in the retained provider coverage; no missing interval is padded and no cause, including an absence of trading, is invented. Sparse trade records with unverified price units are excluded from historical price features.

Separate current price-info probes observed BStock at Oct 6 **21:47:58.630 UTC** and Ondo at **21:47:56.439 UTC**, received at **21:47:58.800654 UTC**. These were liquidity-investigation reads, with no contemporaneous independent-equity request and no alignment claim. They are not new application observations or historical episodes.

The [official candle contract](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/general-data) supplies historical OHLC/volume/timestamp/trade-count arrays and before/after pagination. Historical economic ratios and historical liquidity are not returned by this operation. Historical candle volume units are not inferred from current price-info or another vendor's OHLCV.

## Secondary GeckoTerminal coverage

The two previously verified diagnostic pools are retained. They do not become authoritative token-price sources. The recovery appended **2,329 real older Ondo hourly rows**; BStock's earlier-than-Jul-29 query returned no additional bars. No synthetic fill was requested.

| Pool-scoped completed history | BStock selected pool | Ondo selected pool |
|---|---|---|
| Daily | 69, Jul 29–Oct 5; max gap 1 day | 182, Apr 6–Oct 5; max gap 2 days |
| Hourly | 1,667, Jul 29 07:00–Oct 6 17:00; max gap 1 hour | 3,327, Mar 3 07:00–Oct 6 17:00; max gap 93,600s (26h), 717 gaps over 1h |
| Minute, deduplicated prior captures | 1,998, Oct 4 19:26–Oct 6 18:27 | 684, Sep 24 22:09–Oct 6 18:26 |

The BStock minute history contains two separately requested windows; the gap between them is a capture boundary. Its final pre-opening Oct 5 window contains dense actual rows. Ondo's minute history remains sparse, including a 22,380s gap. Earlier reports' endpoint-specific counts are preserved; union/deduplication explains these combined counts. Pool creation timestamps are metadata, not earliest captured-history claims. Neither bounded retrieval proves absolute provider retention.

## Independent equity and calendar coverage

**Historical equity target access succeeds.** All **62 new Massive historical reads** returned HTTP 200/business OK, one validated completed bar per endpoint. There are 31 actual previous-close/first-five-minute-opening pairs. Exact millisecond ranges use the existing signed/authenticated read-only transport, with its 12.1-second request spacing. This does not retest or resolve denied current Snapshot/NBBO entitlement.

- Existing 2,083 Massive BAR records cover Oct 2 08:00–Oct 5 23:59 UTC, including minute data and 192 five-minute bars. They remain stored unchanged.
- Added close bars span Mar 6 20:59–Oct 2 19:59 UTC; added opening bars span Mar 9 13:30–Oct 5 13:30. These are 31 targeted pairs, not continuous equity history between March and October.
- Old plus new Massive BAR captures contain **2,143 unique interval/timestamp events**: 1,921 one-minute and 222 five-minute. Of the 62 new endpoint rows, two repeat existing events. No revision conflict was found in the paired close/target prices.
- Previously captured Twelve Data history remains diagnostic-only: 1,560 one-minute and 312 five-minute bars across Jan 2/5 and Oct 2/5. No new Twelve Data request or production integration occurred. January samples are outside the current 180-day audit; the large January–October gap is unsampled coverage.

The [Massive aggregate contract](https://www.massive.com/docs/rest/stocks/aggregates/custom-bars) supports the tested date/millisecond windows. A previous reference is the actual minute ending at the calendar's regular close. The target is the actual five-minute bar beginning at regular open and completing five minutes later. Opening return is calculated with Decimal precision 256 and retained as **posthoc outcome only**. Historical adjusted bars are not current LIVE quotes and their historical revision/first-publication ledger remains unverified.

The existing calendar is `NYSE-2026-10-06`, America/New_York, with verified schedule coverage Jan 1, 2026–Dec 31, 2028. Every investigated date is covered, including March DST and holiday-adjusted previous sessions. The 180-day audit contains **26 distinct weekend/holiday reopenings**. Calendar bounds are not the observed blocker; the schedule does not establish unscheduled halts or historical issuer restrictions.

## Historical ratio investigation

**Classification: HISTORICAL_RATIO_UNAVAILABLE for both representations and all evaluated episode dates.** This is the result for usable as-of economic ratios in the reviewed Binance APIs/local evidence, not a claim that every possible external archive is nonexistent.

The current [Binance RWA contract](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/rwa-data) has six operations: platforms, price, search, underlying-profile, tokens and underlying-market. The reviewed ratio-bearing profile/catalog provides current `tokenToShareRatio`; no effective-dated historical ratio query or version ledger is exposed. Both actual profile reads returned the expected identities and current ratios, with receipt provenance only. Existing metadata versions observed on October 6 do not establish ratios for March–October episode decisions. No constant-ratio assumption is made.

BStock's returned collateral proof has `supported=true` and a null URL. Ondo's returned daily and monthly attestation URLs both returned **403** in this investigation; their bodies are not treated as ratio evidence. The separate official [Ondo multiplier-history API](https://docs.ondo.finance/api-reference/assets/get-shares-multiplier-history-for-an-asset) documents a historical change ledger. The anonymous `range=all` probe again returned **403**; no local `ONDO_API_KEY` or `ONDO_GLOBAL_MARKETS_API_KEY` is configured. No historical multiplier values were obtained. Access would still require exact contract/economic-ratio mapping and effective-time/revision/availability validation.

General backing statements, dividend/split documentation and scaled-display multiplier specifications are not substitutes for a verified deployed-contract economic ratio ledger. Current Binance ratios were retained separately and never attached to the new historical bars.

The CLI's current Binance schema download returned **202**, not a successfully parsed schema. The reviewed official web documentation/schema and actual profile responses provide the contract evidence; the 202 body is not used as proof of absent endpoints. Public GeckoTerminal Swagger returned 200.

## Candidate construction, validation and rejection

There are **48 full-span representation-windows**: 17 BStock and 31 Ondo, corresponding to **31 distinct NVDA reopening dates**. Five older Ondo dates lie outside the current 180-day baseline lookback. Within that lookback there are **43 representation-windows**, corresponding to **26 distinct stock openings**. Issuer-scoped pairs sharing an opening date are not independent stock outcomes.

For each candidate the audit records the calendar close, real off-hours token rows, raw token close-time anchors when present, end-window density, independent close/opening bars, Decimal opening return, missing features and rejection reasons. All normalized exposure/deviation and required-feature outputs remain null when the ratio/as-of evidence is unavailable. Every full-span candidate has a rejection ledger.

| Independent validation stage, 180-day window | BStock /17 | Ondo /26 |
|---|---:|---:|
| Real primary intraday token data during closure | 17 | 26 |
| Exact independent close + completed first 5m opening bar | 17 | 26 |
| Raw token bar completing at previous close, primary or secondary | 14 | 26 |
| Primary minute density alone passes | 9 | 2 |
| Secondary minute density alone passes | 1 | 0 |
| Verified historical economic ratio | 0 | 0 |
| Historical authoritative liquidity | 0 | 0 |
| Comparable verified historical volume units | 0 | 0 |
| Point-in-time feature/revision availability | 0 | 0 |
| Decision-time historical news coverage | 0 | 0 |
| Complete eligible Trust samples | 0 | 0 |

The cumulative **primary** validation funnel is **17 →17 →9 →0** for BStock and **26 →26 →2 →0** for Ondo: token rows, equity target, density, historical ratio. All subsequent cumulative stages remain zero. Raw close-time anchors do not prove a fresh historical quote or as-of ratio; that independent diagnostic count is not an extra production gate.

Density checks preserve the existing two-minute boundary/gap limits for a completed 30-minute window. Bar completion time is used to inspect raw minute coverage; a candle is not relabeled an eligible PRICE_INFO observation. The nine/two density passes do not certify the remaining mandatory features.

Primary density fails for **8 BStock and 24 Ondo** in-window candidates. Every one of the 43 in-window candidates fails historical ratio, authoritative liquidity, candle-volume units, first availability/revisions, historical decision-time news and complete Trust-feature requirements. Three BStock candidates lack an exact raw close-time token anchor for a weekend-return calculation. All five additional older Ondo candidates have real off-hours hourly data and equity targets, but lack dense minute features and all the as-of requirements; they are also outside the current baseline lookback.

New history was first seen in this run, after the historical decisions. Historical news already stored has October capture provenance and cannot be backdated to those decisions. These are historical availability failures, not a reversal of accepted current decision-window news coverage. The opening bar/outcome is always after the decision and excluded from features.

Result: **0/30 baseline episodes, 0/30 opening-model episodes, 0/3 eligible real analogues**. Thirty-one measured opening returns are outcomes with incomplete features, not qualifying model samples. No regression/model, agent, prediction or analogue vector was constructed from them.

## Liquidity authority

```text
LIQUIDITY_AUTHORITY=UNVERIFIED
```

Both selected pools are PancakeSwap V3 on **BSC / chain 56**, with the exact NVDA token as base and **USDT** `0x55d398326f99059ff775485246999027b3197955` as quote. Selection preserves the earlier reproducible rule: largest reported reserve among the previously enumerated exact-token active stable-counterasset pools, for diagnostics only. Enumeration is not exhaustive and selection is not an execution route recommendation.

| Measurement | BStock | Ondo |
|---|---|---|
| Token | `0x02fca66c1d1afb4e2a7884261eb00f63598a7436` | `0xa9ee28c80f960b889dfbd1902055218cba016f75` |
| Diagnostic pool | `0x8fb4243b553ac29ba088acf00b9b7da24bd6690c` | `0xb90bdbfbdffd4af5a636b5805539edeafb969308` |
| GeckoTerminal reported pool reserve, USD | 5,826,139.6028 | 9,700.7778 |
| Reported base-token price, USD | 240.611269915307 | 238.56065702881 |
| Pool 24h volume, USD | 4,402,208.1900015 | 362.5391169546 |
| GeckoTerminal receipt UTC, Oct 6 | 21:58:17.941157 | 21:58:34.075736 |
| Verified reserve measurement timestamp/block | Unavailable | Unavailable |
| Historical reserve/liquidity values in OHLCV | Unavailable | Unavailable |
| Same pool in Binance top-pool response | Yes | No |
| Binance liquidity for this pool, USD | 5,818,445.525510348498572649 | Not returned for this pool |

Binance's [top-pool operation](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/general-data) reports pool liquidity in USD and token composition. The actual BStock response has 15 pools, 10 with non-null values, received at 21:47:08.181520 UTC. Ondo has 8 pools, all liquidity values null, received at 21:47:34.090687. Binance price-info still has `liquidity=null` for both tokens. Provider-specific scope and receipt times are preserved; the two BStock reserve values are not a synchronized comparison.

These measurements establish current **pool-data availability**, including a primary-source BStock pool identity match. They do not establish fresh historical/as-of measurements, current-tick executable depth, price impact, aggregate route coverage or complete token-market equivalence. Receipt time, server-envelope timestamp, pool creation time and last token-price time are not substituted for liquidity measurement time. No reserve summation or silent replacement of the existing Trust liquidity metric occurs. Ondo's selected experimental pool is not even in the returned Binance top-pool list. Neither representation passes the unchanged authoritative-liquidity requirement.

## Achievability and exact remaining blockers

**30/30/3 is not achieved or presently supported by eligible evidence.** Raw equity target availability has improved to 31 real stock openings, and deep token history exists. This rules out a blanket conclusion that free/existing sources have no useful historical prices. Raw targets and dense intervals alone are insufficient.

The unchanged 180-day baseline/analogue scope contains 26 reopening dates, not 30. Baseline episodes are completed 30-minute feature windows and can be multiple per date when properly observed; they are not necessarily one per opening. Full-span Ondo has 31 posthoc opening-target candidates, but five are outside that baseline lookback and all lack required as-of evidence. Opening-model feasibility remains conditional on complete eligible features and its separately verified scope; this task does not implement it or change any lookback/minimum. Historical ratio changes further partition baseline/analogue scopes.

Exact remaining external/data prerequisites:

1. Historical effective-dated economic ratios for both exact contracts; accessible issuer/event archives with verified raw-token/share mapping and revision/availability provenance.
2. Authoritative time-stamped liquidity/activity with comparable scope and units, including historical coverage. BStock pool reserves improve discovery; they do not supply the required historical/token-market measurement. Ondo primary liquidity remains absent.
3. Verified historical candle volume units, dense required observation windows and missing opening-window/close-anchor coverage. Coarse candles cannot be padded into minute samples.
4. Point-in-time feature, corporate-action/price revision and historical news availability. Newly fetched records cannot become evidence that the system knew their values at the old decision time.
5. Enough qualifying completed samples within each permitted stock/representation/regime/ratio/reference scope, then 30 baseline episodes, 30 opening-model episodes and 3 eligible analogues. No synthetic or duplicated issuer outcomes count.
6. Independent current-reference eligibility remains a separate unresolved integration prerequisite. Accepted Twelve Data last-quote freshness evidence is preserved; the 30-second alignment diagnostic was not run in this task, and Twelve Data was not admitted to production Trust. Massive current-equity denial was not retested or bypassed.

TRUST_GATE remains BLOCKED, Opportunity remains BLOCKED_BY_TRUST, and all LIVE gates remain BLOCKED. Next work stays within Canonical Phase 2 data remediation, with separately authorized provider/availability verification. No Opportunity, agent, ML or execution implementation begins.

## Files, evidence and verification

New files in this task:

- [Isolated collector/auditor](../scripts/investigate-trust-blockers.py).
- [15 synthetic diagnostic control tests](../backend/tests/unit/test_trust_blocker_investigation.py).
- [Actual raw historical backfill and read ledger](evidence/TRUST_BLOCKER_HISTORICAL_BACKFILL.json).
- [Final per-window audit](evidence/TRUST_BLOCKER_HISTORICAL_AUDIT.json).
- [Preserved initial audit before deepening](evidence/TRUST_BLOCKER_HISTORICAL_AUDIT_INITIAL.json).
- [Actual attestation-link denials](evidence/TRUST_BLOCKER_RATIO_ATTESTATIONS.json).
- This report.
- `docs/evidence/TRUST_BLOCKER_VERIFICATION.json` records final preservation and verification results.

Commands used, in order: `.venv/bin/python scripts/investigate-trust-blockers.py --collect`, then `--audit` for the initial snapshot, then `--deepen`, preservation of the initial audit, and `--audit` for the final snapshot. Collect/audit refuse existing output overwrite. Deepening appends to this task's capture once and preserves the earlier rows. No command imports observations into application databases.

**Tests:** all 326 backend tests PASS (311 retained, 15 new synthetic diagnostic controls), all 47 frontend tests PASS; Ruff lint/format PASS for 74 Python files; established security audit and extended configured-secret checks PASS. The existing Starlette/httpx deprecation remains. Application source and frontend are unchanged, so no browser/build rerun was required for this data-only task.

Final checks confirm all **198 pre-existing source/document/data artifacts remain byte-identical**, including every database, production Trust source, both master copies, prior reports, alignment setup and formal gate evidence. No Git metadata exists; preservation uses a pre-task SHA256 manifest. The formal Trust gate remains `f84e8489a756df2924b9a21f5486d84d563c9270362f076e0463f6c79c8aabdd`.

The alignment runner and saved instructions remain unchanged. Its automatic job was stopped by the prior explicit request; it awaits the saved manual regular-session run and was not rearmed here. No provider `/quote`, wallet, order, RFQ submission, swap, broadcast or execution endpoint was called during this investigation. Stop after this data investigation.
