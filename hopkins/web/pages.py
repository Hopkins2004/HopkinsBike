"""Static / chrome pages: root redirect, home, explainer pages, file serving, close window."""
import os

from flask import (Blueprint, current_app, redirect, render_template,
                   render_template_string, send_file, send_from_directory, url_for)

from .util import fetch_role

bp = Blueprint('pages', __name__)


@bp.route('/download/<path:document_path>', methods=['GET'])
def f_download_document(document_path):
    """Claude_f_download_document: serve a generated PDF from the uploads folder."""
    return send_file(os.path.join(current_app.config['UPLOAD_FOLDER'], document_path + '.pdf'),
                     as_attachment=True)


@bp.route('/uploads/<path:filename>')
def show_file(filename):
    """Claude_show_file: serve a stored upload by filename."""
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)


@bp.route('/')
def f_root():
    """Claude_f_root: redirect bare root URL to home, which handles guest vs logged-in branching"""
    return redirect(url_for('pages.f_home'))


@bp.route('/home')
def f_home():
    """Claude_f_home: redirect logged-in users to history; show home only to guests"""
    role = fetch_role()
    if role != 'guest':
        return redirect(url_for('activities.f_history'))
    return render_template('home.html')


@bp.route('/close_window')
def f_close_window():
    """Claude_f_close_window: tiny page that closes itself (used by popups)."""
    return render_template_string('''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>Close Window</title>
        </head>
        <body>
            <script>
                setTimeout(function() {
                window.close();
            }, 500);
            </script>
        </body>
        </html>
    ''')


@bp.route('/how-it-works')
def f_how_it_works():
    """Claude_f_how_it_works: render the How it works explainer page"""
    return render_template('how_it_works.html')


@bp.route('/whitepaper')
def f_whitepaper():
    """Claude_f_whitepaper: render the technical whitepaper page"""
    return render_template('whitepaper.html')
