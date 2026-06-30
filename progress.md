# Progress Log

## Refactor: address after.txt (structural audit) — 2026-06-30

**Goal:** apply every issue flagged in `after.txt` via a full package split
(after.txt §1 layout) + the auth/IDOR security fixes (§4), while keeping all
**legitimate** user-facing functionality byte-identical. Only anonymous/forged
requests may behave differently (that is the security fix).

**How "no functionality change" is proven**
- `tests/test_physics_golden.py` — 13 physics functions vs values captured from the
  ORIGINAL app.py (`tests/fixtures/golden.json`).
- `tests/test_urlmap.py` — exposed URL rules + methods vs the original 32-rule snapshot
  (`tests/fixtures/urlmap.json`). Endpoint *names* may change (blueprints prefix them);
  URL paths + methods must not.
- End-to-end Playwright: guest pages + register→login→/history + a synthetic-GPX
  route flow (`/view_route` → `/calculate_route` → `/toptube_pdf`).

**Known verification limitation:** `templates/uploads/` has no `.fit`/`.gpx` files on
disk (DB references activities/routes whose files are gone), so the activity (`.fit`)
web flows cannot be driven live. They are covered by the physics golden tests +
route-trace review. The GPX route flow IS driven live with a synthetic GPX.

---

### Phase 0 — Safety net ✅
- Captured golden physics values from the current monolith into
  `tests/fixtures/golden.json`; captured the 32-rule URL map into
  `tests/fixtures/urlmap.json`; built a deterministic `tests/fixtures/synthetic.gpx`.
- Wrote `tests/test_physics_golden.py` + `tests/test_urlmap.py`. **14 passed** against
  the unmodified `app.py`.
- Added `pytest>=8.0` to requirements; added `.gitignore`.
- `git init` + initial commit of the current state, then a working branch for the refactor.
