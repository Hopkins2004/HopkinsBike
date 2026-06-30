"""Activities blueprint: FIT upload, history, visualise, segment create/save/edit/delete,
and the CdA calculation pages.

Every route here requires a logged-in user (enforced by before_request) and is scoped to
the session owner: ids supplied by the client (q token / form fields) are validated against
the session user's rows, so one user can never read or mutate another user's data (IDOR)."""
import json
import os

from flask import (Blueprint, current_app, redirect, render_template, request,
                   session, url_for)

from ..db import get_db
from ..physics.cda import rideCDA
from ..physics.parsing import (aggregate_segments, extract_data, gpx_points,
                               gpx_raw_points, make_segments)
from ..physics.route import compute_section_borders
from .util import (current_user_id, decode_q, encode_q, segment_owner_id,
                   user_owns_activity)

bp = Blueprint('activities', __name__)


@bp.before_request
def require_login():
    """Claude_require_login: redirect anonymous visitors to the login page (no more 500s)."""
    if 'username' not in session:
        return redirect(url_for('auth.go_to_login'))


def _activity_path(user, id_act):
    """Claude__activity_path: on-disk path of a stored FIT activity."""
    return os.path.join(current_app.config['UPLOAD_FOLDER'], 'Activite' + str(user) + '_' + str(id_act) + '.fit')


@bp.route('/history')
def f_history():
    """Claude_f_history: fetch activities and their saved segments for the current user"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id_user FROM users WHERE email = ?", (session['username'],))
        idu = cursor.fetchall()[0][0]
        cursor.execute('SELECT id_analysis,length, title, day, distance FROM files WHERE id_user = ? ORDER BY id_analysis DESC', (idu,))
        data = cursor.fetchall()
        segments_by_activity = {}
        for row in data:
            id_act = row[0]
            cursor.execute("SELECT id_segments, title, cda, comment, cda_data FROM segments WHERE id_analysis = ?", (id_act,))
            segments_by_activity[id_act] = cursor.fetchall()
    return render_template('history.html', user=idu, data=data, segments_by_activity=segments_by_activity)


@bp.route('/upload', methods=['POST'])
def f_upload():
    """Claude_f_upload: store an uploaded FIT (activity) or GPX (route) and route onward."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id_user FROM users WHERE email = ?", (session['username'],))
        iduser = cursor.fetchall()[0][0]

        file = request.files['file']
        file_extension = file.filename.rsplit('.', 1)[1].lower()

        if file_extension == 'fit':
            cursor.execute("INSERT INTO files (id_user) VALUES (?)", (iduser,))
            conn.commit()
            cursor.execute('SELECT id_analysis FROM files WHERE id_user = ? ORDER BY id_analysis DESC', (iduser,))
            idactivite = cursor.fetchall()[0][0]

            filename = os.path.join(current_app.config['UPLOAD_FOLDER'], 'Activite' + str(iduser) + '_' + str(idactivite) + '.' + file_extension)
            file.save(filename)
            points, lapstamps = extract_data(filename)
            length = len(points)
            coords = []
            power = []
            date = points[0].timestamp.strftime('%d/%m/%Y')
            for point in points:
                coords.append([point.latitude, point.longitude])
                power.append(point.power)
            avg_power = 0
            for powe in power:
                avg_power += powe
            avg_power /= length
            distance = points[len(points) - 1].distance / 1000
            distance = round(distance, 3)
            avg_power = round(avg_power, 3)
            cursor.execute('UPDATE files SET (length, day, title, distance, avg_pwr) = (?,?,?,?,?) WHERE id_analysis = ?', (length, date, 'New Activity', distance, avg_power, idactivite))
            conn.commit()
            parameters = [iduser, idactivite]
            print(f'Parsed activity {idactivite}: {len(coords)} points')
            return render_template('visualise.html', parameters=parameters, data=coords, power=power, start=0, end=len(power) - 1, results=[])

        elif file_extension == 'gpx':
            original_name = request.files['file'].filename.rsplit('.', 1)[0]
            cursor.execute("INSERT INTO gpx (id_user, title) VALUES (?, ?)", (iduser, original_name))
            conn.commit()
            cursor.execute('SELECT id_route FROM gpx WHERE id_user = ? ORDER BY id_route DESC', (iduser,))
            idroute = cursor.fetchall()[0][0]

            filename = os.path.join(current_app.config['UPLOAD_FOLDER'], 'Route' + str(iduser) + '_' + str(idroute) + '.' + file_extension)
            file.save(filename)

            raw_pts = gpx_raw_points(filename)
            profile = gpx_points(filename)
            total_dist = round(profile[-1][0] / 1000, 3) if profile else 0
            cursor.execute('UPDATE gpx SET length = ?, distance = ? WHERE id_route = ?', (len(raw_pts), total_dist, idroute))
            conn.commit()
            return redirect('/view_route?q=' + encode_q(0, len(raw_pts), str(iduser) + ',' + str(idroute)))


@bp.route('/visualise')
def f_visualise():
    """Claude_f_visualise: decode opaque q param and render the activity map/charts.
    Identity comes from the session, not the token (IDOR-safe)."""
    start, end, data_str = decode_q(request.args.get('q'))
    datas = list(map(str, data_str.split(',')))
    id_act = int(datas[1])
    user = current_user_id()
    with get_db() as conn:
        if not user_owns_activity(conn, user, id_act):
            return redirect('/history')
    points, lapstamps = extract_data(_activity_path(user, id_act))
    coords = []
    power = []
    altitude = []
    i = 0
    for point in points:
        if i % 1 == 0:
            coords.append([point.latitude, point.longitude])
            power.append(point.power)
            altitude.append(point.altitude / 2)
        i += 1
    points = points[start:end]
    points = aggregate_segments(make_segments(points), 3)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id_segments, title, cda, comment FROM segments WHERE id_analysis = ?", (id_act,))
        results = cursor.fetchall()
    print(f'Activity {id_act}: {len(results)} saved segments')

    parameters = [user, id_act]

    return render_template('visualise.html', parameters=parameters, data=coords, start=start, end=end, results=results)


@bp.route('/new_segment')
def f_new_segment():
    """Claude_f_new_segment: load activity, compute lap indices, pass to segment template"""
    start, end, data_str = decode_q(request.args.get('q'))
    datas = list(map(str, data_str.split(',')))
    id_act = int(datas[1])
    user = current_user_id()
    with get_db() as conn:
        if not user_owns_activity(conn, user, id_act):
            return redirect('/history')
    all_points, lapstamps = extract_data(_activity_path(user, id_act))
    coords = []
    power = []
    altitude = []
    distances = []
    speed = []
    for point in all_points:
        coords.append([point.latitude, point.longitude])
        power.append(point.power)
        altitude.append(point.altitude / 2)
        distances.append(round(point.distance, 1))
        speed.append(round((point.speed or 0) * 3.6, 2))

    # Convert lapstamp boundaries to point indices as [[start, end], ...]
    lap_start_times = {lap[0] for lap in lapstamps}
    lap_end_times = {lap[1] for lap in lapstamps}
    lap_start_map = {pt.timestamp: i for i, pt in enumerate(all_points) if pt.timestamp in lap_start_times}
    lap_end_map = {pt.timestamp: i for i, pt in enumerate(all_points) if pt.timestamp in lap_end_times}
    lap_bounds = []
    for lap in lapstamps:
        s = lap_start_map.get(lap[0])
        e = lap_end_map.get(lap[1])
        if s is not None and e is not None:
            lap_bounds.append([s, e])
    lap_indices = [b[1] for b in lap_bounds]

    points = all_points[start:end]
    points = aggregate_segments(make_segments(points), 3)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id_segments, title, cda, comment FROM segments WHERE id_analysis = ?", (id_act,))
        results = cursor.fetchall()

    parameters = [user, id_act]

    total_length = len(all_points)
    return render_template('segment.html', parameters=parameters, data=coords, power=power, elevation=altitude, distances=distances, speed=speed, start=start, end=end, total_length=total_length, results=results, lap_indices=lap_indices, lap_bounds=lap_bounds)


@bp.route('/calculate')
def f_calculate():
    """Claude_f_calculate: peucker_douglas multi-section CdA calculation"""
    start, end, data_str = decode_q(request.args.get('q'))
    datas = list(map(str, data_str.split(',')))
    id_act = int(datas[1])
    crr, weight, efficiency = float(datas[2]), float(datas[3]), float(datas[4])
    user = current_user_id()
    with get_db() as conn:
        if not user_owns_activity(conn, user, id_act):
            return redirect('/history')
    all_points, lapstamps = extract_data(_activity_path(user, id_act))

    pts = all_points[start:end]
    if len(pts) < 4:
        return redirect('/history')

    duree = (pts[-1].timestamp - pts[0].timestamp).total_seconds()
    micro_segs = make_segments(pts)

    # Build (cumulative_distance, altitude) profile for peucker_douglas
    cum_dist = 0.0
    alt = pts[0].altitude
    profile = [(cum_dist, alt)]
    for s in micro_segs:
        cum_dist += s.distance
        alt += s.altitude
        profile.append((cum_dist, alt))

    # CdA: large cutoff for few grade-homogeneous sections, hard-capped at 5
    section_borders = compute_section_borders(profile, 6, 5)

    # Compute CdA per homogeneous section
    sections = []
    for i in range(len(section_borders) - 1):
        b0, b1 = section_borders[i], section_borders[i + 1]
        seg_slice = micro_segs[b0:b1]
        if len(seg_slice) < 3:
            continue
        agg = aggregate_segments(seg_slice, 3)
        cdas = rideCDA(agg, crr, weight, efficiency)
        if not cdas:
            continue
        cdas_sorted = sorted(cdas)
        n = len(cdas_sorted)
        trimmed = cdas_sorted[n // 10: n - n // 10] if n > 5 else cdas_sorted
        if not trimmed:
            continue
        sec_dist = sum(c[1] for c in trimmed)
        avg_grade = (sum(c[2] * c[1] for c in trimmed) / sec_dist) if sec_dist > 0 else 0
        avg_cda = sum(c[0] for c in trimmed) / len(trimmed)
        sec_time = sum(s.time for s in seg_slice)
        avg_speed_s = (sec_dist / sec_time * 3.6) if sec_time > 0 else 0
        avg_pwr_s = (sum(s.time * s.avg_power for s in seg_slice) / sec_time) if sec_time > 0 else 0
        sections.append({
            'cda': round(avg_cda, 4),
            'grade': round(avg_grade, 2),
            'speed': round(avg_speed_s, 1),
            'power': round(avg_pwr_s, 0),
            'distance': round(sec_dist, 0)
        })

    if not sections:
        return redirect('/history')

    total_dist = sum(s['distance'] for s in sections)
    rep_cda = sum(s['cda'] * s['distance'] for s in sections) / total_dist if total_dist > 0 else sections[0]['cda']
    avg_speed_all = (total_dist / duree * 3.6) if duree > 0 else 0
    avg_pwr_all = sum(s['power'] * s['distance'] for s in sections) / total_dist if total_dist > 0 else 0

    border_distances = [profile[min(b, len(profile) - 1)][0] for b in section_borders]
    params_meta = {'user': user, 'id_act': id_act, 'crr': crr, 'weight': weight, 'efficiency': efficiency, 'start': start, 'end': end}
    return render_template('save_comment.html',
        params_meta=params_meta,
        sections=sections,
        rep_cda=round(rep_cda, 4),
        avg_speed=round(avg_speed_all, 1),
        avg_power=round(avg_pwr_all, 0),
        total_dist=round(total_dist, 0),
        profile=profile,
        border_distances=border_distances)


@bp.route('/save_segment', methods=['POST'])
def f_save_segment():
    """Claude_f_save_segment: save segment with per-section CdA data as JSON"""
    idactivity = request.form['idactivity']
    crr = request.form['crr']
    weight = request.form['weight']
    efficiency = request.form['efficiency']
    start = request.form['start']
    end = request.form['end']
    title = request.form.get('title', '')
    comments = request.form.get('comments', '')
    cda_data_json = request.form.get('cda_data', '[]')
    rep_cda = float(request.form.get('rep_cda', 0))

    iduser = current_user_id()
    rep_cda = round(rep_cda, 3)
    parameters_str = 'CRR:' + crr + ',Weight:' + weight + ',Efficiency:' + efficiency

    with get_db() as conn:
        if not user_owns_activity(conn, iduser, idactivity):
            return redirect('/history')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO segments (id_analysis, start_pt, end_pt, parameters, cda, title, comment, cda_data) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (idactivity, start, end, parameters_str, rep_cda, title, comments, cda_data_json)
        )
        conn.commit()
        cursor.execute('SELECT length FROM files WHERE id_analysis = ?', (idactivity,))
        row = cursor.fetchone()
    activity_length = row[0] if row else 0
    return redirect('/visualise?q=' + encode_q(0, activity_length, str(iduser) + ',' + str(idactivity)))


@bp.route('/view_segment')
def f_view_segment():
    """Claude_f_view_segment: show saved segment with map, charts, peucker overlay and per-section CdA"""
    start, end, data_str = decode_q(request.args.get('q'))
    datas = data_str.split(',')
    seg_id = int(datas[1])
    user = current_user_id()

    with get_db() as conn:
        if segment_owner_id(conn, seg_id) != user:
            return redirect('/history')
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id_analysis, start_pt, end_pt, parameters, cda, title, comment, cda_data FROM segments WHERE id_segments = ?',
            (seg_id,)
        )
        row = cursor.fetchone()
    if not row:
        return redirect('/history')

    id_act, start_pt, end_pt, parameters_str, rep_cda, title, comment, cda_data_json = row
    sections = json.loads(cda_data_json) if cda_data_json and cda_data_json != 'null' else []

    # Claude_parse_params: parse stored parameter string into individual fields for the edit form
    param_vals = {'crr': '', 'weight': '', 'efficiency': ''}
    if parameters_str:
        for part in parameters_str.split(','):
            if ':' in part:
                k, v = part.split(':', 1)
                key = k.strip().lower()
                if key == 'crr':
                    param_vals['crr'] = v.strip()
                elif key == 'weight':
                    param_vals['weight'] = v.strip()
                elif key == 'efficiency':
                    param_vals['efficiency'] = v.strip()

    all_points, _ = extract_data(_activity_path(user, id_act))
    pts = all_points[start_pt:end_pt]

    coords = [[p.latitude, p.longitude] for p in pts]
    power = [p.power for p in pts]
    altitude = [p.altitude / 2 for p in pts]
    d_base = pts[0].distance if pts else 0
    pts_distances = [round(p.distance - d_base, 1) for p in pts]
    pts_speed = [round((p.speed or 0) * 3.6, 2) for p in pts]

    micro_segs = make_segments(pts)
    cum_dist = 0.0
    alt = pts[0].altitude
    elev_profile = [(cum_dist, alt)]
    for s in micro_segs:
        cum_dist += s.distance
        alt += s.altitude
        elev_profile.append((cum_dist, alt))

    section_borders = compute_section_borders(elev_profile, 21)
    border_distances = [elev_profile[min(b, len(elev_profile) - 1)][0] for b in section_borders]

    return render_template('view_segment.html',
        user=user, seg_id=seg_id, id_act=id_act,
        coords=coords, power=power, altitude=altitude,
        pts_distances=pts_distances, pts_speed=pts_speed,
        elev_profile=elev_profile, border_distances=border_distances,
        sections=sections, rep_cda=rep_cda,
        title=title, comment=comment, parameters_str=parameters_str,
        param_vals=param_vals)


@bp.route('/delete_segment', methods=['GET', 'POST'])
def f_delete_segment():
    """Claude_f_delete_segment: delete a segment and redirect to history or visualise"""
    seg = request.form['supression']
    from_history = request.form.get('from_history', '0')
    uid = current_user_id()
    with get_db() as conn:
        if segment_owner_id(conn, seg) != uid:
            return redirect('/history')
        cursor = conn.cursor()
        cursor.execute('SELECT id_analysis FROM segments WHERE id_segments = ?', (seg,))
        analysis = cursor.fetchone()[0]

        cursor.execute('DELETE FROM segments WHERE id_segments = ?', (seg,))
        conn.commit()

        if from_history == '1':
            return redirect('/history')

        cursor.execute('SELECT id_user, length FROM files WHERE id_analysis = ?', (analysis,))
        id_user, length = cursor.fetchone()
    return redirect('/visualise?q=' + encode_q(0, length, str(id_user) + ',' + str(analysis)))


@bp.route('/edit_segment', methods=['POST'])
def f_edit_segment():
    """Claude_f_edit_segment: update segment title and comment from history tab"""
    seg_id = request.form['id_segments']
    new_title = request.form['title']
    new_comment = request.form['comment']
    uid = current_user_id()
    with get_db() as conn:
        if segment_owner_id(conn, seg_id) != uid:
            return redirect('/history')
        cursor = conn.cursor()
        cursor.execute('UPDATE segments SET title = ?, comment = ? WHERE id_segments = ?', (new_title, new_comment, seg_id))
    return redirect('/history')


@bp.route('/update_segment', methods=['POST'])
def f_update_segment():
    """Claude_f_update_segment: save edits and fully recalculate CdA with new parameters"""
    seg_id = request.form['id_segments']
    new_title = request.form['title'].strip()
    new_comment = request.form['comment'].strip()
    crr = float(request.form['crr'].strip())
    weight = float(request.form['weight'].strip())
    efficiency = float(request.form['efficiency'].strip())
    parameters_str = 'CRR:' + str(crr) + ',Weight:' + str(weight) + ',Efficiency:' + str(efficiency)

    user = current_user_id()
    with get_db() as conn:
        if segment_owner_id(conn, seg_id) != user:
            return redirect('/history')
        cursor = conn.cursor()
        cursor.execute('SELECT id_analysis, start_pt, end_pt FROM segments WHERE id_segments = ?', (seg_id,))
        row = cursor.fetchone()
    if not row:
        return redirect('/history')
    id_act, start_pt, end_pt = row

    all_points, _ = extract_data(_activity_path(user, id_act))
    pts = all_points[start_pt:end_pt]
    micro_segs = make_segments(pts)
    cum_dist = 0.0
    alt = pts[0].altitude
    profile = [(cum_dist, alt)]
    for s in micro_segs:
        cum_dist += s.distance
        alt += s.altitude
        profile.append((cum_dist, alt))

    section_borders = compute_section_borders(profile, 6, 5)

    sections = []
    for i in range(len(section_borders) - 1):
        b0, b1 = section_borders[i], section_borders[i + 1]
        seg_slice = micro_segs[b0:b1]
        if len(seg_slice) < 3:
            continue
        agg = aggregate_segments(seg_slice, 3)
        cdas = rideCDA(agg, crr, weight, efficiency)
        if not cdas:
            continue
        cdas_sorted = sorted(cdas)
        n_c = len(cdas_sorted)
        trimmed = cdas_sorted[n_c // 10: n_c - n_c // 10] if n_c > 5 else cdas_sorted
        if not trimmed:
            continue
        sec_dist = sum(c[1] for c in trimmed)
        avg_grade = (sum(c[2] * c[1] for c in trimmed) / sec_dist) if sec_dist > 0 else 0
        avg_cda = sum(c[0] for c in trimmed) / len(trimmed)
        sec_time = sum(s.time for s in seg_slice)
        avg_speed_s = (sec_dist / sec_time * 3.6) if sec_time > 0 else 0
        avg_pwr_s = (sum(s.time * s.avg_power for s in seg_slice) / sec_time) if sec_time > 0 else 0
        sections.append({
            'cda': round(avg_cda, 4),
            'grade': round(avg_grade, 2),
            'speed': round(avg_speed_s, 1),
            'power': round(avg_pwr_s, 0),
            'distance': round(sec_dist, 0)
        })

    if sections:
        total_dist = sum(s['distance'] for s in sections)
        rep_cda = round(sum(s['cda'] * s['distance'] for s in sections) / total_dist if total_dist > 0 else sections[0]['cda'], 3)
    else:
        rep_cda = 0

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE segments SET title = ?, comment = ?, parameters = ?, cda = ?, cda_data = ? WHERE id_segments = ?',
            (new_title, new_comment, parameters_str, rep_cda, json.dumps(sections), seg_id)
        )
    return redirect('/view_segment?q=' + encode_q(0, 0, str(user) + ',' + str(seg_id)))


@bp.route('/rename_activity', methods=['POST'])
def f_rename_activity():
    """Claude_f_rename_activity: update the title of an activity for the current user"""
    id_analysis = request.form['id_analysis']
    new_title = request.form['new_title'].strip()
    uid = current_user_id()
    with get_db() as conn:
        if not user_owns_activity(conn, uid, id_analysis):
            return redirect('/history')
        cursor = conn.cursor()
        cursor.execute('UPDATE files SET title = ? WHERE id_analysis = ?', (new_title, id_analysis))
    return redirect('/history')


@bp.route('/delete_file', methods=['GET', 'POST'])
def f_delete_file():
    """Claude_f_delete_file: delete an activity record owned by the current user."""
    file = request.form['supression']
    uid = current_user_id()
    with get_db() as conn:
        if not user_owns_activity(conn, uid, file):
            return redirect('/history')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM files WHERE id_analysis = ?', (file,))
    return redirect('/history')


@bp.route('/upload')
def f_go_to_upload():
    """Claude_f_go_to_upload: render the upload page."""
    return render_template('upload.html')
