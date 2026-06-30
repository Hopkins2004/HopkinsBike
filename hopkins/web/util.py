"""Web helpers: the opaque navigation token, role lookup, and the login_required guard."""
import base64
import json
from functools import wraps

from flask import redirect, session, url_for

from ..db import get_db


def encode_q(start, end, data_str):
    """Claude_encode_q: encode start/end/data into a single urlsafe base64 token"""
    payload = json.dumps({'s': int(start), 'e': int(end), 'd': str(data_str)}, separators=(',', ':'))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip('=')


def decode_q(q):
    """Claude_decode_q: decode a urlsafe base64 token back to start, end, data_str"""
    padded = q + '=' * (-len(q) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded).decode())
    return payload['s'], payload['e'], payload['d']


def fetch_role():
    """Claude_fetch_role: status of the logged-in user, or 'guest' when not logged in."""
    username = session.get('username')
    if not username:
        return 'guest'
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM users WHERE email=?", (username,))
        row = cursor.fetchone()
    return row[0] if row else 'guest'


def current_user_id():
    """Claude_current_user_id: id_user of the logged-in user, or None if not logged in /
    unknown. Used to scope data queries to the session owner (IDOR fix)."""
    username = session.get('username')
    if not username:
        return None
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id_user FROM users WHERE email = ?", (username,))
        row = cursor.fetchone()
    return row[0] if row else None


def login_required(view):
    """Claude_login_required: redirect anonymous visitors to /login instead of 500-ing."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('auth.go_to_login'))
        return view(*args, **kwargs)
    return wrapped
