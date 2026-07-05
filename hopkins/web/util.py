"""Web helpers: the opaque navigation token, role lookup, and the login_required guard."""
import base64
import json
from functools import wraps

from flask import redirect, session, url_for

from ..db import get_db


def encode_q(start, end, data_str):
    """Claude_encode_q: encode start/end/data into a single urlsafe base64 token.
    A None bound (e.g. an activity whose length was never recorded because its upload never
    finished) coerces to 0, so one incomplete row can't 500 a whole page of links."""
    payload = json.dumps({'s': int(start or 0), 'e': int(end or 0), 'd': str(data_str)}, separators=(',', ':'))
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


def user_owns_activity(conn, uid, id_analysis):
    """Claude_user_owns_activity: True if activity `id_analysis` belongs to user `uid`."""
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM files WHERE id_analysis = ? AND id_user = ?", (id_analysis, uid))
    return cursor.fetchone() is not None


def user_owns_route(conn, uid, id_route):
    """Claude_user_owns_route: True if GPX route `id_route` belongs to user `uid`."""
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM gpx WHERE id_route = ? AND id_user = ?", (id_route, uid))
    return cursor.fetchone() is not None


def segment_owner_id(conn, seg_id):
    """Claude_segment_owner_id: id_user that owns the activity behind segment `seg_id`, or None."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT f.id_user FROM segments s JOIN files f ON s.id_analysis = f.id_analysis "
        "WHERE s.id_segments = ?",
        (seg_id,),
    )
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
