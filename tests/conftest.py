"""Shared test fixtures: isolated app on a temp DB and a CSRF-aware test client."""
import os

import pytest

from hopkins import create_app
from hopkins.config import Config


@pytest.fixture
def app(tmp_path):
    """Claude_app: app factory bound to a throwaway DB/upload dir so data/ stays untouched."""
    class C(Config):
        DB_PATH = str(tmp_path / "t.db")
        UPLOAD_FOLDER = str(tmp_path / "up")
        SECRET_KEY = "test"
    os.makedirs(C.UPLOAD_FOLDER, exist_ok=True)
    return create_app(C)


class CsrfClient:
    """Claude_CsrfClient: wraps the Flask test client, injecting the session CSRF token
    into every POST so tests exercise routes the way real forms do."""

    def __init__(self, client):
        self._c = client

    def get(self, *args, **kwargs):
        return self._c.get(*args, **kwargs)

    def post(self, url, data=None, **kwargs):
        with self._c.session_transaction() as sess:
            sess.setdefault('_csrf', 'test-token')
            token = sess['_csrf']
        data = dict(data or {})
        data['_csrf'] = token
        return self._c.post(url, data=data, **kwargs)

    def post_without_csrf(self, url, **kwargs):
        return self._c.post(url, **kwargs)

    def session_transaction(self, *args, **kwargs):
        return self._c.session_transaction(*args, **kwargs)


@pytest.fixture
def client(app):
    """Claude_client: CSRF-aware test client for the isolated app."""
    return CsrfClient(app.test_client())
