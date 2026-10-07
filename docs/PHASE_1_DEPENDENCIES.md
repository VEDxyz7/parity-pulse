# Phase 1 resolved dependencies

Verified 2026-10-06 on Python 3.12.10 / Node 24.12.0. Direct dependencies are pinned; runtime/development Python transitive pins are in requirements.txt / requirements-dev.txt, npm transitive pins in package-lock.json. Future analytics/trading packages are not installed in Phase 1.

## Python direct dependencies

| Package | Version | Distribution license metadata |
|---|---|---|
| fastapi | 0.142.2 | MIT |
| pydantic | 2.13.5 | MIT |
| pydantic-settings | 2.15.0 | MIT |
| SQLAlchemy | 2.1.3 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| httpx | 0.28.1 | BSD-3-Clause |
| pytest | 9.1.1 | MIT |
| pytest-cov | 7.1.0 | MIT |
| ruff | 0.16.10 | MIT |

## npm direct dependencies

| Package | Version | Distribution license metadata |
|---|---|---|
| @tailwindcss/vite | 4.3.3 | MIT |
| @tanstack/react-query | 5.104.1 | MIT |
| @testing-library/jest-dom | 7.0.1 | MIT |
| @testing-library/react | 16.3.3 | MIT |
| @testing-library/user-event | 14.6.7 | MIT |
| @types/react | 19.3.0 | MIT |
| @types/react-dom | 19.3.0 | MIT |
| @vitejs/plugin-react | 6.1.2 | MIT |
| jsdom | 27.4.0 | MIT |
| lucide-react | 1.52.0 | ISC |
| react | 19.3.0 | MIT |
| react-dom | 19.3.0 | MIT |
| tailwindcss | 4.3.3 | MIT |
| typescript | 7.0.2 | Apache-2.0 |
| vite | 8.3.3 | MIT |
| vitest | 5.0.3 | MIT |

These are declared package licenses, not a legal audit. Installation peer/requirement checks passed; absent OS-specific optional binaries on macOS are expected. Docker Linux resolution/build is not verified here.

Compatibility correction: jsdom30 required a newer Node minor than the installed24.12; jsdom27.4.0 is pinned at the workspace root so the hoisted Vitest runner resolves it correctly. All frontend tests/build pass. An upstream Starlette1.7 TestClient warning recommends httpx2; the current pinned httpx-backed API tests remain supported and pass.


## Phase 2 runtime dependency amendment

Phase1 records above are historical. Existing pinned httpx0.28.1 is now a runtime dependency for bounded read-only clients; certifi/httpcore/httpx moved into requirements.txt and redundant dev entries were removed. No additional package installation or frontend dependency change was needed. pip check, Ruff, TypeScript/Vite and regression tests passed. No wallet, execution, LLM or statistical package was added.
