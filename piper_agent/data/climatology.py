"""Versioned store of regional climatologies.

Every region (0.5° cell) keeps monthly rainfall and temperature percentiles in
`data/baselines/regions/{region}_v{VERSION}.json`. With that, any run can
explain whether a value is normal, extreme or missing.

The version changes when the computation method changes; the file also records
the data source and the period used, so a result can be reproduced.
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import date, datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from piper_agent.data import generate_cache as gc
from piper_agent.data.ingestion.pipeline import ingest_point, region_key

logger = logging.getLogger("pier.data.climatology")

BASELINES_VERSION = "1"
REGIONS_DIR = os.path.join(gc.BASELINES_DIR, "regions")
CLIMATOLOGY_YEARS = 10
MIN_DAYS_PER_MONTH = 60  # fewer than this: the month has too little data

# variable -> (low percentile key, high percentile key, unit)
VARIABLES = {
    "rain_3d": ("p05", "p95", "mm in 3 days"),
    "rain_30d": ("p10", "p90", "mm in 30 days"),
    "tmax": ("p05", "p95", "°C"),
    "tmin": ("p05", "p95", "°C"),
}


def _percentiles(series: pd.Series) -> dict[str, float]:
    values = series.dropna().to_numpy()
    return {
        f"p{p:02d}": round(float(np.percentile(values, p)), 2)
        for p in (5, 10, 50, 90, 95)
    }


def build_climatology(
    power_df: pd.DataFrame,
    rainfall_df: pd.DataFrame,
    lat: float,
    lon: float,
    fuente_datos: str,
) -> dict[str, Any]:
    """Compute monthly percentiles of cumulative rainfall and temperature."""
    power = power_df.copy()
    power["date"] = pd.to_datetime(power["date"])
    rainfall = rainfall_df.copy()
    rainfall["date"] = pd.to_datetime(rainfall["date"])
    rainfall = rainfall.sort_values("date")
    rainfall["rain_3d"] = rainfall["precipitation_mm"].rolling(3, min_periods=3).sum()
    rainfall["rain_30d"] = rainfall["precipitation_mm"].rolling(30, min_periods=30).sum()

    months: dict[str, Any] = {}
    for month in range(1, 13):
        p_month = power[power["date"].dt.month == month]
        r_month = rainfall[rainfall["date"].dt.month == month]
        if len(p_month) < MIN_DAYS_PER_MONTH or r_month["rain_30d"].notna().sum() < MIN_DAYS_PER_MONTH:
            continue
        months[str(month)] = {
            "n_days": int(len(p_month)),
            "rain_3d": _percentiles(r_month["rain_3d"]),
            "rain_30d": _percentiles(r_month["rain_30d"]),
            "tmax": _percentiles(p_month["T2M_MAX"]),
            "tmin": _percentiles(p_month["T2M_MIN"]),
        }

    frost = None if gc.is_tropical(lat) else gc._first_autumn_frost(
        power.assign(date=power["date"].dt.strftime("%Y-%m-%d")), lat
    )
    return {
        "version": BASELINES_VERSION,
        "region": region_key(lat, lon),
        "lat": lat,
        "lon": lon,
        "fuente_datos": fuente_datos,
        "period": {
            "start": str(power["date"].min().date()),
            "end": str(power["date"].max().date()),
        },
        "created": datetime.now(timezone.utc).isoformat(),
        "tropical": gc.is_tropical(lat),
        "first_autumn_frost": frost,
        "months": months,
        "note": "monthly percentiles; typical values for the cell, local calibration required",
    }


def climatology_path(lat: float, lon: float, version: str = BASELINES_VERSION) -> str:
    return os.path.join(REGIONS_DIR, f"{region_key(lat, lon)}_v{version}.json")


def save_climatology(climatology: dict[str, Any]) -> str:
    os.makedirs(REGIONS_DIR, exist_ok=True)
    path = climatology_path(climatology["lat"], climatology["lon"], climatology["version"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(climatology, f, indent=2, ensure_ascii=False)
    return path


def load_climatology(lat: float, lon: float, version: str = BASELINES_VERSION) -> dict | None:
    path = climatology_path(lat, lon, version)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_climatology(
    lat: float,
    lon: float,
    until: str | None = None,
    demo_mode: bool | None = None,
) -> dict[str, Any]:
    """Climatology of the region: the stored one if it exists and is usable; otherwise computed.

    A stored synthetic climatology is recomputed when requested through the
    production path, so synthetic data is not left where real data may exist.
    """
    if demo_mode is None:
        demo_mode = os.environ.get("PIER_DEMO_MODE", "1") == "1"
    stored = load_climatology(lat, lon)
    if stored and (demo_mode or stored.get("fuente_datos") != "sintetico"):
        return stored

    end = date.fromisoformat(until) if until else date.today()
    start = end.replace(year=end.year - CLIMATOLOGY_YEARS, day=min(end.day, 28))
    # 10-year baselines come from POWER (1 request); imergpy fetches 1 file per day.
    data = ingest_point(
        lat, lon, start.isoformat(), end.isoformat(),
        demo_mode=demo_mode, use_imerg=False,
    )
    climatology = build_climatology(
        data["power"], data["rainfall"], lat, lon, data["fuente_datos"]
    )
    save_climatology(climatology)
    return climatology


def classify_value(
    climatology: dict[str, Any] | None,
    variable: str,
    value: float | None,
    on_date: str,
) -> dict[str, Any]:
    """Tell whether `value` is normal, extreme or missing for that month and region.

    Returns:
        dict with `status` ("normal" | "extreme" | "missing"), `direction`
        ("high" | "low" | None), the thresholds used and an `explanation`.
    """
    if variable not in VARIABLES:
        raise ValueError(f"Unknown variable: {variable}. Options: {sorted(VARIABLES)}")
    low_key, high_key, unit = VARIABLES[variable]
    month = str(date.fromisoformat(on_date[:10]).month)
    base = {"variable": variable, "value": value, "month": int(month), "direction": None}

    if value is None or (isinstance(value, float) and math.isnan(value)):
        return {**base, "status": "missing", "explanation": f"No {variable} value for {on_date}."}
    stats = ((climatology or {}).get("months") or {}).get(month, {}).get(variable)
    if not stats:
        return {**base, "status": "missing",
                "explanation": f"Not enough {variable} climatology for month {month}."}

    low, high, median = stats[low_key], stats[high_key], stats["p50"]
    result = {
        **base, "low_threshold": low, "high_threshold": high, "median": median,
        "fuente_datos": climatology.get("fuente_datos"), "version": climatology.get("version"),
    }
    usual = f"usual range for the month: {low}–{high} {unit}, median {median}"
    if value > high:
        return {**result, "status": "extreme", "direction": "high",
                "explanation": f"{variable} = {value:.1f}: above normal ({usual})."}
    if value < low:
        return {**result, "status": "extreme", "direction": "low",
                "explanation": f"{variable} = {value:.1f}: below normal ({usual})."}
    return {**result, "status": "normal",
            "explanation": f"{variable} = {value:.1f}: within normal ({usual})."}


__all__ = [
    "BASELINES_VERSION", "build_climatology", "save_climatology",
    "load_climatology", "get_climatology", "classify_value",
]
