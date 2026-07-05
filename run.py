"""Entry point: build the app via the factory and run the dev server.

    .venv/bin/python run.py

Configuration comes from the environment (see hopkins/config.py): HOPKINS_SECRET,
HOPKINS_DB, HOPKINS_UPLOADS, HOPKINS_MAPS_KEY, HOPKINS_DEBUG, HOPKINS_CORS_ORIGINS.
"""
from hopkins import create_app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=app.config['DEBUG'])
