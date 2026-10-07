# Canonical Phase 2 — Trust Layer

## Capability remediation re-verification — current state

2026-10-06: **TRUST_GATE=BLOCKED**. The completed Trust implementation was reused. Actual snapshot/NBBO/alternative last trade403 are verified entitlement denials; missing comparable/fresh liquidity and zero real baseline/analogue history remain blockers. The scoped news-window defect is corrected: actual requested-window coverage passes while full history remains partial and source updates hourly. Both actual representations remain INSUFFICIENT_EVIDENCE/null confidence.302 backend /47 frontend tests, type/build, Ruff, security, API and desktop/mobile checks pass.

See [remediation report](PHASE_2_TRUST_REMEDIATION.md) for the exact blocker table, liquidity candidate contracts, history counts, changed files and evidence. [Current formal gate](evidence/CANONICAL_PHASE_2_TRUST_GATE.json) separates real prerequisites from synthetic software verification; [initial gate](evidence/CANONICAL_PHASE_2_TRUST_GATE_INITIAL.json) is preserved byte-for-byte. Canonical Phase1/DATA/DRY_RUN remain PASS; Opportunity and all LIVE gates remain blocked. STOP after Trust re-verification.

**The original completed implementation report below is preserved as the earlier snapshot. Its news-partial blocker/test totals/next-work statements are superseded only within the measured remediation scope above.**

Date:2026-10-06. Deterministic analytical implementation and software verification completed. **TRUST_GATE=BLOCKED** because actual mandatory financial evidence is insufficient. This is not Engineering Stage 2 — Data Layer; [PHASE_2_REPORT.md](PHASE_2_REPORT.md) and all its historical evidence remain byte-identical.

## Audit and completed work reused

[Pre-code audit](CANONICAL_PHASE_2_TRUST_AUDIT.md): the accepted Canonical Phase 1 and Engineering Stages 1/2 were preserved, with189 backend/33 frontend tests passing before changes. Reused stock-first resolution/discovery, issuer/chain/profile/ratio provenance, exact exposure arithmetic, typed Binance/Massive providers, bounded market-only read allowlists, independent snapshot/news/actual-close adapters, versioned New York calendar, data repository/database, structured errors, IDs and sanitized logging.

Missing at audit: Trust reference selection/alignment, regime evidence, economic deviation, stock/regime episode baselines, verified-unit liquidity interpretation, temporally aligned directional/coverage news evidence, completed historical cosine retrieval, deterministic classifier, Trust API/repository/UI and formal gate. DATA_CONTRACTS.md and TEST_MATRIX.md were absent; created to document this scope.

## Implemented architecture and services

Existing read-only discovery/providers → independent reference and scheduled regime → shared exact economics → contemporaneous features → partitioned completed episodes/baseline → verified liquidity and aligned news → prior analogues → deterministic classification → persisted analytical assessment and backend-authoritative UI.

| Component | Responsibility |
|---|---|
| shared normalization | One exact P/R function reused by Ask and Trust; E×R and dimensionless deviation; unchanged Phase 1 upward-rounded presentation/budget behavior |
| MarketRegimeService | Existing calendar states and actual previous close, early-close/reopening/multi-day context; no invented sessions |
| IndependentReferenceService | Current-versus-actual-close selection, independent source/kind/quality, mode/identity/ratio/availability/freshness/skew guards |
| LiquidityEvidenceService | Verified PRICE_INFO USD/count inputs, explicit optional absence and malformed/stale/ambiguous-unit rejection |
| NewsAlignmentService | Publication and first-seen cutoff, bounded window/coverage, relevance and conservative headline direction; no provider LLM sentiment |
| TrustFeatures/EpisodeBuilder | Contemporaneous exact feature vector; covered completed30minute windows; distinct-event counts, middle-window features and separately completed outcomes |
| BaselineService | Exact stock/issuer/chain/contract/regime/ratio/reference-kind/policy partitions,180day lookback, minimum30 and Decimal distributions/percentiles/z-score |
| AnalogueService | Past-only baseline-scaled L2 vectors, cosine top3, minimum3, explicit quality/counts, outcome-free ranking |
| TrustClassifier | Explicit NORMAL / LIKELY_NOISE / LIKELY_INFORMATION rules; INSUFFICIENT_EVIDENCE/null confidence on missing/conflicting/mixed evidence; LOW confidence cap |
| TrustRepository/API | Frozen exact schemas, immutable availability/mode separation, additive revision4 tables, analytical GET /api/assets/{ticker}/trust, persisted IDs/audit event |
| TrustPanel | Explicit GET after submission, backend prices/reasons/freshness/regime/reference/baseline/liquidity/news/analogue display; failed/expired evidence cleared; no Trust calculation |

No new framework/dependency, agent, candidate scan, scheduler, opportunity ranking, budget/risk optimization, opening prediction, transaction construction, wallet interface or execution gateway was introduced. Trust does not alter Ask selection/proposals. The minimal Ask interface change shares existing normalization and clarifies that separate **proposal Trust integration** remains unassessed; the proposal's legacy NOT_IMPLEMENTED field is retained rather than silently endorsing execution.

## Formulas, rules and research mapping

P USD/token; R shares/token; E independent USD/share. Effective price/share=P/R; comparable value/token=E×R; deviation=(P−E×R)/(E×R), an exact dimensionless fraction. All financial/statistical/cosine arithmetic uses Decimal precision256 and JSON text persistence. Original base-unit budget computation remains unchanged.

Detailed [data contracts](DATA_CONTRACTS.md) document all thresholds, regime buckets, units, reference types and look-ahead safeguards. ENGINEERING_POLICY v1:120second current/token/ratio-receipt freshness;30second current skew;180day lookback; covered UTC30minute episodes; observed persistence horizon15minutes/gap<=120seconds; minimum30 baseline episodes/3 analogues; cosine>=0.8/top3. These numerical thresholds are safeguards and documented heuristics, not paper coefficients or validated investment rules.

NORMAL requires absolute deviation<=the exact scope's past p75 and liquidity>=p25. NOISE additionally combines unusually large deviation>=p95, volume/persistence/liquidity<=their past p25, no relevant news in the covered window and at least2/3 reversed analogues. INFORMATION combines deviation>=p95, volume/persistence>=p75, liquidity>=p50, directional headline evidence and at least2/3 persisted analogues. Conflicting/partial/unknown mandatory evidence does not produce a positive class. Confidence stays LOW for v1; no statistical calibration or probability is asserted. Zero-SD/truncated/insufficient baselines fail closed.

REGULAR requires a fresh verified current independent quote. Other scheduled regimes may use the previous actual regular-close minute, explicitly HISTORICAL in LIVE. This is never a current quote. Both token/equity source times, raw bar start/reference close and skew/ages remain visible. Market calendar coverage2026–2028 and schedule-not-halt limits remain unchanged.

Research priors and the original Phase 0 mapping are preserved, with the implemented adaptation separately documented in [RESEARCH_TO_IMPLEMENTATION.md](RESEARCH_TO_IMPLEMENTATION.md). No0.98/0.90 multiplier, crypto performance, profitability, research coefficient or causal news claim is imported. Provider LLM sentiment is excluded; conservative deterministic headline cues are evidence only. Published research and synthetic fixtures do not count as local calibration. All outcomes used as analogue evidence were completed/available before decision time; outcome values never enter similarity vectors.

## Actual data limits and current-equity403

New [read-only LIVE verification](evidence/CANONICAL_PHASE_2_TRUST_LIVE.json), 2026-10-06T16:56:18–16:56:36Z:

- NVDA resolved; BStock and Ondo representations discovered.
- Nine Binance market/RWA reads succeeded, including the POST PRICE_INFO **read** operation. No Trading/Transaction/Wallet endpoint was called.
- Current Massive snapshot returned HTTP403, recorded as FORBIDDEN/UNAVAILABLE. The prior NBBO403 observation remains accepted; no redundant NBBO probe or price substitute was performed.
- Massive news GET succeeded but remained bounded/PARTIAL. No directional classification was manufactured.
- Mandatory liquidity was absent (verified USD volume was available) in evaluated PRICE_INFO results, so liquidity is UNAVAILABLE despite successful endpoint access. Official USD units are verified; absent metrics are not zeros or invented liquidity.
- Both assessments persisted as INSUFFICIENT_EVIDENCE; independent comparison/economic deviation unavailable; no qualifying real baseline episodes/analogues; no broadcast; DEMO retrieval cannot access LIVE assessments.
- Ratio source-asof remains unavailable and receipt time is explicitly distinguished. Current metadata is not used to reconstruct a fake as-of historical ratio. Current catalog PARTIAL3 rejected representations is a new observation, not a rewrite of historical Data Layer/Phase 1 rejection counts.

The endpoint's ASSESSED status means evidence/limitations were assembled; it is not a passing market classification or Trust gate. All current-equity403 handling is fail-closed. Existing historical equity data remains HISTORICAL. Historical candle/trade-unit ambiguity, as-of ratio uncertainty, absent earnings coverage and calendar bounds remain explicit. Historical bars are not silently promoted to a current quote or bootstrapped into30 Trust episodes.

Default fixed DEMO fixtures remain unchanged. They supply no invented fresh timestamp, liquidity or30-episode history, so default UI assessments are insufficient. Unit/API synthetic completed-history scenarios are isolated in temporary DEMO databases, clearly labeled SYNTHETIC_TEST/SYNTHETIC_DEMO; they are not actual account or empirical evidence.

## Tests and checks

| Verification | Result |
|---|---|
| Complete backend suite | **282 passed,0 failed**, preserving189 prior tests and adding93 Trust checks;94.61% application statement coverage |
| Complete frontend suite | **47 passed,0 failed**, preserving33 prior tests and adding14 Trust checks |
| Type/build | PASS: TypeScript noEmit and Vite production build |
| Lint/format | PASS: Ruff backend/scripts,62 Python files formatted |
| Local integration | PASS: existing health/status/proxy/Ask/persistence controls plus analytical Trust/IDs/false-execution checks |
| Direct backend GET health/system-status/Trust | HTTP200 each, exact canonical backend command, database connected |
| Trust browser | PASS: disposable Chrome desktop1440/mobile390, backend evidence, unsupported stock, no overflow/runtime exceptions or automatic Trust fetch |
| Ask regression browser | PASS: completed NVDA proposal and unsupported-stock failure, desktop/mobile, unchanged proposal economics/safety |
| Security | PASS: configured-secret leakage scan, frontend isolation, environment ignore/build exclusions; no credentials in artifacts/logs; unchanged external read allowlists |
| Actual providers | Correct read-only insufficient result; current-equity403/mandatory metrics/news/history gaps retain BLOCKED gate |
| Docker | NOT_RUN; existing Docker-unavailable limitation remains, no new container verification claim |

The existing upstream Starlette TestClient/httpx deprecation warning remains unsuppressed. No other warnings or test failures remain. Tests include current/closed HISTORICAL reference safety, precision, exact skew boundary, missing/invalid ratios/prices, all required calendar states, units, baseline partitions/minimums/degeneracy/truncation, completed episode chronology/density/dedup, news alignment/conflicts/speculation/partial history, cosine determinism/future-outcome perturbation, three full synthetic API classifications, no LLM/execution, persistence/isolation/upgrade and secret rejection. See [TEST_MATRIX.md](TEST_MATRIX.md) and [formal gate evidence](evidence/CANONICAL_PHASE_2_TRUST_GATE.json).

Backend listener PID93858 uses the unchanged canonical uvicorn factory command on127.0.0.1:8000. The previously verified owned backend was gracefully restarted to load the final code. Existing root `npm run dev` frontend PID86767 remained available at127.0.0.1:5173; HMR loaded UI changes. No unrelated process was stopped or source port changed.

## Formal gate and remaining blockers

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

The12 deterministic/safety criteria pass automated software verification. Actual mandatory current reference, liquidity/activity, news coverage and qualifying real history cannot certify a real-provider Trust decision. The gate therefore remains BLOCKED; passing synthetic scenarios does not substitute for these capabilities.

Required next work **within Canonical Phase 2**: verify appropriate independent reference entitlement/freshness, obtain mandatory contemporaneous verified-unit metrics and complete bounded news coverage, collect at least30 qualifying completed episodes per supported exact scope and retrieve at least3 eligible prior analogues without backdating data or ratios. Re-run full gates against that actual evidence. Historical-close support alone cannot certify regular-session current-equity access. Earnings/as-of/calendar and uncalibrated-policy limits remain explicit and constrain supported scope.

**Exact next recommendation: Canonical Phase 2 — Trust input/capability remediation and TRUST_GATE re-verification. Do not begin Canonical Phase 3 — Opportunity Mode while Trust remains blocked.** All existing DRY_RUN/PROPOSE_ONLY/required-simulation/no-live settings, risk, wallet, confirmation, transaction-equivalence, RFQ and fail-closed rules remain unchanged. STOP after this Phase 2 run.

## Evidence and preservation

- [Formal Trust gate](evidence/CANONICAL_PHASE_2_TRUST_GATE.json) —12 checks, results, source/test fingerprints and preserved-history manifest.
- [Actual read-only provider statuses](evidence/CANONICAL_PHASE_2_TRUST_LIVE.json) —endpoint/status/permission/capability/time ledger, analytical result summary only.
- [Existing synthetic DEMO verification](evidence/CANONICAL_PHASE_2_TRUST_DEMO.json) —explicit insufficient evidence, persistence/isolation/no broadcast.
- [Direct backend and proxy integration](evidence/CANONICAL_PHASE_2_TRUST_API.json).
- [Trust browser](evidence/CANONICAL_PHASE_2_TRUST_BROWSER.json) and [Ask regression browser](evidence/CANONICAL_PHASE_2_ASK_REGRESSION.json).

Both master copies, the entire Engineering Stage 2 Data Layer report/evidence, original Canonical Phase 1 reports/evidence, sanitized provider response fixtures, demo data and calendar remain unchanged. Workspace has no Git metadata; changes are audited with pre/post SHA-256 manifests. Local ignored databases and frontend build output are generated artifacts, not historical evidence rewrites.

## Files changed

The complete source/documentation/script/test/evidence inventory for this authorized task follows.

- `README.md`
- `backend/app/api/trust.py`
- `backend/app/database.py`
- `backend/app/main.py`
- `backend/app/models/data_tables.py`
- `backend/app/models/trust.py`
- `backend/app/repositories/trust.py`
- `backend/app/services/exposure.py`
- `backend/app/services/normalization.py`
- `backend/app/services/trust.py`
- `backend/app/services/trust_classifier.py`
- `backend/app/services/trust_evidence.py`
- `backend/app/services/trust_history.py`
- `backend/app/utils/logging.py`
- `backend/tests/integration/test_trust_api.py`
- `backend/tests/security/test_boundaries.py`
- `backend/tests/unit/test_database_demo.py`
- `backend/tests/unit/test_trust.py`
- `docs/API_MATRIX.md`
- `docs/ARCHITECTURE.md`
- `docs/CANONICAL_PHASE_2_TRUST_AUDIT.md`
- `docs/CAPABILITY_GAPS.md`
- `docs/DATA_CONTRACTS.md`
- `docs/EXECUTION_GATES.md`
- `docs/PHASE_2_TRUST_REPORT.md`
- `docs/PHASE_MAP.md`
- `docs/RESEARCH_TO_IMPLEMENTATION.md`
- `docs/TEST_MATRIX.md`
- `docs/evidence/CANONICAL_PHASE_2_ASK_REGRESSION.json`
- `docs/evidence/CANONICAL_PHASE_2_TRUST_API.json`
- `docs/evidence/CANONICAL_PHASE_2_TRUST_BROWSER.json`
- `docs/evidence/CANONICAL_PHASE_2_TRUST_DEMO.json`
- `docs/evidence/CANONICAL_PHASE_2_TRUST_GATE.json`
- `docs/evidence/CANONICAL_PHASE_2_TRUST_LIVE.json`
- `frontend/src/App.tsx`
- `frontend/src/components/AskFlow.tsx`
- `frontend/src/components/TrustPanel.tsx`
- `frontend/src/services/trust.ts`
- `frontend/src/styles.css`
- `frontend/src/test/TrustPanel.test.tsx`
- `scripts/check-ask-browser.mjs`
- `scripts/check-integration.mjs`
- `scripts/check-trust-browser.mjs`
- `scripts/verify-trust.py`

Generated/ignored artifacts: the running local SQLite database receives additive schema/analytical records; `data/phase2-trust-demo-verification.db` and `data/phase2-trust-live-verification.db` are new isolated verification databases; `frontend/dist` is rebuilt. Disposable screenshots/JUnit/coverage/manifests remain in private temporary storage. Historical verification databases are untouched.
