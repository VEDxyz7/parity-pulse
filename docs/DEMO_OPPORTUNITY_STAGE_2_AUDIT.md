# Hackathon Demo Stage 2 — stopped at the existing Trust boundary

Audited 2026-10-07 at checkpoint **v0.2-demo-trust**, commit `83a0a2bc38549b84bbabcc44b4b50b28b05a4b6e`. **Stage status: BLOCKED; no Opportunity integration implemented.**

The user's stop instruction is: “If an existing downstream component cannot operate from DEMO inputs, stop at the cleanest supported boundary and report what is missing rather than bypassing it.” The supported boundary is the completed DEMO Trust assessment. The checkpoint contains a planned Opportunity architecture, but no existing Opportunity, financial Risk, provider Quote, transaction-building or simulation service to invoke. This missing implementation is an independent integration blocker; production gates remain unchanged.

The [machine-readable audit](evidence/DEMO_OPPORTUNITY_STAGE_2_AUDIT.json) records actual service/route inventories, offline scenario results, existing proposal behavior, the input-compatibility probe, validation and preservation checks. Diagnostic status strings in that file are audit descriptions, not new public Opportunity/Risk contracts or engine decisions.

## Inspected architecture and smallest integration point

| Required component | Actual repository evidence | Current supported boundary |
|---|---|---|
| DEMO Trust | `DemoTrustSandbox.assess` injects existing DEMO providers, a fixed synthetic clock and isolated history into `TrustService.assess` | All three existing synthetic scenarios work. `DemoTrustResult.assessment` is the typed candidate input for a future downstream adapter. |
| Opportunity engine/API/schemas | No Opportunity service, engine, router, candidate schema or decision schema exists under `backend/app`. Actual `/api/opportunity` and `/api/demo/opportunity` probes both return404. Master sections39/39A and engineering stage7 describe future filtering/ranking/selection. | No Opportunity analysis can be invoked or claimed. No adapter can connect to an absent implementation. |
| Opportunity gate | Existing `docs/EXECUTION_GATES.md` and `DemoProductionGates` report BLOCKED_BY_TRUST | Gate and semantics remain unchanged. Synthetic Trust classification supplies no global gate pass. |
| Financial risk | No implemented Risk Engine or risk approval contract. Exposure input checks validate identity, issuer state, freshness, decimals and budget arithmetic; they do not implement financial risk authorization. | No risk-approved notional, stress-loss check, daily-loss/trade-count/cooldown authorization or risk rejection can be reported. |
| Phase1 proposal/quote | `ExposureService.propose`, `ExposureProposal`, POST `/api/exposure/quote` and mode-isolated proposal retrieval exist | Indicative market-price estimates and non-executable proposals work independently. There is no Trust-to-Opportunity/proposal handoff. |
| Provider quote | No aggregator QuoteService or provider quote integration. The production Binance client permits only its reviewed market-read operations. Archived Phase0 quote verification is not an application QuoteService. Massive's `get_latest_quote` is an independent equity reference, not a token-execution quote. | Provider quote ID remains null; fees remain UNKNOWN. |
| Transaction preparation | No transaction builder, prepared-transaction contract, fingerprint/equivalence validator or route-specific preparation API | Unavailable. No fictitious calldata, chain/account binding, minimum receive or prepared transaction was created. |
| Simulation | No simulation adapter or simulation service. `ExposureProposal.simulation_status` is literally UNAVAILABLE | Unavailable; required simulation remains true and execution readiness false. |
| Opening prediction/expected economics | No opening-model service or expected-adjustment/net-edge implementation exists. DEMO Trust fixtures contain baseline episodes, not opening-model examples. | Trust deviation/analogue outcomes cannot be relabeled expected adjustment, predicted return or net edge. The separate30-example opening-model safeguard remains intact. |
| Frontend | Existing sandbox selection, derived Trust evidence and clearly synthetic markers; Opportunity navigation disabled | Preserved. No button was added to pretend an unavailable downstream service exists. |

The minimum integration point would consume the existing typed `DemoTrustResult.assessment` and invoke a shared Opportunity service with explicit mandate, eligibility, economic and risk inputs. At this checkpoint that receiving service and its contracts do not exist. Creating new Opportunity/Risk/build/simulation implementations would exceed the requested reuse-only integration and the explicit stop boundary. No new engine, classification shortcut, gate bypass or phantom success result was introduced.

## Actual scenario behavior

All three scenarios were evaluated offline through the existing `DemoTrustSandbox` and unchanged `TrustService`. Real provider construction, external HTTP transport and socket connects were prohibited, with **zero network attempts**. Databases used for the probes were memory-only and disposed after use.

| Scenario | Derived Trust result | Downstream result in this checkpoint |
|---|---|---|
| NORMAL / `steady` | NORMAL; LOW uncalibrated confidence; baseline30; analogues3 | Opportunity analysis not run because the engine is absent. No proposed action or risk approval. This is not a measured Opportunity-engine no-op decision. |
| LIKELY_NOISE / `thin-move` | LIKELY_NOISE; LOW confidence; baseline30; analogues3 | Opportunity analysis not run. No fabricated suppression decision or risk rejection. |
| LIKELY_INFORMATION / `supported-move` | LIKELY_INFORMATION; LOW confidence; baseline30; analogues3 | No computed Opportunity direction, expected adjustment, net edge or risk-approved size. No provider quote, preparation or simulation. Information classification alone does not authorize an action. |

The information scenario's0.02 deviation is a token/share-price comparison, **not** a predicted2% profit or opening adjustment. Its synthetic corroborating headline and persisted analogues are Trust evidence; they do not supply missing economic/risk decisions. No scenario-to-action mapping was implemented.

## Existing quote boundary and compatibility probe

In an isolated DEMO application, the existing Phase1 request `I have $50 of Nvidia` returns a DRY_RUN proposal with `route_type=INDICATIVE_MARKET_ESTIMATE`, `quote_status=INDICATIVE_ONLY`, `provider_quote_id=null`, `fee_status=UNKNOWN`, `simulation_status=UNAVAILABLE`, `execution_ready=false` and `transaction_broadcast=false`. This uses the existing independent Ask fixture, not the selected Trust scenario, and is not an Opportunity-driven action. The retained `TRUST_NOT_IMPLEMENTED` proposal blocker refers to missing proposal/Trust integration, not absence of the separately implemented Trust engine.

A separate synthetic compatibility probe supplied the information scenario's **unchanged** token/equity inputs to the existing ExposureService. Its token observation is PRICE_INFO; the Phase1 estimator requires PRICE. The actual result is **NO_PROPOSAL / quote UNAVAILABLE**, no selected representation, and `TOKEN_PRICE_MISSING_OR_WRONG_KIND`. Simulation remains UNAVAILABLE and no transaction is broadcast. The explicit USD50 amount was a diagnostic input, not a derived Opportunity position size or recommendation.

No PRICE_INFO observation was relabeled PRICE, no ordinary Ask fixture was silently substituted for scenario evidence, no execution blocker was removed, and no provider operation allowlist was extended.

## Validation and preservation

| Command/check | Result |
|---|---|
| `.venv/bin/python -m pytest` | 345 passed,0 failed |
| `npm test` | 66 passed,0 failed |
| `npm run build` | PASS: TypeScript noEmit and Vite production build |
| `.venv/bin/ruff check backend scripts` | PASS |
| `.venv/bin/ruff format --check backend scripts` | PASS:78 files |
| `.venv/bin/python scripts/check-security.py` | PASS; new audit artifacts additionally scanned for all configured provider credentials without displaying values |
| `git diff --check` | PASS |
| Browser | No rerun: no frontend/behavior change. Prior Stage1 desktop/mobile browser evidence, corresponding source and fixtures remain byte-identical. No Stage2 browser success is claimed. |

Tests added: **zero**. The requested Opportunity/Risk/build/simulation behavior tests cannot prove functionality absent from the checkpoint. Existing Trust/DEMO isolation, LIVE regression, proposal and execution-blocking tests were retained and rerun; none were weakened. The existing upstream Starlette/httpx TestClient deprecation warning remains.

All **230 pre-existing inventoried artifacts remain byte-identical**, including application/test source, fixture datasets, all eight databases, production gate records, master specifications, historical reports, the saved alignment diagnostic and prior browser evidence. Production historical counts are unchanged: **0/30 qualifying baseline episodes,0/30 opening-model episodes and0/3 real analogues**. Synthetic results remain excluded from production coverage. No real provider, wallet, swap, RFQ, Agentic Wallet or execution endpoint was called. Existing services were not restarted or modified. Git HEAD and the peeled checkpoint tag remain unchanged; no commit was made.

Exactly two files were added:

- `docs/DEMO_OPPORTUNITY_STAGE_2_AUDIT.md` — this report.
- `docs/evidence/DEMO_OPPORTUNITY_STAGE_2_AUDIT.json` — measured inventory, probes and validation evidence.

Architecture/integration changes: **none**. New downstream stages working: **none**. Existing DEMO Trust and separate Phase1 indicative proposals remain working. Production gate states:

```text
DATA_GATE=PASS
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

## Prerequisites before a Paper Execution stage

First establish one shared deterministic Opportunity implementation and candidate/decision contracts, consuming existing Trust evidence alongside explicitly supplied mandate, expected-economic inputs, costs and regime eligibility. Establish the shared financial Risk Engine and its policy/input contracts before proposing authorized sizes. Supply a legitimate DEMO quote representation compatible with the selected scenario and existing estimate contract; keep any indicative estimate visibly distinct from a provider execution quote. Transaction preparation, fingerprints, route-equivalence checks and simulation need their own implemented, tested components before success can be claimed.

Paper Execution would additionally need a separately authorized isolated ledger/state machine, explicit fill/cost/outcome semantics and no production persistence or execution access. None of those components was implemented here. Production Trust requirements and all30/30/3 safeguards remain unchanged. **Stop at the completed Trust boundary; Paper Execution has not started.**
