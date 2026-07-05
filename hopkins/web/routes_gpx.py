"""GPX routes blueprint: list routes, view a route, estimate time/power, and the
print-ready top-tube card.

Every route requires login (before_request) and is scoped to the session user: the route
id from the client is validated against the session user's rows, so one user cannot read or
mutate another user's routes (IDOR)."""
import os

from flask import (Blueprint, current_app, redirect, render_template, request,
                   session, url_for)

from ..db import get_db
from ..physics.parsing import gpx_points, gpx_raw_points
from ..physics.route import approximate_detailed, parameter
from .util import current_user_id, decode_q, user_owns_route

bp = Blueprint('routes_gpx', __name__)


@bp.before_request
def require_login():
    """Claude_require_login: redirect anonymous visitors to the login page (no more 500s)."""
    if 'username' not in session:
        return redirect(url_for('auth.go_to_login'))


def _route_path(user, id_route):
    """Claude__route_path: on-disk path of a stored GPX route."""
    return os.path.join(current_app.config['UPLOAD_FOLDER'], 'Route' + str(user) + '_' + str(id_route) + '.gpx')


@bp.route('/routes')
def f_routes():
    """Claude_f_routes: list GPX routes for the current user"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id_user FROM users WHERE email = ?", (session['username'],))
        idu = cursor.fetchall()[0][0]
        cursor.execute('SELECT id_route, title, distance FROM gpx WHERE id_user = ? ORDER BY id_route DESC', (idu,))
        routes = cursor.fetchall()
    return render_template('routes.html', user=idu, routes=routes)


@bp.route('/view_route')
def f_view_route():
    """Claude_f_view_route: show GPX map and param form for a route"""
    start, end, data_str = decode_q(request.args.get('q'))
    datas = data_str.split(',')
    id_route = int(datas[1])
    user = current_user_id()
    with get_db() as conn:
        if not user_owns_route(conn, user, id_route):
            return redirect('/routes')
        cursor = conn.cursor()
        cursor.execute('SELECT title, distance FROM gpx WHERE id_route = ?', (id_route,))
        row = cursor.fetchone()
    gpx_path = _route_path(user, id_route)
    raw_pts = gpx_raw_points(gpx_path)
    profile = gpx_points(gpx_path)
    title = row[0] if row else ''
    total_dist = row[1] if row else 0
    return render_template('view_route.html',
        user=user, id_route=id_route, raw_pts=raw_pts, profile=profile,
        title=title, total_dist=total_dist,
        results=None, section_data=None, border_distances=[], max_sections=5)


@bp.route('/calculate_route', methods=['POST'])
def f_calculate_route():
    """Claude_f_calculate_route: run peucker_douglas+calculate on GPX and return sections"""
    id_route = int(request.form['id_route'])
    crr = float(request.form['crr'])
    weight = float(request.form['weight'])
    cda_flat = float(request.form['cda_flat'])
    cda_up = float(request.form['cda_up'])
    np_target = float(request.form['np_target'])
    user = current_user_id()
    with get_db() as conn:
        if not user_owns_route(conn, user, id_route):
            return redirect('/routes')
    gpx_path = _route_path(user, id_route)

    max_sections = int(request.form.get('max_sections', 5))

    params = parameter()
    params.weight = weight
    params.crr = crr
    params.cda_low = cda_flat
    params.cda_base = cda_up
    params.max_speed = 60

    total_time, total_np, section_data, border_distances = approximate_detailed(gpx_path, np_target, params, max_sections)

    secs = int(total_time % 60)
    total_time_min = int(total_time // 60)
    mins = total_time_min % 60
    hours = total_time_min // 60
    time_str = str(hours) + "h" + str(mins).zfill(2) + "'" + str(secs).zfill(2)

    raw_pts = gpx_raw_points(gpx_path)
    profile = gpx_points(gpx_path)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT title, distance FROM gpx WHERE id_route = ?', (id_route,))
        row = cursor.fetchone()
    title = row[0] if row else ''
    total_dist = row[1] if row else 0
    results = {'time': time_str, 'np': round(total_np, 0)}
    form_vals = {'crr': crr, 'weight': weight, 'cda_flat': cda_flat, 'cda_up': cda_up, 'np_target': np_target}
    return render_template('view_route.html',
        user=user, id_route=id_route, raw_pts=raw_pts, profile=profile,
        title=title, total_dist=total_dist,
        results=results, section_data=section_data, border_distances=border_distances,
        max_sections=max_sections, form_vals=form_vals)


@bp.route('/toptube_pdf', methods=['POST'])
def f_toptube_pdf():
    """Claude_f_toptube_pdf: generate print-ready top-tube card with per-section power, grade, time"""
    id_route = int(request.form['id_route'])
    crr = float(request.form['crr'])
    weight = float(request.form['weight'])
    cda_flat = float(request.form['cda_flat'])
    cda_up = float(request.form['cda_up'])
    np_target = float(request.form['np_target'])
    max_sections = int(request.form.get('max_sections', 5))
    orientation = request.form.get('orientation', 'horizontal')
    user = current_user_id()
    with get_db() as conn:
        if not user_owns_route(conn, user, id_route):
            return redirect('/routes')
    gpx_path = _route_path(user, id_route)

    params = parameter()
    params.weight = weight
    params.crr = crr
    params.cda_low = cda_flat
    params.cda_base = cda_up
    params.max_speed = 60

    total_time, total_np, section_data, border_distances = approximate_detailed(gpx_path, np_target, params, max_sections)

    secs = int(total_time % 60)
    total_time_min = int(total_time // 60)
    mins = total_time_min % 60
    hours = total_time_min // 60
    time_str = str(hours) + "h" + str(mins).zfill(2) + "'" + str(secs).zfill(2)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT title, distance FROM gpx WHERE id_route = ?', (id_route,))
        row = cursor.fetchone()
    title = row[0] if row else ''
    total_dist = row[1] if row else 0

    cum_dist = 0.0
    for s in section_data:
        s['cum_dist_start'] = round(cum_dist / 1000, 2)
        cum_dist += s['distance']
        s['cum_dist_end'] = round(cum_dist / 1000, 2)
        t_min = int(s['time'] // 60)
        t_sec = int(s['time'] % 60)
        s['time_str'] = str(t_min) + "'" + str(t_sec).zfill(2)

    return render_template('toptube.html',
        title=title, total_dist=total_dist, time_str=time_str,
        total_np=round(total_np, 0), section_data=section_data, orientation=orientation)


@bp.route('/rename_route', methods=['POST'])
def f_rename_route():
    """Claude_f_rename_route: update route title"""
    id_route = request.form['id_route']
    new_title = request.form['new_title'].strip()
    uid = current_user_id()
    with get_db() as conn:
        if not user_owns_route(conn, uid, id_route):
            return redirect('/routes')
        cursor = conn.cursor()
        cursor.execute('UPDATE gpx SET title = ? WHERE id_route = ?', (new_title, id_route))
    return redirect('/routes')


@bp.route('/delete_route', methods=['POST'])
def f_delete_route():
    """Claude_f_delete_route: remove route from DB and its GPX file from disk"""
    id_route = request.form['id_route']
    uid = current_user_id()
    with get_db() as conn:
        if not user_owns_route(conn, uid, id_route):
            return redirect('/routes')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM gpx WHERE id_route = ?', (id_route,))
    gpx_path = _route_path(uid, id_route)
    if os.path.exists(gpx_path):
        os.remove(gpx_path)
    return redirect('/routes')
