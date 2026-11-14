"""Tests for the real-data wave: real ingestion, climatologies and calibration."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from piper_agent.data import calibration, climatology, resilience
from piper_agent.data._series_cache import extraterrestrial_radiation_mm
from piper_agent.data.fetch_openet import fetch_openet_eta
from piper_agent.data.fetch_smap import fetch_smap_moisture
from piper_agent.data.ingestion import imerg_etl, pipeline
from piper_agent.data.resilience import CircuitBreaker


@pytest.fixture
def no_network(monkeypatch):
    import requests

    def forbidden(*a, **k):
        raise AssertionError("there must be no network calls")

    monkeypatch.setattr(requests, "get", forbidden)


@pytest.fixture
def production(monkeypatch, tmp_path):
    """Production path with temporary folders and a clean circuit breaker."""
    monkeypatch.setenv("PIER_DEMO_MODE", "0")
    monkeypatch.delenv("EARTHDATA_USERNAME", raising=False)
    monkeypatch.delenv("EARTHDATA_PASSWORD", raising=False)
    monkeypatch.setattr(pipeline, "REAL_DIR", str(tmp_path / "real"))
    monkeypatch.setattr(climatology, "REGIONS_DIR", str(tmp_path / "regions"))
    monkeypatch.setattr(resilience, "live_circuit_breaker", CircuitBreaker())
    monkeypatch.setattr(resilience.time, "sleep", lambda s: None)
    return tmp_path


def _fake_power(lat, lon, start, end, attempts=3, parameters=imerg_etl.POWER_PARAMETERS):
    days = pd.date_range(start, end, freq="D")
    columns = {
        "T2M_MAX": np.full(len(days), 30.0),
        "T2M_MIN": np.full(len(days), 16.0),
        "PRECTOTCORR": np.full(len(days), 2.0),
        "GWETROOT": np.full(len(days), 0.5),
    }
    df = pd.DataFrame({p: columns[p] for p in parameters})
    df.insert(0, "date", days.strftime("%Y-%m-%d"))
    return df


# ── Ingestion ───────────────────────────────────────────────────────────

def test_region_key_is_a_half_degree_cell():
    assert pipeline.region_key(41.8, -93.6) == "lat+42.0_lon-093.5"
    assert pipeline.region_key(41.76, -93.44) == pipeline.region_key(41.8, -93.6)


def test_demo_mode_uses_demo_cache_without_network(no_network):
    data = pipeline.ingest_point(41.8, -93.6, "2025-05-01", "2025-05-15", demo_mode=True)
    assert data["fuente_datos"] == "sintetico"
    assert data["demo_scenario"] == "normal"
    assert data["fallback_reason"] is None
    assert len(data["power"]) == 15 and len(data["rainfall"]) == 15


def test_demo_mode_far_from_demos_generates_a_series(no_network):
    data = pipeline.ingest_point(-33.4, -70.7, "2024-01-01", "2024-01-31", demo_mode=True)
    assert data["demo_scenario"] is None
    assert len(data["power"]) == 31
    assert list(data["rainfall"].columns) == ["date", "precipitation_mm"]


def test_production_uses_real_power_and_caches_it(production, monkeypatch):
    calls = []

    def fake(*a, **k):
        calls.append(1)
        return _fake_power(*a, **k)

    monkeypatch.setattr(imerg_etl, "download_power", fake)
    data = pipeline.ingest_point(10.0, -84.0, "2024-01-01", "2024-01-10")
    assert data["fuente_datos"] == "nasa_power"
    assert "GWETROOT" in data["power"].columns
    assert data["rainfall"]["precipitation_mm"].tolist() == [2.0] * 10
    again = pipeline.ingest_point(10.0, -84.0, "2024-01-01", "2024-01-10")
    assert again["fuente_datos"] == "nasa_power" and len(calls) == 1, "the second call hits the cache"


def test_production_with_imerg_labels_the_source(production, monkeypatch):
    monkeypatch.setattr(imerg_etl, "download_power", _fake_power)
    records = [{"date": "2024-01-01", "precipitation_mm": 9.5},
               {"date": "2024-01-02", "precipitation_mm": 0.0}]
    monkeypatch.setattr(imerg_etl, "fetch_with_retry", lambda *a, **k: ("x.xlsx", records))
    data = pipeline.ingest_point(10.0, -84.0, "2024-01-01", "2024-01-02", use_imerg=True)
    assert data["fuente_datos"] == "nasa_power+imerg"
    assert data["rainfall"]["precipitation_mm"].tolist() == [9.5, 0.0]


def test_production_falls_back_without_raising(production, monkeypatch):
    def fails(*a, **k):
        raise RuntimeError("no network")

    monkeypatch.setattr(imerg_etl, "download_power", fails)
    data = pipeline.ingest_point(41.8, -93.6, "2025-05-01", "2025-05-15")
    assert data["fuente_datos"] == "sintetico"
    assert "no network" in data["fallback_reason"]
    assert not data["power"].empty


# ── Versioned climatologies ─────────────────────────────────────────────

def test_climatology_is_saved_with_version_and_source(no_network, monkeypatch, tmp_path):
    monkeypatch.setattr(climatology, "REGIONS_DIR", str(tmp_path))
    clim = climatology.get_climatology(41.8, -93.6, until="2025-05-15", demo_mode=True)
    assert clim["version"] == climatology.BASELINES_VERSION
    assert clim["fuente_datos"] == "sintetico"
    assert len(clim["months"]) == 12
    assert (tmp_path / "lat+42.0_lon-093.5_v1.json").exists()
    assert climatology.load_climatology(41.8, -93.6) == clim


def test_synthetic_climatology_is_recomputed_in_production(production, monkeypatch):
    climatology.get_climatology(41.8, -93.6, until="2025-05-15", demo_mode=True)
    monkeypatch.setattr(imerg_etl, "download_power", _fake_power)
    real = climatology.get_climatology(41.8, -93.6, until="2025-05-15")
    assert real["fuente_datos"] == "nasa_power"


def test_classify_value_normal_extreme_and_missing(no_network, monkeypatch, tmp_path):
    monkeypatch.setattr(climatology, "REGIONS_DIR", str(tmp_path))
    clim = climatology.get_climatology(41.8, -93.6, until="2025-05-15", demo_mode=True)
    median = clim["months"]["5"]["rain_3d"]["p50"]

    normal = climatology.classify_value(clim, "rain_3d", median, "2025-05-15")
    assert normal["status"] == "normal" and normal["direction"] is None

    high = climatology.classify_value(clim, "rain_3d", 105.0, "2025-05-15")
    assert high["status"] == "extreme" and high["direction"] == "high"
    assert "above normal" in high["explanation"]

    low = climatology.classify_value(clim, "rain_30d", 0.0, "2025-05-15")
    assert low["status"] == "extreme" and low["direction"] == "low"

    assert climatology.classify_value(clim, "tmin", None, "2025-05-15")["status"] == "missing"
    assert climatology.classify_value(None, "tmax", 30.0, "2025-05-15")["status"] == "missing"
    with pytest.raises(ValueError):
        climatology.classify_value(clim, "wind", 1.0, "2025-05-15")


# ── Real soil moisture and evapotranspiration ───────────────────────────

def test_smap_uses_power_gwetroot_in_production(production, monkeypatch):
    monkeypatch.setattr(imerg_etl, "download_power", _fake_power)
    df = fetch_smap_moisture(10.0, -84.0, "2024-01-01", "2024-01-05", cache_dir=str(production / "smap"))
    assert df.attrs["source"] == "nasa_power_gwetroot"
    assert df["soil_moisture_vol_pct"].tolist() == [22.5] * 5  # 0.5 saturation × 45 % porosity


def test_openet_uses_hargreaves_with_power_in_production(production, monkeypatch):
    monkeypatch.setattr(imerg_etl, "download_power", _fake_power)
    df = fetch_openet_eta(10.0, -84.0, "2024-01-01", "2024-01-05", cache_dir=str(production / "openet"))
    assert df.attrs["source"] == "nasa_power_hargreaves"
    assert df["eta_mm"].between(2.0, 8.0).all(), df["eta_mm"].tolist()


def test_series_fall_back_to_estimated_if_power_fails(production, monkeypatch):
    def fails(*a, **k):
        raise RuntimeError("no network")

    monkeypatch.setattr(imerg_etl, "download_power", fails)
    df = fetch_smap_moisture(10.0, -84.0, "2024-01-01", "2024-01-05", cache_dir=str(production / "smap"))
    assert df.attrs["source"] == "estimated" and len(df) == 5


def test_extraterrestrial_radiation_matches_fao():
    # FAO-56, example 8: 20°S, 3 September (day 246) → Ra = 32.2 MJ/m²/day
    assert extraterrestrial_radiation_mm(-20.0, 246) / 0.408 == pytest.approx(32.2, abs=0.2)


# ── Local calibration ───────────────────────────────────────────────────

@pytest.fixture
def calibration_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PIER_CALIBRATION_DIR", str(tmp_path))
    return tmp_path


def test_observations_are_stored_per_region(calibration_dir):
    calibration.record_observation(41.8, -93.6, "2025-09-30", "Cowpea",
                                   observed_yield_t_ha=1.2, note="hail in August")
    calibration.record_observation(41.76, -93.44, "2025-10-02", "Cowpea", damage_pct=30)
    assert len(calibration.load_observations(41.8, -93.6)) == 2
    assert calibration.load_observations(9.0, 41.0) == []
    assert (calibration_dir / "lat+42.0_lon-093.5.json").exists()


def test_invalid_observation_is_rejected(calibration_dir):
    with pytest.raises(ValueError):
        calibration.record_observation(41.8, -93.6, "2025-09-30", "Cowpea", damage_pct=140)
    with pytest.raises(ValueError):
        calibration.record_observation(41.8, -93.6, "30/09/2025", "Cowpea")
    assert calibration.load_observations(41.8, -93.6) == []


def test_correction_factor_needs_three_observations(calibration_dir):
    for observed in (1.2, 1.0):
        calibration.record_observation(41.8, -93.6, "2025-09-30", "Cowpea",
                                       observed_yield_t_ha=observed,
                                       expected_yield_t_ha=1.5)
    uncalibrated = calibration.correction_factor(41.8, -93.6, "Cowpea")
    assert uncalibrated == {"factor": 1.0, "calibrated": False, "n_observations": 2}

    calibration.record_observation(41.8, -93.6, "2026-09-30", "Cowpea",
                                   observed_yield_t_ha=1.35,
                                   expected_yield_t_ha=1.5)
    calibrated = calibration.correction_factor(41.8, -93.6, "Cowpea")
    assert calibrated["calibrated"] is True and calibrated["factor"] == pytest.approx(0.8)
    assert calibration.correction_factor(41.8, -93.6, "Millet")["calibrated"] is False


def test_correction_factor_is_bounded(calibration_dir):
    for _ in range(3):
        calibration.record_observation(41.8, -93.6, "2025-09-30", "Millet",
                                       observed_yield_t_ha=0.1,
                                       expected_yield_t_ha=1.5)
    assert calibration.correction_factor(41.8, -93.6, "Millet")["factor"] == 0.5


def test_history_feeds_confidence_calibration(calibration_dir):
    from piper_agent.tools.confidence_calibration import calibrate_confidence

    for matured in (True, True, False, True, True):
        calibration.record_observation(41.8, -93.6, "2025-09-30", "Cowpea", event_type="flood",
                                       predicted_confidence=0.9, crop_matured=matured)
    calibration.record_observation(41.8, -93.6, "2025-09-30", "Cowpea", note="no outcome")
    history = calibration.validation_history(41.8, -93.6)
    assert len(history) == 5
    assert set(history[0]) == {"event_type", "predicted_confidence", "actual_outcome"}
    assert 0.0 <= calibrate_confidence(0.9, "flood", history) < 0.9
