# Hackathon Demo Stage 1 — isolated Trust sandbox

Implemented and verified 2026-10-07. **DEMO_SANDBOX_STAGE_1=PASS**, scoped exclusively to a synthetic analytical demonstration. Production TRUST_GATE remains BLOCKED. This stage does not resolve any real-data prerequisite, authorize Opportunity or implement execution.

## Pre-code audit and smallest implementation

The existing `TrustService.assess` already composes discovery, provider evidence, exact normalization, features, completed history, baseline statistics, analogue retrieval and classification. Its constructor accepts a data layer, database and clock. Historical samples/episodes are fetched from its `TrustRepository`; classifiers require a nondegenerate baseline of at least 30 eligible episodes and at least three qualified analogues. The implemented Trust path does not consume opening-model episodes: opening prediction remains unimplemented. Its separate 30-example safeguard is preserved, with no opening-model fixtures or model added here.

Existing synthetic tests demonstrate all three labels. The real inventory remains insufficient, as documented by the prior [Replay Stage 1 audit](REPLAY_STAGE_1_AUDIT.md). The new instruction explicitly authorizes synthetic/non-production fixtures, unlike that earlier real-history replay request. No historical-ratio or provider investigation was repeated.

The implementation supplies equivalent inputs through existing DEMO providers and repositories. It calls the unchanged **`TrustService.assess`**, not a copied Trust implementation or an alternative classifier. A small synthetic market provider supplies PRICE_INFO observations, and a fixed synthetic clock supplies deterministic timestamps. The common frontend evidence display is extracted without changing its ordinary Trust-panel behavior.

## Runtime and isolation

`RUNTIME_MODE=LIVE` is the default and preserves the existing application path, configured database, data provider selection and ordinary Trust endpoint. This name does **not** enable live trading. Existing `DATA_MODE=DEMO` and `DATA_MODE=LIVE_READ_ONLY` meanings remain unchanged. The LIVE runtime does not load the new sandbox fixtures or register sandbox endpoints; its `/api/system-status` response retains the existing keys.

`RUNTIME_MODE=DEMO` requires `DATA_MODE=DEMO`; a mixed LIVE_READ_ONLY configuration is rejected. The entire application uses `sqlite:///:memory:` instead of opening the configured database. Existing Ask/data behavior remains usable with DEMO inputs in that isolated memory. Each sandbox assessment additionally uses a **fresh private in-memory database**, seeds only its selected scenario and closes that database after returning the derived assessment. Scenario requests cannot accumulate history in the application database, mix datasets, affect production coverage or make real provider requests.

The sandbox runtime adds an explicit `runtime_mode=DEMO` field to system status. The frontend shows a prominent **DEMO SANDBOX / SIMULATED DATA — NOT LIVE MARKET DATA** indicator and replaces the ordinary Trust form with the scenario selector. Synthetic timestamps remain visible as a fixed synthetic clock; they are not labeled current market observations or historical replay. Results use the existing evidence component, with additional feature values, synthetic headlines, fixture SHA256 and expandable baseline/analogue/news evidence.

Analytical endpoints exist only in this explicit runtime:

- `GET /api/demo/trust/scenarios` — marked synthetic scenario catalog.
- `GET /api/demo/trust/scenarios/{identifier}` — derive an assessment through the existing engine. Only `steady`, `thin-move` and `supported-move` are accepted. Query toggles and writable methods are rejected.

No execution, wallet, RFQ, swap, paper-execution, Opportunity, agent or prediction path is added. All assessments retain DRY_RUN/PROPOSE_ONLY, required simulation, false live/ready/broadcast flags, LOW uncalibrated confidence and the explicit no-broadcast statement. Production Trust/Opportunity/LIVE gates remain blocked even when a synthetic classification is positive.

## Run locally

From the repository root, with the canonical backend port available:

```sh
RUNTIME_MODE=DEMO DATA_MODE=DEMO .venv/bin/python -m uvicorn app.main:create_app --factory \
  --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
```

In a second terminal, also from the repository root:

```sh
npm run dev
```

Open <http://127.0.0.1:5173>, find **DEMO SANDBOX**, choose a scenario and press **Run demo scenario**. The selector labels describe intended demonstrations; the displayed classification comes from the backend engine. No scenario is automatically assessed when the page opens. Selecting another scenario clears the prior assessment and cancels its pending request.

The process-level environment overrides above do not edit `.env`. Provider credentials are unnecessary for the sandbox. The configured database URL is not opened in DEMO runtime. Use `RUNTIME_MODE=LIVE` or leave it unset to retain the existing ordinary application behavior; execution remains blocked.

Verification used separate temporary localhost ports 8011 and 5174, with the built frontend's API reads routed to the actual isolated backend in the disposable browser. The existing services and canonical frontend proxy were not changed.

## Fixture structure and derived classifications

Three frozen JSON files live in `data/demo/trust-sandbox/`. Each dataset and every wrapped input/history record explicitly contains:

```json
{"dataset_type": "DEMO_FIXTURE", "synthetic": true, "production_eligible": false}
```

Each root carries a version (`demo-trust-1`), scenario identity/title/description, fixed synthetic decision time, typed asset/issuer/token/PRICE_INFO/equity inputs, synthetic news, 30 completed synthetic baseline episodes and zero or 15 preceding synthetic samples. All provider records use DEMO mode/quality, the chain is DEMO, contracts have `demo:` identities, and historical episodes have `evidence_kind=SYNTHETIC_TEST`. Synthetic economic ratio is explicitly 0.5 shares/token; independent synthetic equity price is USD100/share. No real Binance contract or historical ratio is reused.

The fixtures contain **no final `classification` field**. Titles are presentation metadata. Baseline features and preceding samples were generated offline through the existing Trust feature calculation; completed baseline outcomes were constructed using the existing `EpisodeBuilder`. Thirty prior calendar-regular sessions provide each scenario's completed synthetic history. These are invented demonstration observations, not reconstructed real observations. Outcome fields REVERSED/PERSISTED describe synthetic completed episode outcomes, not the current classification. The unmodified engine computes current economics, persistence, statistics, similarity, news alignment and final classification on each request.

| Dataset / selector | Current synthetic evidence | Actual engine result |
|---|---|---|
| `steady.json` / NORMAL | USD50.35/token, ratio0.5, effective USD100.7/share, deviation0.007; volume USD1,000, liquidity USD5,000, 900s observed persistence; covered no-news window | NORMAL: deviation falls within baseline p75 and liquidity exceeds baseline p25 |
| `thin-move.json` / LIKELY NOISE | USD51/token, effective USD102/share, deviation0.02; volume USD100, liquidity USD10, persistence0s; covered no-news window and reversed completed synthetic outcomes | LIKELY_NOISE: deviation exceeds p95, relative volume/liquidity/persistence are low and at least two retrieved outcomes reversed |
| `supported-move.json` / LIKELY INFORMATION | USD51/token, effective USD102/share, deviation0.02; volume USD3,000, liquidity USD5,000, persistence900s; explicitly synthetic “Nvidia (DEMO) raises guidance” headline and persisted completed synthetic outcomes | LIKELY_INFORMATION: deviation exceeds p95, relative activity/persistence/liquidity satisfy existing rules, headline corroborates and at least two retrieved outcomes persisted |

Every scenario has a sufficient **30-episode** baseline and retrieves **3 eligible analogues** using the existing similarity policy. No thresholds, confidence cap, financial calculations or deterministic decision logic were modified. Changing the noise selection's inputs to the normal fixture produces NORMAL despite keeping its noise identifier/title; removing liquidity produces INSUFFICIENT_EVIDENCE. Backend and frontend tests explicitly verify that selection/labels are not authoritative classification.

## Verification and production preservation

| Check | Result |
|---|---|
| `.venv/bin/python -m pytest` | 345 passed: all 326 existing tests retained plus 19 sandbox tests |
| `npm test` | 66 passed: all 47 existing tests retained plus 19 sandbox tests |
| `npm run build` | PASS: TypeScript noEmit and Vite production build |
| `.venv/bin/ruff check backend scripts` | PASS |
| `.venv/bin/ruff format --check backend scripts` | PASS: 78 Python files |
| `.venv/bin/python scripts/check-security.py` | PASS; extended configured-secret scan also covers Twelve Data/Finnhub/issuer keys |
| `git diff --check` | PASS |
| Desktop/mobile browser | PASS: all three actual engine outputs, explicit synthetic evidence/provenance, disabled Opportunity, no automatic scenario assessment, no runtime errors, 390px mobile without horizontal overflow |

Isolation coverage prohibits real provider construction and network transports, proves the configured database can remain an untouched non-SQLite sentinel, checks unchanged application Trust-table counts after all scenarios, verifies fresh scenario histories and deterministic repeated inputs, rejects contaminated/unmarked fixtures, preserves the legacy LIVE response and proves the engine's return value is authoritative. Frontend tests cover all scenarios, labels differing from backend results, validation, request cancellation/late results, catalogue timeout, failed replacement and no LIVE fallback.

The existing upstream Starlette/httpx deprecation warning remains. Synthetic success does not demonstrate real-stock calibration, independent current-equity entitlement/alignment, authoritative real liquidity or actual historical 30/30/3 sufficiency.

The [verification record](evidence/DEMO_TRUST_SANDBOX_VERIFICATION.json) preserves before/after historical counts, protected-artifact hashes, fixture hashes and all changed filenames. All eight pre-existing databases remain byte-identical. Production Trust sources/policy/models, gate documents/evidence, both master copies, historical evidence and saved alignment setup remain unchanged. Real qualifying sample/episode counts remain zero; demo records never enter those databases. [Browser evidence](evidence/DEMO_TRUST_SANDBOX_BROWSER.json) records the actual local GET-only journey.

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

## Exact files changed

Modified:

- `.env.example` — documented opt-in runtime setting; no real environment/credential changes.
- `README.md` — sandbox entry point and runbook link.
- `backend/app/config.py` — explicit runtime selector and mixed-mode rejection.
- `backend/app/main.py` — isolated runtime database/service lifecycle and conditional demo routes.
- `backend/app/api/schemas.py`, `backend/app/api/system.py` — sandbox-only runtime status; legacy LIVE response preserved.
- `frontend/src/types/system.ts`, `frontend/src/services/system.ts` — verify the sandbox runtime marker.
- `frontend/src/services/trust.ts` — type optional backend feature fields; existing parser/calculations unchanged.
- `frontend/src/App.tsx` — conditional sandbox indicator/panel.
- `frontend/src/components/TrustPanel.tsx` — reuse extracted evidence rendering.
- `frontend/src/styles.css` — sandbox-scoped layout and responsive selector/evidence styling.

Added:

- `backend/app/models/demo_sandbox.py` — marked synthetic envelopes around existing data/Trust contracts.
- `backend/app/services/demo_sandbox.py` — fixture providers, isolated repositories and unchanged engine invocation.
- `backend/app/api/demo_sandbox.py` — sandbox-only analytical catalog/scenario GETs.
- `backend/tests/integration/test_demo_sandbox.py` — 19 meaningful engine/isolation/regression tests.
- `data/demo/trust-sandbox/steady.json`, `thin-move.json`, `supported-move.json` — explicitly synthetic input/history fixtures.
- `frontend/src/components/TrustEvidence.tsx` — extracted shared evidence display.
- `frontend/src/components/DemoTrustSandbox.tsx` — scenario selection, evidence, markers and cancellation.
- `frontend/src/services/demoSandbox.ts` — strict demo API boundary; no financial/classification calculations.
- `frontend/src/test/DemoTrustSandbox.test.tsx` — 19 frontend verification cases.
- This report, `docs/evidence/DEMO_TRUST_SANDBOX_BROWSER.json`, and `docs/evidence/DEMO_TRUST_SANDBOX_VERIFICATION.json`.

No automatic commit. Stop after Hackathon Demo Stage 1. Production Trust blockers remain unresolved; Opportunity Mode, Opportunity replay, Paper Execution, historical-ratio/provider research and live execution were not started.
