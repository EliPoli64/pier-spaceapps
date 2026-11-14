"""BR-3: fetch_power_gdd — POWER temperature GDD model.

Computes GDD accumulated to date and GDD remaining to climatological frost.
Uses cache_loader only — no live POWER calls in demo mode.

GDD per day = max(0, (T2M_MAX + T2M_MIN) / 2 - TBASE)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from piper_agent.contracts import GddResult, DEFAULT_TBASE_C
from piper_agent.data.cache_loader import load_baselines, load_power


def fetch_power_gdd(
    lat: float,
    lon: float,
    season_start: str,
    current_date: str,
    baseline_dir: str | None = None,
    demo_name: str | None = None,
) -> GddResult:
    """Compute GDD accumulated and remaining to climatological frost.

    Args:
        lat, lon: field location (informational; data loaded by demo_name).
        season_start: ISO date season began.
        current_date: ISO date "now".
        baseline_dir: directory with baseline JSON (used if demo_name not given).
        demo_name: demo key ("flood", "drought", "normal").

    Returns:
        GddResult with accumulated, remaining, frost_date, avg_daily_gdd.
    """
    if demo_name:
        df = load_power(demo_name)
        baselines = load_baselines(demo_name)
    elif baseline_dir:
        import json
        import os
        df = load_power(os.path.basename(baseline_dir))
        with open(os.path.join(baseline_dir, f"{os.path.basename(baseline_dir)}_baselines.json")) as f:
            baselines = json.load(f)
    else:
        raise ValueError("Either demo_name or baseline_dir must be provided")

    df = df.sort_values("date").reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"])

    season_start_dt = pd.Timestamp(season_start)
    current_dt = pd.Timestamp(current_date)

    # Daily GDD = max(0, (Tmax + Tmin)/2 - TBASE), using DEFAULT_TBASE_C = 10C
    df["gdd_daily"] = ((df["T2M_MAX"] + df["T2M_MIN"]) / 2.0 - DEFAULT_TBASE_C).clip(lower=0.0)

    # GDD accumulated from season_start to current_date
    mask_acc = (df["date"] >= season_start_dt) & (df["date"] <= current_dt)
    gdd_accumulated = float(df.loc[mask_acc, "gdd_daily"].sum())

    # Climatological frost date — apply month-day to current season year
    frost_date_str = baselines.get("climatological_frost_date", "")
    if frost_date_str:
        frost_mmdd = frost_date_str.split("-")[1:]  # ["10", "04"]
        current_year = current_dt.year
        frost_dt = pd.Timestamp(f"{current_year}-{frost_mmdd[0]}-{frost_mmdd[1]}")
        # If frost already passed this year before season_start, roll to next year
        if frost_dt < season_start_dt:
            frost_dt = pd.Timestamp(f"{current_year + 1}-{frost_mmdd[0]}-{frost_mmdd[1]}")
    else:
        frost_dt = current_dt

    # GDD to frost (from season_start to frost_date; data may not extend that far)
    mask_to_frost = (df["date"] >= season_start_dt) & (df["date"] <= frost_dt)
    gdd_to_frost = float(df.loc[mask_to_frost, "gdd_daily"].sum())

    # GDD remaining
    if current_dt >= frost_dt:
        gdd_remaining = 0.0
    else:
        gdd_remaining = max(0.0, gdd_to_frost - gdd_accumulated)

    # Average daily GDD over last 14 days ending at current_date
    start14 = current_dt - timedelta(days=13)
    mask_avg = (df["date"] >= start14) & (df["date"] <= current_dt)
    avg_window = df.loc[mask_avg, "gdd_daily"]
    avg_daily_gdd = float(avg_window.mean()) if not avg_window.empty else float(df["gdd_daily"].mean())

    details: dict[str, Any] = {
        "gdd_to_frost": round(gdd_to_frost, 1),
        "frost_date": frost_dt.strftime("%Y-%m-%d"),
        "frost_baseline_date": frost_date_str,
        "tbase_c": DEFAULT_TBASE_C,
        "season_start": season_start,
        "current_date": current_date,
        "lat": lat,
        "lon": lon,
    }

    return GddResult(
        gdd_accumulated=round(gdd_accumulated, 1),
        gdd_remaining=round(gdd_remaining, 1),
        frost_date=frost_date_str,
        avg_daily_gdd=round(avg_daily_gdd, 2),
        details=details,
    )
