"""Centralised configuration, env-driven. Defaults keep parity with the old monolith
so behaviour is unchanged when no env vars are set."""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The Google Maps key shipped in the old templates. Kept as the default so the maps keep
# working out of the box; override with HOPKINS_MAPS_KEY in any real deployment and
# restrict the key by HTTP referrer in the Google console.
_DEFAULT_MAPS_KEY = 'AIzaSyDUAk339DGU-IlM7XDkLa-WLRWYNBhVuY0'


class Config:
    """Claude_Config: application configuration resolved from the environment."""
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.environ.get('HOPKINS_SECRET', 'dev-secret-change-me')
    DB_PATH = os.environ.get('HOPKINS_DB', os.path.join(BASE_DIR, 'data', 'data.db'))
    UPLOAD_FOLDER = os.environ.get('HOPKINS_UPLOADS', os.path.join(BASE_DIR, 'data', 'uploads'))
    MAPS_API_KEY = os.environ.get('HOPKINS_MAPS_KEY', _DEFAULT_MAPS_KEY)
    DEBUG = os.environ.get('HOPKINS_DEBUG', '0') == '1'
    # Comma-separated list of allowed CORS origins; empty = same-origin only (no CORS header).
    CORS_ORIGINS = [o for o in os.environ.get('HOPKINS_CORS_ORIGINS', '').split(',') if o]
