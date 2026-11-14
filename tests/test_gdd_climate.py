"""Tests for Neithan P2 + Next Wave GDD, climate regimes, and CLI."""
from __future__ import annotations

from datetime import date, timedelta
import json
import math
import socket

import numpy as np
import pandas as pd
import pytest

from piper_agent import __main__ as cli_main
from piper_agent import config, contracts
from piper_agent.data import cache_loader, generate_cache, resilience
from piper_agent.data.ingestion import imerg_etl, pipeline
from piper_agent.tools import fetch_power_gdd as gdd_mod
from piper_agent.tools.fetch_power_gdd import (
    build_climate_contract_bundle,
    compute_climatological_frost_date,
    detect_season_stage,
    fetch_power_gdd,
    validate_hemisphere_frost_baselines,
)


class _NetworkBlockedError(RuntimeError):
    """Raised when a test unexpectedly attempts an outbound network call."""


@pytest.fixture
def no_network(monkeypatch):
    """Block outbound sockets, DNS lookups, and requests.get calls."""
    import requests

    attempts: list[object] = []
    real_connect = socket.socket.connect
    real_getaddrinfo = socket.getaddrinfo

    def guarded_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else str(address)
        unix_family = getattr(socket, "AF_UNIX", -1)
        if host in ("127.0.0.1", "::1", "localhost") or (
            self.family == unix_family
        ):
            return real_connect(self, address, *args, **kwargs)
        attempts.append(("connect", address))
        raise _NetworkBlockedError(f"Blocked socket connect to {address}")

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host not in ("127.0.0.1", "::1", "localhost", None):
            attempts.append(("dns", host))
            raise _NetworkBlockedError(f"Blocked DNS lookup for {host}")
        return real_getaddrinfo(host, *args, **kwargs)

    def guarded_requests_get(url, *args, **kwargs):
        attempts.append(("http", url))
        raise _NetworkBlockedError(f"Blocked HTTP GET to {url}")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(requests, "get", guarded_requests_get)
    yield attempts


def _build_power_frame(
    start: str,
    end: str,
    regime: str,
    *,
    date_format: str = "iso",
    include_gwetroot: bool = True,
    gwetroot_val: float = 0.55,
    fill_every: int | None = None,
    drop_every: int | None = None,
) -> pd.DataFrame:
    """Build deterministic POWER DataFrame across regimes and formats."""
    dates = pd.date_range(start, end, freq="D")
    if drop_every:
        keep_mask = [(idx % drop_every) != 3 for idx in range(len(dates))]
        dates = dates[keep_mask]

    doys = dates.day_of_year.to_numpy(dtype=float)
    if regime == "temperate_north":
        tmean = 13.0 + 14.0 * np.sin(2.0 * np.pi * (doys - 109.0) / 365.0)
        half_span = 6.5
    elif regime == "temperate_south":
        tmean = 11.0 + 13.0 * np.sin(2.0 * np.pi * (doys - 291.5) / 365.0)
        half_span = 6.0
    elif regime == "tropical":
        tmean = 24.5 + 2.0 * np.sin(2.0 * np.pi * (doys - 80.0) / 365.0)
        half_span = 5.5
    else:
        raise ValueError(f"Unknown regime {regime}")

    tmax = np.round(tmean + half_span, 2)
    tmin = np.round(tmean - half_span, 2)
    precip = np.round(2.5 + 2.0 * np.cos(doys / 20.0) ** 2, 2)

    if fill_every:
        for idx in range(0, len(dates), fill_every):
            tmax[idx] = -999.0
            tmin[idx] = -999.0
            precip[idx] = -999.0

    data: dict[str, object] = {}
    if date_format == "iso":
        data["date"] = dates.strftime("%Y-%m-%d").tolist()
    elif date_format == "yyyymmdd":
        data["YYYYMMDD"] = dates.strftime("%Y%m%d").astype(int).tolist()
    elif date_format == "ymd_cols":
        data["YEAR"] = dates.year.tolist()
        data["MO"] = dates.month.tolist()
        data["DY"] = dates.day.tolist()
    else:
        raise ValueError(f"Unknown date_format {date_format}")

    data["T2M_MAX"] = tmax
    data["T2M_MIN"] = tmin
    data["PRECTOTCORR"] = precip
    if include_gwetroot:
        gw = np.full(len(dates), float(gwetroot_val))
        if fill_every:
            for idx in range(0, len(dates), fill_every):
                gw[idx] = -999.0
        data["GWETROOT"] = gw

    return pd.DataFrame(data)


def _make_freeze_series(
    years: range,
    first_freeze_doys: list[int],
    hemisphere: str,
    *,
    include_off_season_cold: bool = True,
) -> pd.DataFrame:
    """Create 10-yr daily series with exact first autumn freeze per year."""
    assert len(list(years)) == len(first_freeze_doys)
    rows: list[dict[str, object]] = []
    for yr, target_doy in zip(years, first_freeze_doys):
        d = date(yr, 1, 1)
        last = date(yr, 12, 31)
        while d <= last:
            doy = d.timetuple().tm_yday
            if hemisphere == "north":
                if include_off_season_cold and doy == 15:
                    tmin, tmax = -5.0, 4.0
                elif doy >= target_doy:
                    tmin, tmax = -1.5, 9.0
                else:
                    tmin, tmax = 12.0, 24.0
            else:
                if include_off_season_cold and doy == 345:
                    tmin, tmax = -3.0, 8.0
                elif 61 <= doy < target_doy:
                    tmin, tmax = 10.0, 22.0
                elif target_doy <= doy <= 200:
                    tmin, tmax = -1.0, 10.0
                else:
                    tmin, tmax = 14.0, 26.0
            rows.append({
                "date": d.isoformat(),
                "T2M_MAX": tmax,
                "T2M_MIN": tmin,
                "PRECTOTCORR": 1.5,
            })
            d += timedelta(days=1)
    return pd.DataFrame(rows)


# ── 1. N4 Config Climate Constants ──────────────────────────────────────────


def test_config_preserves_existing_constants():
    assert config.TOLERANCE_ORDINAL == {"Low": 1, "Medium": 2, "High": 3}
    assert config.DEFAULT_TBASE_C == 10.0
    assert config.SAFETY_MARGIN == 0.8
    assert config.CROP_TBASE == contracts.CROP_TBASE
    assert config.CROP_TBASE == {
        "Sorghum": 10.0,
        "Millet": 10.0,
        "Buckwheat": 5.0,
        "Cowpea": 10.0,
        "Cereal rye (cover)": 0.0,
    }


def test_config_climate_constants_and_frost_bands_match_schema():
    assert config.HEMISPHERE_DEFAULT == "auto"
    assert config.VALID_HEMISPHERES == ("auto", "north", "south")
    assert config.API_MODE_DEFAULT == "demo"
    assert config.VALID_API_MODES == ("demo", "live")
    assert config.TROPICAL_LATITUDE == 23.5
    assert config.FROST_THRESHOLD_C == 0.0
    assert config.HEAT_WAVE_TMAX_C == 35.0
    assert config.HEAT_WAVE_MIN_DAYS == 3

    bands = config.CLIMATE_FROST_BANDS
    disk_bands = cache_loader.load_frost_bands()
    assert bands["tropical_latitude"] == generate_cache.TROPICAL_LATITUDE
    assert bands["north"] == generate_cache.FROST_BANDS["north"]
    assert bands["south"] == generate_cache.FROST_BANDS["south"]
    assert bands["north"] == disk_bands["north"]
    assert bands["south"] == disk_bands["south"]

    for hem in ("north", "south"):
        prev_max = config.TROPICAL_LATITUDE
        for band in bands[hem]:
            assert band["lat_min"] == prev_max
            assert band["lat_min"] < band["lat_max"]
            mm, dd = map(int, band["first_frost"].split("-"))
            assert 1 <= mm <= 12 and 1 <= dd <= 31
            prev_max = band["lat_max"]
        assert prev_max == 90.0

    trop = bands["tropical"]
    assert trop["lat_min"] == -23.5
    assert trop["lat_max"] == 23.5
    assert trop["method"] == "rainy_season_end"
    assert trop["baseline_driven"] is True
    assert trop["north_default"] == "11-15"
    assert trop["south_default"] == "05-15"

    mappings = config.FROST_MONTH_MAPPINGS
    assert set(mappings) == {
        "north_to_south",
        "south_to_north",
        "north_to_south_month",
        "south_to_north_month",
        "bands",
    }
    assert len(mappings["bands"]) == len(bands["north"]) + 1
    for n_mmdd, s_mmdd in mappings["north_to_south"].items():
        assert mappings["south_to_north"][s_mmdd] == n_mmdd
    for n_m, s_m in mappings["north_to_south_month"].items():
        assert mappings["south_to_north_month"][s_m] == n_m


def test_config_season_stages_units_and_representative_coords():
    expected_stages = (
        "planting",
        "vegetative",
        "flowering",
        "harvest",
        "post-harvest",
    )
    assert config.SEASON_STAGES == expected_stages
    thresholds = config.SEASON_STAGE_THRESHOLDS
    assert tuple(thresholds.keys()) == expected_stages

    expected_bounds = [
        (0.0, 0.15),
        (0.15, 0.50),
        (0.50, 0.80),
        (0.80, 1.00),
        (1.00, None),
    ]
    for idx, (stage_name, (lo, hi)) in enumerate(
        zip(expected_stages, expected_bounds), start=1
    ):
        cfg = thresholds[stage_name]
        assert cfg["order"] == idx
        assert cfg["gdd_progress_min"] == lo
        assert cfg["gdd_progress_max"] == hi
        assert set(cfg["hazard_sensitivity"]) == {
            "flood",
            "drought",
            "heat_wave",
            "frost",
        }
        assert set(cfg["hazard_sensitivity"].values()) <= {
            "low",
            "medium",
            "high",
        }
        assert isinstance(cfg["description"], str) and cfg["description"]

    units = config.CLIMATE_UNITS
    assert set(units) == {
        "gdd",
        "temperature",
        "precipitation",
        "root_zone_soil_wetness",
        "doy",
        "coordinates",
    }
    assert units["gdd"]["unit"] == "degC-days"
    assert units["temperature"]["unit"] == "degC"
    assert units["precipitation"]["unit"] == "mm"
    assert units["root_zone_soil_wetness"]["unit"] == "fraction"
    assert units["doy"]["unit"] == "day_of_year"
    assert units["coordinates"]["unit"] == "decimal_degrees"

    regimes = config.REPRESENTATIVE_REGIME_COORDINATES
    assert set(regimes) == {"temperate_north", "temperate_south", "tropical"}
    for key, cfg in regimes.items():
        assert -90.0 <= cfg["lat"] <= 90.0
        assert -180.0 <= cfg["lon"] <= 180.0
        if key == "tropical":
            assert abs(cfg["lat"]) < config.TROPICAL_LATITUDE
        else:
            assert abs(cfg["lat"]) >= config.TROPICAL_LATITUDE
        assert len(cfg["sites"]) >= 1
        for site in cfg["sites"]:
            assert -90.0 <= site["lat"] <= 90.0
            assert -180.0 <= site["lon"] <= 180.0


# ── 2. Q5 Zero Look-Ahead Invariance ────────────────────────────────────────


@pytest.mark.parametrize("current_date", ["2025-05-15", "2025-06-25"])
def test_zero_lookahead_invariance_flood_truncated_and_poisoned(
    monkeypatch, no_network, current_date
):
    base_df = cache_loader.load_power("flood")
    cutoff = pd.Timestamp(current_date)
    future_mask = pd.to_datetime(base_df["date"]) > cutoff
    assert future_mask.any(), "flood power cache must include future rows"

    full = fetch_power_gdd(
        lat=41.8,
        lon=-93.6,
        season_start="2025-04-01",
        current_date=current_date,
        demo_name="flood",
    )

    truncated_df = base_df.loc[~future_mask].copy()

    poisoned_hot_df = base_df.copy()
    poisoned_hot_df.loc[future_mask, "T2M_MAX"] = 99.0
    poisoned_hot_df.loc[future_mask, "T2M_MIN"] = 50.0
    poisoned_hot_df.loc[future_mask, "PRECTOTCORR"] = 500.0

    poisoned_fill_df = base_df.copy()
    poisoned_fill_df.loc[future_mask, "T2M_MAX"] = -999.0
    poisoned_fill_df.loc[future_mask, "T2M_MIN"] = -999.0
    poisoned_fill_df.loc[future_mask, "PRECTOTCORR"] = -999.0

    for variant_df in (truncated_df, poisoned_hot_df, poisoned_fill_df):
        monkeypatch.setattr(
            gdd_mod, "load_power", lambda _name, df=variant_df: df.copy()
        )
        alt = fetch_power_gdd(
            lat=41.8,
            lon=-93.6,
            season_start="2025-04-01",
            current_date=current_date,
            demo_name="flood",
        )
        assert alt.gdd_accumulated == full.gdd_accumulated
        assert alt.gdd_remaining == full.gdd_remaining
        assert alt.avg_daily_gdd == full.avg_daily_gdd
        assert alt.frost_date == full.frost_date
        assert alt.hemisphere == full.hemisphere
        assert alt.details["per_crop_gdd"] == full.details["per_crop_gdd"]
        assert alt.details["ola_calor"] == full.details["ola_calor"]
        assert alt.details["suelo"] == full.details["suelo"]
        assert alt.details["season_stage"] == full.details["season_stage"]
        assert alt.details["lookahead_excluded"] is True

    assert no_network == []


def test_zero_lookahead_gwetroot_and_season_boundaries(no_network):
    base_df = cache_loader.load_power("flood").copy()
    base_df["GWETROOT"] = 0.48
    cutoff = pd.Timestamp("2025-06-25")
    future_mask = pd.to_datetime(base_df["date"]) > cutoff

    poisoned_df = base_df.copy()
    poisoned_df.loc[future_mask, "GWETROOT"] = 0.99
    poisoned_df.loc[future_mask, "T2M_MAX"] = 99.0
    poisoned_df.loc[future_mask, "T2M_MIN"] = 50.0
    snapshot_before = poisoned_df.copy()

    res_full = fetch_power_gdd(
        lat=41.8,
        lon=-93.6,
        season_start="2025-04-01",
        current_date="2025-06-25",
        demo_name="flood",
        power_df=poisoned_df,
    )
    res_cut = fetch_power_gdd(
        lat=41.8,
        lon=-93.6,
        season_start="2025-04-01",
        current_date="2025-06-25",
        demo_name="flood",
        power_df=base_df.loc[~future_mask].copy(),
    )
    pd.testing.assert_frame_equal(poisoned_df, snapshot_before)
    assert res_full.details["suelo"] == res_cut.details["suelo"]
    assert res_full.details["suelo"]["gwetroot_latest"] == 0.48

    # Before season start
    pre = fetch_power_gdd(
        lat=41.8,
        lon=-93.6,
        season_start="2025-04-01",
        current_date="2025-03-15",
        demo_name="flood",
    )
    assert pre.gdd_accumulated == 0.0
    assert pre.gdd_remaining > 0.0
    assert pre.details["season_stage"]["is_pre_season"] is True
    assert pre.details["season_stage"]["stage"] == "planting"

    # Mid-season
    mid = fetch_power_gdd(
        lat=41.8,
        lon=-93.6,
        season_start="2025-04-01",
        current_date="2025-06-25",
        demo_name="flood",
    )
    assert mid.gdd_accumulated > 0.0
    assert mid.gdd_remaining > 0.0

    # Exact frost date (flood_baselines frost date is 2015-09-28 -> 2025-09-28)
    on_frost = fetch_power_gdd(
        lat=41.8,
        lon=-93.6,
        season_start="2025-04-01",
        current_date="2025-09-28",
        demo_name="flood",
    )
    assert on_frost.frost_date == "2025-09-28"
    assert on_frost.gdd_remaining == 0.0
    assert on_frost.gdd_accumulated > 0.0
    assert on_frost.details["season_stage"]["stage"] == "post-harvest"
    assert on_frost.details["season_stage"]["is_post_frost"] is True
    for crop_stats in on_frost.details["per_crop_gdd"].values():
        assert crop_stats["gdd_remaining"] == 0.0

    # After frost date
    after_frost = fetch_power_gdd(
        lat=41.8,
        lon=-93.6,
        season_start="2025-04-01",
        current_date="2025-11-01",
        demo_name="flood",
    )
    assert after_frost.gdd_remaining == 0.0
    assert after_frost.gdd_accumulated > 0.0
    assert after_frost.details["season_stage"]["stage"] == "post-harvest"
    assert no_network == []


# ── 3. N1 Tropics Have No Climatological Frost ──────────────────────────────


def test_tropics_northern_drought_baseline(no_network):
    res = fetch_power_gdd(
        lat=9.0,
        lon=41.0,
        season_start="2024-11-01",
        current_date="2025-01-30",
        demo_name="drought",
    )
    d = res.details
    assert res.hemisphere == "north"
    assert res.frost_date == "2025-06-30"
    assert d["tropical"] is True
    assert d["has_climatological_frost"] is False
    assert d["climate_regime"] == "tropical"
    assert d["season_end_method"] == "rainy_season_end"
    assert d["method"] == "rainy_season_end"
    assert no_network == []


def test_tropics_southern_no_frost_and_no_naive_182d_shift(no_network):
    res_drought = fetch_power_gdd(
        lat=-12.0,
        lon=-75.0,
        season_start="2024-11-01",
        current_date="2025-01-30",
        demo_name="drought",
    )
    res_flood = fetch_power_gdd(
        lat=-12.0,
        lon=-75.0,
        season_start="2024-11-01",
        current_date="2025-01-30",
        demo_name="flood",
    )
    synth_df = _build_power_frame(
        "2015-01-01", "2025-02-01", "tropical", include_gwetroot=True
    )
    synth_df.loc[100, "T2M_MIN"] = -3.0  # cold glitch must not trigger frost
    res_synth = fetch_power_gdd(
        lat=-12.0,
        lon=-75.0,
        season_start="2024-11-01",
        current_date="2025-01-30",
        power_df=synth_df,
    )

    for res in (res_drought, res_flood, res_synth):
        d = res.details
        assert res.hemisphere == "south"
        assert d["tropical"] is True
        assert d["has_climatological_frost"] is False
        assert d["climate_regime"] == "tropical"
        assert d["season_end_method"] == "rainy_season_end"
        assert d["method"] == "rainy_season_end"

    # Must use tropical south_default ("05-15"), never northern 09-28 + 182d
    assert res_flood.frost_date == "2025-05-15"
    assert res_synth.frost_date == "2025-05-15"
    assert res_flood.frost_date not in (
        "2025-03-29",
        "2025-03-30",
        "2025-09-28",
    )
    assert no_network == []


def test_tropical_latitude_boundary(no_network):
    synth = _build_power_frame("2024-01-01", "2025-06-01", "tropical")
    for lat, expected_trop in (
        (0.0, True),
        (23.4, True),
        (-23.4, True),
        (23.5, False),
        (-23.5, False),
    ):
        s_start = "2024-10-01" if lat < 0 else "2025-04-01"
        c_date = "2025-01-15" if lat < 0 else "2025-05-15"
        res = fetch_power_gdd(
            lat=lat,
            lon=0.0,
            season_start=s_start,
            current_date=c_date,
            power_df=synth,
        )
        assert res.details["tropical"] is expected_trop
        assert res.details["has_climatological_frost"] is (not expected_trop)
        expected_method = (
            "rainy_season_end" if expected_trop else "climatological_frost"
        )
        assert res.details["season_end_method"] == expected_method
    assert no_network == []


# ── 4. N2 Multi-Hemisphere & Cross-Year Southern Continuity ─────────────────


@pytest.mark.parametrize(
    "lat,lon",
    [(-33.9, 18.4), (-34.6, -58.4)],
)
def test_southern_temperate_cross_year_continuity(no_network, lat, lon):
    south_df = _build_power_frame(
        "2015-01-01", "2026-05-31", "temperate_south"
    )
    dec = fetch_power_gdd(
        lat=lat,
        lon=lon,
        season_start="2025-10-01",
        current_date="2025-12-15",
        power_df=south_df,
    )
    feb = fetch_power_gdd(
        lat=lat,
        lon=lon,
        season_start="2025-10-01",
        current_date="2026-02-15",
        power_df=south_df,
    )
    assert dec.hemisphere == "south"
    assert feb.hemisphere == "south"
    assert dec.frost_date == feb.frost_date
    assert dec.frost_date[:7] in ("2026-04", "2026-05")
    assert feb.gdd_accumulated > dec.gdd_accumulated > 0.0
    assert dec.gdd_remaining > feb.gdd_remaining > 0.0
    assert dec.details["season_end_method"] == "climatological_frost"

    # Also verify generate_cache Southern archive cross-year continuity
    gen_df = generate_cache.generate_power(
        "2026-05-31", "2015-01-01", lat, season_end=None
    )
    gen_dec = fetch_power_gdd(
        lat=lat,
        lon=lon,
        season_start="2025-10-01",
        current_date="2025-12-15",
        power_df=gen_df,
    )
    gen_feb = fetch_power_gdd(
        lat=lat,
        lon=lon,
        season_start="2025-10-01",
        current_date="2026-02-15",
        power_df=gen_df,
    )
    assert gen_dec.frost_date == gen_feb.frost_date
    assert gen_dec.frost_date.startswith("2026-")
    assert gen_feb.gdd_accumulated > gen_dec.gdd_accumulated > 0.0
    assert gen_dec.gdd_remaining > gen_feb.gdd_remaining > 0.0
    assert no_network == []


def test_southern_baseline_never_double_shifted(tmp_path, no_network):
    site_dir = tmp_path / "cape_town"
    site_dir.mkdir()
    baselines = {
        "p95_3day_cum_rainfall": 30.0,
        "p10_30day_cum_rainfall": 80.0,
        "climatological_frost_date": "2024-05-05",
        "frost_method": "southern_autumn_frost",
        "hemisphere": "south",
        "tropical": False,
        "fuente_datos": "sintetico",
    }
    (site_dir / "cape_town_baselines.json").write_text(
        json.dumps(baselines), encoding="utf-8"
    )
    df = _build_power_frame("2015-01-01", "2026-03-01", "temperate_south")
    df.to_csv(site_dir / "cape_town_power.csv", index=False)

    res = fetch_power_gdd(
        lat=-33.9,
        lon=18.4,
        season_start="2025-10-01",
        current_date="2025-12-15",
        baseline_dir=str(site_dir),
    )
    assert res.hemisphere == "south"
    assert res.frost_date == "2026-05-05"
    assert res.details["frost_baseline_date"] == "2024-05-05"
    assert no_network == []


def test_hemisphere_override_and_invalid_inputs(no_network):
    south_df = _build_power_frame(
        "2015-01-01", "2026-03-01", "temperate_south"
    )
    res_auto = fetch_power_gdd(
        lat=-33.9,
        lon=18.4,
        season_start="2025-10-01",
        current_date="2025-12-15",
        hemisphere="auto",
        power_df=south_df,
    )
    res_south = fetch_power_gdd(
        lat=-33.9,
        lon=18.4,
        season_start="2025-10-01",
        current_date="2025-12-15",
        hemisphere="south",
        power_df=south_df,
    )
    res_north = fetch_power_gdd(
        lat=-33.9,
        lon=18.4,
        season_start="2025-04-01",
        current_date="2025-06-15",
        hemisphere="north",
        demo_name="flood",
    )
    res_south_flood = fetch_power_gdd(
        lat=-33.9,
        lon=18.4,
        season_start="2025-10-01",
        current_date="2025-12-15",
        hemisphere="south",
        demo_name="flood",
    )
    assert res_auto.hemisphere == "south"
    assert res_south.hemisphere == "south"
    assert res_north.hemisphere == "north"
    assert res_north.details["hemisphere_requested"] == "north"
    assert res_north.details["climate_regime"] == "temperate_north"
    assert res_north.frost_date == "2025-09-28"
    assert res_south_flood.frost_date == "2026-05-05"
    assert res_south_flood.details["frost_baseline_date"] == "2026-05-05"

    for bad_hem in ("east", "west", ""):
        with pytest.raises(ValueError, match="hemisphere"):
            fetch_power_gdd(
                lat=41.8,
                lon=-93.6,
                season_start="2025-04-01",
                current_date="2025-05-15",
                demo_name="flood",
                hemisphere=bad_hem,
            )

    for bad_mode in ("offline", "prod", ""):
        with pytest.raises(ValueError, match="api_mode"):
            fetch_power_gdd(
                lat=41.8,
                lon=-93.6,
                season_start="2025-04-01",
                current_date="2025-05-15",
                demo_name="flood",
                api_mode=bad_mode,
            )

    with pytest.raises(ValueError, match="lat"):
        fetch_power_gdd(
            lat=95.0,
            lon=0.0,
            season_start="2025-04-01",
            current_date="2025-05-15",
            demo_name="flood",
        )

    with pytest.raises(ValueError, match="lon"):
        fetch_power_gdd(
            lat=41.8,
            lon=-185.0,
            season_start="2025-04-01",
            current_date="2025-05-15",
            demo_name="flood",
        )

    with pytest.raises(ValueError, match="tbase_c"):
        fetch_power_gdd(
            lat=41.8,
            lon=-93.6,
            season_start="2025-04-01",
            current_date="2025-05-15",
            demo_name="flood",
            tbase_c=float("nan"),
        )
    assert no_network == []


# ── 5. Next Wave #1 Real NASA POWER DataFrame Robustness ────────────────────


@pytest.mark.parametrize(
    "regime,lat,lon,season_start,current_date,date_format",
    [
        (
            "temperate_north",
            41.8,
            -93.6,
            "2025-04-01",
            "2025-06-25",
            "ymd_cols",
        ),
        (
            "temperate_south",
            -33.9,
            18.4,
            "2025-10-01",
            "2025-12-15",
            "yyyymmdd",
        ),
        (
            "tropical",
            9.0,
            41.0,
            "2025-04-01",
            "2025-06-15",
            "iso",
        ),
        (
            "tropical",
            -12.0,
            -75.0,
            "2024-11-01",
            "2025-01-30",
            "ymd_cols",
        ),
    ],
)
def test_real_power_dataframe_robustness_all_regimes(
    no_network, regime, lat, lon, season_start, current_date, date_format
):
    df = _build_power_frame(
        "2018-01-01",
        "2026-03-01",
        regime,
        date_format=date_format,
        include_gwetroot=False,
        fill_every=9,
        drop_every=7,
    )
    res = fetch_power_gdd(
        lat=lat,
        lon=lon,
        season_start=season_start,
        current_date=current_date,
        power_df=df,
    )
    assert math.isfinite(res.gdd_accumulated) and res.gdd_accumulated > 0.0
    assert math.isfinite(res.gdd_remaining) and res.gdd_remaining > 0.0
    assert math.isfinite(res.avg_daily_gdd) and res.avg_daily_gdd >= 0.0
    for stats in res.details["per_crop_gdd"].values():
        assert math.isfinite(stats["gdd_accumulated"])
        assert math.isfinite(stats["gdd_remaining"])
        assert math.isfinite(stats["gdd_to_frost"])
    assert res.details["suelo"]["gwetroot_latest"] is None
    assert res.details["suelo"]["gwetroot_mean_14d"] is None
    assert (
        res.details["confianza_calibrada_inputs"]["has_real_gwetroot"]
        is False
    )
    json.dumps(res.details, allow_nan=False)
    assert no_network == []


def test_single_year_seasonal_cosine_fallback_monotonic_decay(
    monkeypatch, no_network
):
    monkeypatch.setattr(gdd_mod, "_load_local_monthly_tmean", lambda *_: {})

    cases = [
        (
            "temperate_north",
            41.8,
            -93.6,
            "2025-04-01",
            ["2025-04-20", "2025-06-05", "2025-07-20", "2025-09-05"],
        ),
        (
            "temperate_south",
            -33.9,
            18.4,
            "2025-10-01",
            ["2025-10-20", "2025-12-15", "2026-02-15", "2026-04-10"],
        ),
        (
            "tropical",
            -12.0,
            -75.0,
            "2024-11-01",
            ["2024-11-20", "2025-01-15", "2025-03-10", "2025-04-25"],
        ),
    ]
    for regime, lat, lon, s_start, probe_dates in cases:
        df = _build_power_frame(
            s_start,
            probe_dates[-1],
            regime,
            date_format="ymd_cols",
            include_gwetroot=False,
            fill_every=11,
        )
        rems: list[float] = []
        for cur in probe_dates:
            res = fetch_power_gdd(
                lat=lat,
                lon=lon,
                season_start=s_start,
                current_date=cur,
                power_df=df,
            )
            assert res.details["projection_method"] == (
                "seasonal_curve_fallback"
            )
            assert math.isfinite(res.gdd_remaining) and res.gdd_remaining > 0.0
            rems.append(res.gdd_remaining)
        assert rems == sorted(rems, reverse=True)
        assert len(set(rems)) == len(rems)

    assert no_network == []


# ── 6. Next Wave #2 Season Stage Detection ──────────────────────────────────


@pytest.mark.parametrize(
    "acc,rem,expected_stage",
    [
        (0.0, 1000.0, "planting"),
        (149.0, 851.0, "planting"),
        (150.0, 850.0, "vegetative"),
        (499.0, 501.0, "vegetative"),
        (500.0, 500.0, "flowering"),
        (799.0, 201.0, "flowering"),
        (800.0, 200.0, "harvest"),
        (999.0, 1.0, "harvest"),
        (1000.0, 0.0, "post-harvest"),
    ],
)
def test_detect_season_stage_all_five_stages_and_thresholds(
    acc, rem, expected_stage
):
    stage = detect_season_stage(
        gdd_accumulated=acc,
        gdd_remaining=rem,
        current_date="2025-07-01",
        season_start="2025-04-01",
        season_end="2025-10-10",
        is_tropical=False,
        event_type="flood",
    )
    cfg = config.SEASON_STAGE_THRESHOLDS[expected_stage]
    assert stage["stage"] == expected_stage
    assert stage["hazard_sensitivity"] == cfg["hazard_sensitivity"]
    interp = stage["hazard_interpretation"]
    assert interp["order"] == cfg["order"]
    assert interp["primary_hazards"] == list(cfg["primary_hazards"])
    assert interp["active_event"] == "flood"
    assert (
        interp["active_event_sensitivity"]
        == cfg["hazard_sensitivity"]["flood"]
    )


def test_detect_season_stage_pre_season_post_frost_and_tropical_notes():
    pre = detect_season_stage(
        gdd_accumulated=10.0,
        gdd_remaining=1200.0,
        current_date="2025-03-20",
        season_start="2025-04-01",
        season_end="2025-10-10",
        is_tropical=False,
    )
    assert pre["stage"] == "planting"
    assert pre["is_pre_season"] is True
    assert pre["is_post_season"] is False
    assert pre["is_post_frost"] is False
    assert pre["progress_ratio"] == 0.0
    assert pre["days_elapsed"] < 0
    assert pre["window"]["pre_season"] is True
    assert pre["window"]["in_season"] is False
    assert "Temperate frost sensitivity" in (
        pre["hazard_interpretation"]["frost_note"]
    )

    post_frost = detect_season_stage(
        gdd_accumulated=1400.0,
        gdd_remaining=0.0,
        current_date="2025-10-20",
        season_start="2025-04-01",
        season_end="2025-10-10",
        is_tropical=False,
    )
    assert post_frost["stage"] == "post-harvest"
    assert post_frost["is_post_season"] is True
    assert post_frost["is_post_frost"] is True
    assert post_frost["days_remaining"] == 0
    assert post_frost["window"]["season_end_label"] == "climatological_frost"

    tropical_stage = detect_season_stage(
        gdd_accumulated=600.0,
        gdd_remaining=400.0,
        current_date="2025-07-10",
        season_start="2024-11-01",
        season_end="2025-06-30",
        is_tropical=True,
    )
    assert tropical_stage["stage"] == "post-harvest"
    assert tropical_stage["is_post_season"] is True
    assert tropical_stage["is_post_frost"] is False
    assert tropical_stage["window"]["season_end_label"] == "rainy_season_end"
    assert "No climatological frost risk in tropical regime" in (
        tropical_stage["hazard_interpretation"]["frost_note"]
    )


# ── 7. N6 & Next Wave #3 10-Yr Frost & Multi-Regime Validation ──────────────


def test_compute_climatological_frost_date_north_south_and_tropics(no_network):
    years = range(2015, 2025)
    north_doys = [275, 277, 279, 281, 283, 285, 287, 289, 291, 293]
    north_df = _make_freeze_series(years, north_doys, "north")
    north_stats = compute_climatological_frost_date(
        north_df, lat=41.8, hemisphere="north"
    )
    assert north_stats["tropical"] is False
    assert north_stats["has_climatological_frost"] is True
    assert north_stats["climate_regime"] == "temperate_north"
    assert north_stats["method"] == "first_autumn_frost"
    assert north_stats["frost_years"] == 10
    assert north_stats["total_years"] == 10
    assert north_stats["median_doy"] == 284.0
    assert north_stats["median_mmdd"] == "10-11"
    assert north_stats["earliest_mmdd"] == "10-02"
    assert north_stats["latest_mmdd"] == "10-20"
    assert north_stats["band_first_frost"] == "10-10"
    assert north_stats["doy_diff_vs_band"] == 1.0

    south_doys = [115, 118, 120, 122, 124, 126, 128, 130, 132, 135]
    south_df = _make_freeze_series(years, south_doys, "south")
    south_stats = compute_climatological_frost_date(
        south_df, lat=-34.6, hemisphere="south"
    )
    assert south_stats["tropical"] is False
    assert south_stats["has_climatological_frost"] is True
    assert south_stats["climate_regime"] == "temperate_south"
    assert south_stats["hemisphere"] == "south"
    assert south_stats["frost_years"] == 10
    assert south_stats["median_doy"] == 125.0
    assert south_stats["median_mmdd"] == "05-05"
    assert south_stats["band_first_frost"] == "05-05"
    assert south_stats["doy_diff_vs_band"] == 0.0

    for lat, expected_band in ((9.0, "11-15"), (-12.0, "05-15")):
        trop_stats = compute_climatological_frost_date(north_df, lat=lat)
        assert trop_stats["tropical"] is True
        assert trop_stats["has_climatological_frost"] is False
        assert trop_stats["climate_regime"] == "tropical"
        assert trop_stats["method"] == "rainy_season_end"
        assert trop_stats["median_doy"] is None
        assert trop_stats["median_mmdd"] is None
        assert trop_stats["frost_years"] == 0
        assert trop_stats["per_year_first_frost"] == {}
        assert trop_stats["band_first_frost"] == expected_band

    assert no_network == []


def test_validate_hemisphere_frost_baselines_full_report(no_network):
    extra_sites = [
        {
            "name": "buenos_aires_pampas",
            "lat": -34.6,
            "lon": -58.4,
            "hemisphere": "south",
            "season_start": "2025-10-01",
            "current_date": "2025-12-15",
        },
        {
            "name": "tropical_south_andes",
            "lat": -12.0,
            "lon": -75.0,
            "hemisphere": "south",
            "season_start": "2024-11-01",
            "current_date": "2025-01-30",
        },
    ]
    report = validate_hemisphere_frost_baselines(extra_sites=extra_sites)
    assert report["passed"] is True, report["failures"]
    assert report["failures"] == []
    assert report["checks_total"] >= 11
    assert report["checks_passed"] == report["checks_total"]
    assert report["frost_bands_valid"] is True
    assert report["offline_safe"] is True

    regimes = report["regimes"]
    assert set(regimes) == {"temperate_north", "temperate_south", "tropical"}
    assert regimes["temperate_north"]["season_end_method"] == (
        "climatological_frost"
    )
    assert regimes["temperate_south"]["season_end_method"] == (
        "climatological_frost"
    )
    assert regimes["tropical"]["tropical"] is True
    assert regimes["tropical"]["season_end_method"] == "rainy_season_end"

    cont = report["cross_year_south_continuity"]
    assert cont["passed"] is True
    assert cont["dec_frost_date"] == cont["feb_frost_date"]
    assert cont["feb_gdd_accumulated"] >= cont["dec_gdd_accumulated"]
    assert cont["feb_gdd_remaining"] <= cont["dec_gdd_remaining"]

    assert {"flood", "drought", "normal", "late_flood"} <= set(
        report["scenarios"]
    )
    assert len(report["extra_sites"]) == 2
    assert no_network == []


# ── 8. Next Wave #4 Rich Contract Keys, Units, Thresholds, Metadata ─────────


def test_per_crop_gdd_and_tbase_ordering(no_network):
    res = fetch_power_gdd(
        lat=41.8,
        lon=-93.6,
        season_start="2025-04-01",
        current_date="2025-06-25",
        demo_name="flood",
    )
    per_crop = res.details["per_crop_gdd"]
    assert set(per_crop) == set(config.CROP_TBASE)
    for crop, expected_base in config.CROP_TBASE.items():
        row = per_crop[crop]
        assert row["tbase_c"] == expected_base
        assert set(row) == {
            "tbase_c",
            "gdd_accumulated",
            "gdd_remaining",
            "gdd_to_frost",
        }
        assert row["gdd_to_frost"] == pytest.approx(
            row["gdd_accumulated"] + row["gdd_remaining"], abs=0.2
        )

    rye = per_crop["Cereal rye (cover)"]
    buckwheat = per_crop["Buckwheat"]
    sorghum = per_crop["Sorghum"]
    for metric in ("gdd_accumulated", "gdd_remaining", "gdd_to_frost"):
        assert rye[metric] >= buckwheat[metric] >= sorghum[metric]
    assert no_network == []


def test_ola_calor_in_window_vs_future_lookahead_and_streak(no_network):
    base_df = _build_power_frame(
        "2024-01-01", "2025-07-31", "temperate_north", include_gwetroot=True
    )
    base_df["T2M_MAX"] = base_df["T2M_MAX"].clip(upper=30.0)
    dates = pd.to_datetime(base_df["date"])

    # Active 4-day heat wave up to current_date (2025-07-05)
    active_df = base_df.copy()
    hot_mask = (dates >= "2025-07-02") & (dates <= "2025-07-05")
    active_df.loc[hot_mask, "T2M_MAX"] = [36.2, 37.5, 38.0, 35.8]
    res_active = fetch_power_gdd(
        lat=41.8,
        lon=-93.6,
        season_start="2025-04-01",
        current_date="2025-07-05",
        power_df=active_df,
    )
    ola = res_active.details["ola_calor"]
    assert ola["detected"] is True
    assert ola["event_type"] == "heat_wave"
    assert ola["max_consecutive_days_above_threshold"] >= 4
    assert ola["lookahead_excluded"] is True
    assert res_active.details["agronomic_metadata"]["heat_wave_active"] is True

    # Future heat wave strictly after current_date must NOT trigger ola_calor
    future_df = base_df.copy()
    future_hot = (dates >= "2025-07-06") & (dates <= "2025-07-12")
    future_df.loc[future_hot, "T2M_MAX"] = 42.0
    res_future = fetch_power_gdd(
        lat=41.8,
        lon=-93.6,
        season_start="2025-04-01",
        current_date="2025-07-05",
        power_df=future_df,
    )
    assert res_future.details["ola_calor"]["detected"] is False
    assert res_future.details["ola_calor"]["event_type"] == "none"
    assert res_future.details["ola_calor"]["lookahead_excluded"] is True
    assert (
        res_future.details["agronomic_metadata"]["heat_wave_active"] is False
    )

    # Non-consecutive hot days (2 hot, 1 cool, 2 hot) -> streak 2 < 3
    broken_df = base_df.copy()
    broken_df.loc[
        dates.isin(pd.to_datetime(["2025-07-01", "2025-07-02"])), "T2M_MAX"
    ] = 37.0
    broken_df.loc[dates == "2025-07-03", "T2M_MAX"] = 29.0
    broken_df.loc[
        dates.isin(pd.to_datetime(["2025-07-04", "2025-07-05"])), "T2M_MAX"
    ] = 37.5
    res_broken = fetch_power_gdd(
        lat=41.8,
        lon=-93.6,
        season_start="2025-04-01",
        current_date="2025-07-05",
        power_df=broken_df,
    )
    assert res_broken.details["ola_calor"]["detected"] is False
    assert (
        res_broken.details["ola_calor"]["max_consecutive_days_above_threshold"]
        == 2
    )
    assert no_network == []


def test_contract_bundle_soil_confidence_units_thresholds_json_serializable(
    no_network,
):
    for gwet, expected_status in (
        (0.85, "saturated"),
        (0.20, "dry"),
        (0.50, "adequate"),
    ):
        df = _build_power_frame(
            "2022-01-01",
            "2025-06-25",
            "temperate_north",
            include_gwetroot=True,
            gwetroot_val=gwet,
        )
        res = fetch_power_gdd(
            lat=41.8,
            lon=-93.6,
            season_start="2025-04-01",
            current_date="2025-06-25",
            power_df=df,
        )
        assert res.details["suelo"]["moisture_status"] == expected_status

    res = fetch_power_gdd(
        lat=41.8,
        lon=-93.6,
        season_start="2025-04-01",
        current_date="2025-06-25",
        power_df=_build_power_frame(
            "2022-01-01", "2025-06-25", "temperate_north"
        ),
    )
    bundle = build_climate_contract_bundle(
        res, event_confidence=0.85, event_type="flood"
    )
    required_keys = {
        "per_crop_gdd",
        "ola_calor",
        "suelo",
        "confianza_calibrada_inputs",
        "fuente_datos",
        "units",
        "thresholds",
        "agronomic_metadata",
    }
    assert required_keys <= set(res.details)
    assert required_keys <= set(bundle)
    assert bundle["event_confidence_input"] == 0.85
    assert 0.0 <= bundle["event_confidence_calibrated"] <= 1.0
    assert bundle["units"] == json.loads(json.dumps(config.CLIMATE_UNITS))
    assert bundle["thresholds"]["heat_wave_tmax_c"] == config.HEAT_WAVE_TMAX_C
    assert (
        bundle["thresholds"]["frost_threshold_c"]
        == config.FROST_THRESHOLD_C
    )
    assert bundle["thresholds"]["crop_tbase_c"] == config.CROP_TBASE
    assert bundle["confianza_calibrada_inputs"]["has_real_gwetroot"] is True

    dumped_details = json.dumps(res.details, allow_nan=False)
    dumped_bundle = json.dumps(bundle, allow_nan=False)
    assert isinstance(json.loads(dumped_details), dict)
    assert isinstance(json.loads(dumped_bundle), dict)
    assert no_network == []


# ── 9. N3 & N5 CLI Flags & Live/Fallback Path ───────────────────────────────


def test_cli_hemisphere_flags_and_invalid_exit(no_network, capsys):
    for hem_flag, expected_hem in (
        ("auto", "south"),
        ("south", "south"),
        ("north", "north"),
    ):
        rc = cli_main.main([
            "--lat",
            "-33.9",
            "--lon",
            "18.4",
            "--date",
            "2025-12-15",
            "--demo-name",
            "flood",
            "--hemisphere",
            hem_flag,
            "--json",
        ])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["hemisphere_requested"] == hem_flag
        assert payload["hemisphere"] == expected_hem
        assert payload["gdd_result"]["hemisphere"] == expected_hem
        if expected_hem == "south":
            assert payload["gdd_result"]["details"]["season_start"] == (
                "2025-10-01"
            )
            assert payload["gdd_result"]["frost_date"] == "2026-05-05"
            assert payload["gdd_result"]["gdd_remaining"] > 0.0

    with pytest.raises(SystemExit) as exc:
        cli_main.main([
            "--lat",
            "41.8",
            "--lon",
            "-93.6",
            "--date",
            "2025-05-15",
            "--hemisphere",
            "east",
        ])
    assert exc.value.code != 0
    capsys.readouterr()
    assert no_network == []


def test_cli_demo_name_late_flood_and_season_start_json(no_network, capsys):
    rc_late = cli_main.main([
        "--lat",
        "41.8",
        "--lon",
        "-93.6",
        "--date",
        "2025-08-28",
        "--demo-name",
        "late_flood",
        "--json",
    ])
    assert rc_late == 0
    late_payload = json.loads(capsys.readouterr().out)
    assert late_payload["demo_name"] == "late_flood"
    assert late_payload["recovery_plan"]["fallback"] is True
    assert late_payload["crops"] == []
    assert "cash crop is lost" in late_payload["plan_text"]

    rc_default = cli_main.main([
        "--lat",
        "41.8",
        "--lon",
        "-93.6",
        "--date",
        "2025-05-15",
        "--demo-name",
        "flood",
        "--json",
    ])
    assert rc_default == 0
    default_payload = json.loads(capsys.readouterr().out)

    rc_custom = cli_main.main([
        "--lat",
        "41.8",
        "--lon",
        "-93.6",
        "--date",
        "2025-05-15",
        "--demo-name",
        "flood",
        "--season-start",
        "2025-04-15",
        "--json",
    ])
    assert rc_custom == 0
    custom_payload = json.loads(capsys.readouterr().out)
    assert (
        custom_payload["gdd_result"]["details"]["season_start"]
        == "2025-04-15"
    )
    assert (
        custom_payload["gdd_result"]["gdd_accumulated"]
        < default_payload["gdd_result"]["gdd_accumulated"]
    )
    assert set(custom_payload["per_crop_gdd"]) == set(config.CROP_TBASE)
    assert custom_payload["agronomic_metadata"]["season_stage"] in (
        config.SEASON_STAGES
    )
    assert custom_payload["fuente_datos"]["source"] == "sintetico"
    assert no_network == []


def test_cli_api_mode_live_mocked_nasa_power(monkeypatch, capsys):
    import requests

    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("offline test sandbox")
        ),
    )
    power_df = _build_power_frame(
        "2018-01-01", "2025-05-15", "temperate_north", include_gwetroot=True
    )
    rainfall_df = power_df[["date", "PRECTOTCORR"]].rename(
        columns={"PRECTOTCORR": "precipitation_mm"}
    )
    calls: list[dict[str, object]] = []

    def fake_ingest_point(**kwargs):
        calls.append(kwargs)
        return {
            "power": power_df.copy(),
            "rainfall": rainfall_df.copy(),
            "fuente_datos": "NASA_POWER",
            "fallback_reason": None,
            "demo_scenario": None,
            "region": "lat+42.0_lon-093.5",
        }

    monkeypatch.setattr(cli_main, "ingest_point", fake_ingest_point)

    rc = cli_main.main([
        "--lat",
        "41.8",
        "--lon",
        "-93.6",
        "--date",
        "2025-05-15",
        "--api-mode",
        "live",
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert calls and calls[0]["demo_mode"] is False
    assert payload["api_mode"] == "live"
    assert payload["demo_mode"] is False
    assert payload["fuente_datos"]["source"] == "NASA_POWER"
    assert payload["agronomic_metadata"]["data_source"] == "NASA_POWER"
    assert payload["fallback_reason"] is None


def test_cli_api_mode_live_offline_fallback_json_and_text(
    monkeypatch, tmp_path, capsys
):
    import requests

    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("offline test sandbox")
        ),
    )
    monkeypatch.setattr(pipeline, "REAL_DIR", str(tmp_path / "real"))
    monkeypatch.setattr(
        resilience, "live_circuit_breaker", resilience.CircuitBreaker()
    )
    monkeypatch.setattr(resilience.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        imerg_etl,
        "download_power",
        lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("offline sandbox")
        ),
    )

    rc_json = cli_main.main([
        "--lat",
        "41.8",
        "--lon",
        "-93.6",
        "--date",
        "2025-05-15",
        "--api-mode",
        "live",
        "--json",
    ])
    assert rc_json == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["api_mode"] == "live"
    assert payload["demo_mode"] is False
    assert payload["fuente_datos"]["source"] == "sintetico"
    assert "offline sandbox" in payload["fallback_reason"]
    assert "offline sandbox" in payload["fuente_datos"]["fallback_reason"]

    rc_text = cli_main.main([
        "--lat",
        "41.8",
        "--lon",
        "-93.6",
        "--date",
        "2025-05-15",
        "--api-mode",
        "live",
    ])
    assert rc_text == 0
    text_out = capsys.readouterr().out
    assert "Data Source / Fuente de Datos: sintetico" in text_out
    assert "Fallback Reason:" in text_out
    assert "offline sandbox" in text_out

    # Also cover live fallback without matching demo scenario (Cape Town)
    south_power = _build_power_frame(
        "2018-01-01", "2025-12-15", "temperate_south"
    )
    south_rain = south_power[["date", "PRECTOTCORR"]].rename(
        columns={"PRECTOTCORR": "precipitation_mm"}
    )
    monkeypatch.setattr(
        cli_main,
        "ingest_point",
        lambda **_kw: {
            "power": south_power,
            "rainfall": south_rain,
            "fuente_datos": "sintetico",
            "fallback_reason": "NASA POWER timeout",
            "demo_scenario": None,
            "region": "lat-34.0_lon+018.5",
        },
    )
    rc_south = cli_main.main([
        "--lat",
        "-33.9",
        "--lon",
        "18.4",
        "--date",
        "2025-12-15",
        "--api-mode",
        "live",
        "--json",
    ])
    assert rc_south == 0
    south_payload = json.loads(capsys.readouterr().out)
    assert south_payload["fuente_datos"]["source"] == "sintetico"
    assert south_payload["fallback_reason"] == "NASA POWER timeout"
    assert south_payload["hemisphere"] == "south"


def test_cli_no_demo_and_mocked_run_pier(monkeypatch, capsys):
    import requests

    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("offline test sandbox")
        ),
    )
    power_df = _build_power_frame(
        "2018-01-01", "2025-05-15", "temperate_north"
    )
    rain_df = power_df[["date", "PRECTOTCORR"]].rename(
        columns={"PRECTOTCORR": "precipitation_mm"}
    )
    seen_demo_modes: list[object] = []

    def fake_ingest(**kwargs):
        seen_demo_modes.append(kwargs.get("demo_mode"))
        return {
            "power": power_df.copy(),
            "rainfall": rain_df.copy(),
            "fuente_datos": "nasa_power",
            "fallback_reason": None,
            "demo_scenario": None,
            "region": "lat+42.0_lon-093.5",
        }

    monkeypatch.setattr(cli_main, "ingest_point", fake_ingest)
    rc = cli_main.main([
        "--lat",
        "41.8",
        "--lon",
        "-93.6",
        "--date",
        "2025-05-15",
        "--no-demo",
        "--json",
    ])
    assert rc == 0
    assert seen_demo_modes == [False]
    payload = json.loads(capsys.readouterr().out)
    assert payload["api_mode"] == "live"
    assert payload["demo_mode"] is False
    assert payload["fuente_datos"]["source"] == "nasa_power"

    # Also test forwarding when run_pier accepts climate kwargs
    captured_kwargs: dict[str, object] = {}
    sample_gdd = fetch_power_gdd(
        lat=41.8,
        lon=-93.6,
        season_start="2025-04-15",
        current_date="2025-05-15",
        demo_name="flood",
    )

    def fake_run_pier(
        lat,
        lon,
        current_date,
        demo_mode=True,
        demo_name=None,
        hemisphere="auto",
        season_start=None,
        api_mode="demo",
    ):
        captured_kwargs.update({
            "lat": lat,
            "lon": lon,
            "current_date": current_date,
            "demo_mode": demo_mode,
            "demo_name": demo_name,
            "hemisphere": hemisphere,
            "season_start": season_start,
            "api_mode": api_mode,
        })
        return {
            "event_result": contracts.EventResult(
                event_type="flood",
                severity="high",
                confidence=0.85,
                details={"cum3_mm": 105.0},
            ),
            "gdd_result": sample_gdd,
            "crops": [],
            "recovery_plan": contracts.RecoveryPlan(
                event_type="flood",
                event_confidence=0.85,
                rescue_confidence=0.5,
                gdd_accumulated=sample_gdd.gdd_accumulated,
                gdd_remaining=sample_gdd.gdd_remaining,
                frost_date=sample_gdd.frost_date,
                fallback=False,
                crops=[],
                plan_text="Mocked plan",
            ),
            "plan_text": "Mocked plan",
            "demo_mode": demo_mode,
            "demo_name": demo_name,
        }

    monkeypatch.setattr(cli_main, "run_pier", fake_run_pier)
    rc_mock = cli_main.main([
        "--lat",
        "41.8",
        "--lon",
        "-93.6",
        "--date",
        "2025-05-15",
        "--demo-name",
        "flood",
        "--hemisphere",
        "north",
        "--season-start",
        "2025-04-15",
        "--json",
    ])
    assert rc_mock == 0
    mock_payload = json.loads(capsys.readouterr().out)
    assert captured_kwargs["hemisphere"] == "north"
    assert captured_kwargs["season_start"] == "2025-04-15"
    assert captured_kwargs["api_mode"] == "demo"
    assert mock_payload["plan_text"] == "Mocked plan"
