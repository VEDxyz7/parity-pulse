# Phase 1 post-gate debug — backend startup

Date: 2026-10-06. **PHASE: 1 POST-GATE DEBUG. STATUS: PASS.**

## Port conflict and action

`lsof -nP -iTCP:8000 -sTCP:LISTEN` identified Python PID **83166**, listening on `127.0.0.1:8000`. Process inspection confirmed the exact Parity Pulse Uvicorn command and working directory `/Users/vedparikh/Desktop/Parity Pulse`. This was the previous verification instance, not an unrelated service. SIGTERM was sent only to that confirmed PID. Its logs recorded `APP_STOPPED`, completed shutdown and process exit; a subsequent listener check found port 8000 free.

The canonical backend command was then run from the repository root:

```sh
.venv/bin/python -m uvicorn app.main:create_app --factory \
  --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
```

**BACKEND COMMAND: PASS.** New PID **86726** started with database connected, completed startup and bound port 8000. Later listener/process checks confirmed it remained running. No application code, API, port or architecture changes were needed.

From a separate process:

| Direct GET endpoint | Result |
|---|---|
| http://127.0.0.1:8000/api/health | PASS — HTTP 200; status ok; database connected |
| http://127.0.0.1:8000/api/system-status | PASS — HTTP 200; development, DEMO, DRY_RUN, PROPOSE_ONLY, live disabled, simulation required |

Both responses referred to the same new application run. No external business API or wallet was accessed.

## Frontend command and load

The root `package.json` defines `dev` as `npm run dev --workspace frontend`; `frontend/package.json` starts Vite on loopback port 5173. The documented working directory and command are correct:

```sh
cd "/Users/vedparikh/Desktop/Parity Pulse"
npm run dev
```

The previous Vite listener, PID **82587**, was independently confirmed by command line and frontend working directory, then stopped with SIGTERM. The fresh root command started Vite successfully, with new listener PID **86767**.

**FRONTEND COMMAND: PASS. FRONTEND LOAD: PASS. URL: http://127.0.0.1:5173/.**

The running-service integration check verified the HTML shell, Vite proxy, healthy API responses and correlation IDs. An isolated headless Chrome profile also loaded the actual frontend modules, rendered React and displayed backend connected, DEMO and DRY RUN. It verified DATA pass, DRY_RUN not yet tested and all three LIVE gates blocked, with no backend-unavailable alert. The disposable browser profile and probe processes were cleaned up.

An initial Chrome DOM-dump probe timed out; a debugging-interface probe then rendered the page, but its case-sensitive gate-label assertion failed. The assertion was corrected to normalize displayed text, and the final browser verification passed. Neither diagnostic failure required an application change. No browser dependency was added to the project.

## Tests and checks

| Command/check | Final result |
|---|---|
| .venv/bin/python -m pytest --cov=app --cov-report=term-missing | 34 PASSED; 0 FAILED; 98% application coverage |
| npm test | 14 PASSED; 0 FAILED |
| npm run build | PASS — TypeScript noEmit and Vite production build |
| .venv/bin/ruff check backend scripts | PASS |
| .venv/bin/ruff format --check backend scripts | PASS |
| npm run test:integration | PASS |
| Direct backend endpoint checks from another process | PASS |
| Headless Chrome rendered-frontend verification | PASS |

**Tests passed: 48. Final tests failed: 0.** The canonical startup commands and runtime checks passed. Phase 1 gate: **PASS**.

## Files changed

- `README.md`: explain duplicate development listeners, identity checks and the canonical root frontend command.
- `docs/PHASE_1_REPORT.md`: add the post-gate verification result.
- `docs/PHASE_1_POST_GATE_DEBUG.md`: this report.

No application, configuration, dependency or master specification files were changed for this task.

## Known limitations

The existing upstream Starlette TestClient deprecation warning remains; all tests pass. Docker execution remains unverified because Docker is unavailable. Headless browser loading/rendering is verified, but native interactive visual review, screenshots and mobile layout review remain unverified.

The restarted backend and frontend are intentionally left running. Do not launch duplicate instances while these PIDs occupy their ports; stop the confirmed instances first when a fresh launch is needed. PIDs are point-in-time evidence, so inspect the current listener again before future termination.

## Current execution gates and next phase

```text
DATA_GATE = PASS
DRY_RUN_GATE = NOT_YET_TESTED
SWAP_LIVE_GATE = BLOCKED
RFQ_LIVE_GATE = BLOCKED
AGENTIC_WALLET_LIVE_GATE = BLOCKED
```

**NEXT PHASE: PHASE 2 — DATA LAYER. NOT STARTED.** Stop after the Phase 1 debug verification. LIVE execution remains blocked.
