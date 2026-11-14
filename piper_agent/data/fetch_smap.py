"""SMAP root-zone soil moisture fetcher.

Cache-first, API-second pattern with SYNTHETIC_CACHE fallback.
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger("pier.data.fetch_smap")

SMAP_BASE = os.environ.get(
    "PIER_SMAP_BASE", "https://nsidc.org/api/smap/v1"
)


def fetch_smap_moisture(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    cache_dir: str | None = None,
) -> pd.DataFrame:
    """Fetch SMAP root-zone soil moisture (volumetric percent).

    Args:
        lat, lon: field location.
        start_date, end_date: ISO date range.
        cache_dir: directory for cached CSV fallback.

    Returns:
        DataFrame with columns [date, soil_moisture_vol_pct]. Synthetic data if API unavailable.
    """
    # Try live API (NSIDC SMAP)
    try:
        resp = requests.get(
            f"{SMAP_BASE}/data",
            params={
                "lat": lat,
                "lon": lon,
                "start_date": start_date,
                "end_date": end_date,
                "parameter": "sm_rootzone",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            records = data.get("data", [])
            if records:
                df = pd.DataFrame(records)
                df["date"] = pd.to_datetime(df["date"])
                df = df.rename(columns={"sm_rootzone": "soil_moisture_vol_pct"})[
                    ["date", "soil_moisture_vol_pct"]
                ]
                logger.info(
                    "SMAP fetched %d records for lat=%.4f lon=%.4f",
                    len(df), lat, lon,
                )
                return df
    except Exception as exc:  # noqa: BLE001
        logger.warning("SMAP API failed: %s", exc)

    # Fallback: synthetic cache
    if cache_dir is None:
        cache_dir = os.path.join(
            os.path.dirname(__file__), "..", "data", "cache", "smap"
        )
    os.makedirs(cache_dir, exist_ok=True)
    cache_name = f"{lat:.2f}_{lon:.2f}_{start_date}_{end_date}.csv"
    cache_path = os.path.join(cache_dir, cache_name)

    if os.path.exists(cache_path):
        df = pd.read_csv(cache_path, parse_dates=["date"])
        if "soil_moisture_vol_pct" in df.columns:
            logger.info("SMAP synthetic cache loaded: %s", cache_path)
            return df

    # Generate minimal synthetic moisture
    return _generate_synthetic_moisture(lat, lon, start_date, end_date, cache_path)


def _generate_synthetic_moisture(
    lat: float, lon: float, start_date: str, end_date: str, cache_path: str
) -> pd.DataFrame:
    """Generate synthetic daily root-zone soil moisture."""
    rng = np.random.default_rng(21)
    days = pd.date_range(start_date, end_date, freq="D")
    # Moisture varies by climate zone (roughly)
    abs_lat = abs(lat)
    if abs_lat > 45:
        base_moisture = 25.0  # vol %
    elif abs_lat > 20:
        base_moisture = 20.0
    else:
        base_moisture = 15.0
    doy = np.array([d.timetuple().tm_yday for d in days])
    seasonal = 1.0 + 0.25 * np.sin(2 * np.pi * (doy - 150) / 365.0)
    moisture = base_moisture * seasonal * rng.normal(1.0, 0.1, size=len(days))
    moisture = np.clip(moisture, 5.0, 45.0)
    df = pd.DataFrame({"date": days, "soil_moisture_vol_pct": np.round(moisture, 1)})
    try:
        df.to_csv(cache_path, index=False)
        with open(cache_path + ".SYNTHETIC_CACHE.txt", "w") as f:
            f.write("SYNTHETIC_CACHE: SMAP API unavailable; synthetic moisture for demo.\n")
    except Exception:  # noqa: BLE001
        pass
    logger.info("Generated synthetic SMAP moisture: %d records", len(df))
    return df


__all__ = ["fetch_smap_moisture"]
