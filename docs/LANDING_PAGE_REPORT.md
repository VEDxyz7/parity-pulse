# Cinematic paper entrance

Implemented in the existing React/Vite frontend. The root URL opens a near-black,
emerald paper scene with atmospheric PARITY PULSE typography. Pointer movement changes
lighting; dragging bends the viewing angle with bounded, damped settling. Touch permits
horizontal manipulation and ordinary vertical scrolling. The reference's paper technique
is adapted, with original Parity Pulse print artwork and no financial observations.

## Integration and rendering

`LandingEntrance` surrounds the existing workspace selected by `main.tsx`. The workspace
and QueryClient remain single instances throughout entry, scroll, back and forward.
The entrance occupies roughly one viewport (600px minimum on short screens); scrolling
recedes the mesh, fades and moves the typography/copy, and reveals the real workspace
below. At completion the existing `#overview` route takes over. The entry action skips
the reveal immediately. Hash routes, refreshes and `?workspace=verified` bypass the
entrance, including older provider/demo routes. Keyboard entry focuses the dashboard
heading; returning to the entrance focuses its entry action.

The renderer uses a subdivided plane, arc-length-preserving bend shader with derived
normals, a local CanvasTexture for print/double borders, Fresnel edges, grain and two
pointer-sensitive specular reflections. Motion, projection, lighting and scroll progress
live outside React's render cycle. The renderer is a separate dynamic chunk, requested
only by the entrance when motion is permitted. StrictMode replay shares the module
request and abandons obsolete initializations.

Native passive scroll plus one coalesced animation frame is sufficient for this short
reveal; no wheel interception, scroll lock, GSAP, animation framework or iframe is added.
All CSS is scoped to the entrance. The dashboard's existing components, data, routes,
financial calculations and backend are unchanged.

The renderer caps DPR at 1.75 desktop / 1.25 mobile and uses fewer mobile vertices and
a smaller print texture. It pauses on document visibility and intersection changes,
handles resize/orientation, removes event listeners/observers and pointer capture, cancels
owned frames, and disposes geometry, texture, shader and renderer/context on teardown.
Initialization, shader or context failure retains the static branded fallback and entry
action. Reduced motion loads no renderer and shows that fallback immediately.

## Dependencies and reference review

Added exactly `three@0.186.1` and development declarations `@types/three@0.186.0`;
lockfile updated. `npm ls three --all` confirms one runtime Three.js version.
[Three.js metadata](https://registry.npmjs.org/three/0.186.1) declares MIT licensing.

Before installation, `npm view @designcodeio/threeui version license peerDependencies
dependencies dist.unpackedSize --json` reported version 1.2.0, MIT, React 18–19 support,
and two additional aliases for Three.js r128/r165, with approximately 54.7MB unpacked.
The supplied `ThreeDPaper.tsx` wraps bundled standalone pages in an iframe. A native,
managed renderer avoids those versions, iframe boundaries and vendored library copies.
[ThreeUI metadata](https://registry.npmjs.org/@designcodeio%2fthreeui/1.2.0).

The supplied Original HTML/GLSL/print and React wrapper were inspected. Its integration
and lifecycle were adapted rather than embedded. The actual
[Taste Skill](https://github.com/Leonxlnx/taste-skill/blob/main/skills/taste-skill/SKILL.md)
was consulted as supplementary guidance: one focal object, restrained composition,
consistent identity and motivated motion. The user's explicit composition and existing
dashboard take precedence over generic defaults. No stock imagery or generated financial
charts are added; the engraved line on the paper is decorative.

## Verification

- Backend: **1,768 passed**. Two existing serializer warnings from negative `postAmount`
  fixtures. No backend source or production database was changed by this task.
- Frontend: **304 passed**, including 12 new tests for navigation/state preservation,
  direct routes, native scroll completion, renderer lifecycle, StrictMode replay,
  reduced-motion changes, unavailable WebGL and obsolete asynchronous initialization.
- Type checking and production build: **PASS**. Ruff, secret/isolation security check,
  generated UI contracts (11) and Git whitespace check: **PASS**.
- Full existing provider browser regression: **PASS**, 189 local API requests, zero
  production Trust calls from Demo Sandbox and zero live execution calls.
- Existing scenario product browser regression: **PASS**, desktop/mobile, 15 requests,
  market search, routes, scan/proposal, Research assumptions, portfolio, scorecard and refresh.
- Final landing browser: **PASS**, six viewports: 1440×1000, 820×1180, 390×844,
  375×667, 320×568 and 844×390. Actual WebGL rendering, mouse hover/drag, touch drag and
  touch scrolling, intermediate scroll screenshots, keyboard entry, one dashboard instance,
  back/forward, deep-link refresh and optional-chunk bypass were checked.
- Reduced-motion preference, document visibility pause/resume, real context loss and
  forced WebGL unavailability all preserve usable navigation. Zero console errors,
  HTTP asset failures or external browser requests in the final browser run.
- Desktop, mobile, compact-mobile, tablet, landscape, intermediate reveal and static
  fallback screenshots were visually reviewed. Fixed a missing favicon, short-phone
  hint crowding and compact-phone paper/copy spacing found during verification.
- Existing Vite server at `127.0.0.1:5173` serves the root and new source modules with
  HTTP 200. Running backend status remains `DRY_RUN`, `live_trading_enabled=false`.
  Both existing development processes were preserved; only owned fixture servers stopped.

Machine-readable results and preservation comparison:
[LANDING_VERIFICATION.json](evidence/LANDING_VERIFICATION.json).
Saved final [desktop](evidence/landing-desktop.png) and [mobile](evidence/landing-mobile.png)
screenshots. The JSON records retained temporary directories containing the full set
of intermediate, interaction and fallback screenshots and original browser evidence.

### Reproduction from repository root

```sh
npm test
npm run build
.venv/bin/python -m pytest backend/tests -q
.venv/bin/ruff check backend scripts
.venv/bin/python scripts/check-security.py
PYTHONPATH=backend .venv/bin/python scripts/generate-ui-contracts.py --check
.venv/bin/python scripts/verify-frontend-phase15.py
```

For just the new browser checks after building:

```sh
.venv/bin/python scripts/verify-frontend-phase15.py --landing-only
```

Chrome must be installed; ports 8054–8057/5178 must be free. The runner supplies only
credential-free fixture APIs, refuses occupied ports and shuts down its own processes.
For interactive review, retain/run the canonical backend and `npm run dev`, then open
`http://127.0.0.1:5173/`. Direct dashboard: `http://127.0.0.1:5173/#overview`.

## Files changed in this task

Modified:

- `frontend/src/main.tsx` — entrance wrapper around the same workspace instance.
- `frontend/index.html` — local favicon reference, eliminating the asset 404.
- `frontend/package.json`, `package-lock.json` — pinned Three.js and types.
- `scripts/verify-frontend-phase15.py` — adds landing checks and `--landing-only`.
- `README.md` — documents the entrance and preserved direct routes.

Created:

- `frontend/src/landing/LandingEntrance.tsx`
- `frontend/src/landing/PaperScene.tsx`
- `frontend/src/landing/paperRenderer.ts`
- `frontend/src/landing/paperShaders.ts`
- `frontend/src/landing/paperTexture.ts`
- `frontend/src/landing/landing.css`
- `frontend/public/parity-mark.svg`
- `frontend/src/test/LandingEntrance.test.tsx`
- `scripts/check-landing-browser.mjs`
- `docs/LANDING_PAGE_REPORT.md`
- `docs/evidence/LANDING_VERIFICATION.json`
- `docs/evidence/landing-desktop.png`
- `docs/evidence/landing-mobile.png`

## Limits and preserved controls

Chromium was tested with software WebGL2/SwiftShader for repeatable renderer availability.
Physical-device GPU/battery measurements, Safari and Firefox were not performed. No
remaining visual/navigation defect was observed in the tested views. Vite retains the
pre-existing large-entry warning (~848KB minified); the optional renderer also exceeds
the 500KB warning (~530KB minified / ~133KB gzip). It is not requested on direct
dashboard routes or reduced motion. No build warning was suppressed.

All pre-existing backend, gate, schema, provider and dashboard files remain byte-for-byte
unchanged from this task's start. Existing dirty work was preserved; only the six
explicitly listed pre-existing integration/documentation files changed. Branch/HEAD
remain unchanged. No stash, reset, commit, push or merge was performed.

DATA_GATE=PASS; DRY_RUN_GATE=PASS; TRUST_GATE=BLOCKED;
OPPORTUNITY_GATE=BLOCKED_BY_TRUST; SWAP_LIVE_GATE=BLOCKED;
RFQ_LIVE_GATE=BLOCKED; AGENTIC_WALLET_LIVE_GATE=BLOCKED.
No execution, signing, wallet, RFQ submission, provider verification or external market
request was performed. The entrance contains no invented market prices or performance claims.
