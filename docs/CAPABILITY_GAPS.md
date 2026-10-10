# Capability gaps and closure evidence

## Finnhub event adapter increment — October 10, 2026

Typed, bounded company-news, earnings, US status and holiday reads are implemented and
authenticated in an isolated eight-request diagnostic. Raw event access is available; exhaustive
coverage, schedule publication/revisions and historical first availability remain unverified.
Five returned holiday entries have malformed post-market hours and remain INVALID.
The adapter is an explicit research reader, not a replacement for existing Trust news/calendar
consumers. There is no production persistence or new qualifying history.

Current equity freshness/alignment, historical economic ratios/as-of features, authoritative
liquidity and real 30/30/3 evidence remain unresolved. Finnhub quotes/candles are excluded from
this adapter. All production gates are unchanged. See [implementation report](FINNHUB_EVENTS_REPORT.md)
and the preserved [multi-provider diagnostic](MULTI_PROVIDER_DATA_DIAGNOSTIC.md).

## Session-aware continuation — October 10, 2026

The missing Alpaca adapter is now implemented and independently selectable; external access
remains NOT_VERIFIED because credentials are absent. This does not close G03 or any Trust/LIVE
blocker. Current default/legacy Massive behavior and historical evidence remain intact.
New open dependencies: actual Alpaca feed/account entitlement/freshness/alignment and licensing;
reference-policy integration (unchanged Trust source allowlist currently rejects Alpaca);
official close/extended-session support and provider-independent resumable backfill;
Finnhub events/session integration; optional runtime-verified HIP-3 corroboration.
Historical ratio/as-of, liquidity and qualifying 30/30/3 evidence gaps remain unchanged.
See [the gap analysis and diagnostic evidence](SESSION_AWARE_DATA_REPORT.md).

## Latest read-only data investigation — 2026-10-06T17:56Z

**TRUST_GATE=BLOCKED.** Fresh current Snapshot/NBBO reads return403 with explicit entitlement-denial categories; historical aggregates/news return200 with the same key. Exact account plan is UNKNOWN. A qualifying real-time Snapshot is sufficient for the existing analytical reference; NBBO is optional. The minimum listed individual plan is Advanced USD199/month, subject to individual/nonprofessional licensing and actual returned-data freshness. Fifteen-minute delay does not meet current120s age/30s skew requirements. No upgrade or alternate data substitution occurred. [Current pricing](https://massive.com/stocks).

Ondo BSC NVDA PRICE_INFO200/business0 has price, documented USD activity and holder counts, but absent/null liquidity and no separate authoritative liquidity asof. Neither activity nor partial top pools close this gap; no adapter change was warranted.

Real bounded backfill improves NVDA token observations39→122 and equity BAR records945→2083 (plus1 separate REGULAR_CLOSE), with1 potential weekend reopening and1 measurable posthoc opening outcome. **Qualifying baseline episodes0/30, opening-model episodes0/30, historical analogues0/3, complete-feature episodes0.** Historical ratio provenance, liquidity, candle-volume units, first availability/revisions, news first-seen and sparse minute coverage prevent qualification. Real captures and synthetic tests remain separate. No sample requirement, confidence rule or LIVE restriction changed.

See [latest investigation, exact metrics and rejection reasons](PHASE_2_TRUST_REMEDIATION.md#read-only-trust-data-investigation--latest-gate-evidence), [actual before/after evidence](evidence/CANONICAL_PHASE_2_TRUST_DATA_INVESTIGATION.json), and [current formal gate](evidence/CANONICAL_PHASE_2_TRUST_GATE.json). Earlier sections below remain historical snapshots; raw coverage growth is not Trust readiness. Current Phase1/DATA/DRY_RUN=PASS; Opportunity=BLOCKED_BY_TRUST; all three LIVE gates=BLOCKED.

## Latest capability remediation — 2026-10-06

TRUST_GATE remains BLOCKED. Snapshot, NBBO and alternative last trade were freshly denied403/NOT_AUTHORIZED with entitlement-denial categories; exact account plan remains UNKNOWN. PRICE_INFO token liquidity is missing for both issuers; top-pool diagnostics cannot establish comparable token-wide liquidity/freshness. All inspected real Trust sample/episode counts are0, below30 episodes/3 analogues. No historical backfill can establish missing asof ratios/liquidity from the available raw bars.

G17 is partially remediated for the measured **decision window**: an order/provenance/availability-verified descending news prefix reaches strictly before the required start. Full history remains PARTIAL; hourly refresh/unknown causal direction remain explicit. News absence still cannot prove no information. No threshold, confidence, LIVE control or other gap was downgraded. See the exact [blocker table and candidate audit](PHASE_2_TRUST_REMEDIATION.md) and [fresh actual evidence](evidence/CANONICAL_PHASE_2_TRUST_REMEDIATION_REVERIFIED.json). Older snapshots below remain historical.

## Current Canonical Phase 2 capability boundary (2026-10-06)

Deterministic Trust services/API/UI are implemented and software-verified. TRUST_GATE=BLOCKED; Canonical Phase 1/DATA/DRY_RUN remain PASS; OPPORTUNITY_GATE=BLOCKED_BY_TRUST and three LIVE gates remain BLOCKED. Earlier current/untested/unimplemented statements below record historical snapshots. See [Trust report](PHASE_2_TRUST_REPORT.md) and [gate evidence](evidence/CANONICAL_PHASE_2_TRUST_GATE.json).

Remaining actual blockers: regular-session independent snapshot403 (previous NBBO403 evidence accepted unchanged); mandatory PRICE_INFO liquidity absent (volume is available) for evaluated NVDA representations; bounded news PARTIAL; no30 qualifying completed real Trust episodes or3 analogues. Ratio source-asof and earnings context remain unavailable. Historical equity remains HISTORICAL, historical ratio/unit uncertainty is excluded from backfilled baselines, and closed-session support cannot certify current quotes. No research calibration or paper coefficients are claimed.

The numerical-boundary portion of G07 has an implemented analytical solution: shared fixed-precision Decimal normalization, Decimal statistics/square roots/cosine and JSON-text persistence; no statistical-library float conversion. This does not close real calibration/history or any LIVE gap. No execution, wallet, RFQ, simulation/equivalence or risk requirement is changed.


**Current update after the historical record (2026-10-06):** Canonical Phase 1 Working Ask Flow is PASS; DRY_RUN_GATE=PASS for non-executable estimates/proposals only. DATA_GATE remains PASS; TRUST_GATE=NOT_YET_TESTED; OPPORTUNITY_GATE=BLOCKED_BY_TRUST; all three LIVE gates remain BLOCKED. Trust has not started. Original snapshots below are historical; [current gate definitions](EXECUTION_GATES.md) and [Phase 1 report](PHASE_1_REPORT.md#canonical-phase-1--working-ask-flow) supersede their implementation-readiness statements without changing their evidence.

**Phase numbering reconciliation (2026-10-06):** The original ledgers and phase-specific snapshots below remain historical evidence. Foundation and Data Layer are Engineering Stages 1/2, PASS within their reported scope; they do not complete Canonical Phase 1 — Working Ask Flow or implement Canonical Phase 2 — Trust Layer. Current documentation gates are DATA_GATE=PASS; TRUST_GATE=NOT_YET_TESTED; OPPORTUNITY_GATE=BLOCKED_BY_TRUST; DRY_RUN_GATE=NOT_YET_TESTED; SWAP_LIVE_GATE=BLOCKED; RFQ_LIVE_GATE=BLOCKED; AGENTIC_WALLET_LIVE_GATE=BLOCKED. Trust classification, baselines/confidence and opportunity selection remain unimplemented; calendar/quality data alone do not close those gaps. Opportunity must not begin until Trust completion. No existing gap is resolved or downgraded by this reconciliation. See [PHASE_MAP.md](PHASE_MAP.md) and [current gate requirements](EXECUTION_GATES.md).

Date: 2026-10-06. Reconnaissance facts remain accepted. The 2026-10-06 amendment separates development advancement from LIVE gates; no implementation or execution-safety waiver.

| ID | Severity / gate effect | Gap | Safe disposition | Required closure evidence |
|---|---|---|---|---|
| G01 | CRITICAL for RFQ LIVE; RFQ_LIVE_GATE BLOCKED | RFQ final vendor-relayed settlement has no verified exact pre-execution simulation/equivalence mechanism | Disable LIVE RFQ, including signing/submission; keep reads and proposals | Official vendor/gateway mechanism identifying coverage, settlement bindings and limits; sanitized non-capital validation |
| G02 | CRITICAL for wallet LIVE; AGENTIC_WALLET_LIVE_GATE BLOCKED | baw absent; Developer Mode path documented but runtime equivalence, gas/nonce handling and session behavior untested | All LIVE gateway operations unavailable | Installed compatible official CLI/skill, user-controlled connected runtime, preview fixtures and exact-call reconciliation tests without real capital |
| G03 | CRITICAL for live analysis/action | Massive account entitlement, independent quote delay, history and redistribution access unknown | No freshness-dependent live decision; label unavailable/delayed accurately | Account plan evidence and sanitized responses for quotes, snapshots, minute bars, news and schedule |
| G04 | HIGH; complete contract verification incomplete | Current schema browsable but download blocked; no complete schema diff or uploaded snapshot | Do not call contracts exhaustively schema-verified | Nonempty official schema, provenance/hash, required endpoint comparison and documented rendering exceptions |
| G05 | HIGH for numeric research claims | Full Tokenized Stocks tables/dataset unavailable; 0.98/0.90 not independently re-established | Do not use coefficients or claim paper fully read | Complete latest author/SSRN manuscript, exact tables/population/sample details |
| G06 | HIGH for replay | Massive upcoming holidays are forward-looking; historical schedule source not implemented or fully specified | No historical session inference from weekday alone | Versioned historical exchange schedule, DST/early-close/reopening fixtures |
| G07 | HIGH for numerical implementation | Decimal-all-financial requirement versus float-oriented statistical packages | No implicit numeric exception | Explicit approved statistical boundary or compatible Decimal/fixed-point modeling plan with error/threshold tests |
| G08 | MEDIUM; not a fabricated comparison | Uploaded proposal/OpenAPI absent; master path corrected in Phase 0.1 | Root master retained and copied exactly to docs; unavailable artifact comparisons recorded | Supplied artifacts or confirmed absence; do not invent differences |
| G09 | HIGH before opportunity LIVE | Actual historical coverage, baseline and episode counts unknown | BASELINE_PROVISIONAL / INSUFFICIENT_DATA | Available-time historical ingestion and sufficient local stock/issuer/regime samples |
| G10 | HIGH for trading | Runtime RWA contracts, funding decimals, liquidity, issuer restrictions and aggregator support untested | Runtime discovery required; unsupported path unavailable | Signed read-only discovery/metadata/status/quote responses and validated chain/contract mappings |
| G11 | MEDIUM, optional | Agent Studio, BTC/ETH subsystem, model/vendor and earnings calendar unspecified | Defer optional features; no invented services | Separate official verification if selected; configurable LLM schema/limits |
| G12 | HIGH for autonomous mode | External-sign docs require user confirmation; Developer Mode quotas separate | PROPOSE_ONLY; do not claim autonomous external execution | Officially supported confirmation/policy behavior compatible with product mandate; no bypass |

## Exact execution conclusion

The official CLI now documents external EVM contract calls and EIP-712 message signing. That closes the question of whether a command family exists. It does **not** close runtime transaction equivalence or RFQ settlement simulation. The broad wallet overview is less detailed than the current skill references; use the latter for command syntax.

The [Trading API](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/trading-api) describes vendor-relayed RFQ settlement. The [external-sign reference](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/external-sign.md) describes parsed messages and risk checks, not a final RFQ settlement transaction preview. This report's inability to establish equivalence is an inference from reviewed coverage, not a claim that no possible mechanism exists anywhere.

## Non-capital reassessment plan

1. Obtain missing artifacts, an official schema snapshot and complete research text.
2. Verify installed skill/CLI versions and read-only connected wallet capability; no installation or authentication was performed here.
3. Verify account entitlements and sanitized read-only discovery, metadata, independent equity and quote responses.
4. Examine documented contract-call preview for exact transaction/gas/fingerprint binding. Never execute during the reassessment.
5. Obtain an official final-settlement RFQ safety contract. A typed-data signing preview alone cannot close G01.
6. Reassess each affected capability gate independently against its required evidence. The original failed development decision is superseded by the explicit gate amendment; critical LIVE blockers remain critical.

## Phase 0.1 current evidence and gate separation

The [remediation ledger](PHASE_0_REMEDIATION.md) is the current per-blocker record with attempts, exact evidence, safe behavior, disabled paths, dependencies and phase impacts. G08's master-location subgap is RESOLVED by byte-equivalent copying; unavailable uploads remain unverified.

G13 (new): Binance credentials were initially absent. After local configuration, ten signed read-only probes returned HTTP200/business0. Credential availability, authentication and those specific read permissions are VERIFIED ([sanitized evidence](evidence/BINANCE_READONLY_STATUS.json)). Build, exact simulation, actual-wallet reads, RWA RFQ quote and execution/write permissions remain NOT_TESTED. No generic account-wide entitlement is asserted. G10 is therefore PARTIALLY VERIFIED for RWA discovery/funding metadata/standard quoting; actual RWA execution eligibility remains unknown.

G01 remains RFQ_LIVE_SAFE=NOT_VERIFIED, not resolved. G02 remains local runtime UNAVAILABLE: no baw/global package or matching installed skills in inspected paths. Official missing dependencies: @binance/agentic-wallet compatible with wallet skill 1.12.0 (currently required CLI1.10.0), installed selected Binance skills and user-controlled App pairing, followed by validated worker/session access. Node v24.12.0 is already present. Installation and pairing were documented, not performed.

Separate [gates](PHASE_0_GATE.md): DATA reads VERIFIED only in measured scope; DRY_RUN design feasible but not implemented/tested; SWAP LIVE NOT_VERIFIED; RFQ LIVE NOT_VERIFIED; Agentic Wallet LIVE unavailable locally. All LIVE writes remain disabled. Unresolved RFQ safety does not make independent reads/DEMO/DRY_RUN impossible. The amended PHASE 0 DEVELOPMENT GATE is PASS and Phase 1 MAY BEGIN; Phase 1 has not started in this task.

## Current development and capability decisions

| Gate | State | Gap impact |
|---|---|---|
| PHASE 0 DEVELOPMENT GATE | PASS | Safe non-live advancement allowed; no LIVE ambiguity is marked resolved |
| DATA_GATE | PASS | Accepted measured reads; untested sources and freshness stay explicit |
| DRY_RUN_GATE | NOT_YET_TESTED | Feasible; implement and test no-live-action behavior later |
| SWAP_LIVE_GATE | BLOCKED | G02/G10 and exact SWAP simulation/execution equivalence remain unverified |
| RFQ_LIVE_GATE | BLOCKED | G01 exact vendor-settlement safety remains unverified |
| AGENTIC_WALLET_LIVE_GATE | BLOCKED | G02/G12 runtime, worker and confirmation-policy evidence pending |

[EXECUTION_GATES.md](EXECUTION_GATES.md) defines each gate's prerequisites, evidence, unlocks and blocked capabilities. G03–G07/G09/G10 continue to constrain affected source, replay, modeling and execution claims; safe DEMO/mocks do not resolve those gaps. Phases 1–7 may proceed non-live, Phase 8 only safety/execution infrastructure and DRY_RUN, and Phase 9 only abstractions/mocks/read-only/verified interfaces. No LIVE capability is unlocked. Required future configuration: DATA_MODE=DEMO or LIVE_READ_ONLY; EXECUTION_MODE=DRY_RUN; APPROVAL_MODE=PROPOSE_ONLY; LIVE_TRADING_ENABLED=false; REQUIRE_SIMULATION=true. No broadcasts, RFQ submissions, wallet settings changes, fund movements or real positions. This amendment starts no implementation.


## Phase 2 measured gap updates — 2026-10-06

Historical Phase0/1 descriptions above remain evidence of their respective scope. Current changes:

| Gap | Current evidence | Remaining restriction |
|---|---|---|
| G03 | PARTIALLY VERIFIED: configured Massive key; status/holidays/minute+day bars/news/splits/dividends200; snapshot/NBBO403 | No current independent equity quote; account plan/delay/redistribution unknown; no freshness-dependent decision |
| G06 | PARTIALLY VERIFIED: implemented versioned official NYSE2026–2028 calendar, UTC/DST/early-close/closure/reopening tests | Other venues' extended hours, older schedules, emergency closures and historical revisions unknown; no replay outside coverage |
| G10/G13 | Read-only implementation and signed runtime validation for all13 selected Binance market/RWA reads; dynamic NVDA Ondo/BStock discovery and exact ratios | No funding/execution eligibility proof; liquidity/unit and issuer restriction gaps remain; no quote/build/simulation/wallet test in Phase2 |
| G14 (new) | Real488-row BSC catalog includes37 critically invalid rows; documented pause differs from returned paused; invalid types/names also observed | Exclude affected representations, mark catalog PARTIAL; do not claim exhaustive eligible-universe coverage |
| G15 (new) | Real NVDA/NVDAB reported trade price unit differs from plausible USD/token price | Quarantine price as CONFLICTING/null; raw reported price retained; no USD-price or liquidity inference |
| G16 (new) | Candle lower bound ignored and end cursor inclusive in measured calls | Local exclusive-window filtering, counted exclusions and progress guard; monthly duration and candle volume unit unverified |
| G17 (new) | News bounded first page100 persisted; valid next cursor exists | Partial history marked; no complete retention, revisions or point-in-time historical availability claimed |

[Pipeline](evidence/PHASE_2_PIPELINE.json) passes the Phase2 read-only gate to measured entitlement level. Snapshot/NBBO403 is isolated from RWA/history/news; no fallback to Binance referencePrice or DEMO. Two slow default-window Binance probes returned401; no credential values or bodies were retained, and auth failures were not automatically retried. A subsequent explicit verification using the documented60000ms receive window passed. Timing makes window expiry a plausible explanation, not a verified provider error reason.

G01/G02/G04/G05/G07/G09/G11/G12 remain unresolved in their applicable scope. No safety requirement is weakened. DATA_GATE=PASS; DRY_RUN_GATE=NOT_YET_TESTED; SWAP_LIVE_GATE=BLOCKED; RFQ_LIVE_GATE=BLOCKED; AGENTIC_WALLET_LIVE_GATE=BLOCKED. Phase2 completion does not authorize any later phase or live action.

G18 (new): historical token bars/trades carry metadata ratios observed at ingestion, not independently verified as-of historical ratios. Exact metadata versions and corporate-action reads are retained, but no historical adjusted/look-ahead-safe series is claimed. Future research must resolve temporal ratio availability before using these observations for decisions.
