"""Route power model: estimate ride time / power profile for a GPX route, plus the
Peucker-Douglas section splitter used to break a route into grade-homogeneous sections."""
from math import acos, copysign, cos, pi, sqrt

from .parsing import gpx_points, gpx_segments


class parameter():
    def __init__(self):
        """Claude_parameter_init: tunable inputs for the route power model."""
        self.cda_low = 0
        self.cda_base = 0
        self.weight = 0
        self.crr = 0
        self.max_speed = 0


def power(speed, grade, weight, cda, crr):
    """Claude_power: power (W) to hold `speed` at `grade` for the given rider/bike."""
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
    """Claude_speed: closed-form speed from power and grade, capped at max_speed."""
    v = solve_cubic_speed(pwr, grade, weight, cda, crr)
    v = max(v, 0.0)
    if v > max_speed / 3.6:
        return max_speed / 3.6
    return v


def time(distance, speed):
    """Claude_time: seconds to cover `distance` at `speed`."""
    return (distance / speed)


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


def grade_rank(grade_permille):
    """Claude_grade_rank: bucket a per-mille gradient into (rank 0-7, is_low) for the
    8-way power split. `is_low` marks the shallow buckets that use the low-CdA value.
    Single source of truth shared by calculate() and get_power()."""
    if grade_permille < -30:
        return 0, False
    if grade_permille < 0:
        return 1, True
    if grade_permille < 10:
        return 2, True
    if grade_permille < 20:
        return 3, True
    if grade_permille < 30:
        return 4, False
    if grade_permille < 50:
        return 5, False
    if grade_permille < 80:
        return 6, False
    return 7, False


def calculate(segments, powers, parameters):
    """Claude_calculate: total time (and per-bucket time) to ride `segments` at `powers`."""
    times = [0 for i in range(len(powers))]
    for segment in segments:
        rank, low = grade_rank(segment[1])
        cda_val = parameters.cda_base
        if low:
            cda_val = parameters.cda_low
        seg_power = interp_power(powers, segment[1] / 10)
        duree = time(segment[0], speed(seg_power, segment[1] / 10, parameters.weight, cda_val, parameters.crr, parameters.max_speed))
        times[rank] += duree
    t = 0
    for element in times:
        t += element
    return (t, times)


def get_np(powers, times, time):
    """Claude_get_np: normalised power from per-bucket powers and their durations."""
    nrj = 0
    for i in range(len(powers)):
        nrj += powers[i] * powers[i] * times[i]
    return ((nrj / time) ** (1 / 2))


def renormalize(powers, times, prov_time, target):
    """Claude_renormalize: scale bucket powers so their NP equals `target`."""
    facteur = get_np(powers, times, prov_time) / target
    for i in range(len(powers)):
        powers[i] /= facteur
    return (powers)


def iterate(incr, powers, times, prov_time, np, baseline, parameters, segments):
    """Claude_iterate: greedy per-bucket power search that minimises ride time at fixed NP."""
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
            if new_time < prov_time:
                prov_time = new_time
                times = new_times
                powers = temporary
            else:
                while not slowing:
                    temporary = powers.copy()
                    if temporary[rank] > incr:
                        temporary[rank] -= incr
                    temporary = renormalize(temporary, times, prov_time, np)
                    new_time, new_times = calculate(segments, temporary, parameters)

                    temporary = renormalize(temporary, new_times, new_time, np)
                    new_time, new_times = calculate(segments, temporary, parameters)
                    numbers += 1
                    if new_time < prov_time:
                        prov_time = new_time
                        times = new_times
                        powers = temporary
                    else:
                        slowing = True
                rank -= 1
    return (prov_time, times, powers)


def model(segments, np, parameters):
    """Claude_model: optimise the 8-bucket power profile for a route at target NP `np`."""
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


MIN_SPAN_M = 7.0     # halt subdivision when sub-segment span is below this (m)
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
    """Claude_get_power: normalised power achieved riding `segments` at profile `powers`."""
    nrj = 0
    elapsed = 0
    for segment in segments:
        rank, low = grade_rank(segment[1])
        cda_val = parameters.cda_base
        if low:
            cda_val = parameters.cda_low
        seg_power = interp_power(powers, segment[1] / 10)
        duree = time(segment[0], speed(seg_power, segment[1] / 10, parameters.weight, cda_val, parameters.crr, parameters.max_speed))
        elapsed += duree
        nrj += seg_power * seg_power * duree
    normalised = (nrj / elapsed) ** (1 / 2)
    return (normalised)


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
