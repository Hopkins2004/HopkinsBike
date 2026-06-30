import sqlite3
from sqlite3 import IntegrityError
from flask_cors import CORS
from flask import Flask, render_template, render_template_string, request, send_file, send_from_directory, jsonify, redirect, flash, url_for, session,Response
from werkzeug.security import generate_password_hash, check_password_hash
import os
import gpxpy.gpx
import base64, json

app = Flask(__name__, static_url_path='/static', static_folder='static')
CORS(app)
app.secret_key = 'secret'

def encode_q(start, end, data_str):
    """Claude_encode_q: encode start/end/data into a single urlsafe base64 token"""
    payload = json.dumps({'s': int(start), 'e': int(end), 'd': str(data_str)}, separators=(',', ':'))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip('=')

def decode_q(q):
    """Claude_decode_q: decode a urlsafe base64 token back to start, end, data_str"""
    padded = q + '=' * (-len(q) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded).decode())
    return payload['s'], payload['e'], payload['d']

app.jinja_env.globals['encode_q'] = encode_q
app.jinja_env.filters['fromjson'] = json.loads

page_permissions = {
    'guest': ['/home', '/login','/register'],
    'user': ['/history', '/routes', '/upload', '/logout'],
    'admin': ['/history', '/routes', '/upload', '/insights', '/logout']
}

#Noms de chacune des pages
page_titles = {
    '/home':'Home',
    '/register':'Register',
    '/login': 'Login',
    '/logout':'Logout',
    '/history': 'Activities',
    '/routes': 'Routes',
    '/upload' : 'Upload',
    '/gpx_sim' : 'Simulations',
    '/insights' : 'Admin Stuff'
}
from fitparse import*

def init_db():
    conn = sqlite3.connect('templates/data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id_user INTEGER PRIMARY KEY,
            email TEXT NOT NULL,
            password TEXT NOT NULL,
            status TEXT NOT NULL,
            credit INTEGER NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id_analysis INTEGER PRIMARY KEY,
            id_user INTEGER NOT NULL,
            title TEXT,
            length INTEGER,
            distance NUMBER,
            day DATE,
            avg_pwr NUMBER,
            avg_speed NUMBER

            
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS segments (
            id_segments INTEGER PRIMARY KEY,
            id_analysis INTEGER NOT NULL,
            start_pt INTEGER NOT NULL,
            end_pt INTEGER NOT NULL,
            parameters TEXT,
            cda NUMBER,
            title TEXT,
            comment TEXT

            
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gpx (
            id_route INTEGER PRIMARY KEY,
            id_user INTEGER NOT NULL,
            title TEXT,
            length INTEGER,
            distance NUMBER
            
        )
    ''')


    try:
        cursor.execute('ALTER TABLE segments ADD COLUMN cda_data TEXT')
    except Exception:
        pass
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN verified INTEGER DEFAULT 1')
    except Exception:
        pass
    conn.commit()
    conn.close()

def fetch_role():
    try :
        print(session['username'])
        conn = sqlite3.connect('templates/data.db')
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM users WHERE email=?", (session['username'],))
        role = cursor.fetchone()
        return(role[0])
    except:
        return('guest')

class fitpoint:
    def __init__(self, timestamp, altitude, distance, speed, hr, cadence, temperature, power, latitude, longitude):
        self.timestamp = timestamp
        self.altitude = altitude
        self.distance = distance
        self.speed = speed
        self.hr = hr
        self.cadence = cadence
        self.temperature = temperature
        self.power = power
        self.latitude = latitude
        self.longitude = longitude
class fitsegment:
    def __init__(self, time, altitude, distance, speedstart, speedend, avg_hr, avg_cadence, avg_temperature, avg_power):
        self.time = time
        self.altitude = altitude
        self.distance = distance
        self.speedstart = speedstart
        self.speedend = speedend
        self.avg_speed = distance/time
        self.avg_hr = avg_hr
        self.avg_cadence = avg_cadence
        self.avg_temperature = avg_temperature
        self.avg_power = avg_power
        self.grade = altitude/(distance+0.01)*100
def extract_data(filename):

    activity = FitFile(filename)
    activity.parse()
    records = list(activity.get_messages(name = 'lap'))
    lapstamps = []
    for idx_rec, rec in enumerate(records):
        start = rec.get_value('start_time')
        end = rec.get_value('timestamp')
        lapstamps.append([start, end])
    records = list(activity.get_messages(name='record'))
    if len(records) == 0:
        raise ValueError('There is no data inside the FIT file.')
    points = []
    for idx_rec, rec in enumerate(records):
        timestamp = rec.get_value('timestamp')
        altitude = rec.get_value('altitude')
        distance = rec.get_value('distance')
        speed = rec.get_value('speed')
        hr = rec.get_value('heart_rate')
        cadence = rec.get_value('cadence')
        temperature = rec.get_value('temperature')
        power = rec.get_value('power')
        corrupt = False
        latitude = rec.get_value('position_lat')
        try:
            latitude/=11930465
        except:
            corrupt = True
        longitude = rec.get_value('position_long')
        try:
            longitude/=11930465
        except:
            corrupt = True
        try:
            altitude/=1
        except:
            corrupt = True
        if power==None:
            power = 0
        if hr==None:
            hr = 0
        point = fitpoint(timestamp, altitude, distance, speed, hr, cadence, temperature, power, latitude, longitude)
        if not corrupt:
            points.append(point)
    return(points, lapstamps)
def make_segments(points):
    rank = 0
    segments = []
    while rank<len(points)-1:
        start = points[rank]
        finish = points[rank+1]
        time = (finish.timestamp - start.timestamp).total_seconds()
        altitude = finish.altitude - start.altitude
        distance = finish.distance - start.distance
        speedstart = start.speed
        speedend = finish.speed
        avg_hr = start.hr
        avg_cadence = start.cadence
        avg_temperature = start.temperature
        avg_power = start.power
        segment = fitsegment(time, altitude, distance, speedstart, speedend, avg_hr, avg_cadence, avg_temperature, avg_power)
        segments.append(segment)
        rank+=1
    return(segments)
def aggregate_segments(segments, nb_segments):
    rank = nb_segments #crop the very start
    new_segments = []
    while rank < len(segments) - nb_segments:
        time = 0
        altitude = 0
        distance = 0
        speedstart = segments[rank].speedstart
        avg_hr = 0
        avg_cadence = 0
        avg_temperature = 0
        avg_power = 0
        for loop in range(nb_segments):
            segment = segments[rank]
            time += segment.time
            altitude += segment.altitude
            distance += segment.distance
            avg_hr += segment.time*segment.avg_hr
            avg_cadence += segment.time*segment.avg_cadence
            avg_power +=segment.time*segment.avg_power
            rank+=1
        avg_hr/=time
        avg_cadence/=time
        avg_temperature/=time
        avg_power/=time
        speedend = segments[rank].speedend
        if distance !=0:
            new_segment = fitsegment(time, altitude, distance, speedstart, speedend, avg_hr, avg_cadence, avg_temperature, avg_power)
            new_segments.append(new_segment)
    return(new_segments)
def rideCDA(segments, crr, weight, efficiency):
    cdas = []
    for segment in segments:
        if segment.avg_speed>2:
            cdas.append([cda(segment, crr, weight, efficiency), segment.distance, segment.grade])
    return(cdas)
from math import *
import gpxpy.gpx
def power(speed, grade, weight, cda, crr):
    rolling = weight * 9.81 * speed * crr
    air = speed * speed * speed * cda * 0.5 * 1.2
    gravity = speed * grade * weight * 9.81 / 100
    return (rolling + air + gravity)
def solve_cubic_speed(pwr, grade, weight, cda_val, crr):
    """Claude_solve_cubic_speed: Cardano closed-form for 0.6*CdA*v^3 + m*g*(Crr+grade/100)*v = P"""
    a = 0.6 * cda_val
    b = weight * 9.81 * (crr + grade / 100)
    if a < 1e-9:
        return max(pwr / b, 0.0) if abs(b) > 1e-9 else 0.0
    p = b / a
    q = -pwr / a
    D = (q / 2) ** 2 + (p / 3) ** 3
    if D >= 0:
        sqrt_D = sqrt(D)
        u_arg = -q / 2 + sqrt_D
        w_arg = -q / 2 - sqrt_D
        u = copysign(abs(u_arg) ** (1 / 3), u_arg)
        w = copysign(abs(w_arg) ** (1 / 3), w_arg)
        return u + w
    m_val = 2 * sqrt(-p / 3)
    cos_arg = max(-1.0, min(1.0, 3 * q / (p * m_val)))
    theta = acos(cos_arg) / 3
    roots = [m_val * cos(theta), m_val * cos(theta - 2 * pi / 3), m_val * cos(theta + 2 * pi / 3)]
    positive = [r for r in roots if r > 0]
    return max(positive) if positive else 0.0

def speed(pwr, grade, weight, cda, crr, max_speed):
    """Claude_speed: closed-form speed from power and grade"""
    v = solve_cubic_speed(pwr, grade, weight, cda, crr)
    v = max(v, 0.0)
    if v > max_speed / 3.6:
        return max_speed / 3.6
    return v
def time(distance, speed):
    return (distance / speed)
def distgrad_gpx(point1, point2):
    radius = 6371000
    phi1 = point1.latitude * pi / 180
    lambda1 = point1.longitude * pi / 180
    elev1 = point1.elevation
    phi2 = point2.latitude * pi / 180
    lambda2 = point2.longitude * pi / 180
    elev2 = point2.elevation

    deltaphi = phi2 - phi1
    deltalambda = lambda2 - lambda1

    a = sin(deltaphi / 2) * sin(deltaphi / 2) + cos(phi1) * cos(phi2) * sin(deltalambda / 2) * sin(deltalambda / 2)
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    d = radius * c
    return ([d, elev2 - elev1])
def gpx_segments(file):
    gpx_file = open(file, 'r')
    gpx = gpxpy.parse(gpx_file)
    points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                points.append(point)
    i = 0
    somme = 0
    segments = []
    while i < len(points) - 1:
        distance = 0
        denivele = 0
        while distance < 100 and i < len(points) - 1:
            distance += distgrad_gpx(points[i], points[i + 1])[0]
            denivele += distgrad_gpx(points[i], points[i + 1])[1]
            i += 1
        grade = int(1000 * denivele / distance)
        segments.append([distance, grade])
    return (segments)
def gpx_raw_points(file):
    gpx_file = open(file, 'r')
    gpx = gpxpy.parse(gpx_file)
    points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                points.append(point)
    good_points = []
    for point in points:
        good_points.append([point.latitude, point.longitude])
    return(good_points)

def gpx_points(file):
    gpx_file = open(file, 'r')
    gpx = gpxpy.parse(gpx_file)
    points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                points.append(point)

    i = 0
    somme = 0
    good_points = []
    distance = 0
    elevation = points[0].elevation
    good_points.append((distance, elevation))
    while i < len(points) - 1:
        acc = 0
        while acc < 100 and i < len(points) - 1:
            distance += distgrad_gpx(points[i], points[i + 1])[0]
            acc += distgrad_gpx(points[i], points[i + 1])[0]
            elevation += distgrad_gpx(points[i], points[i + 1])[1]
            i += 1
        good_points.append((distance, elevation))
    return (good_points)
def cda(segment, crr, weight, efficiency):
    usedPower = segment.avg_power * efficiency
    usedPower -= segment.avg_speed * segment.grade * weight * 9.81 / 100
    usedPower -= weight * 9.81 * segment.avg_speed * crr
    usedPower /= segment.avg_speed ** 3
    usedPower /= 1.2
    usedPower *= 2
    return (max(usedPower, 0))
def get_crr(watts):
    return (watts * 3.6 / (28.8 * 42.5 * 9.81))
class parameter():
    def __init__(self):
        self.cda_low = 0
        self.cda_base = 0
        self.weight = 0
        self.crr = 0
        self.max_speed = 0

# Representative gradient (percent) at the centre of each of the 8 power buckets used
# by the route model, lowest to highest. The optimiser tunes one power per bucket;
# interp_power turns that stepped set of control points into a smooth piecewise-linear
# power profile by interpolating for a segment's actual gradient.
GRADE_CENTERS = [-5, -1.5, 0.5, 1.5, 2.5, 4, 6.5, 9]

def interp_power(powers, grade):
    """Claude_interp_power: target power for a segment of gradient `grade` (percent),
    linearly interpolated between the two surrounding gradient buckets instead of using
    the single stepped bucket power. Clamped to the end buckets outside the centre range."""
    if grade <= GRADE_CENTERS[0]:
        return powers[0]
    if grade >= GRADE_CENTERS[-1]:
        return powers[7]
    for i in range(len(GRADE_CENTERS) - 1):
        lo, hi = GRADE_CENTERS[i], GRADE_CENTERS[i + 1]
        if lo <= grade <= hi:
            frac = (grade - lo) / (hi - lo)
            return powers[i] + frac * (powers[i + 1] - powers[i])
    return powers[7]

def calculate(segments, powers, parameters):
    times = [0 for i in range(len(powers))]
    for segment in segments:
        low = False
        if segment[1] < -30:
            rank = 0
        elif segment[1] < 0:
            low = True
            rank = 1

        elif segment[1] < 10:
            low = True
            rank = 2

        elif segment[1] < 20:
            low = True
            rank = 3

        elif segment[1] < 30:
            rank = 4

        elif segment[1] < 50:
            rank = 5

        elif segment[1] < 80:
            rank = 6

        else:
            rank = 7

        cda = parameters.cda_base
        if low:
            cda = parameters.cda_low
        seg_power = interp_power(powers, segment[1] / 10)
        duree = time(segment[0], speed(seg_power, segment[1] / 10, parameters.weight, cda, parameters.crr, parameters.max_speed))
        times[rank] += duree
    t = 0
    for element in times:
        t += element
    return (t, times)
def get_np(powers, times, time):
    nrj = 0
    for i in range(len(powers)):
        nrj += powers[i] * powers[i] * times[i]
    return ((nrj / time) ** (1 / 2))
def renormalize(powers, times, prov_time, target):
    facteur = get_np(powers, times, prov_time) / target
    for i in range(len(powers)):
        powers[i] /= facteur
    return (powers)
def iterate(incr, powers, times, prov_time, np, baseline, parameters, segments):
    rank = len(powers) - 1
    normalised_nrj = np * np * baseline
    numbers = 0
    while rank > -1:
        slowing = False
        wrong_order = False
        while not slowing and not wrong_order:
            temporary = powers.copy()
            temporary[rank] += incr
            if rank + 1 != len(powers):
                if temporary[rank] > temporary[rank + 1]:
                    wrong_order = True

            temporary = renormalize(temporary, times, prov_time, np)
            new_time, new_times = calculate(segments, temporary, parameters)
            
            temporary = renormalize(temporary, new_times, new_time, np)
            new_time, new_times = calculate(segments, temporary, parameters)
            
            numbers += 1
            # print(numbers)
            if new_time < prov_time:
                prov_time = new_time
                times = new_times
                powers = temporary
            else:
                while not slowing:
                    temporary = powers.copy()
                    if temporary[rank]>incr:
                        temporary[rank] -= incr
                    temporary = renormalize(temporary, times, prov_time, np)
                    new_time, new_times = calculate(segments, temporary, parameters)

                    temporary = renormalize(temporary, new_times, new_time, np)
                    new_time, new_times = calculate(segments, temporary, parameters)
                    numbers += 1
                    # print(numbers)
                    if new_time < prov_time:
                        prov_time = new_time
                        times = new_times
                        powers = temporary
                    else:
                        slowing = True
                rank -= 1
    return (prov_time, times, powers)

def model(segments, np, parameters):
    powers = [np for i in range(8)]

    baseline, times = calculate(segments, powers, parameters)
    prov_time, times, powers = iterate(20, powers, times, baseline, np, baseline, parameters, segments)
    prov_time, times, powers = iterate(20, powers, times, prov_time, np, baseline, parameters, segments)
    prov_time, times, powers = iterate(5, powers, times, prov_time, np, baseline, parameters, segments)

    powers = renormalize(powers, times, prov_time, np)

    prov_time, times = calculate(segments, powers, parameters)
    powers = renormalize(powers, times, prov_time, np)
    prov_time, times = calculate(segments, powers, parameters)

    final_np = get_np(powers, times, prov_time)

    return (baseline, powers, prov_time, final_np)


MIN_SPAN_M   = 7.0   # halt subdivision when sub-segment span is below this (m)
ELEV_FLOOR_M = 10.0  # a split only occurs when real elevation deviation >= this (m)


def peucker_douglas(indexed_pts, k=10):
    """Claude_peucker_douglas: iterative RDP simplification of an elevation profile.
    Each round scans all current chords, finds each chord's worst interior point
    by perpendicular distance, then adds the globally worst one that also exceeds
    the ELEV_FLOOR_M elevation deviation. Repeats until no candidate remains."""
    n = len(indexed_pts)
    if n == 0:
        return []
    if n <= 2:
        return [p[1] for p in indexed_pts]

    selected = [0, n - 1]

    while len(selected) < k:
        best_i = -1
        best_dist = 0.0

        for seg in range(len(selected) - 1):
            li, ri = selected[seg], selected[seg + 1]
            if ri - li <= 1:
                continue
            a = indexed_pts[li][0]
            b = indexed_pts[ri][0]
            span = b[0] - a[0]
            if span < MIN_SPAN_M:
                continue
            dx, dy = b[0] - a[0], b[1] - a[1]
            chord_len = sqrt(dx * dx + dy * dy)

            # Find this chord's worst interior point
            seg_best_i = -1
            seg_best_dist = 0.0
            for i in range(li + 1, ri):
                pt = indexed_pts[i][0]
                if chord_len < 1e-12:
                    d = sqrt((pt[0] - a[0]) ** 2 + (pt[1] - a[1]) ** 2)
                else:
                    d = abs(dx * (pt[1] - a[1]) - dy * (pt[0] - a[0])) / chord_len
                if d > seg_best_dist:
                    seg_best_dist = d
                    seg_best_i = i

            if seg_best_i < 0:
                continue

            # Check elevation floor
            pt = indexed_pts[seg_best_i][0]
            t = (pt[0] - a[0]) / span if span > 0 else 0
            interp = a[1] + t * (b[1] - a[1])
            if abs(pt[1] - interp) < ELEV_FLOOR_M:
                continue

            if seg_best_dist > best_dist:
                best_dist = seg_best_dist
                best_i = seg_best_i

        if best_i < 0:
            break

        selected.append(best_i)
        selected.sort()

    return [indexed_pts[i][1] for i in selected]


def prep_points(points):
    """Claude_prep_points: annotate a profile list with original indices for peucker_douglas.
    Returns [(pt, i)] where pt=(dist_m, elev_m) and i is the position in the source list."""
    return [(pt, i) for i, pt in enumerate(points)]

def compute_section_borders(profile, cutoff, max_sections=None):
    """Claude_compute_section_borders: turn a (dist_m, elev_m) profile into homogeneous-grade
    section boundary indices. Runs peucker_douglas with the given cutoff, collapses
    duplicate consecutive borders, falls back to [0, last] if fewer than two remain, and
    (when max_sections is set) caps the count by keeping the interior borders whose
    elevation deviates most from the overall chord."""
    raw_borders = peucker_douglas(prep_points(profile), cutoff)
    borders = []
    last = -1
    for b in raw_borders:
        if b != last:
            borders.append(b)
            last = b
    if len(borders) < 2:
        borders = [0, len(profile) - 1]
    if max_sections is not None and len(borders) > max_sections + 1:
        interior = borders[1:-1]
        d0_val = profile[min(borders[0], len(profile) - 1)][0]
        h0_val = profile[min(borders[0], len(profile) - 1)][1]
        dN_val = profile[min(borders[-1], len(profile) - 1)][0]
        hN_val = profile[min(borders[-1], len(profile) - 1)][1]
        total_d = dN_val - d0_val
        slope = (hN_val - h0_val) / total_d if total_d > 0 else 0
        deviations = []
        for b in interior:
            bc = min(b, len(profile) - 1)
            h_chord = h0_val + slope * (profile[bc][0] - d0_val)
            deviations.append((abs(profile[bc][1] - h_chord), b))
        top_interior = sorted([x[1] for x in sorted(deviations, reverse=True)[:max_sections - 1]])
        borders = [borders[0]] + top_interior + [borders[-1]]
    return borders

def get_power(segments, powers, parameters):
    nrj = 0
    elapsed = 0
    for segment in segments:
        low = False
        if segment[1] < -30:
            rank = 0
        elif segment[1] < 0:
            low = True
            rank = 1

        elif segment[1] < 10:
            low = True
            rank = 2

        elif segment[1] < 20:
            low = True
            rank = 3

        elif segment[1] < 30:
            rank = 4

        elif segment[1] < 50:
            rank = 5

        elif segment[1] < 80:
            rank = 6

        else:
            rank = 7

        cda = parameters.cda_base
        if low:
            cda = parameters.cda_low
        seg_power = interp_power(powers, segment[1] / 10)
        duree = time(segment[0], speed(seg_power, segment[1] / 10, parameters.weight, cda, parameters.crr, parameters.max_speed))
        elapsed += duree
        nrj+=seg_power*seg_power*duree
    normalised = (nrj/elapsed)**(1/2)
    return(normalised)

def approximate_detailed(file, np_target, parameters, max_sections=5):
    """Claude_approximate_detailed: run peucker_douglas+calculate and return per-section breakdown.
    max_sections controls how many grade-homogeneous sections to produce (1-20)."""
    segments = gpx_segments(file)
    points = gpx_points(file)
    baseline, powers, prov_time, final_np = model(segments, np_target, parameters)

    section_borders = compute_section_borders(points, max_sections + 1, max_sections)

    border_distances = [points[min(b, len(points) - 1)][0] for b in section_borders]

    def build_sections(pw):
        """Claude_build_sections: per-section power/time/speed breakdown for a power vector."""
        sdata = []
        ntime = 0.0
        energy = 0.0
        j = 0
        while j + 1 < len(section_borders):
            seg_slice = segments[section_borders[j]:section_borders[j + 1]]
            if not seg_slice:
                j += 1
                continue
            pwr = get_power(seg_slice, pw, parameters)
            tmp_powers = [pwr for _ in range(10)]
            seg_time, _ = calculate(seg_slice, tmp_powers, parameters)
            dist = sum(s[0] for s in seg_slice)
            avg_grade_pm = sum(s[1] for s in seg_slice) / len(seg_slice)
            avg_speed = dist / seg_time * 3.6 if seg_time > 0 else 0
            sdata.append({
                'distance': round(dist, 0),
                'time': round(seg_time, 0),
                'power': round(pwr, 0),
                'speed': round(avg_speed, 1),
                'grade': round(avg_grade_pm / 10, 1)
            })
            ntime += seg_time
            energy += pwr * pwr * seg_time
            j += 1
        np_val = (energy / ntime) ** 0.5 if ntime > 0 else 0
        return sdata, ntime, np_val

    # The section-aggregated NP lands a few percent above np_target because each section
    # power is itself an RMS. Quick-and-dirty correction: measure that inflation, scale every
    # bucket power down by it, and rebuild once so the reported NP matches the target.
    _, _, measured_np = build_sections(powers)
    if measured_np > 0:
        powers = [p * np_target / measured_np for p in powers]
    section_data, new_time, total_np = build_sections(powers)
    return new_time, round(total_np, 0), section_data, border_distances

UPLOAD_FOLDER = 'templates/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
#
#
#
#
#
#
#
#
#
#
#
#
#
#                                       Website related stuff
#
#
#
#
#
#
#

@app.route('/download/<path:document_path>', methods=['GET'])
def f_download_document(document_path):
    return send_file('templates/uploads/'+document_path+'.pdf', as_attachment = True)
@app.route('/uploads/<path:filename>')
def show_file(filename):
    # Specify the directory where the files are stored, relative to your app's root
    return send_from_directory('templates/uploads', filename)

@app.route('/')
def f_root():
    # Claude_root: redirect bare root URL to home, which handles guest vs logged-in branching
    return redirect(url_for('f_home'))

@app.route('/home')
def f_home():
    # Claude_home: redirect logged-in users to history; show home only to guests
    role = fetch_role()
    if role != 'guest':
        return redirect(url_for('f_history'))
    return render_template('home.html', page_permissions = page_permissions, page_titles=page_titles, role = role)

@app.route('/history')
def f_history():
    # Claude_history: fetch activities and their saved segments for the current user
    connection = sqlite3.connect('templates/data.db')
    cursor = connection.cursor()
    cursor.execute("SELECT id_user FROM users WHERE email = ?", (session['username'],))
    idu = cursor.fetchall()[0][0]
    cursor.execute('SELECT id_analysis,length, title, day, distance FROM files WHERE id_user = ? ORDER BY id_analysis DESC', (idu,))
    data = cursor.fetchall()
    segments_by_activity = {}
    for row in data:
        id_act = row[0]
        cursor.execute("SELECT id_segments, title, cda, comment, cda_data FROM segments WHERE id_analysis = ?", (id_act,))
        segments_by_activity[id_act] = cursor.fetchall()
    connection.close()
    return render_template('history.html', user = idu, role = fetch_role, data = data, segments_by_activity = segments_by_activity, page_permissions = page_permissions, page_titles=page_titles)

@app.route('/register', methods=['POST'])
def f_register():
    # Claude_f_register: create user with username and password, no email verification required
    if request.method == 'POST':
        mail = request.form['email']
        password = request.form['password']

        conn = sqlite3.connect('templates/data.db')
        cursor = conn.cursor()
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        try:
            cursor.execute("INSERT INTO users (email, password, status, credit, verified) VALUES (?, ?, ?, ?, ?)", (mail, hashed_password, 'user', 100, 1))
            conn.commit()
            conn.close()
            flash('Registration successful!', 'success')
            return redirect(url_for('go_to_login'))

        except IntegrityError:
            conn.rollback()
            conn.close()
            flash('Username already in use!', 'error')
            return redirect(url_for('go_to_login'))
        finally:
            try:
                conn.close()
            except Exception:
                pass

@app.route('/login', methods=['POST'])
def f_login():
    #if request.method == 'POST':
        print('Attempting login')
        mail = request.form['email']
        password = request.form['password']

        conn = sqlite3.connect('templates/data.db')
        cursor = conn.cursor()
        print(mail, type(mail))
        cursor.execute("SELECT * FROM users WHERE email=?", (mail,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['username'] = user[1]
            flash('Bienvenue '+user[1]+' !', 'success')
            return redirect(url_for('f_history'))
        else:
            flash('Invalid username or password', 'error')
            return redirect(url_for('go_to_login'))

@app.route('/logout')
def f_logout():
    del session['username']
    flash('Logged out', 'error')
    return(redirect(url_for('f_home')))

@app.route('/upload', methods = ['POST'])
def f_upload(): 
    connection = sqlite3.connect('templates/data.db')
    cursor = connection.cursor()
    cursor.execute("SELECT id_user FROM users WHERE email = ?", (session['username'],))
    iduser = cursor.fetchall()[0][0]

    file = request.files['file']
    file_extension = file.filename.rsplit('.', 1)[1].lower()

    if file_extension == 'fit':
        cursor.execute("INSERT INTO files (id_user) VALUES (?)", (iduser,))
        connection.commit()
        cursor.execute('SELECT id_analysis FROM files WHERE id_user = ? ORDER BY id_analysis DESC', (iduser,))
        idactivite = cursor.fetchall()[0][0]

        file = request.files['file']
        file_extension = file.filename.rsplit('.', 1)[1].lower()
        filename = os.path.join(app.config['UPLOAD_FOLDER'], 'Activite'+str(iduser)+'_'+str(idactivite)+'.'+file_extension)
        file.save(filename)
        points, lapstamps = extract_data("templates/uploads/"+'Activite'+str(iduser)+'_'+str(idactivite)+'.'+file_extension)
        length = len(points)
        connection.commit()
        coords = []
        power = []
        date = points[0].timestamp.strftime('%d/%m/%Y')
        for point in points:
            coords.append([point.latitude, point.longitude])
            power.append(point.power)
        avg_power = 0
        for powe in power:
            avg_power+=powe
        avg_power/=length
        distance = points[len(points)-1].distance/1000
        distance = round(distance, 3)
        avg_power = round(avg_power, 3)
        cursor.execute('UPDATE files SET (length, day, title, distance, avg_pwr) = (?,?,?,?,?) WHERE id_analysis = ?', (length, date, 'New Activity', distance, avg_power, idactivite))
        connection.commit()
        connection.close()
        parameters = [iduser, idactivite]
        print(f'Parsed activity {idactivite}: {len(coords)} points')
        return render_template('visualise.html', parameters = parameters, data = coords, power = power, start = 0, end = len(power)-1, results = [], page_permissions = page_permissions, role = fetch_role, page_titles = page_titles)
    

    elif file_extension == 'gpx':
        original_name = request.files['file'].filename.rsplit('.', 1)[0]
        cursor.execute("INSERT INTO gpx (id_user, title) VALUES (?, ?)", (iduser, original_name))
        connection.commit()
        cursor.execute('SELECT id_route FROM gpx WHERE id_user = ? ORDER BY id_route DESC', (iduser,))
        idroute = cursor.fetchall()[0][0]

        file = request.files['file']
        file_extension = file.filename.rsplit('.', 1)[1].lower()
        filename = os.path.join(app.config['UPLOAD_FOLDER'], 'Route'+str(iduser)+'_'+str(idroute)+'.'+file_extension)
        file.save(filename)

        gpx_path = "templates/uploads/"+'Route'+str(iduser)+'_'+str(idroute)+'.'+file_extension
        raw_pts = gpx_raw_points(gpx_path)
        profile = gpx_points(gpx_path)
        total_dist = round(profile[-1][0] / 1000, 3) if profile else 0
        cursor.execute('UPDATE gpx SET length = ?, distance = ? WHERE id_route = ?', (len(raw_pts), total_dist, idroute))
        connection.commit()
        connection.close()
        return redirect('/view_route?q=' + encode_q(0, len(raw_pts), str(iduser) + ',' + str(idroute)))
@app.route('/visualise')
def f_visualise():
    # Claude_f_visualise: decode opaque q param
    start, end, data_str = decode_q(request.args.get('q'))
    datas = list(map(str, data_str.split(',')))
    user, id_act = int(datas[0]), int(datas[1])
    points, lapstamps = extract_data("templates/uploads/"+'Activite'+str(user)+'_'+str(id_act)+'.fit')
    coords = []
    power = []
    altitude = []
    i = 0
    for point in points:
        if i%1==0:
            coords.append([point.latitude, point.longitude])
            power.append(point.power)
            altitude.append(point.altitude/2)
        i+=1
    points = points[start:end]
    points = aggregate_segments(make_segments(points), 3)

    connection = sqlite3.connect('templates/data.db')
    cursor = connection.cursor()
    cursor.execute("SELECT id_segments, title, cda, comment FROM segments WHERE id_analysis = ?", (id_act,))
    results = cursor.fetchall()
    print(f'Activity {id_act}: {len(results)} saved segments')
    connection.close()

    parameters = [user, id_act]

    return render_template('visualise.html', parameters = parameters, data = coords, start = start, end = end, results = results, page_permissions = page_permissions, role = fetch_role, page_titles = page_titles)

@app.route('/new_segment')
def f_new_segment():
    # Claude_new_segment: load activity, compute lap indices, pass to segment template
    start, end, data_str = decode_q(request.args.get('q'))
    datas = list(map(str, data_str.split(',')))
    user, id_act = int(datas[0]), int(datas[1])
    all_points, lapstamps = extract_data("templates/uploads/"+'Activite'+str(user)+'_'+str(id_act)+'.fit')
    coords = []
    power = []
    altitude = []
    distances = []
    speed = []
    for point in all_points:
        coords.append([point.latitude, point.longitude])
        power.append(point.power)
        altitude.append(point.altitude/2)
        distances.append(round(point.distance, 1))
        speed.append(round((point.speed or 0) * 3.6, 2))

    # Convert lapstamp boundaries to point indices as [[start, end], ...]
    lap_start_times = {lap[0] for lap in lapstamps}
    lap_end_times   = {lap[1] for lap in lapstamps}
    lap_start_map = {pt.timestamp: i for i, pt in enumerate(all_points) if pt.timestamp in lap_start_times}
    lap_end_map   = {pt.timestamp: i for i, pt in enumerate(all_points) if pt.timestamp in lap_end_times}
    lap_bounds = []
    for lap in lapstamps:
        s = lap_start_map.get(lap[0])
        e = lap_end_map.get(lap[1])
        if s is not None and e is not None:
            lap_bounds.append([s, e])
    lap_indices = [b[1] for b in lap_bounds]

    points = all_points[start:end]
    points = aggregate_segments(make_segments(points), 3)

    connection = sqlite3.connect('templates/data.db')
    cursor = connection.cursor()
    cursor.execute("SELECT id_segments, title, cda, comment FROM segments WHERE id_analysis = ?", (id_act,))
    results = cursor.fetchall()
    connection.close()

    parameters = [user, id_act]

    total_length = len(all_points)
    return render_template('segment.html', parameters = parameters, data = coords, power = power, elevation = altitude, distances = distances, speed = speed, start = start, end = end, total_length = total_length, results = results, lap_indices = lap_indices, lap_bounds = lap_bounds, page_permissions = page_permissions, role = fetch_role, page_titles = page_titles)

@app.route('/calculate')
def f_calculate():
    # Claude_f_calculate: peucker_douglas multi-section CdA calculation
    start, end, data_str = decode_q(request.args.get('q'))
    datas = list(map(str, data_str.split(',')))
    user, id_act = int(datas[0]), int(datas[1])
    crr, weight, efficiency = float(datas[2]), float(datas[3]), float(datas[4])
    all_points, lapstamps = extract_data("templates/uploads/"+'Activite'+str(user)+'_'+str(id_act)+'.fit')

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

    border_distances = [profile[min(b, len(profile)-1)][0] for b in section_borders]
    params_meta = {'user': user, 'id_act': id_act, 'crr': crr, 'weight': weight, 'efficiency': efficiency, 'start': start, 'end': end}
    return render_template('save_comment.html',
        params_meta=params_meta,
        sections=sections,
        rep_cda=round(rep_cda, 4),
        avg_speed=round(avg_speed_all, 1),
        avg_power=round(avg_pwr_all, 0),
        total_dist=round(total_dist, 0),
        profile=profile,
        border_distances=border_distances,
        page_permissions=page_permissions, role=fetch_role, page_titles=page_titles)

@app.route('/save_segment', methods=['POST'])
def f_save_segment():
    # Claude_f_save_segment: save segment with per-section CdA data as JSON
    iduser = request.form['iduser']
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

    rep_cda = round(rep_cda, 3)
    parameters_str = 'CRR:' + crr + ',Weight:' + weight + ',Efficiency:' + efficiency

    connection = sqlite3.connect('templates/data.db')
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO segments (id_analysis, start_pt, end_pt, parameters, cda, title, comment, cda_data) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (idactivity, start, end, parameters_str, rep_cda, title, comments, cda_data_json)
    )
    connection.commit()
    cursor.execute('SELECT length FROM files WHERE id_analysis = ?', (idactivity,))
    row = cursor.fetchone()
    connection.close()
    activity_length = row[0] if row else 0
    return redirect('/visualise?q=' + encode_q(0, activity_length, iduser + ',' + idactivity))

@app.route('/close_window')
def f_close_window():
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

@app.route('/view_segment')
def f_view_segment():
    # Claude_f_view_segment: show saved segment with map, charts, peucker overlay and per-section CdA
    start, end, data_str = decode_q(request.args.get('q'))
    datas = data_str.split(',')
    user, seg_id = int(datas[0]), int(datas[1])

    connection = sqlite3.connect('templates/data.db')
    cursor = connection.cursor()
    cursor.execute(
        'SELECT id_analysis, start_pt, end_pt, parameters, cda, title, comment, cda_data FROM segments WHERE id_segments = ?',
        (seg_id,)
    )
    row = cursor.fetchone()
    connection.close()
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

    all_points, _ = extract_data("templates/uploads/Activite" + str(user) + '_' + str(id_act) + '.fit')
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
        param_vals=param_vals,
        page_permissions=page_permissions, role=fetch_role, page_titles=page_titles)

@app.route('/delete_segment', methods = ['GET', 'POST'])
def f_delete_segment():
    # Claude_delete_segment: delete a segment and redirect to history or visualise
    seg = request.form['supression']
    from_history = request.form.get('from_history', '0')
    connection = sqlite3.connect('templates/data.db')
    cursor = connection.cursor()
    cursor.execute('SELECT id_analysis FROM segments WHERE id_segments = ?', (seg,))
    analysis = cursor.fetchone()[0]

    cursor.execute('DELETE FROM segments WHERE id_segments = ?', (seg,))
    connection.commit()

    if from_history == '1':
        connection.close()
        return redirect(url_for('f_history'))

    cursor.execute('SELECT id_user, length FROM files WHERE id_analysis = ?', (analysis,))
    id_user, length = cursor.fetchone()
    connection.close()
    return redirect('/visualise?q=' + encode_q(0, length, str(id_user) + ',' + str(analysis)))

@app.route('/edit_segment', methods=['POST'])
def f_edit_segment():
    # Claude_edit_segment: update segment title and comment from history tab
    seg_id = request.form['id_segments']
    new_title = request.form['title']
    new_comment = request.form['comment']
    connection = sqlite3.connect('templates/data.db')
    cursor = connection.cursor()
    cursor.execute('UPDATE segments SET title = ?, comment = ? WHERE id_segments = ?', (new_title, new_comment, seg_id))
    connection.commit()
    connection.close()
    return redirect(url_for('f_history'))

@app.route('/update_segment', methods=['POST'])
def f_update_segment():
    # Claude_update_segment: save edits and fully recalculate CdA with new parameters
    seg_id = request.form['id_segments']
    user = request.form['user']
    new_title = request.form['title'].strip()
    new_comment = request.form['comment'].strip()
    crr = float(request.form['crr'].strip())
    weight = float(request.form['weight'].strip())
    efficiency = float(request.form['efficiency'].strip())
    parameters_str = 'CRR:' + str(crr) + ',Weight:' + str(weight) + ',Efficiency:' + str(efficiency)

    connection = sqlite3.connect('templates/data.db')
    cursor = connection.cursor()
    cursor.execute('SELECT id_analysis, start_pt, end_pt FROM segments WHERE id_segments = ?', (seg_id,))
    row = cursor.fetchone()
    connection.close()
    if not row:
        return redirect('/history')
    id_act, start_pt, end_pt = row

    all_points, _ = extract_data("templates/uploads/Activite" + str(user) + '_' + str(id_act) + '.fit')
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

    connection = sqlite3.connect('templates/data.db')
    cursor = connection.cursor()
    cursor.execute(
        'UPDATE segments SET title = ?, comment = ?, parameters = ?, cda = ?, cda_data = ? WHERE id_segments = ?',
        (new_title, new_comment, parameters_str, rep_cda, json.dumps(sections), seg_id)
    )
    connection.commit()
    connection.close()
    return redirect('/view_segment?q=' + encode_q(0, 0, user + ',' + seg_id))

@app.route('/rename_activity', methods=['POST'])
def f_rename_activity():
    # Claude_rename_activity: update the title of an activity for the current user
    id_analysis = request.form['id_analysis']
    new_title = request.form['new_title'].strip()
    connection = sqlite3.connect('templates/data.db')
    cursor = connection.cursor()
    cursor.execute('UPDATE files SET title = ? WHERE id_analysis = ?', (new_title, id_analysis))
    connection.commit()
    connection.close()
    return redirect('/history')

@app.route('/delete_file', methods = ['GET', 'POST'])
def f_delete_file():
    file = request.form['supression']
    connection = sqlite3.connect('templates/data.db')
    cursor = connection.cursor()

    cursor.execute('DELETE FROM files WHERE id_analysis = ?', (file,))
    connection.commit()
    

    return redirect('/history')


@app.route('/routes')
def f_routes():
    # Claude_f_routes: list GPX routes for the current user
    connection = sqlite3.connect('templates/data.db')
    cursor = connection.cursor()
    cursor.execute("SELECT id_user FROM users WHERE email = ?", (session['username'],))
    idu = cursor.fetchall()[0][0]
    cursor.execute('SELECT id_route, title, distance FROM gpx WHERE id_user = ? ORDER BY id_route DESC', (idu,))
    routes = cursor.fetchall()
    connection.close()
    return render_template('routes.html', user=idu, routes=routes, page_permissions=page_permissions, role=fetch_role, page_titles=page_titles)

@app.route('/view_route')
def f_view_route():
    # Claude_f_view_route: show GPX map and param form for a route
    start, end, data_str = decode_q(request.args.get('q'))
    datas = data_str.split(',')
    user, id_route = int(datas[0]), int(datas[1])
    gpx_path = "templates/uploads/Route" + str(user) + '_' + str(id_route) + '.gpx'
    raw_pts = gpx_raw_points(gpx_path)
    profile = gpx_points(gpx_path)
    connection = sqlite3.connect('templates/data.db')
    cursor = connection.cursor()
    cursor.execute('SELECT title, distance FROM gpx WHERE id_route = ?', (id_route,))
    row = cursor.fetchone()
    connection.close()
    title = row[0] if row else ''
    total_dist = row[1] if row else 0
    return render_template('view_route.html',
        user=user, id_route=id_route, raw_pts=raw_pts, profile=profile,
        title=title, total_dist=total_dist,
        results=None, section_data=None, border_distances=[], max_sections=5,
        page_permissions=page_permissions, role=fetch_role, page_titles=page_titles)

@app.route('/calculate_route', methods=['POST'])
def f_calculate_route():
    # Claude_f_calculate_route: run peucker_douglas+calculate on GPX and return sections
    user = int(request.form['user'])
    id_route = int(request.form['id_route'])
    crr = float(request.form['crr'])
    weight = float(request.form['weight'])
    cda_flat = float(request.form['cda_flat'])
    cda_up = float(request.form['cda_up'])
    np_target = float(request.form['np_target'])
    gpx_path = "templates/uploads/Route" + str(user) + '_' + str(id_route) + '.gpx'

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
    connection = sqlite3.connect('templates/data.db')
    cursor = connection.cursor()
    cursor.execute('SELECT title, distance FROM gpx WHERE id_route = ?', (id_route,))
    row = cursor.fetchone()
    connection.close()
    title = row[0] if row else ''
    total_dist = row[1] if row else 0
    results = {'time': time_str, 'np': round(total_np, 0)}
    form_vals = {'crr': crr, 'weight': weight, 'cda_flat': cda_flat, 'cda_up': cda_up, 'np_target': np_target}
    return render_template('view_route.html',
        user=user, id_route=id_route, raw_pts=raw_pts, profile=profile,
        title=title, total_dist=total_dist,
        results=results, section_data=section_data, border_distances=border_distances,
        max_sections=max_sections, form_vals=form_vals,
        page_permissions=page_permissions, role=fetch_role, page_titles=page_titles)

@app.route('/toptube_pdf', methods=['POST'])
def f_toptube_pdf():
    # Claude_f_toptube_pdf: generate print-ready top-tube card with per-section power, grade, time
    user = int(request.form['user'])
    id_route = int(request.form['id_route'])
    crr = float(request.form['crr'])
    weight = float(request.form['weight'])
    cda_flat = float(request.form['cda_flat'])
    cda_up = float(request.form['cda_up'])
    np_target = float(request.form['np_target'])
    max_sections = int(request.form.get('max_sections', 5))
    orientation = request.form.get('orientation', 'horizontal')
    gpx_path = "templates/uploads/Route" + str(user) + '_' + str(id_route) + '.gpx'

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

    connection = sqlite3.connect('templates/data.db')
    cursor = connection.cursor()
    cursor.execute('SELECT title, distance FROM gpx WHERE id_route = ?', (id_route,))
    row = cursor.fetchone()
    connection.close()
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

@app.route('/rename_route', methods=['POST'])
def f_rename_route():
    # Claude_f_rename_route: update route title
    id_route = request.form['id_route']
    new_title = request.form['new_title'].strip()
    connection = sqlite3.connect('templates/data.db')
    cursor = connection.cursor()
    cursor.execute('UPDATE gpx SET title = ? WHERE id_route = ?', (new_title, id_route))
    connection.commit()
    connection.close()
    return redirect('/routes')

@app.route('/delete_route', methods=['POST'])
def f_delete_route():
    # Claude_f_delete_route: remove route from DB (file stays on disk)
    id_route = request.form['id_route']
    connection = sqlite3.connect('templates/data.db')
    cursor = connection.cursor()
    cursor.execute('DELETE FROM gpx WHERE id_route = ?', (id_route,))
    connection.commit()
    connection.close()
    return redirect('/routes')

@app.route('/login')
def go_to_login():
    return render_template('login_page.html')
@app.route('/register')
def go_to_register():
    return render_template('register.html')
@app.route('/upload')
def f_go_to_upload():
    return render_template('upload.html', role = fetch_role, page_permissions=page_permissions, page_titles=page_titles)
@app.route('/how-it-works')
def f_how_it_works():
    # Claude_f_how_it_works: render the How it works explainer page
    return render_template('how_it_works.html', role=fetch_role, page_permissions=page_permissions, page_titles=page_titles)
@app.route('/whitepaper')
def f_whitepaper():
    # Claude_f_whitepaper: render the technical whitepaper page
    return render_template('whitepaper.html', role=fetch_role, page_permissions=page_permissions, page_titles=page_titles)
#############################################################################################################
if __name__ == '__main__':
    init_db()
    app.run(debug=True)