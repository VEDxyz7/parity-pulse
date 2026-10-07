# Canonical Phase 1 — pre-implementation audit

Date: 2026-10-06. Read the phase map, accepted Engineering Stage 2 report, execution gates, reconnaissance gate, API matrix, architecture and current master requirements. Both master copies match the accepted SHA-256 45ef4fbc1547c850308267cefb6041293351d0cc36d7be423348b18d3b17991f. No product or safety requirement is amended.

| Capability | Existing evidence / action |
|---|---|
| Foundation, protected settings, request IDs, SQLite, health/status, frontend shell | PASS; reuse |
| Stock-first ticker/company matching, runtime issuer/chain/representation discovery | Implemented in AssetDiscoveryService; reuse |
| Strict provider schemas, prices, shares/token ratios, timestamps and mode provenance | Implemented; reuse without provider contract changes |
| Independent equity reads | Implemented; current account snapshot/NBBO forbidden; do not replace with Binance referencePrice or historical close |
| Natural-language stock budget request | Missing; add bounded deterministic grammar; ambiguity requires explicit correction, no LLM |
| Issuer comparison and budget/exposure arithmetic | Missing; add backend Decimal calculations, integer token units and conservative rounding |
| Route/result/proposal | Missing; construct a non-executable market-price estimate, compare eligible representations, expose unknown fees/liquidity/simulation; no invented vendor quote, funding token or wallet |
| Proposal/audit persistence and retrieval | Missing; add isolated proposal records with request/run IDs, input observations, policy/version and expiry; never create orders/positions |
| Ask form/result display | Missing; add explicit user-triggered proposal request and backend-value display |
| Verified DRY_RUN gate | Missing; add normal/failure/expiry/mode/no-execution tests and complete regression verification |

Selection eligibility here means eligible for an indicative exposure estimate, never eligibility to trade. Unknown costs cannot be treated as zero or lowest all-in cost. Trust, wallet eligibility, funding balance/conversion, vendor execution support and transaction simulation stay unverified and block execution readiness. LIVE prices must be fresh at the time of the request and their observation identity/ratio must match metadata. DEMO fixed observations remain visibly synthetic.

Stop after the Working Ask Flow and its gate. Canonical Trust Layer remains NOT STARTED; Opportunity remains BLOCKED_BY_TRUST; all three LIVE gates remain BLOCKED. No Trading/Transaction/Wallet external adapter or live endpoint will be added for this milestone.
