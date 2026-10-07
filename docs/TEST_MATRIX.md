# Verification matrix — Canonical Phase 2 Trust Layer

Created2026-10-06; the file was absent at audit. All original tests remain. Three old database-version assertions and exact table/route inventories are expanded for revision4 and the analytical GET; no acceptance or safety assertion is removed. Financial Phase 1 outputs/selection and all189 earlier backend/33 frontend checks are retained.

| Requirement | Automated evidence |
|---|---|
| Shared exact normalization, fractional/missing/invalid ratios, precision and comparison | unit/test_trust.py: shared normalization/comparable units, invalid ratios, positive/negative deviation, repeating256-digit features; original unit/test_exposure.py |
| Regimes and actual prior close | Regular/pre/post/overnight/weekend/holiday/early-close/reopening cases, actual Thursday close on holiday weekend, early13:00 close, multi-day closure, schedule bounds; existing calendar/DST integration tests |
| Independent reference | Current quote kind/source/mode/quality/availability/age/skew; exact30second boundary; missing price/reference; no Binance reference fallback; LIVE closed reference remains HISTORICAL |
| Liquidity | Verified USD/counts, absent fields, stale/conflicting identities, non-finite/float values, TRADE/CANDLE/UNKNOWN/TOKEN exclusions |
| News | Publication and first-seen cutoff, relevance, corroboration/conflict, opposite signals, no-news caveat, bounded PARTIAL coverage, speculation/negation suppression, no provider LLM sentiment |
| Baseline | Thirty-episode safeguard, exact statistics/quantiles,180day cutoff, ticker/regime/ratio/issuer/contract/mode partitions, available-time/future exclusion, truncation/degenerate handling |
| Completed episodes | Fixed windows, coverage/gap requirements, duplicate-event exclusion, completion timing, immutable availability and invalid chronology |
| Analogue retrieval | Decimal normalized cosine/top3, input-order determinism, minimum counts, future exclusion, future-outcome perturbation does not affect IDs/similarities |
| Classifier | NORMAL/LIKELY_NOISE/LIKELY_INFORMATION synthetic rules; all missing requirement overrides; conflicting/mixed evidence fails closed; conservative LOW confidence |
| Full composed API and persistence | integration/test_trust_api.py: three explicitly synthetic completed-history scenarios, exact economics, baseline40/top3, IDs, persisted equality, missing403, unsupported/malformed ratios, no public POST, query rejection, cross-mode retrieval and schema upgrade |
| No execution or secrets | Existing security suite/client read allowlists; literal false live/ready/broadcast flags; no order/transaction/position/wallet tables; credential-input rejection and no log/database leakage |
| Frontend | TrustPanel.test.tsx: no automatic request, explicit GET, backend strings/reasons, unavailable handling, unsafe/cross-mode/LLM/numeric-finance rejection, expiration, request timeout/unmount; all earlier Ask/App tests |
| Local integration | Existing health/status/proxy/Ask/persistence checks retained; appended analytical Trust/IDs/insufficient-data/false-execution checks |
| Browser | New disposable Chrome desktop1440/mobile390 Trust and Ask regression journeys, unsupported inputs, no overflow/runtime errors, no automatic requests; Opportunity/Autopilot disabled |
| Actual account capability | New isolated read-only LIVE verification: NVDA/two issuers, current snapshot403, PRICE_INFO read succeeds but mandatory liquidity absent, news partial, persisted INSUFFICIENT_EVIDENCE |

Final check counts/results and evidence fingerprints are recorded in [PHASE_2_TRUST_REPORT.md](PHASE_2_TRUST_REPORT.md) and the [gate record](evidence/CANONICAL_PHASE_2_TRUST_GATE.json). Synthetic complete-history cases verify software behavior; they do not certify current-equity entitlements, real baseline availability, calibrated statistics, profitability or LIVE execution.

Reproduce locally:

```sh
.venv/bin/python -m pytest --cov=app --cov-report=term-missing
.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
npm test
npm run build
.venv/bin/python scripts/check-security.py
npm run test:integration
node scripts/check-trust-browser.mjs
node scripts/check-ask-browser.mjs
```

The last three commands use running loopback services; browser checks use disposable profiles. Optional explicit provider verification: `.venv/bin/python scripts/verify-trust.py --live-read-only`; default without flag uses only existing DEMO data. New Trust verification artifacts/databases never overwrite historical PHASE_2/Data Layer or Canonical Phase 1 evidence.

## Capability remediation additions — 2026-10-06

All282 backend /47 frontend checks retained. Added20 backend tests:14 synthetic scoped-news boundary/order/source/mode/ticker/availability/reset/before-bound checks in test_news_window_remediation.py;2 REAL_CAPTURED_INPUTS_REPLAY checks in test_trust_real_capture.py;4 isolated diagnostic allowlist/403-redaction checks in test_trust_remediation_diagnostics.py. Captured replay retains actual timestamps and LIVE provenance but is neither fresh entitlement evidence nor positive classification/calibration. Genuine sufficient real history and real positive classifications remain NOT_AVAILABLE; existing synthetic sufficient-history/three-class tests are explicitly software-only. Full suite now302 backend /47 frontend PASS. [Remediation report](PHASE_2_TRUST_REMEDIATION.md) and [formal gate](evidence/CANONICAL_PHASE_2_TRUST_GATE.json) retain the blocked real-data prerequisite distinction.
