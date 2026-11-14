"""OpenET actual evapotranspiration fetcher.

Cache-first, API-second pattern with SYNTHETIC_CACHE fallback.
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger("pier.data.fetch_openet")

OPENET_BASE = os.environ.get(
    "PIER_OPENET_BASE", "https://api.openet.io/api/v1"
)
OPENET_API_KEY = os.environ.get("PIER_OPENET_API_KEY", "")


def fetch_openet_eta(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    cache_dir: str | None = None,
) -> pd.DataFrame:
    """Fetch OpenET ETa (actual evapotranspiration) in mm/day.

    Args:
        lat, lon: field location.
        start_date, end_date: ISO date range.
        cache_dir: directory for cached CSV fallback.

    Returns:
        DataFrame with columns [date, eta_mm]. Synthetic data if API unavailable.
    """
    # Try live API first
    if OPENET_API_KEY:
        try:
            resp = requests.get(
                f"{OPENET_BASE}/eta",
                params={
                    "lat": lat,
                    "lon": lon,
                    "start_date": start_date,
                    "end_date": end_date,
                    "network": "ensemble",
                    "units": "mm",
                },
                headers={"Authorization": f"Bearer {OPENET_API_KEY}"},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                records = data.get("data", [])
                if records:
                    df = pd.DataFrame(records)
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.rename(columns={"eta": "eta_mm"})[
                        ["date", "eta_mm"]
                    ]
                    logger.info(
                        "OpenET fetched %d records for lat=%.4f lon=%.4f",
                        len(df), lat, lon,
                    )
                    return df
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenET API failed: %s", exc)

    # Fallback: synthetic cache
    if cache_dir is None:
        cache_dir = os.path.join(
            os.path.dirname(__file__), "..", "data", "cache", "openet"
        )
    os.makedirs(cache_dir, exist_ok=True)
    cache_name = f"{lat:.2f}_{lon:.2f}_{start_date}_{end_date}.csv"
    cache_path = os.path.join(cache_dir, cache_name)

    if os.path.exists(cache_path):
        df = pd.read_csv(cache_path, parse_dates=["date"])
        if "eta_mm" in df.columns:
            logger.info("OpenET synthetic cache loaded: %s", cache_path)
            return df

    # Generate minimal synthetic ETa (climate-zone typical)
    return _generate_synthetic_eta(lat, lon, start_date, end_date, cache_path)


def _generate_synthetic_eta(
    lat: float, lon: float, start_date: str, end_date: str, cache_path: str
) -> pd.DataFrame:
    """Generate synthetic daily ETa based on latitude climate zone."""
    import numpy as np

    rng = np.random.default_rng(11)
    days = pd.date_range(start_date, end_date, freq="D")
    # ETa roughly follows temperature: higher near equator, seasonal cycle
    abs_lat = abs(lat)
    if abs_lat > 45:
        base_eta = 2.0  # mm/day
    elif abs_lat > 20:
        base_eta = 4.0
    else:
        base_eta = 5.5
    # Add seasonal variation
    doy = np.array([d.timetuple().tm_yday for d in days])
    seasonal = 1.0 + 0.3 * np.sin(2 * np.pi * (doy - 80) / 365.0)
    eta_mm = base_eta * seasonal * rng.normal(1.0, 0.15, size=len(days))
    eta_mm = np.clip(eta_mm, 0.0, None)
    df = pd.DataFrame({"date": days, "eta_mm": np.round(eta_mm, 2)})
    try:
        df.to_csv(cache_path, index=False)
        with open(cache_path + ".SYNTHETIC_CACHE.txt", "w") as f:
            f.write("SYNTHETIC_CACHE: OpenET API unavailable; synthetic ETa for demo.\n")
    except Exception:  # noqa: BLE001
        pass
    logger.info("Generated synthetic OpenET ETa: %d records", len(df))
    return df


__all__ = ["fetch_openet_eta"]
