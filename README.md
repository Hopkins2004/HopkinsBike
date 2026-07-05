# Hopkins — bike aero analyser

Upload a `.fit` ride or a `.gpx` route. FIT rides are parsed, the GPS track is shown on a
map and the data is graphed; you select a section (or a lap) and measure its **CdA** from
power, speed and gradient. GPX routes are run through a power model to estimate finishing
time and a per-section power plan (and a printable top-tube card).

## Stack
Python / Flask, SQLite, server-rendered Jinja templates + JS, CSS.

## Layout
```
hopkins/                application package
  __init__.py           create_app() factory, context processor, blueprint registration
  config.py             env-driven configuration
  db.py                 get_db() connection helper + schema/migrations
  physics/
    parsing.py          FIT/GPX -> points / segments / elevation profile
    cda.py              segment CdA measurement
    route.py            route power model + Peucker-Douglas section splitter
  web/
    util.py             q-token, role/ownership helpers, login_required
    auth.py             login / register / logout            (blueprint)
    pages.py            home / explainer pages / file serving (blueprint)
    activities.py       FIT upload, history, visualise, segments, CdA (blueprint)
    routes_gpx.py       GPX routes, estimate, top-tube card   (blueprint)
templates/  static/     Jinja templates and assets
data/                   data.db + uploads/ (git-ignored runtime data)
scripts/view_tables.py  debug: dump the DB
tests/                  physics golden, url-map, auth/IDOR, route-flow
run.py                  dev entry point
```

## Run
```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py            # serves on http://127.0.0.1:5000
```

### Configuration (environment variables, all optional)
| var | default | purpose |
|-----|---------|---------|
| `HOPKINS_SECRET` | `dev-secret-change-me` | Flask session secret — **set a real value in production** |
| `HOPKINS_DB` | `data/data.db` | SQLite file path |
| `HOPKINS_UPLOADS` | `data/uploads` | uploaded FIT/GPX storage |
| `HOPKINS_MAPS_KEY` | (shipped key) | Google Maps JS key — set & restrict by referrer in prod |
| `HOPKINS_DEBUG` | `0` | `1` enables the Werkzeug debugger (dev only) |
| `HOPKINS_CORS_ORIGINS` | (none) | comma-separated allowed CORS origins; empty = same-origin only |

## Tests
```bash
.venv/bin/python -m pytest tests/
```
- `test_physics_golden.py` — engine outputs vs values captured from the original code.
- `test_urlmap.py` — the public URL/method surface is unchanged.
- `test_auth_idor.py` — login enforcement + cross-user access blocked.
- `test_route_flow.py` — register → login → view/estimate a GPX route end-to-end.
# HopkinsBike
