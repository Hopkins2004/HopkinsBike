"""Authentication blueprint: register, login, logout, Google sign-in, and the
login/register pages."""
import json
import secrets
import urllib.parse
import urllib.request
from sqlite3 import IntegrityError

from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import get_db

bp = Blueprint('auth', __name__)

# Google OAuth 2.0 / OpenID Connect endpoints.
GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://openidconnect.googleapis.com/v1/userinfo'


@bp.route('/register', methods=['POST'])
def f_register():
    """Claude_f_register: create user with username and password, no email verification required"""
    mail = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    if '@' not in mail or len(mail) < 3:
        flash('Please enter a valid email address.', 'error')
        return redirect(url_for('auth.go_to_register'))
    if len(password) < 8:
        flash('Password must be at least 8 characters.', 'error')
        return redirect(url_for('auth.go_to_register'))
    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (email, password, status, credit, verified) VALUES (?, ?, ?, ?, ?)",
                (mail, hashed_password, 'user', 100, 1),
            )
        flash('Registration successful!', 'success')
        return redirect(url_for('auth.go_to_login'))
    except IntegrityError:
        flash('Email already in use!', 'error')
        return redirect(url_for('auth.go_to_register'))


@bp.route('/login', methods=['POST'])
def f_login():
    """Claude_f_login: verify credentials and start a session, else flash an error."""
    mail = request.form['email']
    password = request.form['password']

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email=?", (mail,))
        user = cursor.fetchone()

    if user and check_password_hash(user[2], password):
        session['username'] = user[1]
        flash('Bienvenue ' + user[1] + ' !', 'success')
        return redirect(url_for('activities.f_history'))
    else:
        flash('Invalid username or password', 'error')
        return redirect(url_for('auth.go_to_login'))


@bp.route('/logout')
def f_logout():
    """Claude_f_logout: clear the session and return to the home page."""
    session.clear()
    flash('Logged out', 'success')
    return redirect(url_for('pages.f_home'))


@bp.route('/login')
def go_to_login():
    """Claude_go_to_login: render the login page."""
    return render_template('login_page.html')


@bp.route('/register')
def go_to_register():
    """Claude_go_to_register: render the registration page."""
    return render_template('register.html')


def _google_configured():
    """Claude__google_configured: True when both Google OAuth credentials are set."""
    return bool(current_app.config.get('GOOGLE_CLIENT_ID') and current_app.config.get('GOOGLE_CLIENT_SECRET'))


def _ensure_google_user(email):
    """Claude__ensure_google_user: find the user by email, creating one (with an unusable
    password so only Google sign-in works for it) if absent. Google verifies the email, so
    linking to an existing same-email account is safe."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id_user FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            return
        unusable = generate_password_hash(secrets.token_urlsafe(32), method='pbkdf2:sha256')
        cursor.execute(
            "INSERT INTO users (email, password, status, credit, verified) VALUES (?, ?, ?, ?, ?)",
            (email, unusable, 'user', 100, 1),
        )


def _google_fetch_email(code, redirect_uri):
    """Claude__google_fetch_email: exchange an auth code for tokens, then read the verified
    email from Google's userinfo endpoint. Returns the email or None."""
    data = urllib.parse.urlencode({
        'code': code,
        'client_id': current_app.config['GOOGLE_CLIENT_ID'],
        'client_secret': current_app.config['GOOGLE_CLIENT_SECRET'],
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
    }).encode()
    token_req = urllib.request.Request(GOOGLE_TOKEN_URL, data=data, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(token_req, timeout=10) as resp:
        token = json.loads(resp.read().decode())
    access_token = token.get('access_token')
    if not access_token:
        return None
    info_req = urllib.request.Request(GOOGLE_USERINFO_URL, headers={'Authorization': 'Bearer ' + access_token})
    with urllib.request.urlopen(info_req, timeout=10) as resp:
        info = json.loads(resp.read().decode())
    if not info.get('email_verified', False):
        return None
    return info.get('email')


@bp.route('/login/google')
def google_login():
    """Claude_google_login: start the OAuth flow — store a state token and redirect to Google."""
    if not _google_configured():
        flash('Google sign-in is not configured.', 'error')
        return redirect(url_for('auth.go_to_login'))
    state = secrets.token_urlsafe(24)
    session['oauth_state'] = state
    params = {
        'client_id': current_app.config['GOOGLE_CLIENT_ID'],
        'redirect_uri': url_for('auth.google_callback', _external=True),
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'access_type': 'online',
        'prompt': 'select_account',
    }
    return redirect(GOOGLE_AUTH_URL + '?' + urllib.parse.urlencode(params))


@bp.route('/login/google/callback')
def google_callback():
    """Claude_google_callback: verify state, exchange the code, and sign the user in."""
    if not _google_configured():
        flash('Google sign-in is not configured.', 'error')
        return redirect(url_for('auth.go_to_login'))
    if request.args.get('error'):
        flash('Google sign-in was cancelled.', 'error')
        return redirect(url_for('auth.go_to_login'))
    expected = session.pop('oauth_state', None)
    if not expected or expected != request.args.get('state'):
        flash('Google sign-in failed (invalid state). Please try again.', 'error')
        return redirect(url_for('auth.go_to_login'))
    code = request.args.get('code')
    if not code:
        flash('Google sign-in failed.', 'error')
        return redirect(url_for('auth.go_to_login'))
    try:
        email = _google_fetch_email(code, url_for('auth.google_callback', _external=True))
    except Exception:
        flash('Could not complete Google sign-in. Please try again.', 'error')
        return redirect(url_for('auth.go_to_login'))
    if not email:
        flash('Your Google account did not return a verified email.', 'error')
        return redirect(url_for('auth.go_to_login'))
    _ensure_google_user(email)
    session['username'] = email
    flash('Signed in with Google.', 'success')
    return redirect(url_for('activities.f_history'))
