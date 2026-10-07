# Master engineering Phase 5 — Research / Prediction

Verified October 7, 2026. Scope: offline production-capable research machinery, real local
historical inventory/replay, and isolated synthetic verification. No Phase 6 implementation,
provider request, live-session alignment test, application API change, or commit.

```text
PHASE 5 IMPLEMENTATION=PASS
PHASE 5 DATA GATE=BLOCKED
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

## Authority and audit

The task's `/mnt/data/Parity_Pulse_Master_Build_Prompt_VERIFIED_v2(1).txt` is absent on this
Mac. The complete locally available authoritative VERIFIED v2 copy was read at
`/Users/vedparikh/Downloads/Parity_Pulse_Master_Build_Prompt_VERIFIED_v2.txt`.
SHA-256: `8d436286338a8ac9fbb7a6ee76ffce3b81cf96ff9e8c51ea85dfe9e6f2f22554`.
Both existing repository master copies remain unchanged, including earlier safety/gate amendments.
Starting commit: `a9de631af887ae343880f5e7cc4dc743bcd7b11c`; working tree was clean.

The existing implementation already had Decimal normalization, calendar-aware reference selection,
deterministic news/liquidity/Trust evidence, 30-minute reversal episodes, stock/issuer/ratio/regime
baselines and Trust analogue retrieval. Those reversal episodes are not opening-return training
targets. Missing machinery was an explicit opening research contract, independent target availability,
configurable opening regression, opening-history vectors/retrieval and reproducible offline replay.
The pre-code relevant Trust/history audit suite passed 101 tests. No working DEMO service was rebuilt.

## Architecture and historical contracts

`HistoricalSource` reads only the reviewed analytical tables from existing SQLite files using
`mode=ro`, `PRAGMA query_only` and a read transaction. Each table has a 20,000-row completeness bound;
overflow aborts. It combines the existing official raw historical capture, retaining null ratios,
UNKNOWN candle volume units and original first-seen times. It excludes DEMO rows, Twelve Data
diagnostics, GeckoTerminal pools and all execution/scorecard tables. Event duplicates retain the
earliest actual receipt; price/revision conflicts stop. Malformed rows are explicitly counted.

`ResearchFrame` supplies an explicit historical decision T. `ResearchEpisodeBuilder` invokes
the unchanged `TrustService.evaluate_representation` through a disposable in-memory analytical
snapshot. That snapshot has no database, provider transport or execution client. Existing
`EpisodeBuilder`, `BaselineService`, `AnalogueService`, classifier, normalization, calendar,
independent-reference, liquidity and news services remain authoritative for Trust evidence.

`ResearchDecision` stores stock/representation/mode, T, regime, actual previous close/next open,
known token and independent equity observations, exact Trust features, baseline volume percentile,
persistence, liquidity, news, time-to-open, starting/current deviation, optional normalized
off-hours return and closure token, eligibility/rejection reasons, policy and bound provenance.
Starting deviation in the reused Trust features means the observed move's persistence window;
it is not fabricated as a weekend-close anchor. Optional off-hours movement uses independently
proven ratios at both endpoints, so a ratio change is not mistaken for token-market return.
Without both known endpoints/proofs that feature is null, never backfilled.

`ResearchEpisode` adds a separately typed `OpeningTarget`: actual regular opening, completion
time, first availability, previous-close/first-bar prices, opening return and revision provenance.
Raw outcomes without revision proof are POSTHOC_ONLY; missing/conflicting/incomplete bars are
UNSCORABLE. Synthetic records require DEMO and cannot enter LIVE history. No execution authority
exists in these contracts.

## Opening target and look-ahead protection

The one configured target is previous regular close → first completed five-minute regular bar.
`OPENING_MINUTES` is the shared constant; the older diagnostics import the same configuration.
The first diagnostic's existing outcome calculation moved into `opening_target.py` and is reused.
It checks the exact minute ending at the calendar close and the bar starting at regular open,
matching independent source/stock/adjustment mode, positive prices and completed bars. Conflicting
captures cannot silently choose the first price. No extended-hours or later opening bar substitutes.

Features require both provider observation and original ingestion at/before T. Freshness remains
120 seconds and regular-session alignment 30 seconds under the existing reference service;
off-hours reference age is the actual closure age, not a falsely current quote. Ratio/equity
revision proofs bind SHA-256 of the exact payload, effective time, first availability and source.
The locally verified calendar version cannot be backdated before its verification timestamp.
Newly downloaded adjusted history does not prove historical corporate-action knowledge.

Future candles/quotes, future-published news, articles first seen after T, future liquidity and
future ratio/corporate-action proofs are excluded. Analogue/model outcomes must have completed
and become available by T. Scorecards are neither accepted frame fields nor read sources.
Future opening outcomes never enter the decision digest or feature vector. Tests alter future
observations/outcomes and prove earlier decisions, retrieval and forecasts unchanged.

## Retrieval and opening model

The research vector covers deviation, absolute deviation, baseline volume percentile, persistence,
time-to-open, starting/current deviation and fixed one-hot regime/news indicators. Policy declares
scales explicitly: deviation 0.01, persistence 900 seconds, time 86,400 seconds; percentile/one-hot
values use unit scale. Decimal L2 normalization and cosine similarity are deterministic.
Eligibility fixes stock/issuer/chain/contract/ratio/regime/reference/policy/target scope and
180-day past availability. Independent opening outcomes are deduplicated; repeated captures
and multiple decisions for one opening cannot inflate samples. Top-K defaults to 3, similarity
floor to 0.8; ties use immutable IDs. Results include IDs, similarities, feature/outcome availability,
eligibility/rejections, bound provenance and observed UP/DOWN/FLAT opening patterns.
These opening patterns are not claims about future token-price reversal. Fewer than 3 matches
means INSUFFICIENT_DATA. Production Trust retrieval remains unchanged.

`RollingOpeningModel` fits local OLS using twice-reorthogonalized Decimal QR at precision 256,
avoiding normal-equation conditioning. This implements local least-squares estimation and residual
variance, following the [NIST least-squares methodology](https://www.itl.nist.gov/div898/handbook/pmd/section4/pmd431.htm).
The last 120 eligible independent openings are the default rolling window, with a fixed minimum
of 30. Configurable columns include normalized off-hours return, deviation/absolute/starting/ending
deviation, volume percentile, persistence, time-to-open and news flag; exact regime is a scope,
not an artificial varying coefficient. The default reduced feature set is deviation, volume
percentile and persistence, explicitly recorded in policy. Selecting an unavailable off-hours
feature returns NOT_READY rather than substituting a proxy.

Scaling/centering is fit solely on available training rows. Missing features, rejected current
evidence, invalid targets/scopes, rank deficiency and extrapolation beyond measured support fail
closed. No paper coefficients or 0.90/0.98 prior are used. Outputs include model/dataset identity,
training IDs/counts, coefficients, predicted return, direction and an approximate normal residual
prediction interval. The configurable multiplier defaults to 1.96; intervals/confidence are
explicitly UNCALIBRATED, not guaranteed coverage or calibrated trading probability. Directional
accuracy remains null until actual earlier walk-forward forecasts have available outcomes.

## Replay and persistence

Every enumerated captured opening/representation is replayed, including rejected rows. Processing
is ordered by decision T/immutable ID. Each row carries Trust evidence, historical retrieval,
opening prediction, predicted share adjustment, optional cost-adjusted edge, hypothetical decision,
hypothetical risk and separately labeled opening outcome. Shared `analytical_edge` was extracted
from the existing Opportunity engine without changing its formula or rules; DEMO and replay use
the same arithmetic. Missing historical fees/gas/slippage/buffer are not zero-filled.

A research-only proposal needs valid features/model, at least 3 analogues, Information Trust and
positive measured cost-adjusted edge. It still reports REJECTED_PRODUCTION_GATES. Existing
financial Risk/Opportunity contracts are DEMO-only, and no historical wallet balances/risk budgets
were captured; replay therefore reports NOT_READY or gate rejection rather than pretending to
pass those limits or sizing a position. No routing/quote/transaction gateway is invoked. An equity
opening return is not token sale proceeds: token execution P&L remains unavailable. This preserves
the clean supported analytical boundary while exercising the complete hypothetical replay sequence.

The research store is separate from application SQLite and writes content-addressed JSON through
atomic no-overwrite publication. Artifacts include the full typed episode dataset, costs, policy,
input digest, source snapshot hashes, implementation checksum, deterministic run ID,
all rows/counts/accuracy and a SHA-256
integrity envelope. Same input/config reproduces the same output, including after loading an
artifact. Corruption/conflicting identities stop. No wall clock, random UUID or scorecard enters
the replay identity. Local artifacts under `data/research/` are ignored by Git.

Run from the repository root, with no credentials or network needed:

```sh
.venv/bin/python scripts/replay-research.py
# Optional new evidence file; existing evidence is never overwritten:
.venv/bin/python scripts/replay-research.py --evidence /private/tmp/new-phase5-evidence.json
```

## Measured real data coverage and data gate

[Real replay evidence](evidence/PHASE_5_REAL_REPLAY.json) uses existing real captures only.

| Coverage | BStock NVDAB | Ondo NVDAon |
|---|---:|---:|
| Distinct official historical candles | 2,805 | 4,546 |
| Earliest candle UTC | Jun 12 00:00 | Mar 3 07:00 |
| Latest candle UTC | Oct 6 10:00 | Oct 5 23:00 |
| Daily / hourly / minute candles | 107 / 2,388 / 310 | 174 / 4,102 / 270 |
| Enumerated full-span reopening candidates | 17 | 31 |
| Eligible research training episodes | 0 | 0 |

Combined inventory retains 122 original token observation records and 7,336 isolated raw bars;
deduplicated official candles total 7,351. Independent Massive history has 2,143 distinct BAR events:
1,921 one-minute and 222 five-minute bars, Mar 6 20:59–Oct 5 23:59 UTC. Sparse targeted windows are
not continuous coverage. There are 48 representation-windows sharing 31 actual stock openings;
48 posthoc outcome attachments do not mean 48 independent stock outcomes. The prior historical
audit has 43 representation-windows /26 openings inside its 180-day current audit window.

Actual persisted real Trust samples/baseline episodes remain zero. Real qualifying baseline/model/
analogue counts remain **0/30, 0/30, 0/3**, respectively. No real prediction or measured directional
accuracy is reported. Every one of the 48 historical decisions lacks a known as-of ratio,
known close reference/token metadata and complete features; the calendar copy was verified later.
Newly captured close/opening prices are retained solely as POSTHOC_ONLY outcomes. The existing
[full rejection/density audit](TRUST_BLOCKER_HISTORICAL_REPORT.md) remains unchanged: missing
historical authoritative liquidity, comparable candle-volume units, revision/first-availability
and decision-time news evidence also block qualification. These are data/provenance blockers,
not qualifying rows lost by a join.

The implementation gate concerns machinery correctness. The data gate requires a supported exact
scope with at least 30 qualifying baseline episodes, at least 30 independent model outcomes and
at least 3 eligible analogues, plus an actually valid local fit and all point-in-time evidence.
Software/synthetic test success cannot pass that data gate. TRUST_GATE and every production gate
are unchanged. Massive current snapshot/NBBO remains denied; Twelve Data is not admitted to Trust,
and the scheduled alignment diagnostic was not run. GeckoTerminal does not become authoritative.

## Verification and preservation

Full backend suite, frontend regression, TypeScript/build, Ruff lint/format, dependency consistency,
security and desktop/mobile browser checks pass. Final counts and preservation hashes are recorded
in [verification evidence](evidence/PHASE_5_VERIFICATION.json). New synthetic controls cover
construction/normalization/reference-close/target, first availability, future news/liquidity/ratio/
corporate actions/outcomes, vectors/cosine/top-K, insufficient/malformed/mixed inputs, rolling
univariate/multivariate fits, rank deficiency, reproducibility, costs and blocked risk, persistence/
corruption, DEMO isolation, source SQL read-only behavior, early close/holiday/DST and regular
30-second alignment. Existing tests were retained. The existing Starlette/httpx deprecation
warning remains; no dependency or safety workaround was introduced.

Browser evidence verifies all three existing DEMO scenarios on desktop and mobile, including
the full Information→paper execution→exit→scorecard flow, stand-down paths, unchanged ordinary
Overview INSUFFICIENT_EVIDENCE and disabled production Opportunity navigation: 39 local HTTP200
requests, zero provider/live execution calls. Its new evidence file preserves prior browser evidence.
Temporary test servers were stopped; existing user services were not changed.

Changed files:

- `backend/app/models/research.py` — immutable research, availability, target, model and replay contracts.
- `backend/app/services/opening_target.py` — shared configured opening outcome calculation.
- `backend/app/services/research_episodes.py` — historical Trust snapshot, decisions/targets/candidates.
- `backend/app/services/research_model.py` — deterministic vectors/retrieval and rolling QR OLS.
- `backend/app/services/research_replay.py` — walk-forward orchestration, counts, accuracy and abstention.
- `backend/app/repositories/research_source.py` — read-only primary historical inventory/loader.
- `backend/app/repositories/research.py` — isolated immutable replay persistence/integrity.
- `backend/app/services/opportunity.py` — extracted shared economics; existing rules unchanged.
- `backend/tests/unit/test_research.py`, `backend/tests/integration/test_research_source.py` — synthetic controls.
- `scripts/replay-research.py` — explicit offline real-data audit/replay command.
- `scripts/investigate-trust-data.py`, `scripts/investigate-trust-blockers.py` — reuse shared target/configuration.
- `.gitignore` — exclude local research artifacts.
- `README.md`, `docs/PHASE_MAP.md`, `docs/EXECUTION_GATES.md`, `docs/ARCHITECTURE.md` — current scope/runbook.
- This report and `docs/evidence/PHASE_5_REAL_REPLAY.json`, `PHASE_5_BROWSER.json`, `PHASE_5_VERIFICATION.json`.

No historical report/evidence, raw database, DEMO fixture, Trust source/policy, production gate
implementation, master copy, frontend code or external provider permission was changed. No commit.

**Next engineering phase: Phase 6 — Multi-Agent Intelligence, only on separate authorization.**
Its consumers must preserve NOT_READY/INSUFFICIENT_DATA and the blocked real data/Trust/Opportunity/
LIVE boundaries. Phase 5 data remediation remains necessary for real predictions. STOP after Phase 5.
