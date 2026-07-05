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
