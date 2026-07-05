"""WSGI entry point for production servers.

Gunicorn (see the Render start command) imports the module-level ``app`` callable:

    gunicorn wsgi:app --bind 0.0.0.0:$PORT

Configuration is read from the environment by hopkins/config.py. See the README for the
full list of variables (HOPKINS_SECRET, HOPKINS_MAPS_KEY, HOPKINS_HTTPS, the Google OAuth
pair, and the optional persistent-storage paths).
"""
from hopkins import create_app

app = create_app()
