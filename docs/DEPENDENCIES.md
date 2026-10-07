# External dependency review — Phase 0

Checked 2026-10-06. No dependencies installed, manifests generated or application code written. Official documentation availability and intended capability were reviewed; this is not a resolved compatibility matrix or security certification.

## Service dependencies

| Dependency | Official evidence | Decision / unverified assumption |
|---|---|---|
| Binance signed Web3 APIs | [Authentication](https://web3.binance.com/en/dev-docs/authentication), [API schema](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/1.0.0/schema.json) | One client; keys/permissions/region/runtime responses untested |
| Agentic Wallet CLI and skills | [Skills Hub](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/SKILL.md) | Skill1.12.0 / requiredCLI1.10.0 observed; CLI unavailable; no install |
| Tokenized securities skill | [Official skill](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-tokenized-securities-info/SKILL.md) | Supplemental Ondo BAPI; different envelope and volume semantics |
| Massive/Polygon | [REST quickstart](https://massive.com/docs/rest), [Stocks overview](https://massive.com/docs/rest/stocks/overview) | Current base api.massive.com; account entitlements unavailable |
| Calendar | [Massive holidays](https://massive.com/docs/rest/stocks/market-operations/market-holidays), [NYSE schedules](https://www.nyse.com/trade/hours-calendars) | Upcoming alone insufficient for historical replay; versioned historical schedule required |
| News | [Massive news](https://massive.com/docs/rest/stocks/news) | Default selected; publication/first-seen provenance and actual coverage required |
| Earnings events | No provider selected in prompt | News/status is not complete forward earnings calendar; stronger policy or no action if event context unknown |
| LLM | Vendor/model deliberately unspecified by prompt | No vendor-specific endpoint invented; verify structured-output support, limits and auth upon selection |
| BSC chain/node | [Transaction API](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/transaction-api) | Chain56 must be in provider intersection; no independent RPC URL invented |
| Optional Agent Studio | Not selected | Phase18 only; no core dependency |
| Optional BTC/ETH | Not selected | No secondary trading subsystem |
| Optional MCP | [Current specification](https://modelcontextprotocol.io/specification/2026-07-28) | Phase14, same deterministic controls; no remote execution authority |

## Backend and tooling

| Dependency | Official docs reviewed | Phase 0 conclusion / future validation |
|---|---|---|
| Python3.12+ / Decimal | [decimal](https://docs.python.org/3.12/library/decimal.html) | Exact decimal arithmetic from strings; explicit rounding/traps; pin interpreter later |
| FastAPI | [Docs](https://fastapi.tiangolo.com/) | Supported backend framework; test chosen Python/Pydantic combination |
| Pydantic | [Current validation docs](https://docs.pydantic.dev/latest/) | Structured input/output validation; do not assume financial computation authority |
| SQLAlchemy | [2.0 docs](https://docs.sqlalchemy.org/en/20/) | ORM/session boundary; pin compatible release and transaction semantics |
| SQLite | [Types](https://sqlite.org/datatype3.html) | REAL is binary floating point; money text/scaled integer; check Decimal round trips |
| httpx | [Docs](https://www.python-httpx.org/) | Sync/async clients; strict timeouts; preserve signed raw serialization |
| pandas | [Docs](https://pandas.pydata.org/docs/) | Historical tabular analysis; no implicit float financial arithmetic |
| NumPy | [Docs](https://numpy.org/doc/stable/) | Numerical arrays; explicit precision boundary unresolved |
| SciPy | [Docs](https://docs.scipy.org/doc/scipy/) | Scientific routines; not inherently Decimal financial implementation |
| statsmodels | [Docs](https://www.statsmodels.org/stable/index.html) | OLS/robust models available; G07 precision contract must be resolved |
| tenacity | [Docs](https://tenacity.readthedocs.io/en/latest/) | Configure finite retries/backoff; default indefinite retry unsuitable |
| APScheduler | [Stable guide](https://apscheduler.readthedocs.io/en/stable/userguide.html) | Single scheduler owner; do not mix version-specific APIs; persistent recovery required |
| pytest | [Docs](https://docs.pytest.org/en/stable/) | Future test runner; no Phase0 application tests |
| Docker | [Docs](https://docs.docker.com/get-started/) | Public app isolation; authenticated CLI not silently embedded |

## Frontend

| Dependency | Official docs reviewed | Phase 0 conclusion / future validation |
|---|---|---|
| React | [Docs](https://react.dev/) | Component UI; no frontend financial authority |
| Vite | [Guide](https://vite.dev/guide/) | Verify Node engine for pinned release before Phase1 setup |
| TypeScript | [Docs](https://www.typescriptlang.org/docs/) | Static types do not replace backend validation |
| TailwindCSS | [Vite installation](https://tailwindcss.com/docs/installation/using-vite) | Follow selected major's current integration, not stale configuration recipes |
| Recharts | [Official site](https://recharts.org/en-US/) | Candidate charts; compatible React version and accessibility need implementation checks |
| Lucide | [React guide](https://lucide.dev/guide/packages/lucide-react) | Icon package available; no custom icon subsystem needed |
| TanStack Query | [React overview](https://tanstack.com/query/latest/docs/framework/react/overview) | Server-state cache; stale cached observations never authorize trades |
| SSE/WebSocket | Optional browser/backend transport, not chosen | Decide only when required; no Binance stream capability assumed |
| Browser E2E runner | Not specified / not selected | Choose during foundation; no test package installed |

## Version policy and compatibility gate

Do not pin “latest” from this review by assumption. Phase1 must resolve concrete Python/Node engines and exact direct/transitive versions, validate peer dependencies and supported APIs, record licenses and run required checks. There is no lockfile or install evidence today. Python3.12 is the minimum specification target, not proof that every future latest package supports it.

The numerical tension is material: statsmodels/NumPy commonly operate on floats, while the master requires Decimal/fixed-point for all financial values including expected edge and risk. Model estimates need an explicit policy and tests before they become authoritative. G07 remains open rather than introducing an unapproved exception.

## Phase 0.1 dependency state

Binance Web3 credentials are now configured locally and ten authenticated reads were verified; no credential values are retained here. Node v24.12.0 is present. The compatible Agentic Wallet CLI, installed Binance wallet/securities skills and connected user-controlled wallet/worker session remain unavailable or untested. Official installation and connection references, exact missing evidence and phase impacts are recorded in [PHASE_0_REMEDIATION.md](PHASE_0_REMEDIATION.md). No dependency was installed in this remediation.

## Phase 1 resolved foundation subset

The Phase 0 no-install statement above is historical. The subsequent foundation installed and pinned only the required backend/UI/test subset. See [PHASE_1_DEPENDENCIES.md](PHASE_1_DEPENDENCIES.md), root requirements.txt/requirements-dev.txt and package-lock.json for exact versions and declared licenses. Python dependency consistency, npm peer resolution,34 backend tests,14 frontend tests and the production build pass. Analytics, schedulers, external service clients and wallet runtimes remain deferred; no LIVE blocker was resolved. Docker runtime verification is unavailable here.
