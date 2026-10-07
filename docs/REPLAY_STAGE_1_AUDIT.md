# Replay Stage 1 — stopped at the real-evidence prerequisite

Audit date: 2026-10-07. **Stage status: BLOCKED; implementation not started.**

The user's attached instruction requires: “If an existing production calculation cannot produce one of the three outcomes from currently available real historical evidence, STOP and report exactly what evidence is missing rather than weakening the classifier.” The repository audit and offline reassessment reach this condition for all three requested positive scenarios. This is an evidence failure, not a failing software test or a declaration that replay is generally impossible.

The machine-readable [audit evidence](evidence/REPLAY_STAGE_1_AUDIT.json) records the current inventory, real-input reassessments, original timestamps, source hashes, prior historical audit provenance, verification results and preservation checks. No provider request or historical-ratio research was performed. The saved Twelve Data/Binance alignment diagnostic was not run or rearmed.

## Repository audit and existing reuse points

| Area inspected | Existing implementation and finding |
|---|---|
| Runtime/configuration | `backend/app/config.py` accepts `DATA_MODE=DEMO` or `LIVE_READ_ONLY`; `DataLayer` maps them to record modes DEMO/LIVE. No separate LIVE/REPLAY runtime selector exists. DRY_RUN/PROPOSE_ONLY, simulation required and live trading disabled remain enforced. |
| Trust entry points | `TrustService.assess` obtains read-only provider evidence; `evaluate_representation` composes existing reference, liquidity, news, normalization, feature, baseline, analogue and classifier services. The latter is already usable with captured inputs, an isolated database and a fixed historical clock. No second engine is needed. |
| API and persistence | `GET /api/assets/{ticker}/trust` returns and persists the existing `TrustAssessment`. Revision 4 tables store assessments, samples and episodes as exact JSON text with mode isolation and immutable first availability. There is no public history-writing or execution endpoint. |
| Episode/schema contracts | Frozen `TrustSample` and `TrustEpisode` retain exact scope, ratio, feature/availability times and completed outcomes. `EpisodeBuilder` requires completed 30-minute windows with boundary coverage and gaps no greater than 120 seconds. Synthetic episodes are restricted to DEMO. |
| Historical fixtures and data | A sanitized real captured-input fixture and isolated real historical backfill exist. Neither contains sufficient eligible real feature history. Positive-classification fixtures are explicitly synthetic test controls. DEMO fixtures do not supply a real historical baseline. |
| Frontend | The existing `TrustPanel` requests backend assessments, validates safety/mode/evidence, displays backend financial strings and expires current results after 120 seconds. It has no historical scenario selector or REPLAY badge. |
| Opportunity flow | Opportunity navigation remains disabled; no implemented Opportunity engine, agent, opening prediction or paper-execution path exists. Planned architecture is preserved. |
| Tests | Existing tests already exercise all three positive classifications with synthetic completed history, real-input failure, no network during captured replay, mode isolation, immutable availability, look-ahead exclusion and unchanged blocked gates. |

A runtime selector, frozen-dataset loader, historical presentation and reuse of the existing engine would be the implementation boundary after suitable real evidence exists. No part of that implementation was added after the explicit stop condition was established. Historical inputs cannot be made acceptable merely by moving the clock: their actual ingestion/availability times and types remain significant.

## Real evidence inspected

Read-only inspection covered all eight local application/verification databases. Deduplicated real persisted records comprise **122 token observations, 2,084 equity records, four Trust assessments, zero Trust samples and zero Trust episodes**. Of the equity records, 2,083 are BAR records; the remaining REGULAR_CLOSE record does not represent an additional unique minute. All eight representation results in the four real assessments are `INSUFFICIENT_EVIDENCE`.

The preserved historical audit, captured **2026-10-06T22:05:10.394402Z**, additionally accounts for 7,351 distinct official Binance historical candles across old/new captures: 2,805 BStock and 4,546 Ondo. Its 43 representation-specific reopening candidates cover 26 distinct opening dates within the existing lookback. They yield **0/30 qualifying baseline episodes, 0/30 opening-model episodes and 0/3 eligible real analogues**. Counts remain historical audit facts, not a new provider capture or new production ingestion.

An additional offline reassessment passed the real fixture's four metadata versions across the two exact BSC representations through the existing `TrustService.evaluate_representation`. All four return `INSUFFICIENT_EVIDENCE`, unavailable independent reference/liquidity, no constructed features, zero baseline episodes and zero analogues. Original source/receipt/ratio times were retained; no classification was supplied as an input. HTTP sends and socket connects were prohibited, with **zero network attempts**. Only a temporary database was used and removed.

## Exact missing evidence and scenario outcomes

There is **no optional-input path to a positive label** in the existing classifier. Every positive classification requires an available independent reference and liquidity, computed features, a sufficient nondegenerate baseline of at least 30 eligible episodes, at least three qualified analogues and complete requested news-window coverage. The separate 30-opening-model safeguard remains unchanged; it is not a substitute for these classifier prerequisites.

Shared missing evidence:

- Effective-dated, legitimately available historical economic shares/token ratios for each exact contract. Current metadata receipts do not establish ratios at older decisions; the 7,336 newly captured historical Binance bars all have null historical ratios. Equity/token division and present-day ratio backfill cannot repair this.
- Authoritative historical liquidity and comparable USD activity evidence with actual observation/availability timestamps. Captured Binance PRICE_INFO liquidity is null. Diagnostic pool reserves are not a verified replacement for the engine's token-market measurement; historical candle volume units remain unverified.
- Eligible price/reference observations and availability history. Historical CANDLE observations are not the engine's verified PRICE/PRICE_INFO inputs. In a regular session, historical equity BAR data cannot be relabeled a current QUOTE/SNAPSHOT. The real regular-session fixture has no independent reference. A closed-session reference path exists, but does not remove the other missing prerequisites.
- Contemporaneously available features, news-window coverage and revision/first-seen evidence at historical decisions. October retrieval times cannot be backdated into March–October decisions. Accepted current news-prefix coverage does not establish coverage at older decisions.
- Enough completed, nondegenerate episodes and similarity-qualified analogues in each exact stock/issuer/contract/regime/ratio/reference/policy scope. Cross-issuer pooling, duplicate observations and posthoc opening returns cannot supply these counts.

| Requested replay scenario | Existing classification path after shared prerequisites | Available real result |
|---|---|---|
| NORMAL | Absolute deviation at or below baseline p75; liquidity at or above baseline p25 | Cannot establish the required features, baseline or analogues; `INSUFFICIENT_EVIDENCE`. Scenario not created. |
| LIKELY_NOISE | Deviation at or above p95; low relative volume/liquidity, short persistence, covered no-news window and at least two reversed retrieved outcomes | No complete real evidence bundle or qualifying reversal analogues; `INSUFFICIENT_EVIDENCE`. Scenario not created. |
| LIKELY_INFORMATION | Deviation at or above p95; high relative volume/persistence, adequate liquidity, corroborating directional headline and at least two persisted retrieved outcomes | No complete real evidence bundle or qualifying persistence analogues; `INSUFFICIENT_EVIDENCE`. Scenario not created. |

The existing synthetic controls prove that the production calculation/classifier can produce all three labels when its required inputs are supplied. They are not the currently available real historical evidence required by this task's stop clause, and were not promoted into a product replay dataset.

## Verification and files changed

| Existing command | Result |
|---|---|
| `.venv/bin/python -m pytest` | 326 passed; existing upstream Starlette/httpx deprecation warning |
| `npm test` | 47 passed |
| `npm run build` | PASS: TypeScript noEmit and Vite build |
| `.venv/bin/ruff check backend scripts` | PASS |
| `.venv/bin/ruff format --check backend scripts` | PASS: 74 files |
| `.venv/bin/python scripts/check-security.py` | PASS |

**Tests added: zero.** Existing real-input replay and synthetic positive-scenario tests provide the relevant coverage for this audit. No new runtime exists to test. Browser checks were not rerun because no UI implementation was added.

Exactly two documentation/evidence files were added: this report and `docs/evidence/REPLAY_STAGE_1_AUDIT.json`. Architecture, application/test source, schemas, fixtures, dependencies, configuration, all databases, historical reports, both master copies, execution gates and alignment setup are unchanged. SHA256 comparison confirms **all 214 pre-existing inventoried artifacts remain byte-identical**. Build/test commands regenerate their usual disposable outputs.

**Architecture changes: none. Replay schema/dataset introduced: none. Required positive real replay scenarios created: zero.** LIVE behavior is preserved by unchanged production source and the passing existing suite. Trust was not bypassed, reduced or passed artificially; no external provider, wallet, trading or execution operation occurred during the audit.

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

Stop at the evidence prerequisite. No Paper Execution, Opportunity replay, UI redesign or historical-ratio research was started. Replay Stage 1 remains blocked by the real evidence listed above.
