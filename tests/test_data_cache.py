"""Tests for the data-cache work: cache, ingestion, soil, OpenET and SMAP."""
import json
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from piper_agent.data import cache_loader, generate_cache, resilience
from piper_agent.data.fetch_openet import fetch_openet_eta
from piper_agent.data.fetch_smap import fetch_smap_moisture
from piper_agent.data.ingestion import imerg_etl
from piper_agent.data.resilience import CircuitBreaker, call_with_retry
from piper_agent.data.soil_lookup import lookup_soil


# ── Demo packets and contract ───────────────────────────────────────────

def test_demo_packets_have_season_end():
    for name in ("flood", "drought", "normal"):
        with open(os.path.join("demo", f"{name}_demo.json")) as f:
            assert "season_end" in json.load(f)


def test_load_demo_packet_accepts_short_and_long_name():
    short = cache_loader.load_demo_packet("flood")
    long = cache_loader.load_demo_packet("flood_demo")
    assert short == long
    assert short["date"] == short["current_date"]
    assert short["fuente_datos"] == "sintetico"


def test_crops_path_is_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = cache_loader.get_crops_path()
    assert path.is_absolute() and path.exists()
    assert "crop" in pd.read_csv(path).columns


def test_aliases_used_outside_data_still_work():
    assert cache_loader.ESCENARIOS is cache_loader.SCENARIOS
    assert cache_loader.RUTA_CULTIVOS == cache_loader.CROPS_PATH
    assert cache_loader.get_ruta_cultivos() == cache_loader.get_crops_path()
    assert cache_loader.get_fuente_datos("flood") == cache_loader.get_data_source("flood")


# ── Cache first ─────────────────────────────────────────────────────────

def test_missing_cache_is_regenerated(tmp_path, monkeypatch):
    for attr, sub in (("IMERG_DIR", "imerg"), ("POWER_DIR", "power"), ("BASELINES_DIR", "base")):
        monkeypatch.setattr(generate_cache, attr, str(tmp_path / sub))
    monkeypatch.setattr(cache_loader, "IMERS", str(tmp_path / "imerg"))
    monkeypatch.setattr(cache_loader, "POWERS", str(tmp_path / "power"))
    monkeypatch.setattr(cache_loader, "BASELINES", str(tmp_path / "base"))

    assert not cache_loader.load_imerg("flood").empty
    assert not cache_loader.load_power("flood").empty
    assert cache_loader.load_baselines("flood")["fuente_datos"] == "sintetico"
    assert (tmp_path / "imerg" / "flood_imerg.SYNTHETIC_CACHE.txt").exists()


def test_unknown_scenario_fails_clearly():
    with pytest.raises(FileNotFoundError):
        cache_loader.load_imerg("does_not_exist")


# ── Climate by latitude ─────────────────────────────────────────────────

def test_tropics_have_no_frost_and_accumulate_gdd():
    b = cache_loader.load_baselines("drought")
    assert b["tropical"] is True
    assert b["frost_method"] in {"rainy_season_end", "fin_temporada_lluvias"}
    assert b["climatological_frost_date"] == b["season_end"]
    power = cache_loader.load_power("drought")
    assert power["T2M_MIN"].min() > 0, "it must not freeze in the tropics"
    january = power[(power["date"] >= "2025-01-01") & (power["date"] <= "2025-01-30")]
    assert ((january["T2M_MAX"] + january["T2M_MIN"]) / 2 - 10).clip(lower=0).sum() > 0


def test_temperate_latitude_keeps_frost():
    b = cache_loader.load_baselines("flood")
    assert b["tropical"] is False
    assert b["frost_method"] == "first_T2M_MIN_<=0_after_day200"


def test_southern_hemisphere_power_reverses_seasons():
    df = generate_cache.generate_power("2025-03-01", "2024-01-01", lat=-35.0)
    df["month"] = pd.to_datetime(df["date"]).dt.month
    means = df.groupby("month")["T2M_MAX"].mean()
    assert means[1] > means[7], "January must be warmer than July in the south"


def test_frost_bands_cover_both_hemispheres():
    bands = cache_loader.load_frost_bands()
    assert bands["north"] and bands["south"]
    for band in bands["south"]:
        assert {"lat_min", "lat_max", "first_frost"} <= set(band)


# ── Data source and circuit breaker ─────────────────────────────────────

def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(threshold=3)
    for _ in range(2):
        cb.record_failure()
    assert not cb.is_open()
    cb.record_failure()
    assert cb.is_open()
    cb.record_success()
    assert not cb.is_open()


def test_retry_uses_exponential_backoff():
    waits, calls = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("down")
        return "ok"

    cb = CircuitBreaker()
    assert call_with_retry(flaky, circuit_breaker=cb, sleep=waits.append) == "ok"
    assert waits == [2.0, 4.0]
    assert cb.failures == 0


def test_exhausted_retries_count_one_failure():
    def always_fails():
        raise ConnectionError("down")

    cb = CircuitBreaker(threshold=1)
    with pytest.raises(RuntimeError):
        call_with_retry(always_fails, circuit_breaker=cb, sleep=lambda s: None)
    assert cb.is_open()
    with pytest.raises(RuntimeError, match="open"):
        call_with_retry(lambda: "ok", circuit_breaker=cb)


def test_source_falls_back_to_synthetic_when_breaker_is_open(monkeypatch):
    monkeypatch.setattr(cache_loader, "load_baselines", lambda n: {"fuente_datos": "nasa_power"})
    monkeypatch.setattr(resilience, "live_circuit_breaker", CircuitBreaker())
    assert cache_loader.get_data_source("flood") == "nasa_power"
    cb = CircuitBreaker(threshold=1)
    cb.record_failure()
    monkeypatch.setattr(resilience, "live_circuit_breaker", cb)
    assert cache_loader.get_data_source("flood") == "sintetico"


# ── Real POWER (mocked network) ─────────────────────────────────────────

class _FakeResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def test_download_power_parses_response(monkeypatch):
    import requests

    body = {"properties": {"parameter": {
        "T2M_MAX": {"20240618": 30.1, "20240619": -999.0, "20240620": 28.0},
        "T2M_MIN": {"20240618": 18.2, "20240619": 17.0, "20240620": 16.5},
        "PRECTOTCORR": {"20240618": 0.0, "20240619": 55.3, "20240620": 80.4},
    }}}
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(body))
    monkeypatch.setattr(resilience, "live_circuit_breaker", CircuitBreaker())
    df = imerg_etl.download_power(43.2, -96.3, "2024-06-18", "2024-06-20")
    assert list(df.columns) == ["date", "T2M_MAX", "T2M_MIN", "PRECTOTCORR"]
    assert list(df["date"]) == ["2024-06-18", "2024-06-20"], "the day with -999 is dropped"


def test_refresh_with_real_data_leaves_cache_untouched_on_failure(monkeypatch):
    def fails(*a, **k):
        raise RuntimeError("no network")

    monkeypatch.setattr(imerg_etl, "download_power", fails)
    before = cache_loader.load_baselines("flood")
    assert imerg_etl.refresh_cache_with_real_data("flood") == "sintetico"
    assert cache_loader.load_baselines("flood") == before


# ── Soil, OpenET and SMAP without network in demo mode ──────────────────

@pytest.fixture
def no_network(monkeypatch):
    import requests

    def forbidden(*a, **k):
        raise AssertionError("there must be no network calls in demo mode")

    monkeypatch.setattr(requests, "get", forbidden)


def test_soil_without_network_and_with_new_keys(no_network):
    soil = lookup_soil(9.0, 41.0)
    assert soil["source"] == "climate_zone_estimate"
    assert soil["available_water_mm"] == soil["field_capacity_mm"] - soil["wilting_point_mm"]
    assert soil["organic_matter_pct"] > 0
    assert soil["textura"] == soil["texture_class"]


def test_openet_estimated_then_cached(no_network, tmp_path):
    args = (41.8, -93.6, "2025-05-01", "2025-05-10")
    df = fetch_openet_eta(*args, cache_dir=str(tmp_path))
    assert list(df.columns) == ["date", "eta_mm"] and len(df) == 10
    assert df.attrs["source"] == "estimated"
    again = fetch_openet_eta(*args, cache_dir=str(tmp_path))
    assert again.attrs["source"] == "estimated", "the synthetic marker is honoured on re-read"
    assert again["eta_mm"].tolist() == df["eta_mm"].tolist()


def test_smap_estimated_within_range(no_network, tmp_path):
    df = fetch_smap_moisture(9.0, 41.0, "2025-01-01", "2025-01-30", cache_dir=str(tmp_path))
    assert list(df.columns) == ["date", "soil_moisture_vol_pct"] and len(df) == 30
    assert df["soil_moisture_vol_pct"].between(5.0, 45.0).all()
    assert df.attrs["source"] == "estimated"
