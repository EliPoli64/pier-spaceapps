"""BR-3: fetch_power_gdd — POWER temperature GDD model.

Computes GDD accumulated to date and GDD remaining to climatological frost.
Demo mode uses cache_loader only. With `power` + `baselines` (or `demo_mode=False`)
the tool runs on live data from `live_inputs`; there the observations end today, so
the GDD still to come is projected from the monthly climatology (and labeled).

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
    hemisphere: str | None = None,
    demo_mode: bool = True,
    power: pd.DataFrame | None = None,
    baselines: dict[str, Any] | None = None,
) -> GddResult:
    """Compute GDD accumulated and remaining to climatological frost.

    Hemisphere-aware: Southern Hemisphere growing seasons run opposite to
    Northern (season starts ~Oct-Nov, frost ~Mar-Apr).

    Args:
        lat, lon: field location (informational; data loaded by demo_name).
        season_start: ISO date season began.
        current_date: ISO date "now".
        baseline_dir: directory with baseline JSON (used if demo_name not given).
        demo_name: demo key ("flood", "drought", "normal").
        hemisphere: "north" | "south" | "auto" (default auto from lat sign).
        demo_mode: False lets the tool fetch live data when no source was given.
        power: DataFrame [date, T2M_MAX, T2M_MIN] from the live path.
        baselines: frost date and monthly GDD normals (from `live_inputs.build_baselines`).

    Returns:
        GddResult with accumulated, remaining, frost_date, avg_daily_gdd.
    """
    # Auto-detect hemisphere from latitude
    if hemisphere is None:
        hemisphere = "south" if lat < 0 else "north"

    if power is None and not demo_name and not baseline_dir and not demo_mode:
        from piper_agent.tools.live_inputs import load_live

        live = load_live(lat, lon, current_date, season_start=season_start, demo_mode=False)
        power, baselines = live["power"], live["baselines"]

    if power is not None:
        df = power.copy()
        baselines = baselines or {}
    elif demo_name:
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
    frost_date_str = baselines.get("climatological_frost_date") or ""
    frost_is_local = bool(baselines.get("frost_is_local"))
    if not frost_date_str and baselines.get("season_end"):
        frost_date_str = baselines["season_end"]  # tropics: the season ends with the rains
    if frost_date_str:
        frost_mmdd = frost_date_str.split("-")[1:]  # ["10", "04"]
        current_year = current_dt.year
        frost_dt = pd.Timestamp(f"{current_year}-{frost_mmdd[0]}-{frost_mmdd[1]}")
        # For Southern Hemisphere, shift frost date by ~6 months
        if hemisphere == "south" and not frost_is_local:
            frost_dt = frost_dt + pd.Timedelta(days=182)
        # If frost already passed this year before season_start, roll to next year
        if frost_dt < season_start_dt:
            frost_dt = pd.Timestamp(f"{current_year + 1}-{frost_mmdd[0]}-{frost_mmdd[1]}")
            if hemisphere == "south" and not frost_is_local:
                frost_dt = frost_dt + pd.Timedelta(days=182)
    else:
        frost_dt = current_dt

    normals = baselines.get("monthly_gdd_normal")
    if normals and frost_date_str:
        # Live path: observations end today. The GDD to come is the climatological
        # daily GDD of each remaining month (no look-ahead into future observations).
        remaining_days = pd.date_range(current_dt + pd.Timedelta(days=1), frost_dt, freq="D")
        gdd_remaining = float(sum(normals.get(str(d.month), 0.0) for d in remaining_days))
        gdd_to_frost = gdd_accumulated + gdd_remaining
        remaining_method = "climatological_projection"
    else:
        # GDD to frost (from season_start to frost_date; data may not extend that far)
        mask_to_frost = (df["date"] >= season_start_dt) & (df["date"] <= frost_dt)
        gdd_to_frost = float(df.loc[mask_to_frost, "gdd_daily"].sum())
        remaining_method = "observed_cache"
        # GDD remaining
        if current_dt >= frost_dt:
            gdd_remaining = 0.0
        else:
            gdd_remaining = max(0.0, gdd_to_frost - gdd_accumulated)

    # Failure taxonomy: no frost/season-end reference or no temperatures to accumulate
    if not frost_date_str:
        data_status = {"status": "no_data", "route": "stop",
                       "reason": "No frost date or season end for this region; the GDD window cannot be bounded."}
    elif not bool(mask_acc.any()):
        data_status = {"status": "no_data", "route": "stop",
                       "reason": "No temperature observations between the season start and today."}
    else:
        data_status = {"status": "ok", "route": "recommend", "reason": "GDD window computed."}

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
        "remaining_method": remaining_method,
        "data_status": data_status,
        "season_start": season_start,
        "current_date": current_date,
        "lat": lat,
        "lon": lon,
    }

    return GddResult(
        gdd_accumulated=round(gdd_accumulated, 1),
        gdd_remaining=round(gdd_remaining, 1),
        frost_date=frost_dt.strftime("%Y-%m-%d"),
        avg_daily_gdd=round(avg_daily_gdd, 2),
        hemisphere=hemisphere,
        details=details,
    )
