"""Generate the synthetic IMERG + POWER cache for the demo scenarios.

No Earthdata credentials needed. For every scenario in `demo/*.json` it creates:
- data/cache/imerg/{demo}_imerg.csv     (date, precipitation_mm)
- data/cache/power/{demo}_power.csv     (date, T2M_MAX, T2M_MIN, PRECTOTCORR)
- data/baselines/{demo}_baselines.json  (p95, p10, end of window, fuente_datos)
- data/baselines/southern_hemisphere.json (frost bands by latitude)

Every synthetic file gets a SYNTHETIC_CACHE marker next to it.

Usage:
    python -m piper_agent.data.generate_cache            # every scenario
    python -m piper_agent.data.generate_cache flood      # just one
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMERG_DIR = os.path.join(ROOT_DIR, "data", "cache", "imerg")
POWER_DIR = os.path.join(ROOT_DIR, "data", "cache", "power")
BASELINES_DIR = os.path.join(ROOT_DIR, "data", "baselines")
DEMOS_DIR = os.path.join(ROOT_DIR, "..", "demo")

# Demo scenarios = every demo/*_demo.json (adding a packet is enough to get its cache).
SCENARIOS = tuple(sorted(f[:-10] for f in os.listdir(DEMOS_DIR) if f.endswith("_demo.json")))
TROPICAL_LATITUDE = 23.5  # |lat| below this: no climatological frost
SYNTHETIC_SOURCE = "sintetico"  # contract value of `fuente_datos`

# Typical month-day of the first autumn frost per latitude band.
# Indicative values; they need local calibration.
FROST_BANDS = {
    "note": "typical values, local calibration required",
    "tropical_latitude": TROPICAL_LATITUDE,
    "north": [
        {"lat_min": 23.5, "lat_max": 30.0, "first_frost": "12-15"},
        {"lat_min": 30.0, "lat_max": 40.0, "first_frost": "11-05"},
        {"lat_min": 40.0, "lat_max": 50.0, "first_frost": "10-10"},
        {"lat_min": 50.0, "lat_max": 90.0, "first_frost": "09-15"},
    ],
    "south": [
        {"lat_min": 23.5, "lat_max": 30.0, "first_frost": "06-15"},
        {"lat_min": 30.0, "lat_max": 40.0, "first_frost": "05-05"},
        {"lat_min": 40.0, "lat_max": 50.0, "first_frost": "04-10"},
        {"lat_min": 50.0, "lat_max": 90.0, "first_frost": "03-15"},
    ],
}


def is_tropical(lat: float) -> bool:
    return abs(lat) < TROPICAL_LATITUDE


def read_packet(name: str) -> dict:
    """Read demo/{name}_demo.json (single source of dates and coordinates)."""
    with open(os.path.join(DEMOS_DIR, f"{name}_demo.json"), encoding="utf-8") as f:
        return json.load(f)


def date_range(start: str, end: str):
    current = date.fromisoformat(start)
    last = date.fromisoformat(end)
    while current <= last:
        yield current
        current += timedelta(days=1)


def generate_imerg(recent_start, recent_end, baseline_start, event_type) -> pd.DataFrame:
    """Daily rainfall. Flood: 72 h storm > 100 mm. Drought: 30-day deficit."""
    rng = np.random.default_rng(42)
    recent_start_date = date.fromisoformat(recent_start)
    records = []
    for d in date_range(baseline_start, recent_end):
        in_window = recent_start <= d.isoformat() <= recent_end
        if event_type == "flood" and in_window:
            idx = (d - recent_start_date).days
            mm = {1: 40.0, 2: 35.0, 3: 30.0}.get(idx)
            if mm is None:
                mm = float(rng.gamma(2.0, 3.0))
        elif event_type == "drought" and in_window:
            mm = float(rng.gamma(0.5, 1.0))  # very dry
        else:
            mm = float(rng.gamma(2.0, 3.0))
        records.append({"date": d.isoformat(), "precipitation_mm": round(mm, 2)})
    return pd.DataFrame(records)


def _series_end(lat: float, current_date: str, season_end: str | None) -> str:
    """Last day of the POWER series: covers the whole current season."""
    if is_tropical(lat):
        end = season_end or f"{current_date[:4]}-12-31"
        return max(end, current_date)
    if lat > 0:
        return f"{current_date[:4]}-10-15"
    return f"{current_date[:4]}-12-31"


def generate_power(current_date, baseline_start, lat, season_end=None) -> pd.DataFrame:
    """Daily T2M_MAX, T2M_MIN and PRECTOTCORR: 10 years + the current season."""
    rng = np.random.default_rng(123)
    records = []
    for d in date_range(baseline_start, _series_end(lat, current_date, season_end)):
        doy = d.timetuple().tm_yday
        if is_tropical(lat):
            # Tropics: warm all year, small annual cycle, no frost.
            tmean = 22.0 + 2.0 * np.sin(2 * np.pi * (doy - 80) / 365.0)
            half_range = 6.0
            rain_mean = 1.0 + 3.0 * max(0, np.sin(2 * np.pi * (doy - 60) / 365.0))
        elif lat > 0:
            tmean = 12.0 + 15.0 * np.sin(2 * np.pi * (doy - 80) / 365.0)
            half_range = 7.0
            rain_mean = 3.0 + 2.0 * max(0, np.sin(2 * np.pi * (doy - 100) / 365.0))
        else:
            # Temperate Southern Hemisphere: cycle shifted six months.
            tmean = 12.0 + 15.0 * np.sin(2 * np.pi * (doy - 262) / 365.0)
            half_range = 7.0
            rain_mean = 3.0 + 2.0 * max(0, np.sin(2 * np.pi * (doy - 282) / 365.0))
        tmax = tmean + half_range + rng.normal(0, 2.0)
        tmin = tmean - half_range + rng.normal(0, 2.0)
        rain = max(0.0, float(rng.gamma(rain_mean, 1.5)))
        records.append({
            "date": d.isoformat(),
            "T2M_MAX": round(tmax, 1),
            "T2M_MIN": round(tmin, 1),
            "PRECTOTCORR": round(rain, 2),
        })
    return pd.DataFrame(records)


def _first_autumn_frost(power_df: pd.DataFrame, lat: float) -> str | None:
    """First autumn date with T2M_MIN <= 0 °C in the historical archive."""
    dates = pd.to_datetime(power_df["date"])
    doy = dates.dt.dayofyear
    # Autumn: after day 200 in the north; between days 60 and 200 in the south.
    in_autumn = (doy > 200) if lat > 0 else ((doy > 60) & (doy <= 200))
    frosts = power_df.loc[(power_df["T2M_MIN"] <= 0.0) & in_autumn, "date"]
    if frosts.empty:
        return None
    return str(pd.to_datetime(frosts).min().date())


def compute_baselines(power_df, lat, season_end=None, fuente_datos=SYNTHETIC_SOURCE) -> dict:
    """BR-1 thresholds (3-day p95, 30-day p10) and the end of the growing window.

    `climatological_frost_date` is always kept for compatibility: in the tropics
    there is no frost and it holds the end of the rainy season; `frost_method`
    tells which of the two cases applies.
    """
    power_df = power_df.sort_values("date").reset_index(drop=True)
    rain = pd.Series(power_df["PRECTOTCORR"].values)
    p95_cum3 = float(np.percentile(rain.rolling(3, min_periods=1).sum().values, 95))
    p10_cum30 = float(np.percentile(rain.rolling(30, min_periods=1).sum().values, 10))

    if is_tropical(lat):
        window_end = season_end or str(power_df["date"].iloc[-1])[:10]
        method = "rainy_season_end"
    else:
        window_end = _first_autumn_frost(power_df, lat)
        method = "first_T2M_MIN_<=0_after_day200" if lat > 0 else "southern_autumn_frost"
        if window_end is None:
            window_end = "2024-10-15" if lat > 0 else "2024-04-15"
            method = "fallback_fixed_date"

    return {
        "p95_3day_cum_rainfall": round(p95_cum3, 2),
        "p10_30day_cum_rainfall": round(p10_cum30, 2),
        "climatological_frost_date": window_end,
        "frost_method": method,
        "season_end": season_end,
        "tropical": is_tropical(lat),
        "fuente_datos": fuente_datos,
        "note": "typical values, local calibration required",
    }


def write_frost_bands() -> str:
    """Write data/baselines/southern_hemisphere.json (bands for both hemispheres)."""
    os.makedirs(BASELINES_DIR, exist_ok=True)
    path = os.path.join(BASELINES_DIR, "southern_hemisphere.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(FROST_BANDS, f, indent=2, ensure_ascii=False)
    return path


def _mark_synthetic(csv_path: str, message: str) -> None:
    with open(csv_path.replace(".csv", ".SYNTHETIC_CACHE.txt"), "w", encoding="utf-8") as f:
        f.write(f"SYNTHETIC_CACHE: {message}\n")


def generate_scenario(name: str, verbose: bool = False) -> dict:
    """Generate the full synthetic cache of one scenario. Returns its baselines."""
    cfg = read_packet(name)
    for folder in (IMERG_DIR, POWER_DIR, BASELINES_DIR):
        os.makedirs(folder, exist_ok=True)

    imerg_df = generate_imerg(cfg["recent_start"], cfg["recent_end"],
                              cfg["baseline_start"], cfg["event_type"])
    imerg_path = os.path.join(IMERG_DIR, f"{name}_imerg.csv")
    imerg_df.to_csv(imerg_path, index=False)
    _mark_synthetic(imerg_path, "no Earthdata credentials; synthetic IMERG data for the demo.")

    power_df = generate_power(cfg["current_date"], cfg["baseline_start"],
                              cfg["lat"], cfg.get("season_end"))
    power_path = os.path.join(POWER_DIR, f"{name}_power.csv")
    power_df.to_csv(power_path, index=False)
    _mark_synthetic(power_path, "NASA POWER API not queried; synthetic temperature and rainfall.")

    baselines = compute_baselines(power_df, cfg["lat"], cfg.get("season_end"))
    baselines_path = os.path.join(BASELINES_DIR, f"{name}_baselines.json")
    with open(baselines_path, "w", encoding="utf-8") as f:
        json.dump(baselines, f, indent=2)

    if verbose:
        print(f"=== {name} ===")
        print(f"  IMERG: {imerg_path} ({len(imerg_df)} rows)")
        print(f"  POWER: {power_path} ({len(power_df)} rows)")
        print(f"  Baselines: {baselines_path} -> {baselines}\n")
    return baselines


def generate_cache(names=None, verbose: bool = False) -> None:
    """Generate the synthetic cache of the given scenarios (all of them by default)."""
    for name in (names or SCENARIOS):
        generate_scenario(name, verbose=verbose)
    write_frost_bands()


if __name__ == "__main__":
    generate_cache(sys.argv[1:] or None, verbose=True)
    print("Done. All caches are SYNTHETIC_CACHE (no live Earthdata/POWER calls).")
