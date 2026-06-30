"""Golden-value regression tests for the physics engine.

The expected values in tests/fixtures/golden.json were captured from the ORIGINAL
monolithic app.py before the package split. These tests assert the (relocated) physics
functions still produce byte-identical numeric output, proving the refactor changed
structure only, not behaviour.

Functions are reached through the `app` module, which after the split is a shim that
re-exports the physics symbols from the hopkins package.
"""
import json
import math
import os

import app  # the shim re-exports physics + the Flask app

HERE = os.path.dirname(__file__)
GOLDEN = json.load(open(os.path.join(HERE, "fixtures", "golden.json")))
GPXF = os.path.join(HERE, "fixtures", "synthetic.gpx")

REL = 1e-9  # relative tolerance for floats


def _close(a, b):
    """Claude__close: recursive near-equality for nested numbers/lists/dicts."""
    if isinstance(a, dict):
        assert a.keys() == b.keys()
        return all(_close(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        assert len(a) == len(b)
        return all(_close(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=REL, abs_tol=1e-9)
    return a == b


def _param():
    """Claude__param: build the parameter() object used across the golden captures."""
    p = app.parameter()
    p.cda_low, p.cda_base, p.weight, p.crr, p.max_speed = 0.22, 0.30, 78.0, 0.005, 60
    return p


SEGS = [[80, -50], [80, -10], [80, 5], [80, 30], [80, 60], [80, 120], [100, 5],
        [100, 15], [90, -25], [90, 40], [70, 90], [110, -5]]
PROFILE = [(i * 20.0, 1000 + (i * 0.5 if i < 20 else 10 - (i - 20) * 0.3)) for i in range(40)]


def test_cda():
    seg = app.fitsegment(10.0, 2.0, 80.0, 8.0, 8.5, 140, 90, 20, 250)
    assert _close(app.cda(seg, 0.005, 80.0, 0.97), GOLDEN["cda"])


def test_power():
    assert _close(app.power(11.0, 3.0, 78.0, 0.28, 0.005), GOLDEN["power"])


def test_solve_cubic_speed():
    got = [app.solve_cubic_speed(250, 0.0, 78, 0.28, 0.005),
           app.solve_cubic_speed(300, 5.0, 78, 0.30, 0.005),
           app.solve_cubic_speed(200, -4.0, 78, 0.25, 0.004),
           app.solve_cubic_speed(0, 0.0, 78, 0.28, 0.005)]
    assert _close(got, GOLDEN["solve_cubic_speed"])


def test_speed():
    got = [app.speed(250, 0.0, 78, 0.28, 0.005, 60),
           app.speed(900, -8.0, 78, 0.25, 0.004, 60)]
    assert _close(got, GOLDEN["speed"])


def test_get_crr():
    assert _close(app.get_crr(20), GOLDEN["get_crr"])


def test_interp_power():
    got = [app.interp_power([100, 150, 200, 210, 220, 240, 260, 300], g)
           for g in [-10, -5, -1, 0.5, 2, 5, 9, 12]]
    assert _close(got, GOLDEN["interp_power"])


def test_calculate():
    t, times = app.calculate(SEGS, [200] * 8, _param())
    assert _close({"t": t, "times": times}, GOLDEN["calculate"])


def test_get_power():
    assert _close(app.get_power(SEGS, [200] * 8, _param()), GOLDEN["get_power"])


def test_model():
    baseline, powers, prov_time, final_np = app.model(SEGS, 220.0, _param())
    got = {"baseline": baseline, "powers": powers, "prov_time": prov_time, "final_np": final_np}
    assert _close(got, GOLDEN["model"])


def test_peucker_douglas():
    assert _close(app.peucker_douglas(app.prep_points(PROFILE), 10), GOLDEN["peucker_douglas"])


def test_compute_section_borders():
    assert _close(app.compute_section_borders(PROFILE, 6, 5), GOLDEN["compute_section_borders_a"])
    assert _close(app.compute_section_borders(PROFILE, 21), GOLDEN["compute_section_borders_b"])


def test_gpx_parsing():
    assert app.gpx_segments(GPXF)[:5] == [list(x) for x in GOLDEN["gpx_segments_head"]] \
        or _close(app.gpx_segments(GPXF)[:5], GOLDEN["gpx_segments_head"])
    assert len(app.gpx_segments(GPXF)) == GOLDEN["gpx_segments_len"]
    assert len(app.gpx_points(GPXF)) == GOLDEN["gpx_points_len"]
    assert len(app.gpx_raw_points(GPXF)) == GOLDEN["gpx_raw_points_len"]


def test_approximate_detailed():
    nt, tnp, sdata, bdist = app.approximate_detailed(GPXF, 220.0, _param(), 5)
    got = {"time": nt, "np": tnp, "sections": sdata, "borders": bdist}
    assert _close(got, GOLDEN["approximate_detailed"])
