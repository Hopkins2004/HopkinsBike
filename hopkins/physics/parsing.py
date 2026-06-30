"""FIT/GPX parsing and geometry: raw files -> points / segments / elevation profiles."""
from math import atan2, cos, pi, sin, sqrt

import gpxpy.gpx
from fitparse import FitFile


class fitpoint:
    def __init__(self, timestamp, altitude, distance, speed, hr, cadence, temperature, power, latitude, longitude):
        """Claude_fitpoint_init: one parsed FIT record sample."""
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
        """Claude_fitsegment_init: an aggregated stretch between two FIT samples."""
        self.time = time
        self.altitude = altitude
        self.distance = distance
        self.speedstart = speedstart
        self.speedend = speedend
        self.avg_speed = distance / time
        self.avg_hr = avg_hr
        self.avg_cadence = avg_cadence
        self.avg_temperature = avg_temperature
        self.avg_power = avg_power
        self.grade = altitude / (distance + 0.01) * 100


def extract_data(filename):
    """Claude_extract_data: parse a FIT file into (points, lapstamps); drop corrupt samples."""
    activity = FitFile(filename)
    activity.parse()
    records = list(activity.get_messages(name='lap'))
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
            latitude /= 11930465
        except TypeError:
            corrupt = True
        longitude = rec.get_value('position_long')
        try:
            longitude /= 11930465
        except TypeError:
            corrupt = True
        try:
            altitude /= 1
        except TypeError:
            corrupt = True
        if power is None:
            power = 0
        if hr is None:
            hr = 0
        point = fitpoint(timestamp, altitude, distance, speed, hr, cadence, temperature, power, latitude, longitude)
        if not corrupt:
            points.append(point)
    return (points, lapstamps)


def make_segments(points):
    """Claude_make_segments: build per-sample fitsegments between consecutive points."""
    rank = 0
    segments = []
    while rank < len(points) - 1:
        start = points[rank]
        finish = points[rank + 1]
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
        rank += 1
    return (segments)


def aggregate_segments(segments, nb_segments):
    """Claude_aggregate_segments: merge runs of nb_segments micro-segments, cropping the ends."""
    rank = nb_segments  # crop the very start
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
            avg_hr += segment.time * segment.avg_hr
            avg_cadence += segment.time * segment.avg_cadence
            avg_power += segment.time * segment.avg_power
            rank += 1
        avg_hr /= time
        avg_cadence /= time
        avg_temperature /= time
        avg_power /= time
        speedend = segments[rank].speedend
        if distance != 0:
            new_segment = fitsegment(time, altitude, distance, speedstart, speedend, avg_hr, avg_cadence, avg_temperature, avg_power)
            new_segments.append(new_segment)
    return (new_segments)


def distgrad_gpx(point1, point2):
    """Claude_distgrad_gpx: haversine distance (m) and elevation delta between two GPX points."""
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


def _read_gpx_points(file):
    """Claude__read_gpx_points: flatten all track/segment points of a GPX file into a list."""
    gpx_file = open(file, 'r')
    gpx = gpxpy.parse(gpx_file)
    points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                points.append(point)
    return points


def gpx_segments(file):
    """Claude_gpx_segments: turn a GPX track into [distance_m, grade_permille] ~100 m segments."""
    points = _read_gpx_points(file)
    i = 0
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
    """Claude_gpx_raw_points: return [[lat, lon], ...] for every point of a GPX track."""
    points = _read_gpx_points(file)
    good_points = []
    for point in points:
        good_points.append([point.latitude, point.longitude])
    return (good_points)


def gpx_points(file):
    """Claude_gpx_points: build a (cumulative_distance_m, elevation_m) profile every ~100 m."""
    points = _read_gpx_points(file)
    i = 0
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
