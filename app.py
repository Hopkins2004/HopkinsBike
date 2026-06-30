"""Backwards-compatible shim.

The monolith was split into the `hopkins` package (see hopkins/__init__.py). This module
keeps `import app` working for any external runner and for the regression tests: it exposes
the Flask app as `app.app` and re-exports the physics functions/classes that the golden
tests reference.
"""
from hopkins import create_app

# Physics surface re-exported for tests and any legacy callers.
from hopkins.physics.parsing import (  # noqa: F401
    fitpoint, fitsegment, extract_data, make_segments, aggregate_segments,
    distgrad_gpx, gpx_segments, gpx_raw_points, gpx_points,
)
from hopkins.physics.cda import cda, rideCDA, get_crr  # noqa: F401
from hopkins.physics.route import (  # noqa: F401
    parameter, power, solve_cubic_speed, speed, time, GRADE_CENTERS, interp_power,
    grade_rank, calculate, get_np, renormalize, iterate, model,
    peucker_douglas, prep_points, compute_section_borders, get_power, approximate_detailed,
)
from hopkins.web.util import encode_q, decode_q  # noqa: F401

app = create_app()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=app.config['DEBUG'])
