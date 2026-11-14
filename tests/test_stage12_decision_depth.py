"""Tests for Stage 12: decision depth (farmer weights, dollar savings, rotation)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from piper_agent.tools.filter_rescue_crops import filter_rescue_crops
from piper_agent.tools.fetch_market_price import fetch_market_price, compute_dollar_savings
from piper_agent.tools.plan_rotation import plan_rotation


# ── Farmer weights tests ────────────────────────────────────────────────

def test_farmer_weights_re_rank():
    """BR-10: changing weights should change crop order."""
    flood_result_default = filter_rescue_crops(
        event_type="flood",
        gdd_remaining=2000.0,
        current_date="2025-05-15",
        avg_daily_gdd=15.0,
    )
    flood_result_soil = filter_rescue_crops(
        event_type="flood",
        gdd_remaining=2000.0,
        current_date="2025-05-15",
        avg_daily_gdd=15.0,
        farmer_weights={"soil_protection": 1.0, "salvage_revenue": 0.0, "water_conservation": 0.0},
    )
    flood_result_revenue = filter_rescue_crops(
        event_type="flood",
        gdd_remaining=2000.0,
        current_date="2025-05-15",
        avg_daily_gdd=15.0,
        farmer_weights={"soil_protection": 0.0, "salvage_revenue": 1.0, "water_conservation": 0.0},
    )

    # All should have composite_score set
    for c in flood_result_default:
        assert c.composite_score is not None
        assert 0.0 <= c.composite_score <= 1.0

    # Default ranking is by plant_by_date; soil-weighted should put Cereal rye first
    soil_first = flood_result_soil[0].crop
    assert soil_first == "Cereal rye (cover)", f"Expected Cereal rye first for soil_protection, got {soil_first}"

    # Revenue-weighted should put higher-value crop early
    revenue_first = flood_result_revenue[0].crop
    assert revenue_first in ("Cowpea", "Sorghum", "Cereal rye (cover)")


def test_farmer_weights_normalize():
    """Weights should normalize to sum 1.0."""
    result = filter_rescue_crops(
        event_type="drought",
        gdd_remaining=2000.0,
        current_date="2025-01-30",
        avg_daily_gdd=12.0,
        farmer_weights={"soil_protection": 2.0, "salvage_revenue": 2.0, "water_conservation": 2.0},
    )
    for c in result:
        assert c.composite_score is not None


def test_no_weights_ranks_by_plant_by_date():
    """Without weights, ranking is by plant_by_date descending (BR-4)."""
    result = filter_rescue_crops(
        event_type="drought",
        gdd_remaining=2000.0,
        current_date="2025-01-30",
        avg_daily_gdd=12.0,
    )
    if len(result) >= 2:
        dates = [c.plant_by_date for c in result]
        assert dates == sorted(dates, reverse=True), "Should be ranked by plant_by_date desc"


# ── Dollar savings tests ────────────────────────────────────────────────

def test_fetch_market_price():
    price = fetch_market_price("Cowpea", region="global")
    assert price["crop"] == "Cowpea"
    assert price["price_per_unit"] > 0
    assert price["currency"] == "USD"


def test_compute_dollar_savings():
    savings = compute_dollar_savings("Cowpea", expected_yield_tons_per_ha=1.5)
    assert savings["crop"] == "Cowpea"
    assert savings["estimated_revenue_usd_per_ha"] > 0
    assert savings["estimated_savings_usd_per_ha"] == savings["estimated_revenue_usd_per_ha"]
    assert "total loss" in savings["note"].lower()


# ── Rotation planner tests ──────────────────────────────────────────────

def test_plan_rotation_cowpea_rescue():
    """Cowpea rescue → high N fixation → good follow crops."""
    rot = plan_rotation("Cowpea", {"farmer_priority": "soil_protection"})
    assert rot["rotation_sequence"][0] == "Cowpea"
    assert len(rot["rotation_sequence"]) == 3
    assert rot["n_fixation_total_kg_ha"] > 0
    assert rot["soil_health_score"] > 0
    assert "N fixation" in rot["rationale"]


def test_plan_rotation_rye_rescue():
    """Cereal rye rescue → highest soil health score."""
    rot = plan_rotation("Cereal rye (cover)", {"farmer_priority": "soil_protection"})
    assert rot["rotation_sequence"][0] == "Cereal rye (cover)"
    assert rot["soil_health_score"] >= 70  # rye is 90, others contribute


def test_plan_rotation_salvage_revenue():
    """Salvage revenue priority should prefer higher-value crops."""
    rot = plan_rotation("Sorghum", {"farmer_priority": "salvage_revenue"})
    assert len(rot["rotation_sequence"]) == 3
    assert "rationale" in rot


def test_plan_rotation_unknown_crop_defaults():
    """Unknown rescue crop falls back to cereal rye."""
    rot = plan_rotation("UnknownCrop", {})
    assert rot["rotation_sequence"][0] == "Cereal rye (cover)"
