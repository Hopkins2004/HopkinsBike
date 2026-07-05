"""Google sign-in tests. The token/userinfo network calls are stubbed, so nothing here
touches Google — we exercise the state handling, the disabled-by-default guard, and user
provisioning + session on the happy path."""
import os
from urllib.parse import parse_qs, urlparse

import pytest

from hopkins import create_app
from hopkins.config import Config
from hopkins.db import get_db


@pytest.fixture
def google_app(tmp_path):
    """Claude_google_app: app with Google OAuth configured, on a throwaway DB."""
    class C(Config):
        DB_PATH = str(tmp_path / "t.db")
        UPLOAD_FOLDER = str(tmp_path / "up")
        SECRET_KEY = "test"
        GOOGLE_CLIENT_ID = "test-client-id"
        GOOGLE_CLIENT_SECRET = "test-secret"
    os.makedirs(C.UPLOAD_FOLDER, exist_ok=True)
    return create_app(C)


def test_disabled_by_default(app):
    """Without credentials the button is hidden and the routes no-op back to /login."""
    client = app.test_client()
    assert b"Continue with Google" not in client.get("/login").data
    r = client.get("/login/google")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")


def test_button_shown_when_configured(google_app):
    assert b"Continue with Google" in google_app.test_client().get("/login").data


def test_login_google_redirects_to_google(google_app):
    client = google_app.test_client()
    r = client.get("/login/google")
    assert r.status_code == 302
    loc = urlparse(r.headers["Location"])
    assert loc.netloc == "accounts.google.com"
    q = parse_qs(loc.query)
    assert q["client_id"] == ["test-client-id"]
    assert q["response_type"] == ["code"]
    assert "openid email profile" in q["scope"][0]
    with client.session_transaction() as sess:
        assert q["state"] == [sess["oauth_state"]]  # state stored server-side


def test_callback_bad_state_blocked(google_app):
    client = google_app.test_client()
    client.get("/login/google")  # sets a state
    r = client.get("/login/google/callback?state=forged&code=abc")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    with client.session_transaction() as sess:
        assert "username" not in sess  # not signed in


def test_callback_happy_path_provisions_user(google_app, monkeypatch):
    monkeypatch.setattr("hopkins.web.auth._google_fetch_email", lambda code, uri: "newbie@gmail.com")
    client = google_app.test_client()
    client.get("/login/google")
    with client.session_transaction() as sess:
        state = sess["oauth_state"]

    r = client.get(f"/login/google/callback?state={state}&code=goodcode")
    assert r.status_code == 302 and r.headers["Location"].endswith("/history")
    with client.session_transaction() as sess:
        assert sess["username"] == "newbie@gmail.com"

    with google_app.app_context():
        with get_db() as conn:
            row = conn.execute("SELECT status, verified FROM users WHERE email='newbie@gmail.com'").fetchone()
    assert row == ("user", 1)


def test_callback_links_existing_email(google_app, monkeypatch):
    """A Google login for an email that already exists signs into that same account."""
    client = google_app.test_client()
    client.post("/register", data={"email": "dupe@gmail.com", "password": "password123",
                                   "_csrf": _csrf(client)})
    monkeypatch.setattr("hopkins.web.auth._google_fetch_email", lambda code, uri: "dupe@gmail.com")
    client.get("/login/google")
    with client.session_transaction() as sess:
        state = sess["oauth_state"]
    client.get(f"/login/google/callback?state={state}&code=goodcode")

    with google_app.app_context():
        with get_db() as conn:
            n = conn.execute("SELECT COUNT(*) FROM users WHERE email='dupe@gmail.com'").fetchone()[0]
    assert n == 1  # no duplicate account created


def _csrf(client):
    """Claude__csrf: seed and return the session CSRF token for a POST."""
    with client.session_transaction() as sess:
        sess.setdefault("_csrf", "tok")
        return sess["_csrf"]
