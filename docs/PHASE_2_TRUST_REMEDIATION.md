# Canonical Phase 2 capability remediation

Date: 2026-10-06. **TRUST_GATE=BLOCKED.** Reused the completed Trust implementation and all 282 backend / 47 frontend tests. Only the verified news-window coverage defect was corrected. No Opportunity, agents, execution, risk, wallet, simulation, or financial classification thresholds changed.

## Blocker audit

| BLOCKER | CAUSE | REQUIRED CAPABILITY | CURRENT CAPABILITY | CAN BE REMEDIATED? | REMEDIATION | IF NOT REMEDIABLE — SAFE FALLBACK |
|---|---|---|---|---|---|---|
| Current independent equity reference | Massive returns HTTP403 / NOT_AUTHORIZED with entitlement-denial wording for snapshot, NBBO and alternative last trade | Independently verified current equity price, age <=120s and current skew <=30s during REGULAR | News200 authenticates the same configured key; current reads denied; exact billing plan UNKNOWN | Not with demonstrated account permissions | Verified official paths and fresh denial categories; no implementation/configuration error established; no alternate current read verified | Reference UNAVAILABLE, economic comparison null; do not use Binance referencePrice, delayed or historical data as current |
| Authoritative liquidity | PRICE_INFO lacks liquidity for both actual NVDA representations; top-pool coverage/freshness is not equivalent | Contemporaneous verified liquidity metric with consistent meaning and eligible history | USD activity fields exist; BStock pool rows have some USD values; Ondo pool rows omit USD liquidity | Not safely with measured evidence | Probed official top-liquidity GET separately; did not aggregate partial pools, infer measurement time, or change application allowlists | Liquidity UNAVAILABLE, estimated slippage UNAVAILABLE; volume alone cannot replace liquidity |
| Decision-window news coverage | Service applied full-history pagination completeness to a much shorter decision window | All returned-source news in move-start minus1hour through evaluation, publication/availability cutoff preserved |100 descending articles span October1–6; tail is strictly older than both required window starts | Yes, for the measured feed window | Verify descending prefix, bounds, source/mode/ticker and availability; distinguish complete requested window from partial full history | Without proof: PARTIAL/UNAVAILABLE; empty available news is not proof of no information; hourly update limitation remains |
| Baseline | No real contemporaneous Trust samples or completed episodes in any inspected database | >=30 completed, nondegenerate, exact-scope episodes within180days |0 real samples /0 completed episodes; existing raw equity bars are historical | Not by legitimate backfill of available records | Read-only database inventory; retained source/first-availability and ratio limitations; no fabricated ingestion | Baseline INSUFFICIENT, sample_count=0, no statistical confidence |
| Historical analogues / positive real classifications | Missing valid features, baseline and real completed history | >=3 eligible completed prior analogues, cosine>=0.8; complete evidence for each positive classification |0 eligible real analogues; both actual representations INSUFFICIENT_EVIDENCE | Not while upstream prerequisites remain absent | Replayed captured inputs and reran synthetic positive-class tests separately | Analogue INSUFFICIENT; null confidence; real NORMAL/LIKELY_NOISE/LIKELY_INFORMATION remain NOT_AVAILABLE |

## Current-equity entitlement diagnosis

Fresh read-only calls at 17:28:51–17:29:14 UTC returned403 for:

- GET /v2/snapshot/locale/us/markets/stocks/tickers/NVDA
- GET /v2/last/nbbo/NVDA
- GET /v2/last/trade/NVDA — isolated alternative diagnostic only.

The denial bodies were inspected in memory and reduced to NOT_AUTHORIZED / ENTITLEMENT_DENIED categories. No message body, request credential, URL query or header was retained. News with the same key returned200/OK. This establishes endpoint entitlement denial rather than an invalid-key failure for every resource; it does not identify the exact account plan. No billing/account setting was inspected or changed.

Official [snapshot documentation](https://massive.com/docs/rest/stocks/snapshots/single-ticker-snapshot) distinguishes unavailable Basic access, delayed Starter/Developer and real-time Advanced. [NBBO](https://massive.com/docs/rest/stocks/trades-quotes/last-quote) lists individual Advanced real-time access; [last trade](https://massive.com/docs/rest/stocks/trades-quotes/last-trade) lists Developer delayed and Advanced real-time. A15minute delayed price does not meet the unchanged120second freshness requirement. Appropriate current-data entitlement must be independently demonstrated; no purchase or plan assumption was made. Other business arrangements are not excluded by these individual-plan examples.

Existing independent historical bars remain HISTORICAL. Their availability and previous-close support do not certify a current regular-session quote. No alternative current endpoint under the configured account was verified, so no alternate adapter was installed.

## Liquidity candidate audit

Endpoint prefix: /api/v1/dex/market/. Official field definitions: [Binance General Data](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/general-data). Response-envelope time is not a market-measurement timestamp.

| Endpoint | Field | Unit | Timestamp | Meaning | Verification / actual availability |
|---|---|---|---|---|---|
| POST price-info | liquidity | USD | No separate field timestamp; time belongs to price observation | Token liquidity | Documented units; absent for both NVDA issuers; unusable |
| POST price-info | volume24H | USD | price time, plus receipt; separate metric asof absent |24hour activity | Units documented; present for both; does not establish depth, venue coverage or executable liquidity |
| POST price-info | buyVolume24H / sellVolume24H | USD | Same timestamp limitation | Directional activity | Units documented; present for both; not liquidity substitute |
| POST price-info | txs24H / buyTxs24H / sellTxs24H | Counts | Same timestamp limitation | Transaction activity | Typed counts; BStock absent, Ondo reported0; missing is not zero |
| GET token/top-liquidity | liquidityUsd | USD per pool | Envelope/receipt only; no documented per-pool measurement time | Selected-pool liquidity | HTTP200/business0; BStock15 pool rows,10 with field; Ondo8 rows,0 with field. No complete-token aggregate, comparable baseline or freshness proof; diagnostic only |
| GET token/top-liquidity | liquidityAmount[].tokenAmount | Token amount | Same pool timestamp limitation | Pool composition | Not USD liquidity; no conversion or synthetic depth inference |
| GET token/search | liquidity / price | Endpoint metadata/price fields | No demonstrated synchronized liquidity asof | Discovery metrics | Not assessed as authoritative Trust input; not an independently verified alternative |
| GET candles | volume slot | UNVERIFIED | Bar start | Historical reported activity | Existing unit quarantine retained |
| GET trades | reported price / quantity | Price unit remains UNVERIFIED | Trade time | Historical activity | Existing quarantine retained; cannot infer USD depth |

Top-pool GET authorization is confined to the new diagnostic client. Production has the same13 market read operations. No specification-approved equivalent to the required token liquidity evidence was established. Partial pool sums, stock USD turnover and transaction counts were not promoted into that feature.

## News remediation and remaining limitations

The actual100-record descending prefix has earliest publication2026-10-01T11:29Z and latest2026-10-06T17:00Z. Both decision windows begin around16:28:50Z on October6. A strictly older tail proves the remaining descending pages are outside those windows. Equality at the boundary is insufficient because more articles can share its timestamp.

MassiveProvider resets prefix evidence before each call and only certifies an unbounded-latest, verified descending sequence. A historical before-bound cannot certify a current window. NewsAlignmentService additionally checks every row's ticker, mode, source, quality and publication/first-seen cutoff, rechecks order and tail identity, and accounts for the full observed move-start window. Failed, unordered, too-short, future-available or conflicting-source prefixes remain partial. No pagination budget was increased and no synthetic article was added.

Actual result: COMPLETE_REQUESTED_WINDOW / RELEVANT_NEWS, with unknown direction and four time-eligible article IDs. Reasons retain BOUNDED_NEWS_HISTORY and NEWS_NOT_EXHAUSTIVE_MARKET_COVERAGE, and add DESCENDING_PREFIX_COVERS_REQUESTED_WINDOW / SOURCE_UPDATED_HOURLY_NOT_REALTIME_NEWS. This certifies the retrieved source window as received, not exhaustive contemporaneous market information, complete historical retention, historical first publication availability, or causality. [Official news contract](https://massive.com/docs/rest/stocks/news) documents hourly refresh and descending publication sorting. Provider LLM insights remain excluded. No-relevant-news, relevant-news, partial and unavailable remain distinct.

## Real history inventory and leakage

The [actual inventory](evidence/CANONICAL_PHASE_2_TRUST_REMEDIATION_REVERIFIED.json) inspects every data/*.db through SQLite read-only connections. Counts are per database; duplicated captures across databases are never summed into independent history.

| Scope | Real Trust samples | Completed real episodes | Eligible real analogues |
|---|---|---|---|
| NVDA / each issuer and each regime |0 |0 |0 |
| Other tickers / all regimes |0 |0 |0 |
| LOCAL_OBSERVATIONS completed UTC30minute episode type |0 |0 |0 |

REGULAR, PRE_MARKET, POST_MARKET, WEEKDAY_OVERNIGHT, WEEKEND_PREOPEN and MULTI_DAY_REOPEN all have zero real Trust episode counts. EARNINGS_WINDOW coverage remains unavailable. DEMO and SYNTHETIC_TEST never contribute to these counts.

Engineering Data Layer database contains945 NVDA BAR rows and1 REGULAR_CLOSE row, plus25 token observations:3 CANDLE,8 PRICE,4 PRICE_INFO,10 TRADE. These are raw records, not26minute covered contemporary feature episodes. Other verification databases contain price snapshots, but no Trust samples/episodes. The new remediation database contains8 token observations across two captures and zero independent equity observations, zero Trust samples/episodes.

Policy remains >=30 completed episodes per mode/ticker/issuer/chain/contract/regime/ratio/reference-kind/policy scope, nonzero deviation SD,180day lookback; >=3 analogues at cosine>=0.8. EpisodeBuilder requires a completed30minute UTC bucket, first observation <=start+120s, last >=end−120s, no gap>120s, unique timestamps and features available by decision. These density conditions imply at least14 distinct observations over >=26minutes; its preliminary len>=2 check alone is not sufficient. Minimum sample counts are safeguards, not statistical significance.

Repository availability cutoff, immutable first-availability, exact scope/mode partition, completed outcomes and no-future-feature retrieval remain unchanged and tested. Newly fetched news is not backdated to publication. Existing historical token ratios were only known at ingestion; candle/trade units and past liquidity are not verified. Fetching more available equity bars cannot remedy those missing paired asof facts, so redundant historical ingestion and artificial episode construction were deliberately avoided. sample_count=0 and confidence=null remain visible.

## Verification and gate

Software:302 backend tests PASS (all282 retained,20 added);47 frontend tests PASS; TypeScript/build, Ruff lint/format, security, direct/proxy API integration and desktop/mobile Trust/Ask browser checks PASS. Existing Starlette/httpx deprecation remains unsuppressed. Docker remains unavailable/not run.

Added tests cover scoped prefix boundaries, ordering, source/mode/ticker/availability, partial versus no-relevant semantics, stale coverage reset, historical before-bound, diagnostic-only endpoint restrictions and categorical denial redaction. Two captured-input replay checks retain actual timestamps and LIVE provenance, prove news availability restrictions, missing liquidity/current reference/history, persistence and no network/execution. They are labeled REAL_CAPTURED_INPUTS_REPLAY, not fresh provider entitlement proof. Sufficient-history and all three positive classification tests remain explicitly synthetic DEMO scenarios; no genuine sufficient real history or positive real-class evidence exists to test.

The formal [Trust gate](evidence/CANONICAL_PHASE_2_TRUST_GATE.json) separates12 real prerequisites from the preserved automated criteria. [Initial gate](evidence/CANONICAL_PHASE_2_TRUST_GATE_INITIAL.json) preserves the exact previous record. [Before-remediation capture](evidence/CANONICAL_PHASE_2_TRUST_REMEDIATION_LIVE.json) and [after-remediation capture](evidence/CANONICAL_PHASE_2_TRUST_REMEDIATION_REVERIFIED.json) both remain immutable. The original report and all Phase0/1/Data Layer/initial Trust evidence remain intact.

```text
CANONICAL_PHASE_1_GATE=PASS
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

Exact gate reason: current independent reference denied; mandatory comparable/fresh liquidity missing; zero qualifying30-episode real baseline and zero3-analogue history. Consequently deviation and positive real classifications cannot be verified. The measured news-window blocker is resolved, while hourly/full-history limitations remain. Both real assessments persist INSUFFICIENT_EVIDENCE/null confidence, no broadcast/ready/LLM authority; no execution endpoint was called.

Next work remains **Canonical Phase 2 prerequisite acquisition and Trust re-verification**: demonstrate independent current entitlement, contemporaneous verified liquidity and sufficient naturally collected/asof-safe paired history. No paid capability or data collection automation is assumed. **STOP. Canonical Phase3 — Opportunity Mode must not begin.**

## Files changed in this remediation

Application correction (three files only):

- backend/app/providers/massive.py
- backend/app/services/trust_evidence.py
- backend/app/services/trust.py

New checks / isolated diagnostic / captured fixture:

- backend/tests/unit/test_news_window_remediation.py
- backend/tests/unit/test_trust_remediation_diagnostics.py
- backend/tests/integration/test_trust_real_capture.py
- backend/tests/fixtures/trust/real_remediation_capture.json
- scripts/verify-trust-remediation.py

Documentation (all original historical sections retained):

- docs/PHASE_2_TRUST_REMEDIATION.md
- docs/PHASE_2_TRUST_REPORT.md
- docs/CAPABILITY_GAPS.md
- docs/API_MATRIX.md
- docs/EXECUTION_GATES.md
- docs/PHASE_MAP.md
- docs/ARCHITECTURE.md
- docs/DATA_CONTRACTS.md
- docs/TEST_MATRIX.md

Formal / new evidence:

- docs/evidence/CANONICAL_PHASE_2_TRUST_GATE.json
- docs/evidence/CANONICAL_PHASE_2_TRUST_GATE_INITIAL.json
- docs/evidence/CANONICAL_PHASE_2_TRUST_REMEDIATION_LIVE.json
- docs/evidence/CANONICAL_PHASE_2_TRUST_REMEDIATION_REVERIFIED.json
- docs/evidence/CANONICAL_PHASE_2_TRUST_REMEDIATION_API.json
- docs/evidence/CANONICAL_PHASE_2_TRUST_REMEDIATION_BROWSER.json
- docs/evidence/CANONICAL_PHASE_2_TRUST_REMEDIATION_ASK_BROWSER.json

Generated/ignored: new data/phase2-trust-remediation-verification.db; existing running DEMO database receives the authorized local test proposals/assessments; frontend/dist is rebuilt. Five previous isolated verification databases, both master copies, all pre-existing tests/fixtures and prior gate/provider/browser/API evidence remain byte-identical. README, frontend source, financial policy, execution code/configuration and production read allowlists are unchanged. No Git metadata is present; pre/post SHA256 manifests are used. Verified backend PID94450 and unchanged frontend PID86767 remain running at127.0.0.1:8000/5173.

## Read-only Trust data investigation — latest gate evidence

Investigation completed **2026-10-06T17:56:54.818189Z**. This section supplements the earlier remediation above; its records are preserved. **TRUST_GATE=BLOCKED.** No production application code changed. The isolated diagnostic reused the existing providers, calendar, historical ingestion, Decimal models and fail-closed Trust assessment. [Actual capture and before/after inventory](evidence/CANONICAL_PHASE_2_TRUST_DATA_INVESTIGATION.json), [current formal gate](evidence/CANONICAL_PHASE_2_TRUST_GATE.json), and [previous gate archive](evidence/CANONICAL_PHASE_2_TRUST_GATE_PRE_DATA_INVESTIGATION.json) distinguish this investigation from the preceding news correction.

### Massive entitlement and minimum plan

Fresh GET `/v2/snapshot/locale/us/markets/stocks/tickers/NVDA` returned **403** at17:55:40.746423Z and17:56:41.534219Z; GET `/v2/last/nbbo/NVDA` returned **403** at17:55:53.000759Z. In-memory denial inspection produced `NOT_AUTHORIZED` / `ENTITLEMENT_DENIED` only. The same configured key retrieved historical one-minute/five-minute aggregates and news with200/OK. This identifies endpoint entitlement denial; no signing, path or key-configuration defect was established. The exact account subscription remains UNKNOWN. The previous alternative-last-trade403 remains historical evidence; it was not retested here. No credential values, denial bodies, headers or credential-bearing URLs were recorded. No plan was purchased or changed.

Current official [individual Stocks pricing](https://massive.com/stocks), [Snapshot](https://massive.com/docs/rest/stocks/snapshots/single-ticker-snapshot) and [NBBO](https://massive.com/docs/rest/stocks/trades-quotes/last-quote) documentation was checked on2026-10-06:

| Individual plan | Listed USD/month | Snapshot | NBBO/quotes | Meets unchanged current regular-session reference semantics? |
|---|---|---|---|---|
| Basic |0 | Excluded | Excluded | No; permitted historical aggregates do not provide current reference |
| Starter |29 |15minute delayed | Excluded | No |
| Developer |79 |15minute delayed | Excluded | No |
| Advanced |199 | Real time | Real time | Potentially, after verified account entitlement and returned-data freshness checks |

**Advanced at USD199/month is the minimum listed individual plan capable of meeting the current reference requirement.** Its individual/nonprofessional terms apply; public/commercial redisplay needs separately verified licensing. The business offer lists USD2499/month with real-time FMV/EOD SIP and separate live-feed licensing; it is not proof that the existing Snapshot adapter receives an eligible live SIP reference. No business subscription or alternative FMV adapter was verified. Prices are the displayed monthly amounts; annual totals or discounts are not inferred.

Snapshot alone can satisfy the existing analytical comparison when it returns an accepted price/timestamp (supported `lastTrade` or minute close), independently verified real-time entitlement, LIVE provenance, identity and the unchanged **age<=120s / skew<=30s** checks. HTTP200, a plan name, day/previous-day fields or unverified recency alone do not pass. **Live NBBO is not mandatory** for this Trust price comparison; a qualifying Snapshot is supported. This does not establish executable bid/ask depth or execution safety. **15minute delayed data fails current regular-session semantics.** Historical previous-close support in closed regimes does not solve the current403. Binance `referencePrice` remains excluded as an independent equity reference.

### Actual Binance fields, units and liquidity decision

Read-only POST `/api/v1/dex/market/price-info` returned200/business0 at17:55:53.435348Z for actual discovered Ondo NVDA on BSC56, contract `0xa9ee28c80f960b889dfbd1902055218cba016f75`. Price observation time was17:55:50.536Z. Full exact whitelisted statistics are retained in the actual capture; table decimals below are exact returned strings.

| Field | Actual value | Official meaning/unit | Trust disposition |
|---|---|---|---|
| price |240.469258337843321414 | USD/token | Actual token price, not independent equity |
| time |1791309350536 | Price observation milliseconds | Does not timestamp every market statistic |
| liquidity | Absent/null | Token liquidity, USD | UNAVAILABLE |
| volume5M / volume1H / volume4H | Absent/null | USD activity over named windows | Missing, not zero |
| volume24H |15034188704.2425188625 | USD24hour activity | Activity, not depth/liquidity |
| buyVolume24H / sellVolume24H |29540.45076450528828416866 /85843.83096205512808727221 | Directional USD24hour activity | No inferred reconciliation with total volume |
| holders |50866 | Holding-address count | Not investor count or liquidity |
| marketCap |16955676.26437175902022159838038170434400019 | USD | Reported market statistic |
| circSupply |70510.77882591594799436 | Circulating token amount | Not traditional-equity share count |
| txs24H / buyTxs24H / sellTxs24H |0 /0 /0 | Transaction counts | Provider-reported zeros; not missing-field defaults |
| priceChange24H |1.06589975348943388 | Percent | Reported change |
| maxPrice / minPrice |0 /0 |24hour high/low, USD | Reported zeros do not establish valid price extrema |

Units and field meaning come from [official Binance General Data](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/general-data), not inferred names. Separate liquidity/statistic asof and venue-coverage equivalence are not established. The large total-volume versus directional-volume discrepancy cannot be silently reconciled. Previously captured partial top pools remain non-equivalent. **No authoritative fresh liquidity metric was returned**, so no adapter/model change was justified. Historical candle-volume units remain UNKNOWN and quarantined; no USD-volume conversion or liquidity substitution was made.

### Real historical coverage before and after

Inventory covers every local `data/*.db`, LIVE rows only, deduplicated by capture identity across databases. DEMO and synthetic fixtures are excluded. Only **NVDA** has real observations; all other tickers have zero. `REGULAR_CLOSE` is a separate observation kind, not an additional independent BAR.

| Real inventory | Before this task | After bounded backfill |
|---|---|---|
| Token observations |39:16 PRICE,10 PRICE_INFO,10 TRADE,3 CANDLE |122:18 PRICE,14 PRICE_INFO,10 TRADE,80 CANDLE |
| Token source range, UTC |Oct6 08:00–17:28:50.630 |Oct2 21:00–Oct6 17:56:38.344 |
| Candle granularity |3 hourly |61 hourly,19 one-minute |
| Equity BAR records |945 one-minute |2083:1891 one-minute,192 five-minute |
| Separate REGULAR_CLOSE observations |1 |1 |
| Equity source range, UTC |Oct5 08:00–23:59 |Oct2 08:00–Oct5 23:59 |
| Token/equity timestamp-span overlap | None |Oct2 21:00–Oct5 23:59; span only, not continuous or complete paired features |
| Real Trust samples / completed Trust episodes |0 /0 |0 /0 |

Source timestamps are milliseconds normalized to UTC; candle/aggregate timestamps are bar starts, with interval completion checked separately. Event/trade timestamps are not regularly sampled bars. Historical equity retains HISTORICAL quality and adjusted-bar provenance, not a current-quote label.

Backfilled one fixed, calendar-verified Friday Oct2 close20:00Z → Monday Oct5 open13:30Z window for Ondo NVDA. **No candidate scanning or broad historical completeness claim.** Existing authorized Binance candles returned58 hourly weekend bars and19 preopen minute bars; Massive returned1891 one-minute bars for Oct2–5 and192 five-minute bars for Oct5. The isolated database stores those real responses. Net new deduplicated equity BAR identities are1138 (946 minute +192 five-minute); net new token observations are83 (77 historical candles +6 current read observations). Earlier isolated databases remain byte-identical.

The first diagnostic stored the backfill, then hit the public repository's1000-row audit-read limit. Only the diagnostic's read was corrected to a bounded, read-only5000-record capture audit; the application limit was unchanged. The successful rerun inserted0 duplicate historical records, confirming idempotency rather than absence of backfill. Binance returned out-of-bounds rows despite bounds; existing local exclusive-bound validation rejected them. No missing interval was filled. Nineteen minute bars span11:52–13:27Z with a maximum20minute gap; only7 lie in the final13:00–13:30Z bucket. This cannot satisfy the existing<=120s gap requirement. The hourly13:00 bar completes after the13:30 decision and is excluded from end-window features.

### Reopening outcome and unchanged sample thresholds

The requested window contains **1 potential weekend reopening,0 holiday reopenings**, and **0 episodes with all required Trust fields**. Earlier records contained0 fully matched candidates. The weekend is multi-day closure under the existing calendar; no regime policy was changed.

One genuine **posthoc outcome only** is measurable: actual Friday19:59Z minute close completes at20:00Z with USD234; the actual Monday13:30Z five-minute bar completes at13:35Z with close USD237.376. Canonical return `(237.376−234)/234` is approximately **+1.442735%**, with the unrounded256-digit Decimal ratio retained in evidence. Its first local availability is Oct6 17:53:52.617087Z. It is **not a decision feature, Trust episode, training sample or historical analogue**. Split-adjusted revision history asof Monday is unverified. Missing/misaligned/incomplete target bars are tested as UNSCORABLE with null return, never synthesized.

The candidate remains rejected because historical asof token/share ratio is unverified, historical liquidity is absent, candle-volume units are unknown, local first availability/revision provenance does not prove availability at the historical decision, historical news was first seen afterward, and there are no qualifying Trust feature samples. Current ratio metadata was not backdated or used to normalize historical exposure. Sparse token bars independently fail the density policy.

| Real qualification | Count | Unchanged minimum | Result |
|---|---|---|---|
| Baseline episodes |0 |30 | INSUFFICIENT |
| Opening-model episodes |0 |30 | INSUFFICIENT |
| Eligible historical analogues |0 |3 | INSUFFICIENT |

These are distinct from the1 measurable outcome. No positive real classification or statistical confidence is claimed. Synthetic DEMO classifications still test software only. Newly assessed actual BStock/Ondo representations both persist as INSUFFICIENT_EVIDENCE with null economics/features/confidence and literal false execution/broadcast flags.

### Leakage, verification and gate closure

At Monday13:30Z,19 token minute bars had completed by event time but0 captured token features and0 equity references had proven local first availability by the decision. All100 historical news publications were before the decision, but0 were first seen by it. Opening outcome completion13:35Z and recorded availability Oct6 remain after the decision and outside feature construction. Analogue retrieval has0 eligible completed/available prior episodes; existing future-outcome perturbation tests preserve its cutoff. No first-seen timestamp was backdated. This verifies safe exclusion in the measured scope, not historical availability of a sufficient real feature dataset.

**Tests:**311 backend tests PASS (all302 preceding tests retained;9 added diagnostic boundary/leakage cases),47 frontend tests PASS; TypeScript/build, Ruff lint/format (68 Python files), security and existing local API integration PASS. Diagnostic tests are explicitly synthetic and never counted as real history. Prior desktop/mobile Ask/Trust browser evidence is retained; no new browser session was needed because frontend/application source is unchanged. Existing upstream Starlette/httpx deprecation remains unsuppressed; Docker was not run under the existing environment limitation.

Remaining blockers are **current independent equity entitlement**, **comparable fresh authoritative liquidity**, **0/30 qualifying real baseline/opening-model episodes**, and **0/3 eligible real analogues**, with the exact historical rejection reasons above. Raw backfill partially improves historical coverage but closes none of those gate prerequisites. No thresholds or execution controls were weakened.

Current states: CANONICAL_PHASE_1_GATE=PASS; DATA_GATE=PASS; DRY_RUN_GATE=PASS; **TRUST_GATE=BLOCKED**; OPPORTUNITY_GATE=BLOCKED_BY_TRUST; SWAP_LIVE_GATE=BLOCKED; RFQ_LIVE_GATE=BLOCKED; AGENTIC_WALLET_LIVE_GATE=BLOCKED. Remain within Canonical Phase2 data remediation. Do not start Opportunity Mode.

### Files changed in this data investigation

- New isolated diagnostic: `scripts/investigate-trust-data.py`.
- New9 synthetic diagnostic tests: `backend/tests/unit/test_trust_history_investigation.py`.
- Updated documentation: `docs/PHASE_2_TRUST_REMEDIATION.md`, `docs/CAPABILITY_GAPS.md`, `docs/API_MATRIX.md`, `docs/EXECUTION_GATES.md`.
- Updated formal gate: `docs/evidence/CANONICAL_PHASE_2_TRUST_GATE.json`.
- New evidence/archive: `docs/evidence/CANONICAL_PHASE_2_TRUST_DATA_INVESTIGATION.json`, `docs/evidence/CANONICAL_PHASE_2_TRUST_GATE_PRE_DATA_INVESTIGATION.json`.

Generated/ignored: `data/phase2-trust-history-investigation.db`, rebuilt frontend output, coverage artifacts, and authorized local DEMO integration records in the running database. Production code, frontend source, README, master copies, existing tests/fixtures, old isolated databases, prior evidence and financial/execution configuration remain unchanged. No Git metadata exists; SHA256 preservation checks are used.
