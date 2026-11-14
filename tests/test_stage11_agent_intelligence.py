"""Tests for Stage 11: agent intelligence (conformal confidence, analog search, explanations)."""
import sys
import os

import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from piper_agent.tools.confidence_calibration import (
    calibrate_confidence, reliability_data, calibration_error,
)
from piper_agent.tools.search_analogs import (
    search_analogs, analog_calibrated_confidence,
)
from piper_agent.tools.explain_exclusion import (
    explain_exclusion, explain_all_exclusions,
)


# ── Conformal confidence tests ──────────────────────────────────────────

def test_calibrate_confidence_insufficient_history():
    cal = calibrate_confidence(
        raw_confidence=0.8, event_type="flood",
        validation_history=[],  # no history
    )
    assert 0.0 <= cal <= 1.0
    # With no history, raw confidence is slightly penalized (×0.9)
    assert cal == pytest.approx(0.72)


def test_calibrate_confidence_with_history():
    history = [
        {"event_type": "flood", "predicted_confidence": 0.8, "actual_outcome": True},
        {"event_type": "flood", "predicted_confidence": 0.9, "actual_outcome": True},
        {"event_type": "flood", "predicted_confidence": 0.6, "actual_outcome": False},
        {"event_type": "flood", "predicted_confidence": 0.7, "actual_outcome": True},
        {"event_type": "flood", "predicted_confidence": 0.5, "actual_outcome": False},
        {"event_type": "flood", "predicted_confidence": 0.85, "actual_outcome": True},
    ]
    cal = calibrate_confidence(
        raw_confidence=0.8, event_type="flood", validation_history=history,
    )
    assert 0.0 <= cal <= 1.0


def test_calibration_error_in_range():
    history = [
        {"event_type": "flood", "predicted_confidence": 0.8, "actual_outcome": True},
        {"event_type": "flood", "predicted_confidence": 0.2, "actual_outcome": False},
    ]
    ece = calibration_error(history)
    assert 0.0 <= ece <= 1.0


def test_reliability_data_structure():
    history = [
        {"event_type": "flood", "predicted_confidence": 0.85, "actual_outcome": True},
        {"event_type": "flood", "predicted_confidence": 0.15, "actual_outcome": False},
        {"event_type": "flood", "predicted_confidence": 0.90, "actual_outcome": True},
    ]
    bins = reliability_data(history, n_bins=5)
    assert isinstance(bins, list)
    for b in bins:
        assert "bin_center" in b
        assert "predicted_mean" in b
        assert "observed_frequency" in b
        assert "count" in b


# ── Analog search tests ─────────────────────────────────────────────────

def test_search_analogs_empty_archive():
    analogs = search_analogs(
        event_type="flood", lat=41.8, lon=-93.6, gdd_remaining=1000.0,
        archive_dir="/nonexistent/dir",
    )
    assert analogs == []


def test_search_analogs_filters_event_type():
    # Create a temp archive
    import tempfile, json
    tmp = tempfile.mkdtemp()
    with open(os.path.join(tmp, "a1.json"), "w") as f:
        json.dump({
            "event_type": "flood", "lat": 41.8, "lon": -93.6,
            "gdd_remaining": 1000.0, "matched_crops": ["Cowpea"],
            "actual_outcome": True,
        }, f)
    with open(os.path.join(tmp, "a2.json"), "w") as f:
        json.dump({
            "event_type": "drought", "lat": 41.8, "lon": -93.6,
            "gdd_remaining": 1000.0, "matched_crops": ["Millet"],
            "actual_outcome": True,
        }, f)

    analogs = search_analogs(
        event_type="flood", lat=41.8, lon=-93.6, gdd_remaining=1000.0,
        archive_dir=tmp,
    )
    assert len(analogs) == 1
    assert analogs[0]["event_type"] == "flood"
    assert "similarity" in analogs[0]


def test_analog_calibrated_confidence_no_analogs():
    cal = analog_calibrated_confidence([], raw_confidence=0.7)
    assert cal == 0.7


def test_analog_calibrated_confidence_with_analogs():
    analogs = [
        {"similarity": 0.9, "actual_outcome": True},
        {"similarity": 0.8, "actual_outcome": True},
        {"similarity": 0.7, "actual_outcome": False},
    ]
    cal = analog_calibrated_confidence(analogs, raw_confidence=0.5)
    assert 0.0 <= cal <= 1.0
    # With 2 successes (weighted 0.9+0.8=1.7) and 1 failure (0.7),
    # observed_rate = 1.7/2.4 ≈ 0.708, blended = 0.3*0.5 + 0.7*0.708 ≈ 0.646
    assert cal > 0.5  # should be pulled up by successful analogs


# ── Explanation tests ───────────────────────────────────────────────────

def test_explain_exclusion_waterlogging():
    msg = explain_exclusion(
        crop="Buckwheat", event_type="flood", gdd_remaining=1000.0,
        filter_reason="tolerance_waterlogging",
        filter_details={"waterlogging_tolerance": "Low"},
    )
    assert "Buckwheat" in msg
    assert "Low" in msg
    assert "waterlogging" in msg.lower()
    assert "flood" in msg


def test_explain_exclusion_drought():
    msg = explain_exclusion(
        crop="Buckwheat", event_type="drought", gdd_remaining=1000.0,
        filter_reason="tolerance_drought",
        filter_details={"drought_tolerance": "Low"},
    )
    assert "Buckwheat" in msg
    assert "drought" in msg.lower()


def test_explain_exclusion_gdd_window():
    msg = explain_exclusion(
        crop="Sorghum", event_type="drought", gdd_remaining=1000.0,
        filter_reason="gdd_window",
        filter_details={"gdd_requirement": 1800, "gdd_limit": 800.0},
    )
    assert "Sorghum" in msg
    assert "1800" in msg
    assert "800" in msg


def test_explain_all_exclusions():
    all_crops = [
        {"crop": "Sorghum", "waterlogging_tolerance": "Medium", "drought_tolerance": "High",
         "gdd_to_maturity_max": 1800},
        {"crop": "Buckwheat", "waterlogging_tolerance": "Low", "drought_tolerance": "Medium",
         "gdd_to_maturity_max": 1100},
        {"crop": "Cereal rye (cover)", "waterlogging_tolerance": "High", "drought_tolerance": "Medium",
         "gdd_to_maturity_max": 900},
    ]
    eligible = [
        {"crop": "Cereal rye (cover)", "gdd_requirement": 900},
    ]
    explanations = explain_all_exclusions(
        all_crops, eligible, event_type="flood", gdd_remaining=1000.0,
    )
    assert len(explanations) == 2  # Sorghum (GDD) + Buckwheat (waterlogging)
    joined = " ".join(explanations)
    assert "Buckwheat" in joined
    assert "Sorghum" in joined
