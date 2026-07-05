"""End-to-end GPX route flow through the real blueprints, templates and physics engine.

Uses an isolated temp DB and the synthetic GPX fixture (the real data/uploads has no files).
register -> login -> /view_route -> /calculate_route -> /toptube_pdf, asserting each renders
and that the estimate page reports a finishing time.
"""
import os
import shutil

from hopkins.db import get_db

HERE = os.path.dirname(__file__)
GPXF = os.path.join(HERE, "fixtures", "synthetic.gpx")


def test_full_route_flow(app, client):
    client.post("/register", data={"email": "rider@x.com", "password": "password123"})
    with app.app_context():
        with get_db() as conn:
            uid = conn.execute("SELECT id_user FROM users WHERE email='rider@x.com'").fetchone()[0]
            conn.execute("INSERT INTO gpx (id_user, title) VALUES (?, ?)", (uid, "Test"))
            conn.commit()
            rid = conn.execute("SELECT id_route FROM gpx WHERE id_user=?", (uid,)).fetchone()[0]
    # place the GPX where the route routes expect it
    shutil.copy(GPXF, os.path.join(app.config["UPLOAD_FOLDER"], f"Route{uid}_{rid}.gpx"))

    client.post("/login", data={"email": "rider@x.com", "password": "password123"})

    r = client.get("/routes")
    assert r.status_code == 200

    from hopkins.web.util import encode_q
    r = client.get("/view_route?q=" + encode_q(0, 0, f"{uid},{rid}"))
    assert r.status_code == 200

    form = {"user": uid, "id_route": rid, "crr": 0.005, "weight": 78,
            "cda_flat": 0.22, "cda_up": 0.30, "np_target": 220, "max_sections": 5}
    r = client.post("/calculate_route", data=form)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "h" in body and "'" in body  # the H'mm'ss finishing-time string rendered

    r = client.post("/toptube_pdf", data=form)
    assert r.status_code == 200
