# Phase 0.1 remediation

Date: 2026-10-06. **Current PHASE 0 DEVELOPMENT GATE = PASS under the 2026-10-06 amendment. No Phase 1 started; all LIVE gates remain BLOCKED.** The original Phase 0.1 factual observations are accepted unchanged. Its prior FAIL / BLOCKED development decision is superseded only by the user-authorized gate amendment; documentation is still not runtime proof. [Current gate definitions](EXECUTION_GATES.md).

## A. Canonical specification location — VERIFIED

At `2026-10-06T09:41:27.435774Z`, the root [master](../MASTER_BUILD_PROMPT.md) was copied as raw bytes to [docs/MASTER_BUILD_PROMPT.md](MASTER_BUILD_PROMPT.md). Direct byte comparison passed. Each file is 120,969 bytes; each SHA-256 is `8d436286338a8ac9fbb7a6ee76ffce3b81cf96ff9e8c51ea85dfe9e6f2f22554`. Neither specification was edited during that copy step. These size/hash values are historical pre-amendment evidence; both copies now carry the identical authorized development-gate amendment. Current hashes are in [PHASE_0_GATE.md](PHASE_0_GATE.md).

## B. Binance entitlement evidence

Initial presence checks found neither expected credential variable and no workspace environment file. After the user configured the project environment, a new local `.env` appeared. It was read directly into memory for only `BINANCE_WEB3_API_KEY` and `BINANCE_WEB3_SECRET_KEY`; values were never printed, placed in command arguments, written to reports or committed. No shell sourcing/evaluation was used. No private keys or seed phrases were accessed.

Sandbox attempts returned no HTTP/business result and were classified UNAVAILABLE, with permission NOT_MEASURED (`2026-10-06T09:45:52.944Z` through `09:45:54.505Z`). An approved network-enabled retry then succeeded. **Authentication and access to all ten measured reads below are VERIFIED.** This supersedes the earlier missing-credential conclusion for this session. It does not establish write permission, region-wide entitlement or every endpoint in an API family.

Base URL: `https://web3.binance.com/build`. Only the user's requested five evidence fields were retained, with method/query included in the endpoint field. [Sanitized machine-readable evidence](evidence/BINANCE_READONLY_STATUS.json) contains no headers, credential values or response bodies. Business success and payload shape were checked in memory; no response schemas or account data were persisted after the user's narrower recording instruction.

| Endpoint tested (method included) | HTTP / business status | Permission result | Capability result | Timestamp UTC |
|---|---|---|---|---|
| GET /api/v1/dex/market/supported/chain | 200 / 0 | VERIFIED_FOR_THIS_READ | VERIFIED | 2026-10-06T09:46:02.279Z |
| GET /api/v1/dex/market/rwa/platforms | 200 / 0 | VERIFIED_FOR_THIS_READ | VERIFIED | 2026-10-06T09:46:02.851Z |
| GET /api/v1/dex/market/rwa/tokens | 200 / 0 | VERIFIED_FOR_THIS_READ | VERIFIED | 2026-10-06T09:46:07.339Z |
| GET /api/v1/dex/aggregator/supported/chain | 200 / 0 | VERIFIED_FOR_THIS_READ | VERIFIED | 2026-10-06T09:46:09.739Z |
| GET /api/v1/dex/pre-transaction/supported/chain | 200 / 0 | VERIFIED_FOR_THIS_READ | VERIFIED | 2026-10-06T09:46:10.221Z |
| GET /api/v1/dex/pre-transaction/gas-price?binanceChainId=56 | 200 / 0 | VERIFIED_FOR_THIS_READ | VERIFIED | 2026-10-06T09:46:10.706Z |
| GET /api/v1/dex/balance/supported/chain | 200 / 0 | VERIFIED_FOR_THIS_READ | VERIFIED | 2026-10-06T09:46:11.193Z |
| POST /api/v1/dex/market/token/basic-info?binanceChainId=56&tokenContractAddress=0x55d398326f99059fF775485246999027B3197955 | 200 / 0 | VERIFIED_FOR_THIS_READ | VERIFIED | 2026-10-06T09:47:34.539Z |
| POST /api/v1/dex/market/price | 200 / 0 | VERIFIED_FOR_THIS_READ | VERIFIED | 2026-10-06T09:47:36.126Z |
| GET /api/v1/dex/aggregator/quote?binanceChainId=56&amount=1000000000000000000&fromTokenAddress=0x55d398326f99059fF775485246999027B3197955&toTokenAddress=0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE | 200 / 0 | VERIFIED_FOR_THIS_READ | VERIFIED | 2026-10-06T09:47:36.655Z |

The first seven probes cover Market, RWA, Trading, Transaction and Wallet discovery plus gas-price reads. The remaining probes cover read-only POST metadata, read-only POST price, and a standard USDT-to-native-BNB quote. Its amount was gated on metadata validation; it did not create an order or position. A quote response is not execution or settlement evidence. No wallet signer was invented.

Still **NOT_TESTED**: `/aggregator/swap` GET (requires an actual verified wallet and a current quote); `/pre-transaction/simulate` POST (requires a validated non-capital transaction fixture); wallet-specific balance/history reads (no verified wallet address); existing RFQ status reads (no real existing order ID); and an RWA RFQ quote requiring the actual signing wallet. Order submission, transaction broadcast, approvals and signature execution remain disabled and were not attempted.

The [official authentication contract](https://web3.binance.com/en/dev-docs/authentication) separates HTTP 401 authentication errors from HTTP 403/business 40104 permission denial. Neither was observed in the successful probes. Future classifications require measured evidence: VERIFIED for a valid successful operation response; FORBIDDEN for explicit permission denial; UNAUTHORIZED for explicit authentication failure; UNAVAILABLE for measured connectivity/service failure; NOT_TESTED when no qualifying request was made. A discovery success cannot establish simulation or write entitlement. No permission beyond the tested reads is inferred.

## C. Agentic Wallet runtime evidence

| Check | Exact local observation | Conclusion |
|---|---|---|
| Executable | Python shutil.which('baw') returned null; original command-v lookup also absent | UNAVAILABLE on the worker's current PATH |
| Global npm package | npm ls --global @binance/agentic-wallet --depth=0 --json exited 1, returned only name=lib and no package dependency | Not found in inspected global npm prefix; not an exhaustive disk search |
| Node prerequisite | node --version returned v24.12.0 | Node is present; does not prove CLI installation |
| Installed CLI version | No executable/package found | NOT_TESTED; no version invented |
| Wallet skill | No matching SKILL.md in inspected ~/.codex/skills, ~/.codex/plugins or ~/.config; ~/.agents/skills, ~/.claude/skills, ~/.openclaw and ~/.local/share/skills absent | UNAVAILABLE in inspected local agent skill locations |
| Tokenized-securities skill | Same bounded inventory, no matching manifest | UNAVAILABLE locally; official source availability is separate |
| Runtime configuration | ~/.baw and ~/.config/agentic-wallet absent | No configuration found at these candidates; actual storage location not asserted |
| Status/address/balance/order reads | No command executed after executable lookup failed | NOT_TESTED; do not label wallet UNCONNECTED without a response |
| Intended execution worker | No application/worker exists; current shell cannot resolve baw | UNAVAILABLE here; subprocess control, session access and deployment isolation NOT_TESTED |

Inventory observations were made between `2026-10-06T09:41:27.435774Z` and `2026-10-06T09:42:09.538232Z`. There is no wallet login, pairing session, address, balance or order fixture.

Official dependencies and connection path, **documented only; not run**:

- [Skills Hub README](https://github.com/binance/binance-skills-hub) requires Node 22+ and documents `npx skills add https://github.com/binance/binance-skills-hub`. Inspect the selected skills and installation targets before using an installer.
- [Current wallet manifest](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/SKILL.md) reports skill 1.12.0 and required CLI 1.10.0. [Preflight](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/preflight.md) documents `npm install -g @binance/agentic-wallet@1.10.0`, followed by version compatibility and wallet-status checks. Recheck current requirements at installation time.
- [Authentication](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/authentication.md) uses `baw auth signin --json`, Binance App approval of the returned pairing flow, and `baw auth verify --qrCodeId <returned-id> --json`. Connection must be confirmed by a status response. This session-changing flow is outside this read-only remediation.
- Safe subsequent runtime reads: `baw wallet status --json`, `baw wallet address --json`, `baw wallet balance --binanceChainId 56 --json` ([wallet reference](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/wallet-view.md)), then `baw market-order list --json` or a real existing `--orderId` ([order reference](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/market-order.md)). Do not manufacture an order to test status. These commands are not measured successes.
- The [securities skill source](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-tokenized-securities-info/SKILL.md) is available publicly; reading it did not install it or test its APIs. It is a data skill, not an execution gateway.

No install, sign-in, wallet-setting change, preview, signature, approval, trade or broadcast was performed. Published skill files were inspected as API reference material, not installed or activated.

## D. RFQ and SWAP safety analysis

**RFQ_LIVE_SAFE: NOT_VERIFIED. LIVE RFQ EXECUTION MUST REMAIN DISABLED, including signature execution and submission.**

The [Trading API](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/trading-api) describes quote → RFQ mode → swap → rfq.typedDataToSign → EIP-712 signing → order/submit → order-status polling. The quote wallet must match the signer. Submission quoteId refers to swap rfq.orderId; subsequent polling uses the platform orderId. The rendered swap example includes a digest-like typedDataToSign placeholder; it is not a complete runtime signing fixture. No final relayer transaction or exact-settlement simulation contract was established from this surface.

The [Transaction API](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/transaction-api) simulates an explicitly supplied chain transaction. For BSC this is evmTx with from, to, integer-wei value and calldata. It can assess a separately constructed approval or ordinary SWAP transaction; that result does not cover a later vendor-relayed RFQ settlement. Simulating invented settlement calldata would not establish equivalence.

[External signing](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/external-sign.md) distinguishes contract-call preview simulation from sign-message preview parsing/risk checks. EIP-712 input requires the complete typed-data JSON-RPC request. Execute consumes the preview requestId and requires explicit confirmation. A message preview is not a prediction of the vendor's final balance changes. Runtime enforcement remains untested.

Conclusion is an inference from the reviewed coverage, not proof that no mechanism exists anywhere. Closure requires an official gateway/vendor contract identifying the actual settlement bindings, predicted effects, validity/state limits and equivalence enforcement, plus sanitized non-capital validation. A signature, order acknowledgement or approval simulation alone is insufficient. Flash RFQ embedding remains unverified and cannot be a workaround.

**SWAP_LIVE_SAFE: NOT_VERIFIED.** A documented candidate path exists for an actual SWAP response: simulate the exact returned transaction, apply all risk/wallet/confirmation requirements, preserve the execution-critical fingerprint into the gateway, and reconcile terminal chain evidence. No runtime fixture proves this path. CLI market-order execution cannot be assumed to reuse a separately simulated aggregator route. Gas-sensitive parameters, expiry, nonce/session behavior and any changed route require equivalence validation or rebuilding/resimulation. No SWAP is marked LIVE.

## E. Distinct gates

| Gate | Current evidence status | Safe capability / limitation | Required closure |
|---|---|---|---|
| DATA_GATE | PASS; ten accepted reads, safe non-live development scope | Measured Binance reads work independently of RFQ; Massive, source freshness, wallet-specific reads and full data pipeline remain unverified | Untested wallet/build/simulation reads as applicable; freshness validation and Massive entitlement/calendar evidence |
| DRY_RUN_GATE | NOT_YET_TESTED; feasible, not implemented | Wallet credentials are not intrinsically required for DEMO. A real quote/build/simulation dry-run still needs working data APIs. Unknown RFQ settlement safety must stay visible | Implement later with separated demo data, no signing/submission/broadcast, valid fixtures and fail-closed tests; preserve REQUIRE_SIMULATION |
| SWAP_LIVE_GATE | BLOCKED; equivalence NOT_VERIFIED | Exact-transaction simulation is documented; no worker/gateway equivalence proven | Actual SWAP payload, simulation and fingerprint binding, wallet/risk/approval controls, non-capital reconciliation evidence |
| RFQ_LIVE_GATE | BLOCKED; settlement equivalence NOT_VERIFIED | Read-only RFQ quotes/proposals remain possible when their data dependencies work; no final settlement simulation claim | G01 exact-settlement evidence; all shared LIVE controls |
| AGENTIC_WALLET_LIVE_GATE | BLOCKED; runtime integration NOT_VERIFIED | Read-only runtime inspection blocked by missing CLI/skills; no settings or connection changed | Compatible installed runtime, user-controlled connection, worker access, session/quota/confirmation and exact-call safety evidence |

An RFQ failure does not mean DATA or DRY_RUN is impossible. Conversely, feasibility is not a runtime gate pass. The master section 12.3 explicitly allows reads and dry-run route construction while RFQ LIVE is disabled; sections 47/49 and 83G retain simulation and equivalence obligations. No public or worker LIVE capability is ready.

## F. Blocker ledger

Each row retains the original gap and records the attempt, evidence, disposition and phase effects. Phase 1 was not run; the amended Phase 0 development gate now passes. LIVE gaps remain critical to the affected capability and do not block safe non-live foundation work. Later-phase impact refers to the affected feature, not a claim that every other feature is impossible.

| Gap / original blocker | Verification attempted / exact evidence | Current conclusion | Safe now | Remains disabled | Dependency required | Phase 1 impact | Later phases impact | LIVE impact |
|---|---|---|---|---|---|---|---|---|
| G01 RFQ settlement equivalence | Official Trading/Transaction/external-sign rereview, section D; no settlement fixture | NOT_VERIFIED | Documentation, proposals; future authenticated reads | RFQ signatures/submission | Official exact-settlement safety contract + non-capital proof | Does not block non-live foundation; RFQ LIVE BLOCKED | RFQ execution path blocked; independent data/dry-run still feasible | RFQ DISABLED |
| G02 Missing wallet runtime | PATH lookup null, npm package absent, bounded skill inventory empty, section C | UNAVAILABLE here | Runtime/dependency documentation | All wallet writes | @binance/agentic-wallet compatible with current skill; user connection; worker session | Non-live foundation/mocks may proceed; wallet LIVE BLOCKED | Wallet integration and equivalence tests pending | Wallet LIVE DISABLED |
| G03 Massive entitlements/freshness | Original official contracts retained; no Massive account response added | NOT_VERIFIED | Provider design and labeled future demo | Freshness-dependent real decisions | Account plan/access + sanitized quote/history/news responses | Data assumptions remain unresolved | Independent-price trust cannot claim live readiness | Action dependent on real prices blocked |
| G04 Complete schema snapshot | Prior WAF/empty download evidence retained; no full snapshot obtained in remediation | PARTIAL | Linked contract review | Claim of exhaustive schema verification | Nonempty official schema/hash + endpoint comparison | Adapter contracts require completion | Integration contract verification pending | No schema-only LIVE claim |
| G05 Full stock research tables | No new manuscript supplied; prior abstract evidence retained | PARTIAL | Qualitative research mapping | Unverified coefficients/table claims | Full current author/SSRN manuscript | No numerical claims justified | Research validation pending | Research cannot substitute for safety |
| G06 Historical exchange calendar | Prior upcoming-only limitation retained; no historical source fixture | NOT_VERIFIED | Calendar provenance planning | Weekday-only session inference | Versioned historical schedule/DST/early-close data | Future calendar implementation needs source | Historical replay/session tests blocked | Unknown regime fails closed |
| G07 Decimal/statistical boundary | Master precision/equivalence requirements reread; no model execution | UNRESOLVED | Exact financial-value design | Silent float exception | Conforming numeric plan + precision tests; explicit spec decision if needed | Numeric design gap remains | Baselines/calibration require validated boundary | Unverified numbers cannot authorize trade |
| G08 Master path / absent uploads | Raw copy + equality + matching hashes, section A; upload artifacts still absent | MASTER PATH RESOLVED; uploads NOT AVAILABLE | Read canonical docs path | Fabricated proposal/schema comparison | Missing proposal/schema artifacts if comparison required | Location corrected; development may proceed | Comparison coverage remains partial | Copy gives no execution authority |
| G09 Historical coverage/baselines | Historical coverage and episode fixtures not measured; source entitlements unverified | NOT_VERIFIED | Planning; future provisional labels | Claimed calibrated opportunity LIVE | History availability, source timing, adequate issuer/regime samples | Foundation feasibility separate from calibration | Baseline/episode qualification pending | Insufficient data fails closed |
| G10 Runtime token/issuer/funding restrictions | Ten successful reads, including RWA universe, funding metadata and standard quote; no RWA signer/fixture | PARTIALLY VERIFIED; RWA execution eligibility NOT_VERIFIED | Official metadata contract analysis | Claimed tradable routes/contracts | Authenticated discovery + decimals/ratio/status/quote fixtures | No runtime trading assumption justified | Resolution/route integration pending | Unknown route eligibility blocks |
| G11 Optional services unspecified | No optional provider selected | DEFERRED | Document optional boundaries | Invented service support | Official contracts when selected | Does not require optional implementation now | Optional integrations deferred | No optional LIVE capability |
| G12 Confirmation/autonomy mismatch | External-sign requires explicit confirmation; no runtime policy evidence | UNRESOLVED | PROPOSE_ONLY design | Unattended external signing bypass | Supported user-confirmation/policy flow + tests | Gateway policy design incomplete | Autonomous mode not verified | No unattended LIVE claim |
| G13 Binance credentials/entitlements | User configured .env; ten signed reads returned HTTP200/code0, section B and evidence JSON | CREDENTIAL AVAILABILITY/AUTHENTICATION RESOLVED; measured reads VERIFIED; untested permissions UNKNOWN | Verified reads within measured scope | Unverified build/simulation/wallet-specific capabilities and all LIVE writes | Actual signer/non-capital fixtures; operation-specific access evidence | Credential blocker closed; development PASS; LIVE blockers remain | Measured data integration feasible; full pipeline pending | Reads do not establish LIVE execution |

## G. Amended development decision and stop

**PHASE 0 DEVELOPMENT GATE = PASS. Phase 1 MAY BEGIN in DEMO/DRY_RUN.** DATA_GATE=PASS; DRY_RUN_GATE=NOT_YET_TESTED; SWAP_LIVE_GATE=BLOCKED; RFQ_LIVE_GATE=BLOCKED; AGENTIC_WALLET_LIVE_GATE=BLOCKED. No factual execution ambiguity has been falsely closed. The prior Phase 0.1 advancement refusal is superseded by the user's explicit phase-gate amendment.

Phases 1–7 may develop non-live functionality. Phase 8 may develop only safety/execution infrastructure and DRY_RUN, with no live submission. Phase 9 may develop wallet abstractions, mocks, read-only integration and verified interfaces; its LIVE execution stays blocked. Existing per-phase correctness, risk, simulation, wallet, confirmation, equivalence, RFQ and fail-closed requirements remain. The ledger's precision/source/history/interface gaps still must be addressed before the affected feature can claim readiness; they do not prevent unrelated safe foundation work.

While LIVE is blocked, DATA_MODE=DEMO or LIVE_READ_ONLY, EXECUTION_MODE=DRY_RUN, APPROVAL_MODE=PROPOSE_ONLY, LIVE_TRADING_ENABLED=false and REQUIRE_SIMULATION=true. No broadcasts, RFQ submissions, wallet-setting changes, fund movements or real positions are permitted. [EXECUTION_GATES.md](EXECUTION_GATES.md) defines prerequisites/evidence, safe DRY_RUN scope and what each gate unlocks.

Missing CLI/runtime, worker/gateway, RFQ settlement proof and data/schema/precision/history dependencies remain recorded in the ledger. They were not installed, tested or resolved by this amendment. **LIVE execution MUST NOT begin. STOP after the gate amendment; no Phase 1 implementation in this task.**
