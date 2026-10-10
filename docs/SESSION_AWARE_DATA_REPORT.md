# Session-aware data continuation — October 10, 2026

Scope: repository reconnaissance and the highest-priority missing component from the user's
new session-aware implementation prompt: a selectable independent Alpaca data adapter.
This is not completion of the entire new roadmap or advancement of a production gate.

## Reconnaissance and gap analysis

Starting branch `main`, clean working tree, HEAD `be34929` (merged dashboard redesign).
Recent working implementation through Master Phase 16 and the glass dashboard was preserved.
No reset, branch switch, commit, push, application restart or production database write occurred.
No applicable AGENTS.md was found in the project/parent paths or backend/frontend trees.

Reviewed the supplied implementation prompt in full, the existing master and phase/gate/API/
architecture/Trust/research documentation, backend/frontend manifests, provider interfaces,
transport/configuration/logging, observation models, persistence, data consumers and tests.
`docs/MASTER_SPEC.md` remains byte-identical to the previously completely read October 7
authority: SHA-256 `f69a9bd01a622c001c3ec6cb654e00562f6b3d03a8310f9e5ccf68efe4b49c84`.
The user's new provider responsibilities guide this continuation; older master copies were
not substituted or edited.

| Area | Existing evidence / actual gap | Disposition in this increment |
|---|---|---|
| Binance | Signed, allowlisted RWA/Market clients; prior measured read evidence; metadata/ratio/price/candles already implemented | Reused unchanged; no new authenticated probe or execution call |
| Independent equity | Massive adapter/history available; documented current Snapshot/NBBO 403; no Alpaca implementation | Implemented Alpaca adapter and explicit primary-source selector |
| Normalization/persistence | Decimal/UTC provenance, deterministic IDs, immutable mode-separated JSON records | Added feed/delay/quality fields; old payloads normalized before duplicate comparison |
| News/events | Existing Massive news, publication/ingestion handling; no Finnhub integration or configured key | Existing news separated from equity selection; Finnhub deferred |
| Sessions/references | Existing versioned NYSE 2026–2028 calendar, DST/holiday/early-close tests; current-versus-close validator | New source priorities/types/extended/overnight reference policy still missing; unchanged Trust allowlist rejects Alpaca |
| Baselines/Trust | Deterministic scoped history, no-look-ahead, minima, classification and abstention exist | Preserve logic; upstream evidence remains insufficient |
| Research/agents | Existing typed, bounded interpretations, research and persistent outcomes | Reuse; no new prediction or profitability claim |
| Opportunity/routing/risk | Existing deterministic services and isolated DEMO flow | Unchanged; production Opportunity remains blocked |
| Simulation/execution | Existing exact-input guards, unavailable-state handling and DRY_RUN-only gateway | Unchanged; no new execution permissions |
| Optional HIP-3 | No verified runtime instrument mapping/provider | Deferred; never a substitute equity reference |
| Dashboard/scorecard | Existing functional UI, audit and actual-outcome contracts | Unchanged; broader session-aware display awaits verified provider/policy evidence |

The active `data/parity-pulse.db` contains two DEMO token and two DEMO equity observations.
Separate prior verification databases contain LIVE records; read-only inventory confirmed the
historical investigation store's 83 token / 2,083 equity observations. These are distinct stores,
not new coverage or qualifying episodes. Prior Phase 16 replay evidence (122 real token captures,
7,336 raw token bars, 2,143 equity bars) remains historical evidence. No fresh backfill, synthetic
sample promotion, historical ratio inference or revised 30/30/3 count occurred in this task.

## Implemented boundary

`AlpacaClient` reuses `ReadTransport` timeouts, bounded transient retries, Retry-After/circuit
handling, single-flight cache, Decimal JSON parsing, sanitized logs and credential-echo rejection.
Its fixed host is `https://data.alpaca.markets`; only two GET paths are allowed. Credentials are
header-only. Trading/account/wallet paths, arbitrary URLs and bodies fail before transport.
Default pacing is 0.31 seconds; no SDK/package dependency was added.

`AlpacaProvider` returns the existing `EquityObservation` contract:

- Latest quote midpoint `(bid + ask) / 2`, positive two-sided prices/sizes, actual QUOTE kind.
  It does not label a midpoint as a last trade, NBBO for IEX, or official closing price.
- UTC source/receipt times, original RFC3339 nanosecond string retained (datetime comparison
  precision is microseconds), explicit feed, nullable delay status and conservative quality flags.
- UNKNOWN entitlement quality by default; an HTTP 200 never changes account-plan/Trust readiness.
  Configured REALTIME is an operator assertion requiring separate evidence, not an entitlement probe.
  Age >120 seconds is STALE and future quotes INVALID. Explicit delayed feeds remain delayed/stale.
- Bounded 1m/5m history, explicit RFC3339 start/end, immutable feed and opaque page tokens on the
  same host/path. Enforces timestamp ordering/window, completed bars and consistent OHLC.
  Page-bound truncation is marked incomplete. Missing bars remain absent.
- Raw, unadjusted prices and disabled automatic symbol remapping; historical revision availability
  is explicitly unverified. No historical series is certified point-in-time or Trust-ready.
- Official previous close, market status/holidays and corporate actions explicitly unavailable
  in this adapter. No inference from an IEX last bar or overnight price.

`EQUITY_PROVIDER=ALPACA` makes Alpaca the sole primary equity reader in LIVE_READ_ONLY.
There is no automatic fallback after missing credentials, denial, stale data or malformed response.
The default remains MASSIVE to preserve existing installations until an explicit migration.
DEMO still uses only its existing fixtures and instantiates no external clients.

`DataLayer.news` preserves the existing Massive news source independently of the selected equity
provider. Trust's change is limited to reading that existing news dependency; classification,
thresholds, source eligibility, 120s freshness, 30s skew and 30/30/3 safeguards are unchanged.
The legacy Massive-specific ingestion checkpoint explicitly rejects other providers. Alpaca
history is available through the adapter, but resumable production backfill is not implemented.

## Official contracts and actual verification

Reviewed official documentation on October 10, 2026:

| Endpoint | Contract verified | Runtime result in this run |
|---|---|---|
| GET `/v2/stocks/quotes/latest` | symbols, explicit feed, USD; quote timestamp/bid/ask | NOT_CONFIGURED; no HTTP request |
| GET `/v2/stocks/bars` | symbols, timeframe, explicit bounds, feed, raw adjustment, asof, page_token | NOT_CONFIGURED for both 1m/5m; no HTTP request |

Alpaca key/secret were absent from the project environment and shell (including standard APCA
variable-name checks); Finnhub was also absent. Binance/Massive configuration was present;
values were never displayed. The isolated diagnostic records statuses and zero requests in
[ALPACA_READONLY_20261010.json](evidence/ALPACA_READONLY_20261010.json).
No live price, account plan, feed entitlement, 30-second alignment or historical coverage is claimed.

Official sources: [latest quotes](https://docs.alpaca.markets/us/reference/stocklatestquotes-1),
[historical bars](https://docs.alpaca.markets/us/reference/stockbars),
[subscription/authentication](https://docs.alpaca.markets/us/docs/about-market-data-api),
[feed and access FAQ](https://docs.alpaca.markets/us/docs/market-data-faq).
IEX is a single venue, SIP consolidated; latest SIP needs appropriate access and delayed SIP
cannot meet 120-second current freshness. Requested feed acceptance alone is not subscription
or redistribution evidence. No purchase or licensing assumption was made.
[Binance RWA documentation](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/rwa-data)
still describes referencePrice as token-derived, not an independent equity quote. That exclusion remains.

## Reproduction

Configure `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` locally; never paste values into commands/reports.
Choose `ALPACA_FEED` explicitly. Keep `ALPACA_DATA_QUALITY=UNKNOWN` pending actual verification.
The diagnostic does not instantiate the application/database or persist market observations;
`--live` authorizes only the three named market-data reads. It always reports Trust eligibility false.
Use a completed history window of at most two days and a **new** output filename on each run:

```sh
PYTHONPATH=backend .venv/bin/python scripts/verify-alpaca-readonly.py --live \
  --start 2026-10-08T13:30:00Z --end 2026-10-08T14:00:00Z \
  --output docs/evidence/ALPACA_READONLY_NEXT.json
.venv/bin/python -m pytest backend/tests/integration/test_alpaca.py -q
.venv/bin/python -m pytest -q
npm test
npm run build
.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
PYTHONPATH=backend .venv/bin/python scripts/generate-ui-contracts.py --check
.venv/bin/python scripts/check-security.py
git diff --check
```

The saved Twelve Data/Binance synchronization diagnostic was not run or modified.

## Validation and gates

Final complete backend suite: **1,465 passed**, including **47 new Alpaca tests**; no failures.
Two existing Pydantic warnings come from deliberately malformed allowance fixtures.
Frontend: **273 passed / 14 files**. TypeScript/Vite build, Ruff lint/format, seven generated
Pydantic frontend-contract checks, configured-secret/security audit and `git diff --check` pass.
The initial provider/config baseline also passed all 72 relevant tests before editing.
Ordinary adapter tests use synthetic fixtures; they cannot prove external entitlement or real
Trust sample availability. Tests cover source/quote precision, timestamps/freshness, feed isolation,
malformed/unsupported/missing data, denial/rate-limit/secret-echo handling, read-only allowlists,
bounded history/pagination/completion, old JSON idempotency, mode-separated persistence, primary
source/news wiring, no-fetch startup, diagnostic authorization and unchanged public gates.
No browser recheck was needed for this backend-only increment; frontend tests/build cover unchanged UI.

```text
DEVELOPMENT_READINESS=PASS (existing non-live scope)
DATA_GATE=PASS (existing measured scope; Alpaca entitlement NOT_VERIFIED)
DRY_RUN_GATE=PASS
TRUST_GATE=BLOCKED
OPPORTUNITY_GATE=BLOCKED_BY_TRUST
SWAP_LIVE_GATE=BLOCKED
RFQ_LIVE_GATE=BLOCKED
AGENTIC_WALLET_LIVE_GATE=BLOCKED
```

Remaining dependencies: configured Alpaca credentials and actual feed/account entitlement,
regular-session freshness/alignment, verified source-selection/extended-session policy and official
close support, authoritative liquidity, historical ratio/revision/as-of availability, real qualifying
30/30/3 samples, Finnhub events/session integration and full event coverage. Optional HIP-3 mapping
remains unverified. Real wallet/runtime and exact SWAP/RFQ simulation/settlement equivalence remain
independent LIVE blockers. Stop after this adapter increment; next step is isolated Alpaca read-only
verification with configured credentials, followed by evidence-driven reference-policy integration.

## Files changed

- `.env.example`, `backend/app/config.py`: explicit provider/feed/quality settings and secret handling.
- `backend/app/clients/alpaca.py`, `backend/app/providers/alpaca.py`: read-only adapter.
- `backend/app/models/data.py`, `backend/app/repositories/data.py`: additive metadata/backward compatibility.
- `backend/app/services/data_layer.py`, `backend/app/services/trust.py`: independent equity/news wiring only.
- `backend/app/services/ingestion.py`: reject unsupported provider checkpoints.
- `backend/tests/integration/test_alpaca.py`: adapter, persistence, diagnostic and gate tests.
- `scripts/verify-alpaca-readonly.py`, `scripts/check-security.py`: isolated probe and secret-scan coverage.
- `docs/evidence/ALPACA_READONLY_20261010.json`: actual no-credential diagnostic result.
- `docs/SESSION_AWARE_DATA_REPORT.md`, `docs/API_MATRIX.md`, `docs/CAPABILITY_GAPS.md`,
  `docs/ARCHITECTURE.md`, `docs/EXECUTION_GATES.md`, `README.md`: scope, contracts, gaps and reproduction.
