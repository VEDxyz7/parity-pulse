# Master Phase 7 — Opportunity Mode

Verified October 8, 2026 (Asia/Kolkata). Starting checkpoint: pushed Phase 6 commit `914af71`.

```text
PHASE_7_IMPLEMENTATION=PASS
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

## Authority and scope

All 5,321 lines of `docs/MASTER_SPEC.md` were read before coding. It is the sole authority and remains unchanged (SHA256 `f69a9bd01a622c001c3ec6cb654e00562f6b3d03a8310f9e5ccf68efe4b49c84`). The user's current Phase 7 authorization permits implementing non-executable machinery while the production Trust/data prerequisite remains blocked. Older dated advancement statements below earlier reports are historical, not an authorization to unlock production gates.

No Phase 8 work, execution gateway, signer, wallet operation, autonomous trading, live SWAP/RFQ, transaction broadcast, new provider integration, historical backfill or live alignment diagnostic was performed. No commit was created. Existing successful DEMO behavior, fixtures, Trust thresholds, Phase 5 research, routing rules, execution gates and frontend remain unchanged.

## Audit and architecture

Phase 6 already supplied six typed interpreters, candidate ranking, bounded tools/calls, persistent K=4 memory and safe Risk/route previews. Existing discovery, Trust, Phase 5 retrieval/model, exact economics, Risk Engine and RoutingService are reused. Missing pieces were a configurable universe scan, explicit full candidate audit, complete economic/evidence columns, top-K orchestration, request-bound sizing and an analytical API.

The new boundary is:

```text
Validated OpportunityRequest / explicit user mandate
  → existing AssetDiscoveryService / dynamic Binance RWA catalog
  → deterministic universe filters and evidence checks for every representation
  → existing Trust features, independent reference, news and Phase 5 research
  → RiskEngine ex-ante sizing and existing analytical_edge arithmetic
  → existing RoutingService compares eligible issuers for each stock
  → existing lexicographic candidate ranking
  → deterministic top-K (default 5)
  → one existing six-agent orchestration over the structured top-K
  → final existing RiskEngine revalidation
  → BUY proposal / DEFER / NO_QUALIFYING_OPPORTUNITY
  → immutable isolated audit → STOP
```

The service never has an execution gateway. `BUY` is an explicitly synthetic, non-executable analytical proposal. Real scans remain DEFER / rejected by the production Opportunity prerequisite, even if future supplied evidence could support economics. The agent framework's existing LIVE_READ_ONLY Decision behavior remains conservative.

`DataLayerScanSource` uses the existing dynamic discovery and TrustService; only included supported tickers are assessed. The signed GET RWA catalog/platform and price/profile contracts were checked against the [current official Binance RWA documentation](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/rwa-data); no new endpoint or provider was introduced. Rejected or excluded representations remain in the audit. Existing Binance provider catalog quarantine indices/reasons are retained, so malformed ratios/contracts cannot quietly disappear from the universe count. Provider discovery failure is an explicit blocker. Unsupported universe bounds are refused rather than truncated to favorable candidates.

`ScanSnapshot` is a typed host capture, never public-client financial input. Optional captured Phase 5 inputs are point-in-time/mode checked. Weekends/reopening use the existing HistoricalRetrieval and RollingOpeningModel, require 30 model samples and 3 retrieved analogues, and retain the prediction interval/status. Future news/outcomes are projected out before hashing, economics or agent access. No historical/current substitute and no Binance referencePrice is used as independent equity.

`DemoScanSource` reuses the three existing synthetic fixtures and dynamic DEMO discovery. Its regular-session target/cost assumption remains explicitly `SYNTHETIC_SCENARIO`; no opening prediction is fabricated (NOT_READY, sample_count=0). It does not modify fixtures, the existing paper pipeline or production history.

## Contracts and API

- `OpportunityRequest`: separate exact budget and risk budget, PRE_OPEN / BEFORE_MONDAY, optional ticker/issuer/chain filters, optional correlation identifier. Scenario selection is allowed only in the DEMO runtime. Extra input, including policy, costs, evidence and execution configuration, is rejected.
- `ScanPolicy`: top-K=5 (tightenable 1–5), maximum 500 representations / 100 stocks, unchanged 120-second freshness / 30-second current pairing, 30 baseline / 30 model / 3 analogue safeguards. Explicit engineering defaults: liquidity floor USD1,000, slippage ceiling50bps, minimum net edgeUSD0.25; stricter supplied system Risk limits win. No gate bypass setting exists.
- Expanded backward-compatible Phase 6 `Candidate`: ticker/company/token/issuer/chain/contract, ratio and token price, independent reference/source, regime, Trust/confidence, deviation, volume/percentile, liquidity/state, persistence, aligned news, historical pattern/count, opening prediction/interval/status/count, effective share cost, notional/stress, slippage/fees/gas/buffer, gross/net edge, eligibility/reasons/risk flags, provider timestamps and provenance references. Missing fields remain null.
- `CandidateAudit`: inclusion/exclusion, all rejection reasons, rank, top-K membership and shared RouteDecision where applicable.
- `OpportunityScan`: run/correlation/decision identifiers, timestamp/mode/mandate/policy, full universe/eligible/rejected counts, quarantine rows, rejection counts, full audit, top-K, selected candidate, final action/blockers, agent run and final risk status.
- Schema validation binds top-K to ranked eligible rows, preserves mode/mandate, and forbids executable/broadcast/live configurations.

Endpoints:

```text
POST /api/opportunities/scan
GET  /api/opportunities/{run_id}
```

These are analysis and audit-retrieval APIs. Production navigation remains disabled. Overview → Assess Trust is unchanged. No new frontend financial calculations or redesign were introduced; full Opportunity page integration remains a later authorized UI phase.

Example request (DRY_RUN only):

```json
{"budget_usd":"60","risk_budget_usd":"2","time_window":"PRE_OPEN","demo_scenario":"supported-move"}
```

In the existing DEMO policy, a $100/risk$10 mandate is valid input but exceeds the fixture's unchanged $5 platform risk-budget limit. It returns NO_QUALIFYING_OPPORTUNITY, rather than weakening the policy or forcing investment.

## Filters and ranking

Every valid discovered representation receives an audit row. Calendar policy uses the existing baseline bucket (for example actual WEEKEND → WEEKEND_PREOPEN), preserving actual session state. PREMARKET reopening requires the existing reopening/multi-day flag and full prediction evidence. Closed-session reference bars retain their start time; their completed one-minute endpoint and Trust reference_asof must equal the actual previous regular close. Filters cover explicit universe exclusions, unsupported asset/mapping, duplicate contracts, restricted/paused/limited tradability, ratio conflict/staleness, missing/stale token or independent equity, delayed/bar-as-current references, 30-second current pairing, unresolved regime/pre-open window, insufficient Trust/baseline/analogues, liquidity floor/p50, confidence floor, incomplete/unaligned news, missing/stale costs/route, excessive slippage, missing prediction, insufficient net edge and system/wallet/daily-loss/trade/cooldown constraints.

Missing required candidate columns cannot be silently lost inside ranking: the existing Opportunity interpreter's rejection checks are also applied before audit eligibility. All costs are exact explicitly supplied observations/DEMO assumptions. Missing costs never become zero. REAL regular-session PRE_OPEN requests are rejected as an inactive window; closed-market references must match the actual previous regular close. Weekday overnight and unsupported regimes remain restricted.

Issuer economics are delegated to the existing RoutingService with its strict Opportunity policy. When issuers have different size-specific cost bases, the scan fails that group closed rather than comparing incompatible sizes or inventing new quote costs. Non-winning eligible issuer alternatives remain visible as ROUTE_SUPERSEDED with the router's full comparison.

Across stock route winners, the existing Phase 6 rank is reused:

1. hard eligibility;
2. confidence tier descending;
3. net expected USD edge descending;
4. analogue count, then baseline sample count descending;
5. liquidity descending;
6. effective cost per share ascending;
7. ticker/issuer/chain/contract/candidate identity tie-break.

No opaque weights or LLM/ML ranking. Candidate order and filter order do not choose the winner. At most five validated eligible candidates enter the agents; the full universe and rejections remain in the isolated audit. Default deterministic mode uses zero external LLM calls. Optional Phase 6 structured transport is limited to five calls including retries; no provider was selected or called in this task.

## Risk budget, cost and numerical semantics

`risk_budget_usd` is an EX-ANTE risk budget, not a guaranteed maximum realized loss. No risk is inferred from budget and no confidence input is accepted by sizing.

```text
stress_loss = proposed USD notional × configured stress adverse-move fraction
stress_loss <= explicit user risk budget

net edge = gross edge - estimated slippage - fees - gas - execution buffer
```

RiskEngine now exposes a mode-aware analytical sizing method. It shares the exact cap calculation with its pre-existing DEMO validation: position, cost-inclusive budget/wallet capacity, portfolio, cost-inclusive stress risk/daily-loss capacity and liquidity fraction. Wallet/system state must be known and allowed; unknown constraints yield no size. Limits, daily loss, trade count, cooldown, liquidity p50, slippage and confidence remain mandatory. Existing final Risk validation runs again after the Decision Agent and can turn BUY into DEFER.

Quoted costs are size-specific; real size mismatch requires a new observed quote, never a favorable re-estimate. The DEMO source is explicitly hypothetical and may reduce its analytical requested notional. Existing DEMO economics retain their explicit 18-decimal conservative boundary. Sizing rounds down to18 decimals; displayed stress rounds up to18 decimals. Other analytical calculations use the existing256-digit Decimal context. No binary float is used for financial authority.

## Isolation, audit and restart

Full-universe analysis runs in a bounded worker thread; agents keep existing timeout/retry/tool/depth/memory limits. HTTP scans are serialized and overlapping scans return409. No LLM stack runs separately for every stock.

`OpportunityScanStore` stores immutable checksummed structured scans in a separate SQLite/SQLAlchemy database. Application runtime uses a sibling `opportunity/phase7` directory and separate Phase 6 agent memory. DEMO runtime and tests use disposable memory stores; offline CLI can use isolated disk stores. Retrieval is mode scoped. No raw user instructions, news headlines, chain-of-thought or secrets are stored in the scan table. Structured reason codes, public metadata and evidence digests are retained. Stable IDs remove UUID churn from the new scan adapter without changing existing DEMO services.

Protected prior master/evidence/fixture/data hashes: all80 original artifacts remain identical. This run made zero real-provider calls, zero production observation writes, zero wallet/trade calls and no alteration of previous evidence. Live read-only calls in a later explicitly invoked scan remain subject to the existing provider/auth/schema/freshness restrictions.

## Verification

- Backend: **707 passed** (628 retained, 79 new); one existing Starlette/httpx TestClient deprecation warning.
- Frontend: **173 passed /9 files**.
- TypeScript typecheck/Vite build: PASS; existing built bundle hashes unchanged.
- Ruff lint and format: PASS (142Python files).
- Established security audit and configured-secret scan: PASS. Dependency `pip check`: PASS. `git diff --check`: PASS.
- Desktop/mobile actual browser regression: six scenarios /39 successful local requests; full Information Trust→Opportunity→Risk→Route→quote→prepare→simulate→paper fill→position→exit→P&L→scorecard preserved. NORMAL/noise stand-down, ordinary Overview INSUFFICIENT_EVIDENCE and locked production Opportunity navigation verified. Zero Demo→production Trust calls and zero external execution/provider calls.
- New tests cover dynamic Binance discovery with MockTransport, malformed ratio quarantine, every key filter, Decimal formulas/bounds, request-bound risk sizing, stricter constraints, deterministic issuer/stock choice/ties/order, changing economics, top-K=5/tightened3, only structured top-K sent to fake LLM transport, NO rejected-candidate LLM calls, schema failures/disagreement/abstention, real-unavailable DEFER, mode isolation, immutable audit/restart and final Risk rejection after agent BUY.
- Synthetic local scans10/25/50/100 stocks: approximately0.035/0.091/0.228/0.725seconds. All eligible inputs audited, top-K=5 and6 deterministic agent calls. These are software benchmarks with repeated synthetic fixtures, not provider latency, calibrated opening predictions or real-market performance.

Evidence: [typed scan runs and benchmark](evidence/PHASE_7_SCAN_RUNS.json), [browser regression](evidence/PHASE_7_BROWSER.json), [verification record](evidence/PHASE_7_VERIFICATION.json).

## Remaining blockers

Production Trust remains BLOCKED: independent current-equity entitlement/alignment, verified relevant-market liquidity, complete real evidence and historical ratio/as-of coverage are unresolved. Actual historical coverage remains0/30 baseline,0/30 opening-model,0/3 analogues. No additional evidence was manufactured. Verified live cost/route/wallet-system previews are unavailable; the current source exposes them as absent. Real model/analogue insufficiency fails closed. Optional LLM provider entitlement remains unverified.

The production Opportunity prerequisite and every live execution gate remain blocked. A hypothetical DEMO BUY is not production eligibility, simulated settlement, funding validation, quote/simulation equivalence, an order or an execution. Existing DEMO paper results remain synthetic.

## Files changed

- `.gitignore`, `README.md`
- `backend/app/agents/schemas.py`
- `backend/app/api/opportunity_scan.py`, `backend/app/main.py`
- `backend/app/models/opportunity_scan.py`, `backend/app/models/risk.py`
- `backend/app/repositories/opportunity_scan.py`
- `backend/app/services/opportunity_scan.py`, `backend/app/services/opportunity_sources.py`, `backend/app/services/risk.py`
- `backend/app/utils/logging.py`
- `backend/tests/unit/test_opportunity_scan.py`, `backend/tests/integration/test_opportunity_scan_api.py`, `backend/tests/security/test_boundaries.py`
- `scripts/scan-opportunities.py`
- `docs/PHASE_7_REPORT.md`, `docs/ARCHITECTURE.md`, `docs/PHASE_MAP.md`, `docs/EXECUTION_GATES.md`
- `docs/evidence/PHASE_7_SCAN_RUNS.json`, `docs/evidence/PHASE_7_BROWSER.json`, `docs/evidence/PHASE_7_VERIFICATION.json`

## Runbook and stop

```sh
.venv/bin/python scripts/scan-opportunities.py --demo supported-move --budget 60 --risk-budget 2
.venv/bin/python scripts/scan-opportunities.py --demo steady --budget 60 --risk-budget 2
.venv/bin/python scripts/scan-opportunities.py --demo thin-move --budget 60 --risk-budget 2
# Real captured typed evidence only; offline, no provider requests or DEMO fallback:
.venv/bin/python scripts/scan-opportunities.py --snapshot /path/to/captured-scan.json --budget 100 --risk-budget 10
```

CLI defaults to isolated ignored `data/opportunity/phase7`; `--store` selects a separate directory and `--evidence` writes a new file only. No credentials are loaded by the CLI. The API cannot accept snapshots/costs/policies or enable execution.

**STOP after Master Phase7. Phase8 was NOT started.** Exact next engineering title is Master Phase8 — Safety and Execution; it needs separate authorization, and all unchanged live-safety/data prerequisites still apply.
