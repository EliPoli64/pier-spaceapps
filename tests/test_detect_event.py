"""Tests for Stage 2: detect_event (BR-1)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from piper_agent.tools.detect_event import detect_event
from piper_agent.contracts import EventResult


def test_flood_demo_returns_flood():
    res = detect_event(
        lat=41.8, lon=-93.6,
        recent_start="2025-06-20", recent_end="2025-06-25",
        demo_name="flood",
    )
    assert isinstance(res, EventResult)
    assert res.event_type == "flood", f"Expected flood, got {res.event_type}"
    assert 0.0 < res.confidence <= 1.0
    assert res.severity in ("low", "medium", "high")
    assert "cum3_mm" in res.details
    assert "flood_threshold_mm" in res.details


def test_drought_demo_returns_drought():
    res = detect_event(
        lat=9.0, lon=41.0,
        recent_start="2025-01-01", recent_end="2025-01-30",
        demo_name="drought",
    )
    assert isinstance(res, EventResult)
    assert res.event_type == "drought", f"Expected drought, got {res.event_type}"
    assert 0.0 < res.confidence <= 1.0
    assert res.severity in ("low", "medium", "high")
    assert "cum30_mm" in res.details


def test_normal_demo_returns_none():
    res = detect_event(
        lat=41.8, lon=-93.6,
        recent_start="2025-07-01", recent_end="2025-07-07",
        demo_name="normal",
    )
    assert isinstance(res, EventResult)
    assert res.event_type == "none", f"Expected none, got {res.event_type}"
    assert 0.0 < res.confidence <= 1.0


def test_confidence_in_unit_range():
    for demo in ["flood", "drought", "normal"]:
        res = detect_event(
            lat=41.8, lon=-93.6,
            recent_start="2025-06-01", recent_end="2025-06-30",
            demo_name=demo,
        )
        assert 0.0 <= res.confidence <= 1.0, f"{demo} confidence {res.confidence} out of range"


def test_flood_72h_storm_exceeds_threshold():
    res = detect_event(
        lat=41.8, lon=-93.6,
        recent_start="2025-06-20", recent_end="2025-06-25",
        demo_name="flood",
    )
    assert res.details["cum3_mm"] > res.details["flood_threshold_mm"], (
        f"cum3={res.details['cum3_mm']} should exceed threshold={res.details['flood_threshold_mm']}"
    )
