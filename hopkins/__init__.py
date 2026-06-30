"""Hopkins — bike aero analyser. Application factory + package root."""
import json
import os

from flask import Flask

from .config import Config
from .db import init_db
from .web.util import encode_q, fetch_role

# Which nav links each role sees (used only to render the nav bar).
page_permissions = {
    'guest': ['/home', '/login', '/register'],
    'user': ['/history', '/routes', '/upload', '/logout'],
    'admin': ['/history', '/routes', '/upload', '/insights', '/logout'],
}

# Display names for each page.
page_titles = {
    '/home': 'Home',
    '/register': 'Register',
    '/login': 'Login',
    '/logout': 'Logout',
    '/history': 'Activities',
    '/routes': 'Routes',
    '/upload': 'Upload',
    '/gpx_sim': 'Simulations',
    '/insights': 'Admin Stuff',
}


def create_app(config_object=Config):
    """Claude_create_app: build and configure the Flask application (app factory)."""
    base_dir = config_object.BASE_DIR
    app = Flask(
        __name__,
        static_url_path='/static',
        static_folder=os.path.join(base_dir, 'static'),
        template_folder=os.path.join(base_dir, 'templates'),
    )
    app.config.from_object(config_object)
    app.secret_key = app.config['SECRET_KEY']

    # CORS only when explicitly configured (default: same-origin, no wide-open header).
    if app.config.get('CORS_ORIGINS'):
        from flask_cors import CORS
        CORS(app, origins=app.config['CORS_ORIGINS'])

    # Jinja helpers carried over from the monolith.
    app.jinja_env.globals['encode_q'] = encode_q
    app.jinja_env.filters['fromjson'] = json.loads

    @app.context_processor
    def inject_globals():
        """Claude_inject_globals: make role (string), nav data and the maps key available
        to every template, so render_template() no longer passes them by hand."""
        return {
            'role': fetch_role(),
            'page_permissions': page_permissions,
            'page_titles': page_titles,
            'maps_api_key': app.config['MAPS_API_KEY'],
        }

    from .web.auth import bp as auth_bp
    from .web.pages import bp as pages_bp
    from .web.activities import bp as activities_bp
    from .web.routes_gpx import bp as routes_gpx_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(activities_bp)
    app.register_blueprint(routes_gpx_bp)

    init_db(app.config['DB_PATH'])

    return app
