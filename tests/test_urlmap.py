"""URL-map regression test.

tests/fixtures/urlmap.json was captured from the original app.py. After the blueprint
split the endpoint *names* change (they become `blueprint.func`), but the exposed URL
rules and HTTP methods must stay identical. This asserts that the public surface is
unchanged.
"""
import json
import os

import app

HERE = os.path.dirname(__file__)
EXPECTED = [tuple([r[0], tuple(r[1])]) for r in
            json.load(open(os.path.join(HERE, "fixtures", "urlmap.json")))]


def _current():
    """Claude__current: (rule, methods) pairs of the live app, ignoring HEAD/OPTIONS."""
    flask_app = app.app
    rules = sorted(
        (r.rule, tuple(sorted(m for m in r.methods if m not in ("HEAD", "OPTIONS"))))
        for r in flask_app.url_map.iter_rules()
    )
    return rules


def test_url_rules_unchanged():
    assert _current() == sorted(EXPECTED)
