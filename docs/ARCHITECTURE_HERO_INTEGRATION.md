# Overview architectural background

Visual increment verified on October 11, 2026 (Asia/Kolkata).

The supplied `frontend/background.jpg` was moved, byte-for-byte unchanged, to
`frontend/src/assets/parity-pulse-architecture.jpg` (1376 × 768, 165,086 bytes).
Vite resolves the stylesheet's local asset URL and emits a hashed production
asset. There are no external image requests, new dependencies or duplicate
image assets.

Only `frontend/src/styles.css` changes application presentation in this
increment. The overview hero uses decorative CSS layers: the original image,
a left-to-right dark emerald overlay, and a top/bottom fade. The observation
panel uses a nearly opaque fallback and a slightly translucent background with
4px blur where supported. Tablet/mobile positions and stronger overlays retain
the existing hero sizing and responsive layout. Other routes, analytical
surfaces, navigation, amber warnings, and product behavior are unchanged.

## Validation

- Inspected the actual Vite development page at `http://127.0.0.1:5173/#overview`
  in Chrome at 1440 × 1100, 768 × 1024, and 390 × 844. Visually reviewed all
  three screenshots plus the full mobile hero. Verified image loading, readable
  headline/panel, bottom transition, no page overflow, and no hero on Markets.
- The development backend was unavailable. The existing amber warning and
  Unknown/Awaiting verification states remained visible; no healthy state or
  financial values were substituted.
- `npm test`: 282 tests passed across 15 files.
- `npm run build`: TypeScript and Vite passed; the original JPG is bundled once.
- `.venv/bin/ruff check backend scripts`: passed. There is no separate frontend
  lint script configured.
- `.venv/bin/python scripts/check-security.py`: passed.
- `.venv/bin/python scripts/verify-frontend-phase15.py`: browser assertions
  passed against disposable credential-free fixture backends, including six
  scenario runs and 188 local API requests; zero live execution calls and zero
  production Trust calls from the demo flow.
- `git diff --check`: passed. File fingerprints confirm all unrelated
  pre-existing work was preserved and the image bytes match the original.

Evidence: `docs/evidence/ARCHITECTURE_HERO_*_20261011.png`,
`ARCHITECTURE_HERO_BROWSER_20261011.json`, and
`ARCHITECTURE_HERO_REGRESSION_20261011.json`.

No backend, API, provider, financial logic, execution configuration or gate
changes. No commit or push.
