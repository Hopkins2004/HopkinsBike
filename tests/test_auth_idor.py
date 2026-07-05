"""Auth + IDOR behaviour tests (Phase 5).

Run against an isolated temp DB so the real data/ is untouched. Verifies:
  - anonymous requests to data routes redirect to /login (not 500);
  - a logged-in user cannot reach another user's route/activity via a crafted q token.
"""
from hopkins.db import get_db
from hopkins.web.util import encode_q


def _register_and_id(app, client, email):
    """Claude__register_and_id: register a user and return their id_user."""
    client.post("/register", data={"email": email, "password": "password123"})
    with app.app_context():
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id_user FROM users WHERE email = ?", (email,))
            return cur.fetchone()[0]


def test_anonymous_redirects_to_login(client):
    for path in ["/history", "/routes", "/upload"]:
        r = client.get(path)
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/login")


def test_cross_user_route_blocked(app, client):
    a_id = _register_and_id(app, client, "a@x.com")
    b_id = _register_and_id(app, client, "b@x.com")

    # B owns a route
    with app.app_context():
        with get_db() as conn:
            conn.execute("INSERT INTO gpx (id_user, title) VALUES (?, ?)", (b_id, "secret"))
            conn.commit()
            rid = conn.execute("SELECT id_route FROM gpx WHERE id_user = ?", (b_id,)).fetchone()[0]

    # A logs in and forges a q token pointing at B's route
    client.post("/login", data={"email": "a@x.com", "password": "password123"})
    forged = encode_q(0, 0, f"{b_id},{rid}")
    r = client.get("/view_route?q=" + forged)
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/routes")  # blocked, not served


def test_cross_user_segment_delete_blocked(app, client):
    a_id = _register_and_id(app, client, "a@x.com")
    b_id = _register_and_id(app, client, "b@x.com")

    # B owns an activity + a segment on it
    with app.app_context():
        with get_db() as conn:
            conn.execute("INSERT INTO files (id_user, title) VALUES (?, ?)", (b_id, "act"))
            conn.commit()
            fid = conn.execute("SELECT id_analysis FROM files WHERE id_user = ?", (b_id,)).fetchone()[0]
            conn.execute("INSERT INTO segments (id_analysis, start_pt, end_pt) VALUES (?, 0, 1)", (fid,))
            conn.commit()
            sid = conn.execute("SELECT id_segments FROM segments WHERE id_analysis = ?", (fid,)).fetchone()[0]

    client.post("/login", data={"email": "a@x.com", "password": "password123"})
    r = client.post("/delete_segment", data={"supression": str(sid)})
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/history")  # blocked

    # segment still exists
    with app.app_context():
        with get_db() as conn:
            still = conn.execute("SELECT 1 FROM segments WHERE id_segments = ?", (sid,)).fetchone()
    assert still is not None
