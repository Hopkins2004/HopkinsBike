"""Centralised configuration, env-driven.

No real secrets are committed here: every sensitive value comes from an environment variable
and falls back only to an obvious placeholder string, so the app runs but clearly signals what
must be supplied in any real deployment. Set these in your shell / process manager / .env:
    HOPKINS_SECRET                 Flask session-signing secret
    HOPKINS_MAPS_KEY               Google Maps JavaScript API key
    HOPKINS_GOOGLE_CLIENT_ID       Google OAuth client ID     (enables Google sign-in)
    HOPKINS_GOOGLE_CLIENT_SECRET   Google OAuth client secret (enables Google sign-in)
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    """Claude_Config: application configuration resolved from the environment."""
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.environ.get('HOPKINS_SECRET', 'REPLACE_WITH_FLASK_SECRET_KEY')
    DB_PATH = os.environ.get('HOPKINS_DB', os.path.join(BASE_DIR, 'data', 'data.db'))
    UPLOAD_FOLDER = os.environ.get('HOPKINS_UPLOADS', os.path.join(BASE_DIR, 'data', 'uploads'))
    MAPS_API_KEY = os.environ.get('HOPKINS_MAPS_KEY', 'REPLACE_WITH_GOOGLE_MAPS_API_KEY')
    DEBUG = os.environ.get('HOPKINS_DEBUG', '0') == '1'
    # Comma-separated list of allowed CORS origins; empty = same-origin only (no CORS header).
    CORS_ORIGINS = [o for o in os.environ.get('HOPKINS_CORS_ORIGINS', '').split(',') if o]
    # Session cookie hardening: not readable from JS, not sent on cross-site POSTs.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # Set HOPKINS_HTTPS=1 behind TLS so the session cookie is never sent in clear.
    SESSION_COOKIE_SECURE = os.environ.get('HOPKINS_HTTPS', '0') == '1'
    # Uploads are single .fit/.gpx files; 32 MB is far above any real activity.
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024
    # Google sign-in (OAuth 2.0). These intentionally default to EMPTY (not a placeholder):
    # when either is empty the "Sign in with Google" button and routes stay off. Set both from
    # a Google Cloud Console → Credentials → OAuth 2.0 Client ID (Web application) to enable it.
    GOOGLE_CLIENT_ID = os.environ.get('HOPKINS_GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.environ.get('HOPKINS_GOOGLE_CLIENT_SECRET', '')
