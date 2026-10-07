# Canonical Phase 2 — pre-code Trust audit

Audit date: 2026-10-06. Authorized scope: deterministic analytical Trust Layer only. Canonical Phase 1 was accepted PASS; the interrupted Ask implementation was reused. No restart of Foundation, Data Layer or Ask work.

Before coding, the current master and requested phase/gate/API/architecture/gap/research documents were inspected alongside provider/service/model/repository/UI code and tests. Both master copies matched accepted SHA-256 `45ef4fbc1547c850308267cefb6041293351d0cc36d7be423348b18d3b17991f`. DATA_CONTRACTS.md and TEST_MATRIX.md were absent; they are newly created for this scope. Existing suite baseline:189 backend/33 frontend PASS. This workspace has no Git metadata, so tracked status/diff was unavailable; pre-edit SHA-256 fingerprints captured source/tests/docs/scripts/fixtures, excluding environment secrets and generated databases.

| Capability | Existing evidence and reuse | Acceptance gap |
|---|---|---|
| Ask, resolution, representation selection, budget/exposure | Completed Phase 1, persisted indicative DRY_RUN proposals, desktop/mobile and failure evidence | None; no rebuild or financial behavior change |
| RWA/market/independent equity/news | Existing allowlisted signed clients, typed providers, exact decimals, quality/provenance, bounded paging, persistence | Compose analytical inputs; explicit current403 and unit gaps |
| Calendar and actual regular close | Versioned2026–2028 New York schedule; previous_session and historical minute-close adapter | Add regime evidence/baseline bucket without inventing schedule rules |
| Token/share math | Exact Phase 1 P/R calculation and base-unit budget arithmetic | Factor one shared normalizer; add E×R/deviation without competing formulas |
| Reference/price time alignment | Source/ingestion timestamps and quality already recorded | Current versus actual-close selection,120second ages,30second current skew, availability rejection |
| Liquidity | PRICE_INFO validates documented fields; trade/candle units already ambiguous | Explicit verified USD inputs, missing/malformed/freshness handling |
| News | Publication/first-seen, bounded history, provider articles already exist | Temporal window, coverage, conservative deterministic relevance/direction; exclude LLM-derived insights |
| Baselines/history | Raw historical records/checkpoints exist | No Trust episodes/statistics; cannot reuse current ratio as past as-of proof |
| Analogues | Research mapping specifies prior normalized vectors/cosine | No retrieval, completion or available-time guards yet |
| Classification | Not implemented | Deterministic states, insufficient evidence, reasons and evidence quality |
| API/UI | Data inspection and Ask endpoints; no Trust view | Read-only Trust endpoint, separate small backend-authoritative panel |

Missing layers were added as composed services, exact typed analytical records and three additive isolated tables. Existing provider paths/allowlists, configuration, fixture/catalog behavior and risk/execution safety remain unchanged. The minimal Ask change factors shared math with identical upward-rounded output and clarifies its separate proposal-Trust integration display. The new engine never changes representation selection/proposals.

No actual baseline or calibration was present. Synthetic tests are DEMO-only and not evidence of real-stock statistical validation. Phase 2 must remain blocked when real mandatory inputs cannot be demonstrated. See the [current report](PHASE_2_TRUST_REPORT.md), [contracts](DATA_CONTRACTS.md), [test matrix](TEST_MATRIX.md) and [formal gate](evidence/CANONICAL_PHASE_2_TRUST_GATE.json).
