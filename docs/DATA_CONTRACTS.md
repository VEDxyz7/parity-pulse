# Data contracts — Canonical Phase 2 Trust Layer

Created 2026-10-06. This file was absent during the pre-code audit. It documents the implemented analytical scope, not a replacement for the master specification, existing normalized Data Layer schemas, or historical reports.

## Authority and isolation

Provider observations reuse `models/data.py`: exact Decimal input, UTC timestamps, source/identifier, ingestion timestamp, explicit DEMO/LIVE mode and LIVE/DELAYED/HISTORICAL/DEMO/STALE/UNKNOWN quality. DEMO never fills a failed LIVE read. Binance referencePrice is never an independent equity reference. Trading, Transaction and Wallet operations remain outside the clients' unchanged read allowlists.

Trust models live in `models/trust.py`, are frozen, reject extra fields, and serialize financial quantities as decimal strings. `TrustAssessment` includes UUID/request/correlation/run IDs, evaluation time, resolved ticker, regime, representations, policy version, limitations and literal no-execution flags. `ASSESSED` means an assessment was constructed; its individual classification can still be INSUFFICIENT_EVIDENCE. Unsupported, malformed or unavailable discovery produces UNAVAILABLE and no representation assessment.

## Economic comparison and timestamps

P = verified USD/token; R = verified positive shares/token; E = independent USD/share.

```text
effective_price_per_share = P / R
comparable_token_value = E * R
deviation = (P - E * R) / (E * R)
absolute_deviation = abs(deviation)
```

Deviation is a dimensionless fraction, not a percentage. Shared `services/normalization.py` uses Decimal precision256 and rejects floats, booleans, non-finite, non-positive and unsupported-magnitude inputs (96 coefficient digits; absolute adjusted exponent <=36). Phase 1 presentation still rounds effective cost upward to18 fractional places and retains its original exact budget/base-unit calculation and selection behavior. Trust uses the unrounded shared economic result. Statistics and cosine calculations remain Decimal; SQLite stores JSON text, never financial REAL columns.

ENGINEERING_POLICY `trust-engineering-v1`: token price and ratio receipt age0–120 seconds, current independent quote age0–120 seconds, current P/E timestamp skew<=30 seconds. Future observations and not-yet-ingested evidence are rejected. Thresholds are documented engineering choices, not calibrated research coefficients. Token price must be a verified PRICE or PRICE_INFO observation; TRADE/CANDLE price units are excluded. Identities, ratios and modes must match.

During REGULAR, E must be a verified current Massive SNAPSHOT/QUOTE (DEMO_EQUITY only within DEMO). DELAYED, UNKNOWN, HISTORICAL and stale references fail closed. During closed/extended regimes, only the previous **actual** completed regular-close minute is accepted: REGULAR_CLOSE, interval1minute, raw bar start+1minute equals the calendar's previous close. LIVE data remains HISTORICAL. `reference_asof` is that close; raw source timestamp remains the bar start. Closed-session skew reports the closure age and is not mislabeled current-quote alignment. Source, kind, quality and both timestamps remain visible.

Ratio receipt time does not prove issuer publication time. Missing ratio source-asof is explicitly reported. Existing historical bars are never normalized retroactively with a newly fetched ratio to manufacture Trust history. Scope partitions include exact ratio, preventing cross-ratio/corporate-action pooling. Corporate-action/earnings interpretation beyond this partition is unavailable.

## Market and liquidity evidence

Regimes reuse the existing versioned New York schedule, UTC internally, coverage2026–2028. Preserve REGULAR/PREMARKET/POSTMARKET/WEEKDAY_OVERNIGHT/WEEKEND/HOLIDAY and early-close/reopening flags. Non-regular multi-day closures use MULTI_DAY_REOPEN; weekend/holiday otherwise use WEEKEND_PREOPEN; other exact states keep their own baseline bucket. Schedule is not live halt status. Earnings windows remain UNAVAILABLE.

PRICE_INFO accepts only matching verified BINANCE_MARKET (or explicit DEMO_MARKET) observations. Official [Binance General Data](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/general-data) defines volume24H, buy/sellVolume24H and liquidity in USD, and transaction counts as counts. Optional absent fields remain null. Missing volume or liquidity blocks authoritative feature construction. Units of historical trade prices/candle volume remain excluded. Slippage and executable liquidity are UNAVAILABLE; pool liquidity is not a tradable quote.

## News evidence

Reuse Massive normalized articles and their original publication/first-seen times. Window = observed move start minus1hour through decision time. Both publication and ingestion must be <=decision; ticker, source and mode must match. Maximum one existing provider page (100 articles); a remaining page means PARTIAL and blocks classification. This is deliberately conservative, even when some returned articles are older than the relevant window. COMPLETE_REQUESTED_WINDOW never means exhaustive market-information coverage, or a guarantee of timely future publication.

News states: NO_RELEVANT_NEWS, RELEVANT_NEWS, CORROBORATING, CONFLICTING, PARTIAL, UNAVAILABLE. Directional state is retained separately when coverage is partial. Deterministic v1 rules require the full company name or exact uppercase ticker in the headline and one of `raises guidance`, `raises outlook`, `beats estimates`, `cuts guidance`, `cuts outlook`, `misses estimates`. Explicit negation/speculation words suppress directional interpretation. Opposed directions conflict. Other headlines remain UNKNOWN in direction; keyword evidence is heuristic, not causal fact.

Massive documents [LLM-derived sentiment insights](https://www.massive.com/blog/release-notes-september-2024); the Trust implementation does not read them. The [news contract](https://massive.com/docs/rest/stocks/news) supplies publication/ticker metadata and documents hourly updates. No local LLM or sentiment API call is introduced. No-news is never proof that no information exists.

## History, statistics and retrieval

Three new additive schema-revision4 tables: trust_assessments, trust_samples, trust_episodes. Existing proposal/data tables and payload formats remain intact. Repositories require explicit mode, retain first availability, and expose no public writable-history API. Historical Data Layer verification databases/fixtures/evidence remain unchanged; new verification uses separate phase2-trust databases.

TrustSample stores contemporaneously available normalized economics, volume/liquidity, observed same-sign persistence, time-to-next-open, news state and starting/ending deviation **ending at feature time**. All features are known at the recorded decision/availability time. Persistence looks back at most15minutes, cannot bridge gaps above120seconds or observations later than the token observation. It records observed continuity, not proof of continuous trading.

Completed UTC30minute windows require coverage beginning within120seconds of start and ending within120seconds of end, no inter-observation gap above120seconds, and distinct observed events. Middle-window features (<=15minutes) are frozen independently of later within-window outcomes. REVERSED means sign crossed or absolute deviation fell to <=half; PERSISTED means same sign and absolute deviation did not fall; otherwise MIXED. These are engineering outcome labels, not opening predictions. Outcomes are attached only after completion and available no earlier than completion detection.

Baselines partition by mode/ticker/issuer/chain/contract/regime/exact ratio/reference-kind/policy version. Lookback180days; master minimum30 completed episodes. Only features, completed episodes and outcomes available at decision time are eligible. Current window is excluded. Bounded history reads (5000 records) report truncation and fail closed; observation assembly reads the preceding day. No scheduler/backfill, opportunity scan or fabricated historical ingestion is introduced.

Statistics: arithmetic mean, linearly interpolated p25/50/75/90/95/99, median, median absolute deviation, population standard deviation; empirical percentile is fraction of values <=current; z-score uses mean/population SD. Zero deviation SD yields DEGENERATE, not infinite confidence. Samples are not claimed independent: adjacent episodes and rolling24hour volume can overlap economically.

Analogue vectors: deviation, absolute deviation, USD24h volume, persistence, time-to-open, starting deviation, ending-at-feature-time deviation, one-hot news state. Exact scope fixes regime. Scale using the decision-time past baseline (deviation SD, relevant p95, time86400), then L2 normalize and cosine-rank deterministically. Top3; minimum3; engineering similarity floor0.8; episode-ID tie break. Zero-scale components become0; zero norm is excluded. **Outcome never enters vector/scaling/ranking.** Only completed prior outcomes appear after retrieval. This adapts the specified [cosine retrieval approach](https://arxiv.org/html/2501.00826v3); crypto returns or coefficients are not transferred.

## Classification policy and limits

All classifications require available independent comparison/features/liquidity, nondegenerate >=30-episode baseline, >=3 qualified analogues and complete requested news coverage. Any missing, stale, conflicting, ambiguous, truncated or partial mandatory evidence yields INSUFFICIENT_EVIDENCE, null confidence and machine-readable missing/reason codes. Conflicting news fails closed.

| State | Explicit v1 engineering rules within the exact stock/regime scope |
|---|---|
| NORMAL | Absolute deviation<=past p75 and liquidity>=past liquidity p25 |
| LIKELY_NOISE | Absolute deviation>=p95; volume<=p25; persistence<=p25; liquidity<=p25; no relevant news in covered window; at least2/3 retrieved outcomes REVERSED |
| LIKELY_INFORMATION | Absolute deviation>=p95; volume>=p75; persistence>=p75; liquidity>=p50; directional headline corroboration; at least2/3 retrieved outcomes PERSISTED |
| INSUFFICIENT_EVIDENCE | Missing requirements, conflicting news, or evidence supporting no complete rule |

Rule order is NORMAL, NOISE, INFORMATION, otherwise insufficient. These are per-stock/regime percentile conditions, not global deviation thresholds or statistically validated claims. Confidence is conservatively capped LOW for v1; there is no calibrated probability or HIGH/MEDIUM certification. No confidence overrides missing evidence or safety rules. Evidence quality distinguishes insufficient, synthetic DEMO and local measured features; local measurements do not imply statistical validation. No authoritative agent interpretation or paper0.98/0.90 coefficient is used.

GET /api/assets/{ticker}/trust accepts a bounded uppercase ticker and no query toggles. UI requests only on explicit submission, displays backend strings/reasons, clears failed replacements and expires displayed evidence after120seconds. Assessment persistence/logging has no execution authority. All assessments retain DRY_RUN/PROPOSE_ONLY, required simulation, false live/ready/broadcast flags and the explicit no-broadcast statement. Trust is separate from Ask proposals: their legacy trust-not-implemented field remains the unimplemented **proposal integration**, not absence of the separate Trust engine.

## News-window coverage remediation — 2026-10-06

A verified latest descending prefix may cover COMPLETE_REQUESTED_WINDOW despite incomplete full history. The tail must be strictly before move-start minus1hour; all rows must have correct mode/source/quality/ticker and publication/first-seen <=decision time. Ordering and tail identity are rechecked. The provider resets the boundary before every call and disables it for historical before-bounds, failed reads and unordered prefixes. Equality, too-short coverage, unavailable rows or unsupported provenance remain PARTIAL/UNAVAILABLE. BOUNDED_NEWS_HISTORY remains even when the local requested window passes; LIVE feed adds SOURCE_UPDATED_HOURLY_NOT_REALTIME_NEWS. This is source coverage as received, never exhaustive market-information/freshness/causality proof. No financial policy threshold or classifier rule changes. Existing contract paragraphs above describing all bounded history as partial record the initial conservative behavior. [Audit and real evidence](PHASE_2_TRUST_REMEDIATION.md).
