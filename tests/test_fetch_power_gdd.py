"""Tests for Stage 3: fetch_power_gdd (BR-3)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from piper_agent.tools.fetch_power_gdd import fetch_power_gdd
from piper_agent.contracts import GddResult


def test_in_season_gdd_remaining_positive():
    res = fetch_power_gdd(
        lat=41.8, lon=-93.6,
        season_start="2025-04-01", current_date="2025-06-25",
        demo_name="flood",
    )
    assert isinstance(res, GddResult)
    assert res.gdd_accumulated > 0
    assert res.gdd_remaining > 0
    assert res.frost_date  # non-empty
    assert res.avg_daily_gdd > 0


def test_frost_date_matches_baseline():
    from piper_agent.data.cache_loader import load_baselines
    res = fetch_power_gdd(
        lat=41.8, lon=-93.6,
        season_start="2025-04-01", current_date="2025-06-25",
        demo_name="flood",
    )
    b = load_baselines("flood")
    # frost_date is current-year adjusted; baseline_date is the original
    assert res.details["frost_baseline_date"] == b["climatological_frost_date"]


def test_after_frost_gdd_remaining_zero():
    res = fetch_power_gdd(
        lat=41.8, lon=-93.6,
        season_start="2025-04-01", current_date="2025-11-01",
        demo_name="flood",
    )
    assert res.gdd_remaining == 0.0


def test_gdd_values_in_range():
    for demo in ["flood", "drought", "normal"]:
        res = fetch_power_gdd(
            lat=41.8, lon=-93.6,
            season_start="2025-04-01", current_date="2025-06-25",
            demo_name=demo,
        )
        assert res.gdd_accumulated >= 0
        assert res.gdd_remaining >= 0
        assert res.avg_daily_gdd >= 0
