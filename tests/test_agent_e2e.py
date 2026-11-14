"""End-to-end tests for Stage 5: agent tool-calling loop."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from piper_agent.agent import run_pier


def test_flood_demo_e2e():
    result = run_pier(
        lat=41.8, lon=-93.6,
        current_date="2025-05-15",
        demo_mode=True,
        demo_name="flood",
    )
    assert result["demo_mode"] is True
    assert result["event_result"].event_type == "flood"
    assert result["gdd_result"].gdd_remaining >= 0
    assert result["plan_text"]
    assert "Event detection: flood" in result["plan_text"]
    assert "Rescue recommendation confidence" in result["plan_text"]


def test_drought_demo_e2e():
    result = run_pier(
        lat=9.0, lon=41.0,
        current_date="2025-01-30",
        demo_mode=True,
        demo_name="drought",
    )
    assert result["event_result"].event_type == "drought"
    assert result["plan_text"]
    assert "Event detection: drought" in result["plan_text"]


def test_normal_demo_e2e():
    result = run_pier(
        lat=41.8, lon=-93.6,
        current_date="2025-07-07",
        demo_mode=True,
        demo_name="normal",
    )
    assert result["event_result"].event_type == "none"


def test_late_season_fallback():
    # Late season → tiny GDD window → no crops → BR-5 fallback
    result = run_pier(
        lat=41.8, lon=-93.6,
        current_date="2025-09-30",
        demo_mode=True,
        demo_name="flood",
    )
    if not result["crops"]:
        assert result["recovery_plan"].fallback is True
        assert "cash crop is lost" in result["plan_text"]
        assert "soil protection only" in result["plan_text"]


def test_demo_mode_only_cache():
    """Verify demo_mode=False raises NotImplementedError (production path)."""
    try:
        run_pier(lat=41.8, lon=-93.6, current_date="2025-06-25", demo_mode=False)
        assert False, "Expected NotImplementedError for demo_mode=False"
    except NotImplementedError:
        pass  # expected


def test_auto_select_demo():
    result = run_pier(
        lat=41.8, lon=-93.6,
        current_date="2025-06-25",
        demo_mode=True,
        demo_name=None,
    )
    assert result["demo_name"] == "flood"


def test_at_least_2_crops_for_flood():
    """Spec §10: at least 2 eligible rescue crops for flood demo."""
    result = run_pier(
        lat=41.8, lon=-93.6,
        current_date="2025-05-15",
        demo_mode=True,
        demo_name="flood",
    )
    # With mid-season GDD, should have >= 2 crops
    assert len(result["crops"]) >= 2, f"Expected >=2 crops, got {len(result['crops'])}"


def test_at_least_2_crops_for_drought():
    """Spec §10: at least 2 eligible rescue crops for drought demo."""
    result = run_pier(
        lat=9.0, lon=41.0,
        current_date="2025-01-30",
        demo_mode=True,
        demo_name="drought",
    )
    assert len(result["crops"]) >= 2, f"Expected >=2 crops, got {len(result['crops'])}"
