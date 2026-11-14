"""Tests for Stage 3: filter_rescue_crops (BR-2, BR-3, BR-4)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from piper_agent.tools.filter_rescue_crops import filter_rescue_crops
from piper_agent.contracts import CropRecommendation, TOLERANCE_ORDINAL

CROPS_CSV = "piper_agent/data/rescue_crops.csv"


def test_flood_returns_at_least_2_crops():
    res = filter_rescue_crops(
        event_type="flood",
        gdd_remaining=2000.0,
        current_date="2025-06-25",
        avg_daily_gdd=15.0,
        crops_csv=CROPS_CSV,
    )
    assert len(res) >= 2, f"Expected >=2 flood crops, got {len(res)}"
    # BR-2: no Low waterlogging tolerance in flood results
    for c in res:
        assert c.event_match is True


def test_drought_returns_at_least_2_crops():
    res = filter_rescue_crops(
        event_type="drought",
        gdd_remaining=2000.0,
        current_date="2025-01-30",
        avg_daily_gdd=12.0,
        crops_csv=CROPS_CSV,
    )
    assert len(res) >= 2, f"Expected >=2 drought crops, got {len(res)}"
    for c in res:
        assert c.event_match is True


def test_late_season_returns_empty():
    res = filter_rescue_crops(
        event_type="flood",
        gdd_remaining=50.0,  # tiny window
        current_date="2025-10-01",
        avg_daily_gdd=5.0,
        crops_csv=CROPS_CSV,
    )
    assert res == [], f"Expected empty for late season, got {len(res)} crops"


def test_br2_no_low_waterlogging_in_flood():
    res = filter_rescue_crops(
        event_type="flood",
        gdd_remaining=2000.0,
        current_date="2025-06-01",
        avg_daily_gdd=15.0,
        crops_csv=CROPS_CSV,
    )
    # Load raw CSV to check which crops have Low waterlogging
    import pandas as pd
    df = pd.read_csv(CROPS_CSV)
    low_wl = set(df[df["waterlogging_tolerance"] == "Low"]["crop"])
    for c in res:
        assert c.crop not in low_wl, f"{c.crop} has Low waterlogging but appeared in flood results"


def test_br2_no_low_drought_tolerance_in_drought():
    res = filter_rescue_crops(
        event_type="drought",
        gdd_remaining=2000.0,
        current_date="2025-01-01",
        avg_daily_gdd=12.0,
        crops_csv=CROPS_CSV,
    )
    import pandas as pd
    df = pd.read_csv(CROPS_CSV)
    low_dt = set(df[df["drought_tolerance"] == "Low"]["crop"])
    for c in res:
        assert c.crop not in low_dt, f"{c.crop} has Low drought tolerance but appeared in drought results"


def test_br3_gdd_margin_08():
    # A crop needing 1000 GDD should be excluded if remaining=1000 (1000 > 1000*0.8=800)
    res = filter_rescue_crops(
        event_type="drought",
        gdd_remaining=1000.0,
        current_date="2025-01-01",
        avg_daily_gdd=10.0,
        crops_csv=CROPS_CSV,
    )
    for c in res:
        assert c.gdd_requirement <= 800.0, (
            f"{c.crop} needs {c.gdd_requirement} GDD > limit 800 (1000*0.8)"
        )


def test_br4_ranked_by_plant_by_date_desc():
    res = filter_rescue_crops(
        event_type="flood",
        gdd_remaining=1500.0,
        current_date="2025-06-01",
        avg_daily_gdd=15.0,
        crops_csv=CROPS_CSV,
    )
    if len(res) >= 2:
        dates = [c.plant_by_date for c in res]
        assert dates == sorted(dates, reverse=True), "Not ranked by plant_by_date desc"


def test_br4_plant_by_date_explicit():
    res = filter_rescue_crops(
        event_type="flood",
        gdd_remaining=1000.0,
        current_date="2025-06-01",
        avg_daily_gdd=10.0,
        crops_csv=CROPS_CSV,
    )
    for c in res:
        assert c.plant_by_date  # non-empty ISO date
        assert c.days_until_deadline >= 0
        # plant_by_date = current_date + days_until_deadline
        from datetime import datetime, timedelta
        expected = (datetime.fromisoformat("2025-06-01").date() + timedelta(days=c.days_until_deadline)).isoformat()
        assert c.plant_by_date == expected


def test_rescue_confidence_in_range():
    res = filter_rescue_crops(
        event_type="flood",
        gdd_remaining=1500.0,
        current_date="2025-06-01",
        avg_daily_gdd=15.0,
        crops_csv=CROPS_CSV,
    )
    for c in res:
        assert 0.0 <= c.rescue_confidence <= 1.0
