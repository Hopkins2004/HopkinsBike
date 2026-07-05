"""Regression tests for the pre-release hardening pass: CSRF, removed file-serving
routes, logout/register robustness, upload validation, and delete cascades."""
import io
import os

from hopkins.db import get_db


def _register_and_login(client, email="u@x.com", password="password123"):
    """Claude__register_and_login: create a user and start their session."""
    client.post("/register", data={"email": email, "password": password})
    client.post("/login", data={"email": email, "password": password})


def test_post_without_csrf_rejected(client):
    _register_and_login(client)
    r = client.post_without_csrf("/rename_activity", data={"id_analysis": "1", "new_title": "x"})
    assert r.status_code == 400


def test_file_serving_routes_removed(client):
    assert client.get("/uploads/anything.fit").status_code == 404
    assert client.get("/download/../../etc/passwd").status_code == 404


def test_logout_when_anonymous_does_not_500(client):
    r = client.get("/logout")
    assert r.status_code == 302


def test_duplicate_email_rejected(app, client):
    client.post("/register", data={"email": "dup@x.com", "password": "password123"})
    client.post("/register", data={"email": "dup@x.com", "password": "password456"})
    with app.app_context():
        with get_db() as conn:
            n = conn.execute("SELECT COUNT(*) FROM users WHERE email='dup@x.com'").fetchone()[0]
    assert n == 1


def test_register_validation(app, client):
    client.post("/register", data={"email": "short@x.com", "password": "short"})
    client.post("/register", data={"email": "not-an-email", "password": "password123"})
    with app.app_context():
        with get_db() as conn:
            n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert n == 0


def test_upload_rejects_bad_files(app, client):
    _register_and_login(client)

    # unsupported extension
    r = client.post("/upload", data={"file": (io.BytesIO(b"hello"), "notes.txt")},
                    content_type="multipart/form-data")
    assert r.status_code == 302 and r.headers["Location"].endswith("/upload")

    # garbage bytes with a .fit name: no orphan DB row, no leftover file
    r = client.post("/upload", data={"file": (io.BytesIO(b"garbage"), "ride.fit")},
                    content_type="multipart/form-data")
    assert r.status_code == 302 and r.headers["Location"].endswith("/upload")
    with app.app_context():
        with get_db() as conn:
            n = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    assert n == 0
    assert os.listdir(app.config["UPLOAD_FOLDER"]) == []


def test_delete_activity_cascades(app, client):
    _register_and_login(client)
    with app.app_context():
        with get_db() as conn:
            uid = conn.execute("SELECT id_user FROM users").fetchone()[0]
            conn.execute("INSERT INTO files (id_user, title) VALUES (?, 'act')", (uid,))
            conn.commit()
            fid = conn.execute("SELECT id_analysis FROM files").fetchone()[0]
            conn.execute("INSERT INTO segments (id_analysis, start_pt, end_pt) VALUES (?, 0, 1)", (fid,))
            conn.commit()
    fit = os.path.join(app.config["UPLOAD_FOLDER"], f"Activite{uid}_{fid}.fit")
    open(fit, "wb").close()

    r = client.post("/delete_file", data={"supression": str(fid)})
    assert r.status_code == 302
    with app.app_context():
        with get_db() as conn:
            assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0] == 0
    assert not os.path.exists(fit)


def test_encode_q_tolerates_none_bounds():
    """A NULL length (incomplete upload) must not crash token encoding."""
    from hopkins.web.util import decode_q, encode_q
    s, e, d = decode_q(encode_q(0, None, "1,2"))
    assert (s, e, d) == (0, 0, "1,2")


def test_history_renders_with_null_length_activity(app, client):
    """An activity whose upload never finished (NULL length/title/distance) must not 500 /history."""
    _register_and_login(client)
    with app.app_context():
        with get_db() as conn:
            uid = conn.execute("SELECT id_user FROM users").fetchone()[0]
            conn.execute("INSERT INTO files (id_user, length, title, distance) VALUES (?, NULL, NULL, NULL)", (uid,))
            conn.commit()
    assert client.get("/history").status_code == 200


def test_bulk_delete_files_only_owned(app, client):
    """Bulk activity delete removes the caller's rows (and cascades segments) but ignores others."""
    _register_and_login(client, "owner@x.com")
    with app.app_context():
        with get_db() as conn:
            uid = conn.execute("SELECT id_user FROM users WHERE email='owner@x.com'").fetchone()[0]
            # a second user with an activity the caller must NOT be able to delete
            conn.execute("INSERT INTO users (email, password, status, credit) VALUES ('other@x.com','p','user',100)")
            oid = conn.execute("SELECT id_user FROM users WHERE email='other@x.com'").fetchone()[0]
            conn.execute("INSERT INTO files (id_user, title) VALUES (?, 'mine1')", (uid,))
            conn.execute("INSERT INTO files (id_user, title) VALUES (?, 'mine2')", (uid,))
            conn.execute("INSERT INTO files (id_user, title) VALUES (?, 'theirs')", (oid,))
            conn.commit()
            mine = [r[0] for r in conn.execute("SELECT id_analysis FROM files WHERE id_user=?", (uid,)).fetchall()]
            theirs = conn.execute("SELECT id_analysis FROM files WHERE id_user=?", (oid,)).fetchone()[0]
            conn.execute("INSERT INTO segments (id_analysis, start_pt, end_pt) VALUES (?, 0, 1)", (mine[0],))
            conn.commit()

    r = client.post("/delete_files", data={"ids": [str(mine[0]), str(mine[1]), str(theirs)]})
    assert r.status_code == 302
    with app.app_context():
        with get_db() as conn:
            assert conn.execute("SELECT COUNT(*) FROM files WHERE id_user=?", (uid,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM files WHERE id_analysis=?", (theirs,)).fetchone()[0] == 1  # untouched


def test_bulk_delete_routes_only_owned(app, client):
    _register_and_login(client, "owner@x.com")
    with app.app_context():
        with get_db() as conn:
            uid = conn.execute("SELECT id_user FROM users WHERE email='owner@x.com'").fetchone()[0]
            conn.execute("INSERT INTO users (email, password, status, credit) VALUES ('other@x.com','p','user',100)")
            oid = conn.execute("SELECT id_user FROM users WHERE email='other@x.com'").fetchone()[0]
            conn.execute("INSERT INTO gpx (id_user, title) VALUES (?, 'r1')", (uid,))
            conn.execute("INSERT INTO gpx (id_user, title) VALUES (?, 'r2')", (oid,))
            conn.commit()
            mine = conn.execute("SELECT id_route FROM gpx WHERE id_user=?", (uid,)).fetchone()[0]
            theirs = conn.execute("SELECT id_route FROM gpx WHERE id_user=?", (oid,)).fetchone()[0]

    r = client.post("/delete_routes", data={"ids": [str(mine), str(theirs)]})
    assert r.status_code == 302
    with app.app_context():
        with get_db() as conn:
            assert conn.execute("SELECT COUNT(*) FROM gpx WHERE id_route=?", (mine,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM gpx WHERE id_route=?", (theirs,)).fetchone()[0] == 1


def test_gpx_upload_titles_new_route(app, client):
    """Task 10: an uploaded route is titled 'New Route', not the filename."""
    _register_and_login(client)
    gpx = os.path.join(os.path.dirname(__file__), "fixtures", "synthetic.gpx")
    with open(gpx, "rb") as f:
        client.post("/upload", data={"file": (io.BytesIO(f.read()), "MyRide2024.gpx")},
                    content_type="multipart/form-data")
    with app.app_context():
        with get_db() as conn:
            title = conn.execute("SELECT title FROM gpx ORDER BY id_route DESC").fetchone()[0]
    assert title == "New Route"
