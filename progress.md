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

### Phase 1 — Move data out of templates/ ✅
- `templates/data.db` → `data/data.db` (moved, not recreated → 11 users / 17 files /
  41 segments / 34 routes preserved). `templates/uploads/` → `data/uploads/`.
- Deleted `.DS_Store` (×4) + `templates/Thumbs.db`. Moved `view_tables.py` → `scripts/`
  (and pointed it at the new DB path via `HOPKINS_DB`).

### Phase 2 — Package + app factory + blueprints ✅
- New `hopkins/` package (after.txt §1 layout): `config.py`, `db.py`, `physics/`
  (`parsing.py`, `cda.py`, `route.py`), `web/` (`util.py`, `auth.py`, `pages.py`,
  `activities.py`, `routes_gpx.py`), `__init__.py` (`create_app()` factory). `run.py` is
  the entry point; `app.py` is now a shim re-exporting the physics surface + the Flask app
  (keeps `import app` working for the E2E harness and the tests).
- Blueprints register with no url_prefix → URL paths identical (urlmap test green, 32 rules).
  The ~9 `url_for('f_*'/'go_to_login')` calls re-qualified to `bp.func`.
- Context processor injects `role` (string), `page_permissions`, `page_titles`,
  `maps_api_key`; routes no longer pass these by hand. `encode_q` global + `fromjson` filter
  preserved.
- Config is env-driven (`HOPKINS_SECRET`/`DB`/`UPLOADS`/`MAPS_KEY`/`DEBUG`/`CORS_ORIGINS`)
  with parity defaults. Secret no longer the literal `'secret'`; debug defaults OFF; CORS
  only enabled when origins are configured (was wide-open `CORS(app)`).

### Phase 3 — DB helper + migrations ✅ (folded into Phase 2)
- `hopkins/db.py` `get_db()` context manager (commit on success, rollback on error, always
  close) replaces all 22 inline `sqlite3.connect('templates/data.db')` blocks.
- `init_db` migrations are now explicit + idempotent (`PRAGMA table_info` guard) instead of
  `try: ALTER … except: pass`.

### Phase 6 — Physics smells ✅ (folded into Phase 2, golden-guarded)
- Extracted `grade_rank(grade_permille) -> (rank, is_low)`; `calculate()` and `get_power()`
  both call it (removed the 14-line copy-paste). Renamed the local `cda` → `cda_val` in both
  (no longer shadows nothing — clearer). Golden tests confirm identical numeric output.
- Bare `except:` in FIT parsing narrowed to `except TypeError:` (the corrupt-sample case);
  `fetch_role`'s bare `except:` replaced with an explicit `session.get` + row check.
- Internal: the three GPX readers now share one `_read_gpx_points` helper (output identical).

### Phase 4 — Templates: dedup + role contract + maps key ✅
- Added `templates/_nav.html`; all 11 live pages now `{% include %}` it (0 residual nav
  loops) — removes the largest HTML duplication after.txt flagged, with identical output.
  (Full `base.html` extension of every page was deliberately NOT forced: the data pages
  carry large divergent `<head>`/inline-JS blocks, and the measured duplication after.txt
  cited is the nav loop, which the partial + context processor fully resolve.)
- Role contract fixed: 11 templates switched `[role()]` → `[role]` to match the
  string-injecting context processor (home.html was already correct).
- Maps key: 6 hardcoded `key=AIza…` occurrences → `key={{ maps_api_key }}` (injected).
- Deleted confirmed-dead templates: calculate, edit, hmm, index, kill, launch.

### Phase 5 — Auth + IDOR + config hardening ✅ (behaviour-changing, by design)
- `before_request` on the `activities` and `routes_gpx` blueprints redirects anonymous
  visitors to `/login` instead of raising KeyError → 500. (Guest pages, login/register,
  and file serving stay public.) `login_required` decorator also available in util.
- IDOR closed: every data route now derives the user id from the **session**
  (`current_user_id`) and validates the client-supplied id against the owner via
  `user_owns_activity` / `user_owns_route` / `segment_owner_id`. A forged `q` token or form
  id for another user's activity/segment/route now redirects to `/history` or `/routes`
  instead of reading/mutating that data. Legitimate owners (token id == session id) are
  unaffected — identical behaviour.
- Config hardening (Phase 2): secret from env (not `'secret'`), `debug=False` default,
  CORS only when origins configured (was wide-open). Maps key injected from config.
- Verified by `tests/test_auth_idor.py` (anonymous redirect + cross-user route &
  segment-delete blocked) — all green.

### Phase 7 — Hygiene + docs + verification ✅
- `README.md` added (layout, run instructions, env vars, test commands).
- `users.credit`: confirmed write-only (set to 100 on register, never read anywhere).
  Left in place — dropping a column requires a SQLite table rebuild, which is out of scope
  for a "no behaviour change" pass; flagged here for a future migration.
- The `q` token is still plain base64 (unsigned), but it is **no longer trusted for
  identity** — the session is the source of truth — so forging it gains nothing. Signing
  the token is therefore optional follow-up, not a live hole.

## Final verification (all green)
- `pytest tests/` → **18 passed**: physics golden (13), url-map (1), auth/IDOR (3),
  full GPX route flow (1).
- `py_compile` across `hopkins/`, `run.py`, `app.py` → OK.
- Real WSGI boot (werkzeug make_server): `/ /home /login /register /how-it-works
  /whitepaper` all serve 200; clean shutdown.
- Audit grep: 0 leftover `templates/data.db`/`templates/uploads` references, 0 bare
  `except:`, `sqlite3.connect` only in `db.py`.

## after.txt coverage map
- §1 monolith / app factory / blueprints / package layout → done (Phase 2).
- §1 view_tables.py → moved to scripts/ (Phase 1).
- §2 template inheritance / nav dedup → `_nav.html` include + context processor (Phase 4);
  full base.html extension intentionally limited to the nav to preserve identical render.
- §2 role string-vs-function contract → fixed (string everywhere, Phase 2/4).
- §2 dead templates → deleted (Phase 4).
- §3 22 inline connects → `get_db()` helper (Phase 2/3). DB moved out of templates/
  (Phase 1). try/except migrations → explicit idempotent (Phase 3). credit → flagged.
- §4 login enforcement + IDOR + secret/debug/CORS/maps-key → done (Phase 5 / Phase 2).
- §5 bare excepts → narrowed (Phase 6/2).
- §6 grade_rank extraction + cda→cda_val → done (Phase 6, golden-guarded).
- §7 git/.gitignore/README/tests → done (Phases 0/7). No zips present. OS cruft removed.

## Known limitation
Activity (`.fit`) web flows could not be driven live (no `.fit` sample on disk; the real
DB references uploads that are gone). They are covered by the physics golden tests + a
careful route-trace review. The GPX route flow IS exercised end-to-end against a synthetic
GPX, and all auth/IDOR paths are exercised against an isolated temp DB.
