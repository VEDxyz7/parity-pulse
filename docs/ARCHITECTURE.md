# Architecture decision record — through Phase 2

## Master Phase 9 — controlled wallet reads and DRY_RUN, October 8, 2026

**Implementation PASS; actual CLI runtime UNAVAILABLE; production gates unchanged.**
[Phase 9 report](PHASE_9_REPORT.md) and [capability matrix](AGENTIC_WALLET_CAPABILITIES.md)
separate actual observations from official documentation and synthetic tests.

`BawReadOnlyClient` is a closed command/argument transport with no shell, bounded time/output,
sanitized errors and exact reviewed version checks. `AgenticWalletAdapter` produces immutable
typed snapshot/order/history/indicative-quote results. Public startup injects a client-less adapter;
only an explicitly controlled local host/diagnostic can opt into real CLI reads. No authentication,
secret store, remote REST interface, public wallet API or mutation transport is added.

`AgenticWalletCliGateway` extends the existing DRY_RUN gateway and adds wallet identity, chain,
balance, quota, token-scope, session, confirmation and pending-state checks. It reuses all Phase 8
Risk/Funding/Quote/Fingerprint/Simulation/Approval checks and always blocks execution. Snapshots
remain transient; CLI token marks do not become independently timestamped funding/equity prices.

`WalletReconciler` reads existing mode-scoped attempts with their original IDs/CAS versions.
Only the Phase 8 settlement tracker can confirm exact terminal execution; its optional independent
corroboration guard keeps conflicts UNKNOWN. Wallet status/FINISHED/hash alone never confirms.
Timeouts and restarts create no new order. No position persistence, monitoring or exit engine is added.

DEMO fixtures cannot enter LIVE_READ_ONLY. Frontend, research, Trust, routing, agents, Opportunity,
Risk arithmetic and the full paper lifecycle remain unchanged. DATA/DRY_RUN=PASS; TRUST=BLOCKED;
OPPORTUNITY=BLOCKED_BY_TRUST; all three LIVE gates=BLOCKED. Phase 10 was NOT started.
Earlier architecture sections remain historical snapshots; the sole master specification is unchanged.

## Master Phase 8 — host-only safety and execution, October 8, 2026

**Implementation PASS; all production gates unchanged.** [Phase 8 report](PHASE_8_REPORT.md)
describes contracts, eligibility, exact arithmetic, persistence and test evidence. The existing
Trust, research, routing, six-agent and Phase 7 analytical services are reused without new logic
in agents or React. The complete DEMO paper lifecycle and frontend remain unchanged.

`SafetyExecutionService` accepts typed host Risk/funding/allowance evidence and can consume the
existing Phase 7 decision. `RiskEngine.evaluate_execution` shares existing position-cap arithmetic
and adds hard execution controls. Funding resolution uses existing market discovery/metadata;
USD notional, funding-token base units and native gas units remain separate.

`BinanceSafetyClient` reuses the sole signer and bounded HTTP transport, permitting only reviewed
quote/build/simulation/approval-build/status operations. `AggregatorQuoteService` validates exact
request bindings and ranks provider routes deterministically; issuer routing is unchanged.
Builders resolve SWAP/RFQ from the actual route, retain exact provider artifacts and compute
canonical fingerprints. Approvals have separate route-bound fingerprints/simulation. RFQ typed
data and submission bodies are prepared offline; no submission transport exists.

Simulation admits only the documented BSC EVM payload and records its limited coverage.
RFQ settlement is explicitly unavailable; fixture success never certifies live equivalence.
Strict transitions, bounded status reads, idempotent UUIDs, versioned compare-and-swap and
chained audit snapshots support fail-closed recovery. Unknown status cannot authorize a retry
or be locally dismissed to create another order.

Only `DryRunExecutionGateway` implements the execution boundary; it independently rechecks hard
controls and always refuses execution. There is no public execution/approval endpoint and agents
cannot invoke the gateway. Startup injects a real read-only client only in LIVE_READ_ONLY;
DEMO has no real safety client. The separate journal is memory-only for DEMO/tests or stored
under ignored `data/execution/phase8/` beside persistent application data. No historical writes occur.

DATA/DRY_RUN remain PASS; TRUST remains BLOCKED; OPPORTUNITY remains BLOCKED_BY_TRUST;
all three LIVE gates remain BLOCKED. Phase 9 wallet/runtime/signing integration was NOT started.
Earlier sections retain dated architecture history. `docs/MASTER_SPEC.md` is unchanged.

## Master Phase 7 — Opportunity Mode, October 8, 2026

PHASE_7_IMPLEMENTATION=PASS. The user explicitly authorized non-executable Opportunity
machinery while the production Trust/data prerequisite remains blocked. The full-universe
scan, candidate audit, shared routing/ranking, top-K=5, existing Phase 6 agents and
request-bound ex-ante Risk sizing are verified. See [Phase 7 report](PHASE_7_REPORT.md).

DATA_GATE=PASS; DRY_RUN_GATE=PASS; TRUST_GATE=BLOCKED;
OPPORTUNITY_GATE=BLOCKED_BY_TRUST; all three LIVE gates=BLOCKED.
Real history remains 0/30 baseline, 0/30 opening-model, 0/3 analogues.
Implementation PASS does not pass any production gate. Phase 8 has NOT started.

The dated sections below preserve historical checkpoints. Their earlier “not started” or
“next phase” statements are superseded only for implementation status by this explicitly
authorized Phase 7 milestone. Production eligibility, safety rules and prerequisites
remain unchanged. The sole authoritative master is `docs/MASTER_SPEC.md`.

## Master Phase 6 — bounded shared interpretation

The current authoritative [MASTER_SPEC.md](MASTER_SPEC.md) was read entirely before Phase 6.
[Phase 6 report](PHASE_6_REPORT.md) records implementation PASS / data dependency BLOCKED.
`app.agents` consumes existing deterministic Trust/research and DEMO Opportunity/Risk/Route outputs.
Intent → Market/News/Research → Opportunity → Decision/risk preview → audit/memory → STOP.
No execution client or new financial calculation lives in this layer.

DEMO and LIVE_READ_ONLY adapters use the same six classes. Input/output schemas enforce mode,
provenance, chronology, budgets and uncalibrated confidence. Closed per-agent readers have no raw
SQL/network/wallet/execute capability. Optional explicitly injected structured LLM calls cannot
change deterministic facts, confidence or authorization; no vendor entitlement is claimed.

Separate SQLite/SQLAlchemy agent audit and K=4 structured memory never touch application history
or execution databases. Future publications/first availability, historical outcomes and scorecards
are projected before workflow identity/tool access. The CLI `scripts/analyze-agents.py` emits
structured JSON; no API/UI change is required for the reusable service milestone.

Production gates and the full DEMO UI/paper pipeline remain unchanged and regression-verified.
Phase 7 full-universe scanning has NOT started. Earlier architecture sections are historical snapshots.

## Master engineering Phase 5 — isolated production research machinery

October 7, 2026: [Phase 5 report](PHASE_5_REPORT.md) records implementation PASS / data gate BLOCKED.
`HistoricalSource` reads existing analytical SQLite tables in read-only transactions and the existing
official raw history capture. Its payload/dataset provenance preserves first availability and null
historical ratios. Neither experimental pool data nor Twelve Data is admitted to production Trust.

`ResearchEpisodeBuilder` reuses the unchanged Trust evaluator, calendar, normalization, reference,
news, liquidity, baselines and 30-minute episode builder through an in-memory historical snapshot.
Opening outcomes are separately typed and use the shared five-minute target configuration. Explicit
payload-bound effective/availability/revision proofs precede feature eligibility. Raw posthoc targets
remain separate from decision information. Current ratios never become historical ratios.

Research vector/retrieval and rolling Decimal QR OLS operate on exact, same-scope, completed,
available episodes. They return counts, provenance and insufficient/not-ready states. Walk-forward
replay includes rejected candidates, uses the existing Opportunity arithmetic through a shared pure
helper, and abstains when costs/risk evidence is absent. No real row is converted to a DEMO risk
contract. Global production gates continue blocking action; equity outcomes are not execution P&L.

`ResearchStore` publishes immutable, integrity-checked JSON artifacts containing the complete dataset,
policy/cost inputs, source hashes, deterministic IDs and results under Git-ignored `data/research/`.
It never opens or modifies production execution databases. The explicit offline command is
`.venv/bin/python scripts/replay-research.py`; it loads no credentials and has no network client.
No startup hook, endpoint, scheduler, frontend calculation, agent, live route or wallet is added.
The existing DEMO flow and API/gate contracts remain unchanged. Earlier sections are preserved snapshots.

## Latest bounded Trust correction — 2026-10-06

Architecture and financial/execution rules are unchanged. MassiveProvider now resets and verifies a descending latest-news prefix boundary; NewsAlignmentService checks whether that prefix covers the required window while retaining full-history partial and hourly-feed reasons. The existing TrustService passes this provenance only; no agent, scheduler, gateway or new production endpoint was added. Independent403, missing liquidity and zero real history keep TRUST_GATE=BLOCKED. [Remediation audit](PHASE_2_TRUST_REMEDIATION.md) distinguishes diagnostic-only pool/last-trade reads from application permissions and preserves previous evidence.

## Current Canonical Phase 2 implementation (2026-10-06)

The authorized Trust Layer now composes existing read-only providers with MarketRegimeService, IndependentReferenceService, LiquidityEvidenceService, NewsAlignmentService, BaselineService, EpisodeBuilder, AnalogueService and TrustClassifier. One shared Decimal normalizer serves unchanged Phase 1 economics and Trust comparison. New frozen schemas/repository and three additive revision4 tables preserve old data/proposals. GET /api/assets/{ticker}/trust persists analytical evidence/IDs only; the separate minimal UI displays backend values and reasons. No LLM, trading gateway, transaction builder, wallet, risk/Opportunity engine or scheduler is introduced.

TRUST_GATE=BLOCKED: software contracts and synthetic scenarios are verified, but actual NVDA current reference is403, required liquidity metrics absent, news partial and qualifying real episode history unavailable. DATA/DRY_RUN/Canonical Phase 1 remain PASS; Opportunity and all LIVE gates remain blocked. Exact policy/formulas/availability boundaries: [DATA_CONTRACTS.md](DATA_CONTRACTS.md); implementation/evidence: [PHASE_2_TRUST_REPORT.md](PHASE_2_TRUST_REPORT.md).

Earlier “current” Phase 1/reconciliation/engineering-stage sections below are preserved historical snapshots. This section supplies the latest implemented scope; the legacy system-status phase2/five gates still mean Engineering Data Layer plus tested Ask, not Trust readiness. The Trust endpoint separately reports its blocked gate.


**Current Canonical Phase 1 update (2026-10-06):** Working Ask Flow and indicative proposal DRY_RUN gate now PASS. The earlier implementation snapshots below retain their historical engineering-stage scope. Trust Layer remains NOT STARTED; Opportunity remains BLOCKED_BY_TRUST; all LIVE gates remain BLOCKED. See the new implementation section at the end and [current report](PHASE_1_REPORT.md#canonical-phase-1--working-ask-flow).

**Phase numbering reconciliation (2026-10-06):** Implemented "Phase 1 — Foundation" and "Phase 2 — Data Layer" sections below are Engineering Stages 1/2 and retain their historical scope/evidence. Both stages PASS; Canonical Phase 1 — Working Ask Flow is incomplete. Canonical Phase 2 — Trust Layer has NOT started and is NOT complete; trust/opportunity architecture described below remains future design. DATA_GATE=PASS; TRUST_GATE=NOT_YET_TESTED; OPPORTUNITY_GATE=BLOCKED_BY_TRUST; DRY_RUN_GATE=NOT_YET_TESTED; all three LIVE gates remain BLOCKED. Canonical Opportunity Mode cannot begin before Trust completion. [PHASE_MAP.md](PHASE_MAP.md) preserves the full master engineering sequence, and [EXECUTION_GATES.md](EXECUTION_GATES.md) defines the current development/LIVE boundaries. No architecture behavior, API, code or safety rule changes in this reconciliation.

Date: 2026-10-06. The original product architecture remains a design for later phases. Historical Phase 1 implementation is described below; the final Phase 2 section records the current read-only data layer. Product authority: [master prompt](MASTER_BUILD_PROMPT.md), especially sections 6, 14A, 39A, 49, 79A, 80A and 92A. Current external wire contracts override stale syntax.

## Product and authority

Exactly three modes: Direct Exposure, Opportunity, Autopilot. Single user, wallet, portfolio and execution context. Resolve company → equity ticker → discovered issuer/token representation. Reuse the same discovery, normalization, trust, route, risk and execution services for all modes. Optional BTC/ETH integration and Agent Studio remain outside MVP.

Raw provider observations → normalization → deterministic features/trust → bounded agent interpretation → deterministic opportunity/route selection → risk authorization → quote/build → route-specific safety → approval → gateway → terminal reconciliation → positions → scorecard/audit.

Financial facts, prices, ratios, costs, stress sizing, confidence caps and execution state belong to deterministic services. LLM output is untrusted structured interpretation. UI displays backend values, evidence and reason codes, never hidden reasoning.

## Provider boundaries

| Abstraction | Planned adapter | Authority / restrictions |
|---|---|---|
| RWADataProvider | Signed Binance RWA REST | Dynamic assets, issuers, ratio, token status; no invented addresses |
| EquityDataProvider | Massive REST | Independent stock quote/bars; account entitlements and freshness required |
| NewsProvider | Massive news | Publication and first-seen timestamps, ticker relevance; no causal assertion |
| CalendarProvider | Massive status/upcoming plus versioned exchange schedule | New York session logic, UTC storage, historical schedules required |
| TradingProvider | Signed Binance aggregator | Quote/build; returned executionMode determines branch |
| SimulationProvider | Binance Transaction API | Exact BSC EVM call; does not cover vendor RFQ settlement |
| WalletProvider | Controlled baw CLI worker | Runtime status, address, balances, policy and limits |
| LLMProvider | Configurable, vendor not selected | Strict schemas, bounded retries, no raw execution tool |
| ExecutionGateway | DryRun or verified AgenticWalletCli | Separate operation allowlist; unverified live capabilities disabled |

One BinanceWeb3Client owns signing, exact serialization, retries, rate accounting, payload validation and redaction. Do not share signed REST envelope handling with public skill BAPI responses. The tokenized-securities skill is supplemental and currently documents an Ondo-specific surface; it cannot define the complete BStock/Ondo universe.

## Data and numerical contract

Persist source, chain, contract, issuer, ticker, asset type, observed_at, received_at, data mode, quality, raw response reference and schema/config version. Separate DEMO, LIVE and replay datasets. Never silently substitute fixture data for failed live data.

Let P be USD/token, R shares/token, E independent USD/share. Effective cost/share = P/R; equivalent value/token = E×R; deviation = (P−E×R)/(E×R). Validate P,E,R positive and finite. Binance referencePrice is derived token information, not E. Ratios are time-dependent; retain historical versions and corporate-action context.

Use Decimal from provider strings or JSON numeric lexemes, integer token base units, explicit rounding and unit tags. SQLite money is canonical decimal text or scaled integers, never REAL; SQLAlchemy Numeric on SQLite alone is not proof of exact storage. The scientific stack ordinarily uses binary floats. This is an unresolved specification tension: no money/risk decision may silently round-trip through NumPy/statsmodels; approve a precise statistical arithmetic boundary before modeling implementation.

Store paired observation timestamps and skew. During closure, compare to the last actual regular-session close with explicit reference semantics rather than treating that close as a fresh quote. Intraday alignment and off-hours reference-close freshness need different policies. Historical bars must be filtered to actual regular sessions; “previous day” alone is not sufficient.

Keep signed market candle arrays distinct from public skill K-line arrays. Public dynamic tokenInfo.volume24h is stock USD volume, and public K-line slot5 is reserved; neither provides verified on-chain volume for trust/liquidity features. Independent NBBO timestamps are nanoseconds, while Binance price timestamps and Massive bar timestamps are milliseconds; convert explicitly before alignment.

## Trust and opportunity

Deterministic per-stock/per-regime baselines: mean, median, MAD, percentiles, sample_count, provisional flag. NORMAL / LIKELY_NOISE / LIKELY_INFORMATION are classification; LOW / MEDIUM / HIGH are confidence. Missing evidence limits confidence or blocks action.

Engineering defaults: 30 baseline episodes, 30 opening-model episodes, 3 analogues; these do not prove statistical significance. Prediction target is previous regular close → first completed five-minute regular-session bar close; unavailable bar = UNSCORABLE. Fit/retrieve using only information available at decision time, including availability time of revised news, ratios and corporate actions.

Opportunity scans the complete discovered eligible universe deterministically, then selects top K=5. Five batched interpretation calls maximum under normal flow: Market, News, Research, Opportunity, Decision. Intent extraction is separate; retries must have a total cap. Memory defaults to four relevant completed structured episodes per stock. Agents cannot invent numeric values or override eligibility.

Rank by eligibility, confidence tier, net edge, evidence, liquidity/execution quality, then normalized cost. Deduct fees, funding conversion, gas, slippage and buffer consistently in USD; do not sum returns and dollar costs. Weekday overnight Opportunity trading blocked. Weekend/reopening requires full history and prediction gates.

Budget is USD notional; funding defaults to runtime-verified BSC USDT. Stress loss = position_usd × configured adverse_move_fraction; require it within explicit risk budget and stricter platform/wallet limits. It is not a guaranteed maximum loss. No forced investment.

## Concrete wallet path

Official [wallet skill](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/SKILL.md) and [external-sign reference](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/external-sign.md) document the baw CLI, including Developer Mode external calls and EIP-712 signatures. Planned worker uses that CLI rather than an invented wallet REST API.

SWAP/approval candidate: build exact call → Binance simulate → successful baw contract-call preview with matching chain/from/to/value/inputData → inspect risk and wallet restrictions → explicit approval → execute cached requestId → reconcile hash to terminal success. Wallet-managed gas/nonce and preview expiry must be included in an approved equivalence policy. Runtime proof is absent; LIVE SWAP/approval remains unavailable.

RFQ candidate: build → bind signer/vendor/chain/tokens/amount/deadline → verify exact settlement safety coverage → EIP-712 preview/execute → assemble documented signature format → signed REST submit → terminal RFQ status. **Current decision: block before signature creation or submission; final-settlement safety coverage is unverified.** Permission to sign is not permission to claim settlement was simulated.

Do not substitute baw market-order swap for a simulated aggregator transaction: its documented interface has no external quoteId/calldata binding. Quotes/reads can inform proposals, but the integrated market-order path cannot satisfy exact equivalence based on documentation alone.

No autonomous external signing while the documented user-confirmation contract requires confirmation. App settings may impose further approval. Application never changes wallet limits or Developer Mode.

## Execution and recovery

Separate route quote ID, RFQ build order ID, submission UUID and platform settlement order ID. `/order/submit.quoteId` takes `/swap.rfq.orderId`. UUID retries are idempotent only within the documented 30-minute provider window; application persistence and reconciliation must prevent duplicates beyond it.

Approval is a first-class transaction: exact spender/amount, risk/simulation/confirmation, then fresh quote/build/simulation. Long analysis and human approval cannot assume a roughly 30-second quote remains valid. Changing amount, route, recipient, chain, minimum receive, calldata or relevant gas inputs invalidates the approval/fingerprint as appropriate.

States: proposed → risk approved → quote/build → safety passed → approval → submitted → pending → terminal confirmed/failed/expired/cancelled/unknown. Unknown pauses further execution and triggers reconciliation. RFQ FILLED, CLI market-order FINISHED and relay success are distinct source states, mapped explicitly; IDs and hashes alone never mean success.

Persist orders, positions, daily loss, cooldowns and decision uniqueness before submission. One execution worker and durable decision lock/unique constraint prevent concurrent submissions. Startup reconciles pending activity before any new execution. Ten-minute default post-open exit is deterministic and still subject to route safety; inability to exit must be visible, not assumed away.

## Deployment and verification

Public React/Vite/TypeScript UI + FastAPI/Pydantic backend + SQLite/SQLAlchemy. Scheduler performs bounded batched refreshes, drift monitoring and reconciliation, with one owner. Controlled local worker holds authenticated CLI context; no private keys, seeds or CLI sessions in frontend/public API. Worker accepts only structured allowlisted operations tied to persisted decisions.

Default design: DATA_MODE=DEMO, EXECUTION_MODE=DRY_RUN, APPROVAL_MODE=PROPOSE_ONLY, LIVE_TRADING_ENABLED=false, REQUIRE_SIMULATION=true. No runtime configuration was created. RFQ dry-run reports settlement simulation UNAVAILABLE, never PASS.

Planned checks: schema/signature contracts; Decimal/unit boundaries; session/DST/holiday/early-close; leak-free replay; malformed/injected agent evidence; risk rejection; expiry/re-quote; exact execution equivalence; terminal reconciliation; duplicates/restart; demo isolation; browser journeys; observability/performance. Run these only in their implementation phases. Phase 0 cannot certify a gateway from documentation alone.

## Development and capability-gate separation — 2026-10-06

The [EXECUTION_GATES.md](EXECUTION_GATES.md) contract separates development advancement from execution authority. PHASE 0 DEVELOPMENT GATE=PASS; DATA_GATE=PASS; DRY_RUN_GATE=NOT_YET_TESTED; SWAP_LIVE_GATE=BLOCKED; RFQ_LIVE_GATE=BLOCKED; AGENTIC_WALLET_LIVE_GATE=BLOCKED. These are current documentation decisions, not implemented controls or newly measured capabilities.

Phases 1–7 may develop in DEMO/DRY_RUN using verified real read-only data when available. Phase 8 is limited to safety/execution infrastructure and DRY_RUN behavior; Phase 9 to wallet abstractions, mocks, read-only integration and verified interfaces. Each phase still must pass its own development correctness gate. Existing data/source/precision/history requirements remain prerequisites for the affected functionality, with unavailable inputs explicitly failing closed.

Future provider access and gateway dispatch must keep read-only/proposal operations distinct from LIVE actions. Required blocked-LIVE configuration is DATA_MODE=DEMO or LIVE_READ_ONLY, EXECUTION_MODE=DRY_RUN, APPROVAL_MODE=PROPOSE_ONLY, LIVE_TRADING_ENABLED=false, REQUIRE_SIMULATION=true. LIVE_READ_ONLY does not alter source-quality labels or permit trading. DRY_RUN can run data/features/trust/history/agents/route comparison, safe quotes, officially supported builds/simulations and proposals; it cannot broadcast, submit RFQ orders, change settings, move funds or open a real position. Wallet/order signatures and approval execution cannot bypass the boundary.

A future LIVE dispatch requires the relevant route LIVE gate independently PASS, AGENTIC_WALLET_LIVE_GATE PASS when that gateway is used, explicit LIVE enablement and every existing risk/simulation/wallet/confirmation/fingerprint/terminal-reconciliation control. Unknown capability states remain blocked. Passing the development, data or dry-run gate alone never authorizes execution. The original concrete wallet and route-safety requirements above are unchanged.

The gate-amendment task allowed Phase 1 to begin and created no code itself. The subsequent Phase 1 implementation is recorded below. LIVE execution MUST NOT begin.

## Phase 1 — implemented foundation

FastAPI factory `backend/app/main.py` owns a lifespan that validates immutable Pydantic settings, initializes SQLAlchemy/SQLite, loads isolated foundation metadata only in DEMO and disposes the engine on shutdown. Database initialization creates only `schema_metadata` with an idempotent revision record; no business schema exists. SQLite URL validation prevents external database connections in Phase 1.

Public response models expose safe status fields only. `/api/health` verifies readiness and a real SQLite query; `/api/system-status` reports configuration, service/run identity, database, fixed capability states and demo fixture identity. Database failure yields503. Central error handlers omit raw validation/exception input. ASGI middleware creates unique request IDs, validates or replaces correlation UUIDs and adds run IDs to responses/errors. Application/request JSON logs use route templates, allowed scalar metadata and configured-secret redaction; they omit headers/bodies/query strings and raw tracebacks.

React/Vite/TypeScript/Tailwind shell uses Lucide and TanStack Query for safe health/status reads through a same-origin Vite proxy. Strict status parsing rejects unsafe service modes; DEMO fixtures cannot masquerade as LIVE_READ_ONLY. Bounded five-second checks, retry, loading/unavailable states and stale-health removal are implemented. Deferred product navigation has no active later-phase pages. No financial calculations or LIVE controls exist in the frontend.

Safe startup defaults remain DATA_MODE=DEMO, EXECUTION_MODE=DRY_RUN, APPROVAL_MODE=PROPOSE_ONLY, LIVE_TRADING_ENABLED=false and REQUIRE_SIMULATION=true. Typed settings reject LIVE (even with its flag true), autonomous approval, disabled simulation and malformed values. Optional future provider secrets are excluded from serialization; there are no provider clients or wallet operations. LIVE_READ_ONLY is accepted as a safe data boundary but performs no external reads in Phase 1 and loads no demo fixture.

Pinned Python/npm dependencies, unit/API/security/React tests, root Docker backend image, production frontend image, loopback-only Compose services and persistent foundation database volume are included. [README](../README.md) documents startup/configuration/test/Docker commands. [Phase 1 report](PHASE_1_REPORT.md) records the gate and validation limits; [dependency record](PHASE_1_DEPENDENCIES.md) records versions and declared licenses. Docker execution and native browser visual inspection were unavailable in this environment.

Phase 1 implements neither route proposals nor an execution workflow; DRY_RUN_GATE remains NOT_YET_TESTED despite tested safe configuration. DATA_GATE=PASS; SWAP_LIVE_GATE/RFQ_LIVE_GATE/AGENTIC_WALLET_LIVE_GATE remain BLOCKED. No LIVE blocker was investigated or weakened. Phase 2 was subsequently authorized and is recorded below.


## Phase 2 — implemented read-only data layer

Current implementation follows external provider → centralized read transport → raw payload validation → normalization → typed observation → repository → SQLite. `clients/binance_web3.py` is the only signer; it signs exact /build raw path/query/body, uses UTC-ms headers/nonce and restricts transport to the13 reviewed market reads. `clients/massive.py` permits only reviewed GET resources and checks pagination host/path/ticker/range bindings before removing apiKey from continuation parameters. No trading, transaction or wallet client exists.

Transport owns bounded three-attempt transient retries, timeout, exponential backoff, Retry-After cooldown (including the final attempt), conservative pacing, finite TTL cache, single-flight locking and failure circuit. Auth/schema failures stop. Duplicate JSON keys and credential/signature echoes are rejected. Structured logs contain provider/path/status/timing/run/request/correlation IDs, never raw queries, headers, bodies or exceptions. Massive pacing is12.1 seconds/request because the exact plan remains unknown; local limits are not claims about measured provider quota.

Provider protocols define RWA/equity/news/calendar boundaries. `BinanceRWAProvider`, `BinanceMarketProvider`, `MassiveProvider` and `USEquityCalendar` normalize provider facts only. `AssetDiscoveryService` discovers verified BSC stock representations dynamically, intersects supported chains/platforms and search/catalog identities, and limits a resolved stock to10 representations. Critical malformed catalog rows are excluded with an explicit PARTIAL limitation. DEMO uses labeled synthetic identities and never substitutes for failed LIVE_READ_ONLY calls.

Seven immutable Pydantic models preserve provenance, UTC source time, exact raw timestamp/unit, UTC ingestion time, mode and quality. Source-less metadata stays UNKNOWN. Observation qualities include LIVE, DELAYED, HISTORICAL, STALE, MISSING, INVALID, CONFLICTING and UNKNOWN; DEMO requires DEMO quality. Invalid money, timestamps, ratios, enums and OHLC relationships are rejected or explicitly unavailable. Binance referencePrice is a separate derived field and cannot become an EquityObservation. Financial strings/JSON lexemes become Decimal without binary-float round trips; REST and SQLite payloads serialize exact decimal text.

Schema revision2 adds tracked_assets, issuers, token_metadata, token_observations, equity_observations, news_events, market_status and ingestion_checkpoints beside foundation schema_metadata. Metadata/protection/ratio changes retain distinct versions. Observation identity includes mode/source/representation/raw-time/kind/interval; conflicting writes fail instead of overwriting. Queries require explicit DEMO or LIVE mode. LIVE_READ_ONLY application data persists as LIVE, while execution remains DRY_RUN/PROPOSE_ONLY. Batch writes are transactional; the following checkpoint write is independently durable, so interrupted work safely replays through deduplication.

Historical ingestion is explicitly invoked and bounded to1–10 pages. Binance candles page backwards with a strict completed-bar/window filter and checkpoint, trades use provider cursors with progress checks and quarantined price units, and Massive minute bars follow verified same-resource continuation URLs. Checkpoints never retain apiKey. Repeating historical windows is idempotent. No scheduler, research features, baselines, trust, scoring, agents, backtests or prediction are introduced.

The versioned NYSE2026–2028 schedule uses America/New_York for sessions and UTC internally, including DST, holidays,13:00 early closes, multi-day closures and reopenings. Extended hours are specifically NYSE American equities07:00–09:30 and16:00–20:00 (17:00 after an early close), not universal NASDAQ hours. Coverage outside those years fails explicitly. Schedule verification time, evaluation time and ingestion time stay distinct. Emergency halts and older/revised historical schedules remain unavailable. Previous regular close requires the last completed minute ending at the actual session close, excluding extended hours.

Only GET /api/assets and GET /api/assets/{ticker} were added. The React shell displays Phase2 status and backend modes, performs no authoritative financial calculation and retains disabled later-phase navigation. Safe defaults/gates are unchanged; external reads happen only in LIVE_READ_ONLY or the explicit verification script. Startup in that mode does not fetch providers or seed DEMO. A separate local verification database proves LIVE persistence without changing the running DEMO configuration. [Evidence and gate](PHASE_2_REPORT.md).

## Canonical Phase 1 — implemented Working Ask Flow

Ask text → bounded deterministic USD-budget parser → existing stock-first discovery → existing typed RWA profiles/prices → exact exposure arithmetic / estimate eligibility → issuer comparison → indicative route/result → durable proposal and audit event → backend-authoritative React display. Reuses DataLayer clients/providers/repository without rebuilding or extending their external operation allowlists. Ask fetches no news/history/agents.

ExposureService has no gateway, signer, broadcast/order method, simulation adapter or wallet access. It compares only allowed known issuer states, consistent identities/ratios and fresh LIVE prices/recently fetched metadata, at known decimals. Exact rational integer division rounds budget-to-base-units down; Decimal precision256 preserves monetary products. Effective USD/share display rounds upward to18 fractional places, while ranking uses exact rational P/R with issuer/chain/contract tie-break. Output exposes the unspent notional and explicitly unknown fees/slippage/gas/liquidity/funding conversion; it never claims lowest all-in cost or trade eligibility. Metadata receipt time does not prove the source ratio's historical as-of time.

Schema revision3 adds only exposure_proposals beside the existing data tables, preserving prior records. Proposal JSON stores money as strings, source/ratio/price times, mode, normalized mandate, policy version, run/request/correlation IDs and execution blockers. Raw user text is not logged/persisted; configured credentials pasted into a request are rejected before provider access. The sanitized audit event includes proposal UUID/status and mode. DEMO and LIVE retrieval are isolated; successful estimates expire after at most30 seconds, bounded by LIVE price/metadata freshness. Expiry removes the selected route and fails closed.

The Ask form makes a proposal POST only on explicit submission, bounds/cancels pending requests, validates safe response flags and mode, discards failed/replaced results, displays server strings without financial calculation, and hides expired selected quantities. Opportunity and Autopilot navigation remain disabled. Real vendor quotes, liquidity/fees, risk authorization, funding/wallet checks and transaction simulation remain unsupported; simulation=UNAVAILABLE, execution_ready=false and REQUIRE_SIMULATION=true.

DRY_RUN_GATE=PASS proves the indicative exposure/proposal workflow only. No simulation success, execution equivalence, RFQ safety, Trust, agent or Opportunity functionality is claimed. [Current report](PHASE_1_REPORT.md#canonical-phase-1--working-ask-flow). All master safety requirements and LIVE blockers remain unchanged.
