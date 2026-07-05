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
| `HOPKINS_SECRET` | `REPLACE_WITH_FLASK_SECRET_KEY` | Flask session secret — **set a real value in production** |
| `HOPKINS_DB` | `data/data.db` | SQLite file path |
| `HOPKINS_UPLOADS` | `data/uploads` | uploaded FIT/GPX storage |
| `HOPKINS_MAPS_KEY` | `REPLACE_WITH_GOOGLE_MAPS_API_KEY` | Google Maps JS key — set & restrict by referrer in prod |
| `HOPKINS_DEBUG` | `0` | `1` enables the Werkzeug debugger (dev only) |
| `HOPKINS_CORS_ORIGINS` | (none) | comma-separated allowed CORS origins; empty = same-origin only |
| `HOPKINS_HTTPS` | `0` | `1` marks the session cookie Secure (set behind TLS) |
| `HOPKINS_GOOGLE_CLIENT_ID` | (none) | Google OAuth client ID — set with the secret to enable "Sign in with Google" |
| `HOPKINS_GOOGLE_CLIENT_SECRET` | (none) | Google OAuth client secret |

#### Enabling Google sign-in
1. [console.cloud.google.com](https://console.cloud.google.com) → create/select a project.
2. **APIs & Services → OAuth consent screen**: pick *External*, add app name + support email,
   and add your email as a *Test user* (keeps the app in testing mode — no verification needed).
3. **APIs & Services → Credentials → Create credentials → OAuth client ID → Web application**.
   - Authorised JavaScript origins: `http://127.0.0.1:5000` (add your prod origin too).
   - Authorised redirect URIs: `http://127.0.0.1:5000/login/google/callback` (and the prod
     equivalent, e.g. `https://your-domain/login/google/callback`).
4. Copy the client ID + secret into `HOPKINS_GOOGLE_CLIENT_ID` / `HOPKINS_GOOGLE_CLIENT_SECRET`
   and restart. The button appears automatically once both are set.

## Tests
```bash
.venv/bin/python -m pytest tests/
```
- `test_physics_golden.py` — engine outputs vs values captured from the original code.
- `test_urlmap.py` — the public URL/method surface is unchanged.
- `test_auth_idor.py` — login enforcement + cross-user access blocked.
- `test_route_flow.py` — register → login → view/estimate a GPX route end-to-end.
# HopkinsBike
