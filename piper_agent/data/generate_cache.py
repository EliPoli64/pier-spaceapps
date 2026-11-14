"""Generate synthetic cached IMERG + POWER demo data (no Earthdata credentials needed).

Creates:
- data/cache/imerg/{demo}_imerg.csv  (date, precipitation_mm)
- data/cache/power/{demo}_power.csv  (date, T2M_MAX, T2M_MIN, PRECTOTCORR)
- data/baselines/{demo}_baselines.json (p95, p10, climatological_frost_date)

Marks SYNTHETIC_CACHE beside each file.
"""
import json
import os
from datetime import date, timedelta

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMERS = os.path.join(ROOT, "data", "cache", "imerg")
POWERS = os.path.join(ROOT, "data", "cache", "power")
BASELINES = os.path.join(ROOT, "data", "baselines")

os.makedirs(IMERS, exist_ok=True)
os.makedirs(POWERS, exist_ok=True)
os.makedirs(BASELINES, exist_ok=True)

DEMOS = {
    "flood": {
        "lat": 41.8, "lon": -93.6, "event_type": "flood",
        "recent_start": "2025-05-10", "recent_end": "2025-05-15",
        "baseline_start": "2015-05-01", "baseline_end": "2024-05-31",
        "season_start": "2025-04-01", "current_date": "2025-05-15",
    },
    "drought": {
        "lat": 9.0, "lon": 41.0, "event_type": "drought",
        "recent_start": "2025-01-01", "recent_end": "2025-01-30",
        "baseline_start": "2015-01-01", "baseline_end": "2024-01-31",
        "season_start": "2024-11-01", "current_date": "2025-01-30",
    },
    "normal": {
        "lat": 41.8, "lon": -93.6, "event_type": "none",
        "recent_start": "2025-07-01", "recent_end": "2025-07-07",
        "baseline_start": "2015-07-01", "baseline_end": "2024-07-31",
        "season_start": "2025-04-01", "current_date": "2025-07-07",
    },
}


def daterange(start: str, end: str):
    d0 = date.fromisoformat(start)
    d1 = date.fromisoformat(end)
    cur = d0
    while cur <= d1:
        yield cur
        cur += timedelta(days=1)


def gen_imerg(recent_start, recent_end, baseline_start, baseline_end, event_type):
    """Daily rainfall. Flood: 72h storm >100mm. Drought: 30-day deficit. Normal: moderate."""
    rng = np.random.default_rng(42)
    records = []
    for d in daterange(baseline_start, recent_end):
        if event_type == "flood":
            # baseline: light rain; recent window has a 72h storm
            if recent_start <= d.isoformat() <= recent_end:
                # storm on days 2-4 of recent window
                idx = (d - date.fromisoformat(recent_start)).days
                if idx == 1:
                    mm = 40.0
                elif idx == 2:
                    mm = 35.0
                elif idx == 3:
                    mm = 30.0
                else:
                    mm = float(rng.gamma(2.0, 3.0))
            else:
                mm = float(rng.gamma(2.0, 3.0))
        elif event_type == "drought":
            if recent_start <= d.isoformat() <= recent_end:
                mm = float(rng.gamma(0.5, 1.0))  # very dry
            else:
                mm = float(rng.gamma(2.0, 3.0))
        else:  # normal
            mm = float(rng.gamma(2.0, 3.0))
        records.append({"date": d.isoformat(), "precipitation_mm": round(mm, 2)})
    return pd.DataFrame(records)


def gen_power(season_start, current_date, baseline_start, baseline_end, lat, event_type):
    """Daily T2M_MAX, T2M_MIN, PRECTOTCORR for 10 years + full current season to frost."""
    rng = np.random.default_rng(123)
    # Determine end date: extend current season to climatological frost (~Oct 15 northern, Dec 31 equatorial)
    if lat > 0:
        season_end = f"{current_date[:4]}-10-15"
    else:
        season_end = f"{current_date[:4]}-12-31"
    # Build full date range from baseline_start to season_end
    all_days = list(daterange(baseline_start, season_end))
    records = []
    for d in all_days:
        day_of_year = d.timetuple().tm_yday
        # Seasonal temperature cycle (northern hemisphere for Iowa-like; southern for Horn)
        if lat > 0:
            # Northern hemisphere: warm in summer (day 200), cold in winter (day 350)
            temp_amp = 15.0
            tmean = 12.0 + temp_amp * np.sin(2 * np.pi * (day_of_year - 80) / 365.0)
        else:
            # Near equator: milder seasonal cycle
            temp_amp = 6.0
            tmean = 24.0 + temp_amp * np.sin(2 * np.pi * (day_of_year - 10) / 365.0)
        tmax = tmean + 7.0 + rng.normal(0, 2.0)
        tmin = tmean - 7.0 + rng.normal(0, 2.0)
        # Rainfall: seasonal wet/dry
        if lat > 0:
            rain_mean = 3.0 + 2.0 * max(0, np.sin(2 * np.pi * (day_of_year - 100) / 365.0))
        else:
            rain_mean = 1.0 + 3.0 * max(0, np.sin(2 * np.pi * (day_of_year - 300) / 365.0))
        precip = max(0.0, float(rng.gamma(rain_mean, 1.5)))
        records.append({
            "date": d.isoformat(),
            "T2M_MAX": round(tmax, 1),
            "T2M_MIN": round(tmin, 1),
            "PRECTOTCORR": round(precip, 2),
        })
    return pd.DataFrame(records)


def compute_baselines(power_df, current_date):
    """Compute BR-1 baselines: p95 of 3-day cum, p10 of 30-day cum, frost date."""
    power_df = power_df.sort_values("date").reset_index(drop=True)
    precip = power_df["PRECTOTCORR"].values
    # 3-day and 30-day rolling cumulative over the baseline period (10 years)
    cum3 = pd.Series(precip).rolling(3, min_periods=1).sum().values
    cum30 = pd.Series(precip).rolling(30, min_periods=1).sum().values
    p95_cum3 = float(np.percentile(cum3, 95))
    p10_cum30 = float(np.percentile(cum30, 10))
    # Climatological frost: first fall date (doy>200) with T2M_MIN <= 0 C
    frost_date = None
    frost_method = "none"
    for d in daterange("2015-01-01", "2024-12-31"):
        row = power_df[power_df["date"] == d.isoformat()]
        if not row.empty and row.iloc[0]["T2M_MIN"] <= 0.0:
            if d.timetuple().tm_yday > 200:
                frost_date = d.isoformat()
                frost_method = "first_T2M_MIN_<=0_after_day200"
                break
    if frost_date is None:
        frost_date = "2024-10-15" if DEMOS_FROST_LAT > 0 else "2024-12-31"
        frost_method = "fallback_fixed_date"
    return {
        "p95_3day_cum_rainfall": round(p95_cum3, 2),
        "p10_30day_cum_rainfall": round(p10_cum30, 2),
        "climatological_frost_date": frost_date,
        "frost_method": frost_method,
        "note": "typical values, local calibration required",
    }


DEMOS_FROST_LAT = 0

for name, cfg in DEMOS.items():
    DEMOS_FROST_LAT = cfg["lat"]
    # IMERG
    imerg_df = gen_imerg(cfg["recent_start"], cfg["recent_end"],
                         cfg["baseline_start"], cfg["baseline_end"], cfg["event_type"])
    imerg_path = os.path.join(IMERS, f"{name}_imerg.csv")
    imerg_df.to_csv(imerg_path, index=False)
    with open(os.path.join(IMERS, f"{name}_imerg.SYNTHETIC_CACHE.txt"), "w") as f:
        f.write("SYNTHETIC_CACHE: Earthdata credentials unavailable; synthetic IMERG data for demo.\n")

    # POWER
    power_df = gen_power(cfg["season_start"], cfg["current_date"],
                         cfg["baseline_start"], cfg["baseline_end"], cfg["lat"], cfg["event_type"])
    power_path = os.path.join(POWERS, f"{name}_power.csv")
    power_df.to_csv(power_path, index=False)
    with open(os.path.join(POWERS, f"{name}_power.SYNTHETIC_CACHE.txt"), "w") as f:
        f.write("SYNTHETIC_CACHE: NASA POWER API unavailable; synthetic temperature/precip data for demo.\n")

    # Baselines
    baselines = compute_baselines(power_df, cfg["current_date"])
    baseline_path = os.path.join(BASELINES, f"{name}_baselines.json")
    with open(baseline_path, "w") as f:
        json.dump(baselines, f, indent=2)

    print(f"=== {name} ===")
    print(f"  IMERG: {imerg_path} ({len(imerg_df)} rows)")
    print(f"  POWER: {power_path} ({len(power_df)} rows)")
    print(f"  Baselines: {baseline_path} -> {baselines}")
    print()

print("Done. All caches are SYNTHETIC_CACHE (no live Earthdata/POWER calls).")
