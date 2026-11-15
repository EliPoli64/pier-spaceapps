"""Tests for the live-ingestion guardrails: demo-mode contract, single entry point,
Earthdata credential checks and explicit cache refresh."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from piper_agent.data import cache_loader, climatology, generate_cache, redis_cache, resilience
from piper_agent.data.fetch_openet import fetch_openet_eta
from piper_agent.data.fetch_smap import fetch_smap_moisture
from piper_agent.data.ingestion import imerg_etl, pipeline
from piper_agent.data.resilience import CircuitBreaker
from piper_agent.data.soil_lookup import lookup_soil


@pytest.fixture
def no_network(monkeypatch):
    """Any HTTP or socket connection fails the test."""
    import socket

    import requests

    def forbidden(*a, **k):
        raise AssertionError("there must be no network calls")

    monkeypatch.setattr(requests, "get", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


@pytest.fixture
def production(monkeypatch, tmp_path):
    """Production path (PIER_DEMO_MODE=0) with temporary folders and clean breakers."""
    monkeypatch.setenv("PIER_DEMO_MODE", "0")
    monkeypatch.delenv("EARTHDATA_USERNAME", raising=False)
    monkeypatch.delenv("EARTHDATA_PASSWORD", raising=False)
    monkeypatch.setattr(pipeline, "REAL_DIR", str(tmp_path / "real"))
    monkeypatch.setattr(climatology, "REGIONS_DIR", str(tmp_path / "regions"))
    monkeypatch.setattr(resilience, "live_circuit_breaker", CircuitBreaker())
    monkeypatch.setattr(imerg_etl, "_circuit_breaker", imerg_etl.CircuitBreaker())
    monkeypatch.setattr(resilience.time, "sleep", lambda s: None)
    monkeypatch.setattr(imerg_etl.time, "sleep", lambda s: None)
    return tmp_path


@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setenv("EARTHDATA_USERNAME", "someone")
    monkeypatch.setenv("EARTHDATA_PASSWORD", "secret-value")


def _fake_power(lat, lon, start, end, attempts=3, parameters=imerg_etl.POWER_PARAMETERS):
    days = pd.date_range(start, end, freq="D")
    doy = days.dayofyear.to_numpy()
    columns = {
        "T2M_MAX": 26.0 + 4.0 * np.sin(2 * np.pi * (doy - 110) / 365.0),
        "T2M_MIN": 12.0 + 4.0 * np.sin(2 * np.pi * (doy - 110) / 365.0),
        "PRECTOTCORR": np.full(len(days), 2.0),
        "GWETROOT": np.full(len(days), 0.5),
    }
    df = pd.DataFrame({p: columns[p] for p in parameters})
    df.insert(0, "date", days.strftime("%Y-%m-%d"))
    return df


# ── 1. Demo-mode contract: no live calls, explicit argument beats the environment ──

def test_demo_argument_wins_over_production_environment(production, no_network, tmp_path):
    """demo_mode=True must stay offline even when PIER_DEMO_MODE=0."""
    data = pipeline.ingest_point(41.8, -93.6, "2025-05-01", "2025-05-10", demo_mode=True)
    assert data["fuente_datos"] == "sintetico" and data["fallback_reason"] is None

    eta = fetch_openet_eta(41.8, -93.6, "2025-05-01", "2025-05-10",
                           cache_dir=str(tmp_path / "openet"), demo_mode=True)
    assert eta.attrs["source"] == "estimated"

    moisture = fetch_smap_moisture(41.8, -93.6, "2025-05-01", "2025-05-10",
                                   cache_dir=str(tmp_path / "smap"), demo_mode=True)
    assert moisture.attrs["source"] == "estimated"

    assert lookup_soil(41.8, -93.6, demo_mode=True)["source"] == "climate_zone_estimate"
    assert imerg_etl.fetch_with_fallback(41.8, -93.6, "2025-05-01", "2025-05-10",
                                         demo_mode=True)["synthetic"] is True
    clim = climatology.get_climatology(41.8, -93.6, until="2025-05-15", demo_mode=True)
    assert clim["fuente_datos"] == "sintetico"


def test_cache_loader_never_touches_the_network(no_network):
    for name in cache_loader.SCENARIOS:
        assert not cache_loader.load_imerg(name).empty
        assert not cache_loader.load_power(name).empty
        assert cache_loader.load_demo_packet(name)["fuente_datos"] == "sintetico"


def test_redis_is_opt_in(monkeypatch, no_network, tmp_path):
    monkeypatch.delenv("PIER_REDIS_HOST", raising=False)
    monkeypatch.setattr(redis_cache, "_redis_client", None)
    monkeypatch.setattr(redis_cache, "FS_CACHE_ROOT", tmp_path)
    assert redis_cache._get_redis() is None
    redis_cache.set("k", {"a": 1})
    assert redis_cache.get("k") == {"a": 1}


def test_redis_host_set_but_unreachable_falls_back(monkeypatch, tmp_path):
    monkeypatch.setenv("PIER_REDIS_HOST", "redis://127.0.0.1:1")
    monkeypatch.setattr(redis_cache, "_redis_client", None)
    monkeypatch.setattr(redis_cache, "FS_CACHE_ROOT", tmp_path)
    redis_cache.set("k", "v")
    assert redis_cache.get("k") == "v"


# ── 2. ingest_point is the single real-data entry point ─────────────────

def test_soil_moisture_and_et_reuse_the_ingested_download(production, monkeypatch):
    calls = []

    def fake(*a, **k):
        calls.append(k.get("parameters"))
        return _fake_power(*a, **k)

    monkeypatch.setattr(imerg_etl, "download_power", fake)
    args = (10.0, -84.0, "2024-01-01", "2024-01-05")
    moisture = fetch_smap_moisture(*args, cache_dir=str(production / "smap"))
    eta = fetch_openet_eta(*args, cache_dir=str(production / "openet"))
    assert moisture.attrs["source"] == "nasa_power_gwetroot"
    assert eta.attrs["source"] == "nasa_power_hargreaves"
    assert calls == [pipeline.REAL_PARAMETERS], "one POWER download serves both series"
    assert len(list((production / "real").glob("*_power.csv"))) == 1


def test_synthetic_fallback_is_never_labeled_as_nasa(production, monkeypatch):
    def fails(*a, **k):
        raise RuntimeError("no network")

    monkeypatch.setattr(imerg_etl, "download_power", fails)
    args = (10.0, -84.0, "2024-01-01", "2024-01-05")
    assert fetch_openet_eta(*args, cache_dir=str(production / "o")).attrs["source"] == "estimated"
    assert fetch_smap_moisture(*args, cache_dir=str(production / "s")).attrs["source"] == "estimated"


# ── 3. Earthdata credentials and circuit breakers never crash the pipeline ──

def test_earthdata_status_without_credentials(production):
    status = imerg_etl.earthdata_status()
    assert status["available"] is False and status["credentials_set"] is False
    assert "credentials" in status["reason"]


def test_earthdata_status_does_not_leak_credentials(production, credentials):
    status = imerg_etl.earthdata_status()
    assert status["credentials_set"] is True
    assert "secret-value" not in str(status) and "someone" not in str(status)


def test_missing_credentials_yield_nasa_power_with_reason(production, monkeypatch):
    monkeypatch.setattr(imerg_etl, "download_power", _fake_power)

    def must_not_run(*a, **k):
        raise AssertionError("IMERG must not be attempted without credentials")

    monkeypatch.setattr(imerg_etl, "fetch_with_retry", must_not_run)
    data = pipeline.ingest_point(10.0, -84.0, "2024-01-01", "2024-01-05")
    assert data["fuente_datos"] == "nasa_power"
    assert "credentials not set" in data["fallback_reason"]
    assert "PRECTOTCORR" in data["fallback_reason"]

    cached = pipeline.ingest_point(10.0, -84.0, "2024-01-01", "2024-01-05")
    assert cached["fallback_reason"] == data["fallback_reason"], "the reason survives the cache"


def test_invalid_credentials_yield_nasa_power_with_reason(production, credentials, monkeypatch):
    monkeypatch.setattr(imerg_etl, "download_power", _fake_power)
    monkeypatch.setattr(imerg_etl, "earthdata_status",
                        lambda: {"available": True, "reason": None})

    def rejected(*a, **k):
        raise RuntimeError("IMERG fetch failed after 3 attempts: 401 Unauthorized")

    monkeypatch.setattr(imerg_etl, "fetch_with_retry", rejected)
    data = pipeline.ingest_point(10.0, -84.0, "2024-01-01", "2024-01-05")
    assert data["fuente_datos"] == "nasa_power"
    assert "401 Unauthorized" in data["fallback_reason"]


def test_missing_imergpy_fails_fast_without_retries(production, credentials, monkeypatch):
    monkeypatch.setitem(sys.modules, "imergpy", None)  # makes `import imergpy` fail
    slept = []
    monkeypatch.setattr(imerg_etl.time, "sleep", slept.append)
    with pytest.raises(RuntimeError, match="imergpy is not installed"):
        imerg_etl.fetch_with_retry(10.0, -84.0, "2024-01-01", "2024-01-05")
    assert slept == [] and imerg_etl._circuit_breaker.failures == 0


def test_open_power_breaker_yields_sintetico_with_reason(production, monkeypatch):
    breaker = CircuitBreaker(threshold=1)
    breaker.record_failure("POWER down")
    monkeypatch.setattr(resilience, "live_circuit_breaker", breaker)
    data = pipeline.ingest_point(10.0, -84.0, "2024-01-01", "2024-01-05")
    assert data["fuente_datos"] == "sintetico"
    assert "open" in data["fallback_reason"]
    assert not data["power"].empty and not data["rainfall"].empty


def test_skipping_imerg_on_purpose_records_no_reason(production, monkeypatch):
    monkeypatch.setattr(imerg_etl, "download_power", _fake_power)
    data = pipeline.ingest_point(10.0, -84.0, "2024-01-01", "2024-01-05", use_imerg=False)
    assert data["fuente_datos"] == "nasa_power" and data["fallback_reason"] is None


# ── 4. Explicit cache refresh ───────────────────────────────────────────

@pytest.fixture
def scratch_cache(monkeypatch, tmp_path):
    """Point the demo cache at a temporary folder so the real one is not modified."""
    folders = {"IMERG_DIR": tmp_path / "imerg", "POWER_DIR": tmp_path / "power",
               "BASELINES_DIR": tmp_path / "baselines"}
    for attr, folder in folders.items():
        monkeypatch.setattr(generate_cache, attr, str(folder))
    monkeypatch.setattr(cache_loader, "IMERS", str(folders["IMERG_DIR"]))
    monkeypatch.setattr(cache_loader, "POWERS", str(folders["POWER_DIR"]))
    monkeypatch.setattr(cache_loader, "BASELINES", str(folders["BASELINES_DIR"]))
    generate_cache.generate_scenario("flood")
    return tmp_path


def test_refresh_replaces_cache_with_real_data(production, scratch_cache, monkeypatch):
    monkeypatch.setattr(imerg_etl, "download_power", _fake_power)
    assert cache_loader.get_data_source("flood") == "sintetico"

    assert imerg_etl.refresh_cache_with_real_data("flood") == "nasa_power"

    assert cache_loader.get_data_source("flood") == "nasa_power"
    power = cache_loader.load_power("flood")
    assert list(power.columns) == ["date", "T2M_MAX", "T2M_MIN", "PRECTOTCORR"]
    rain = cache_loader.load_imerg("flood")
    assert list(rain.columns) == ["date", "precipitation_mm"]
    assert rain["date"].max() <= pd.Timestamp(generate_cache.read_packet("flood")["recent_end"])
    assert not list(scratch_cache.rglob("flood_*.SYNTHETIC_CACHE.txt"))
    baselines = cache_loader.load_baselines("flood")
    assert baselines["p95_3day_cum_rainfall"] == pytest.approx(6.0)  # 3 days × 2 mm
    assert baselines["frost_method"] in ("first_T2M_MIN_<=0_after_day200", "fallback_fixed_date")


def test_refresh_with_imerg_labels_both_sources(production, scratch_cache, monkeypatch):
    monkeypatch.setattr(imerg_etl, "download_power", _fake_power)
    records = [{"date": d.strftime("%Y-%m-%d"), "precipitation_mm": 1.0}
               for d in pd.date_range("2025-05-01", "2025-05-15")]
    monkeypatch.setattr(imerg_etl, "fetch_with_retry", lambda *a, **k: ("x.xlsx", records))
    assert imerg_etl.refresh_cache_with_real_data("flood", use_imerg=True) == "nasa_power+imerg"
    assert cache_loader.load_imerg("flood")["precipitation_mm"].tolist() == [1.0] * 15


def test_failed_refresh_keeps_synthetic_cache(production, scratch_cache, monkeypatch):
    def fails(*a, **k):
        raise RuntimeError("no network")

    monkeypatch.setattr(imerg_etl, "download_power", fails)
    before = cache_loader.load_power("flood")
    assert imerg_etl.refresh_cache_with_real_data("flood") == "sintetico"
    pd.testing.assert_frame_equal(cache_loader.load_power("flood"), before)
    assert list(scratch_cache.rglob("flood_*.SYNTHETIC_CACHE.txt")), "markers are kept"


def test_synthetic_cache_can_be_restored_after_refresh(production, scratch_cache, monkeypatch):
    monkeypatch.setattr(imerg_etl, "download_power", _fake_power)
    imerg_etl.refresh_cache_with_real_data("flood")
    generate_cache.generate_scenario("flood")
    assert cache_loader.get_data_source("flood") == "sintetico"


# ── 5. imergpy v1.2+ signature and record normalization ─────────────────

def test_fetch_with_retry_uses_imergpy_signature_and_parses_records(production, credentials, monkeypatch, tmp_path):
    """Matches imergpy.get_precipitation(lat, lon, start_datetime, end_datetime, username, password, ...)."""
    import importlib.machinery
    import types

    captured = {}

    def fake_get_precipitation(
        lat, lon, start_datetime, end_datetime, username, password,
        run_type="early", freq="hhr", interp_method="nearest", out_dir=".",
    ):
        captured.update({
            "lat": lat, "lon": lon,
            "start_datetime": start_datetime, "end_datetime": end_datetime,
            "username": username, "password": password,
            "run_type": run_type, "freq": freq, "out_dir": out_dir,
        })
        return str(tmp_path / "out.xlsx"), [
            {
                "Requested_Lat": lat, "Requested_Lon": lon,
                "Actual_Lat": lat, "Actual_Lon": lon,
                "Interpolation": interp_method,
                "Start_Time": "2024-01-01T00:00:00",
                "End_Time": "2024-01-02T00:00:00",
                "Precipitation_mm_per_day": 12.346,
                "IMERG_Version": "V07B",
                "Run_Type": run_type,
            },
            {
                "Requested_Lat": lat, "Requested_Lon": lon,
                "Actual_Lat": lat, "Actual_Lon": lon,
                "Interpolation": interp_method,
                "Start_Time": "2024-01-02T00:00:00",
                "End_Time": "2024-01-03T00:00:00",
                "Precipitation_mm_per_day": 0.0,
                "IMERG_Version": "V07B",
                "Run_Type": run_type,
            },
        ]

    fake_mod = types.ModuleType("imergpy")
    fake_mod.__spec__ = importlib.machinery.ModuleSpec("imergpy", None)
    fake_mod.get_precipitation = fake_get_precipitation
    monkeypatch.setitem(sys.modules, "imergpy", fake_mod)
    monkeypatch.setattr(imerg_etl, "download_power", _fake_power)

    data = pipeline.ingest_point(10.0, -84.0, "2024-01-01", "2024-01-02", use_imerg=True)
    assert captured["start_datetime"] == "2024-01-01"
    assert captured["end_datetime"] == "2024-01-02"
    assert captured["username"] == "someone"
    assert captured["password"] == "secret-value"
    assert captured["run_type"] == "early"
    assert captured["freq"] == "daily"
    assert captured["out_dir"] != "."
    assert data["fuente_datos"] == "nasa_power+imerg"
    assert data["fallback_reason"] is None
    assert data["rainfall"].to_dict(orient="records") == [
        {"date": "2024-01-01", "precipitation_mm": 12.35},
        {"date": "2024-01-02", "precipitation_mm": 0.0},
    ]


def test_real_imergpy_signature_matches_etl_kwargs():
    """Verify the installed imergpy package accepts every keyword fetch_with_retry sends."""
    import inspect

    imergpy = pytest.importorskip("imergpy")
    sig = inspect.signature(imergpy.get_precipitation)
    sig.bind(
        lat=10.0,
        lon=-84.0,
        start_datetime="2024-01-01",
        end_datetime="2024-01-02",
        username="u",
        password="p",
        run_type="early",
        freq="daily",
        out_dir="/tmp",
    )


def test_fetch_with_retry_fails_fast_on_auth_error(production, credentials, monkeypatch):
    import types

    class DownloadAuthError(Exception):
        pass

    calls = []

    def bad_auth(*a, **k):
        calls.append(1)
        raise DownloadAuthError("401 Unauthorized")

    monkeypatch.setitem(sys.modules, "imergpy", types.SimpleNamespace(get_precipitation=bad_auth))
    slept = []
    monkeypatch.setattr(imerg_etl.time, "sleep", slept.append)
    with pytest.raises(RuntimeError, match="401 Unauthorized"):
        imerg_etl.fetch_with_retry(10.0, -84.0, "2024-01-01", "2024-01-02")
    assert len(calls) == 1 and slept == []
    assert imerg_etl._circuit_breaker.failures == 1


def test_imerg_to_dataframe_handles_excel_and_half_hourly():
    hhr = [
        {"Start Time": "2024-01-01 00:00:00", "End Time": "2024-01-01 00:30:00",
         "Precipitation_mm_per_half_hour": 1.25},
        {"Start Time": "2024-01-01 00:30:00", "End Time": "2024-01-01 01:00:00",
         "Precipitation_mm_per_half_hour": 2.50},
    ]
    df = imerg_etl._imerg_to_dataframe(hhr)
    assert df is not None
    assert df.to_dict(orient="records") == [{"date": "2024-01-01", "precipitation_mm": 3.75}]
    assert imerg_etl._imerg_to_dataframe([]) is None


def test_climatology_skips_imerg_ten_year_loop(production, credentials, monkeypatch):
    monkeypatch.setattr(imerg_etl, "download_power", _fake_power)

    def must_not_call_imerg(*a, **k):
        raise AssertionError("climatology must not download 10 years of daily IMERG granules")

    monkeypatch.setattr(imerg_etl, "fetch_with_retry", must_not_call_imerg)
    clim = climatology.get_climatology(10.0, -84.0, until="2025-05-15")
    assert clim["fuente_datos"] == "nasa_power"


def test_probe_aborts_immediately_on_html_login_page(production, credentials, monkeypatch):
    """Multi-day IMERG fetch must abort on the 1-granule probe when NASA returns an HTML page."""
    import types

    probe_calls = []

    class FakeDownloader:
        def __init__(self, username, password, timeout=60, retries=3):
            pass

        def download_granule(self, lat, lon, dt, out_path, run_type="early", freq="hhr"):
            probe_calls.append(dt)
            raise RuntimeError(
                "NASA returned a web page instead of IMERG NetCDF data. This usually means "
                "Earthdata login or GES DISC authorization is required."
            )

    def must_not_loop(*a, **k):
        raise AssertionError("get_precipitation must not loop 200+ days when auth probe fails")

    fake_mod = types.SimpleNamespace(
        downloader=types.SimpleNamespace(EarthdataDownloader=FakeDownloader),
        get_precipitation=must_not_loop,
    )
    monkeypatch.setitem(sys.modules, "imergpy", fake_mod)
    slept = []
    monkeypatch.setattr(imerg_etl.time, "sleep", slept.append)

    with pytest.raises(RuntimeError, match="NASA returned a web page"):
        imerg_etl.fetch_with_retry(41.8, -93.6, "2026-04-01", "2026-11-08")
    assert len(probe_calls) == 1 and slept == []
    assert imerg_etl._circuit_breaker.failures == 1


def test_ingest_point_uses_imerg_start_for_imerg_only(production, credentials, monkeypatch):
    monkeypatch.setattr(imerg_etl, "download_power", _fake_power)
    monkeypatch.setattr(
        imerg_etl, "earthdata_status", lambda: {"available": True, "reason": None}
    )
    seen = {}

    def fake_fetch(lat, lon, start_date, end_date, **k):
        seen["imerg_range"] = (start_date, end_date)
        return "x.xlsx", [
            {"Start_Time": f"{start_date}T00:00:00", "Precipitation_mm_per_day": 5.0},
            {"Start_Time": f"{end_date}T00:00:00", "Precipitation_mm_per_day": 1.0},
        ]

    monkeypatch.setattr(imerg_etl, "fetch_with_retry", fake_fetch)
    data = pipeline.ingest_point(
        41.8, -93.6, "2026-04-01", "2026-11-08", imerg_start="2026-10-04"
    )
    assert seen["imerg_range"] == ("2026-10-04", "2026-11-08")
    assert data["fuente_datos"] == "nasa_power+imerg"
    assert len(data["power"]) > 200
    assert len(data["rainfall"]) == 2
