"""Every known gap is classified: fixed, accepted with a rationale, or follow-up with an owner.

Fails CI when someone adds an xfail without registering it, removes a test but
leaves its entry, or registers a gap without a valid disposition / owner.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from conftest import REPO_ROOT
from gaps import DEMO_IMPACT, DISPOSITIONS, GAPS, TEAM

TESTS_DIR = Path(REPO_ROOT) / "tests"


def _xfail_tests() -> dict[str, str]:
    """{test function name: file} for every test decorated with xfail or @gap in tests/**."""
    found: dict[str, str] = {}
    for path in TESTS_DIR.rglob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
                continue
            for dec in node.decorator_list:
                target = dec.func if isinstance(dec, ast.Call) else dec
                name = ast.unparse(target)
                if name.endswith("xfail") or name == "gap":
                    found[node.name] = str(path.relative_to(REPO_ROOT))
    return found


XFAILS = _xfail_tests()


def test_registry_is_not_empty_and_matches_xfails():
    assert XFAILS, "no xfail tests found — registry scan is broken"


@pytest.mark.parametrize("name", sorted(XFAILS))
def test_every_xfail_is_registered(name):
    assert name in GAPS, (f"{name} ({XFAILS[name]}) is marked xfail but has no entry in "
                          f"tests/acceptance/gaps.py — classify it as fixed / accepted / follow_up")


@pytest.mark.parametrize("name", sorted(GAPS))
def test_registry_entry_is_valid(name):
    g = GAPS[name]
    assert g["disposition"] in DISPOSITIONS, g
    assert g["demo_impact"] in DEMO_IMPACT, g
    assert g["owner"] in TEAM, f"{name}: owner must be a named person, got {g['owner']!r}"
    assert g.get("title") and g.get("task")
    assert len(g.get("rationale", "")) >= 40, f"{name}: rationale is required"
    if g["disposition"] in ("follow_up", "accepted"):
        assert g.get("when"), f"{name}: say until when / before what"


@pytest.mark.parametrize("name", sorted(GAPS))
def test_registry_entry_points_to_a_real_test(name):
    if GAPS[name]["disposition"] == "fixed":
        assert name not in XFAILS, f"{name} is 'fixed': remove its xfail/@gap marker"
        return
    assert name in XFAILS, (f"{name} is registered as {GAPS[name]['disposition']} but no xfail "
                            f"test with that name exists (renamed or fixed?)")


def test_demo_visible_follow_ups_have_a_deadline_before_delivery():
    for name, g in GAPS.items():
        if g["disposition"] == "follow_up" and g["demo_impact"] == "visible":
            assert "before" in g["when"].lower(), f"{name}: visible in the demo, needs a deadline"
