"""Shared logic for cached daily series (OpenET, SMAP).

Order: 1) disk cache, 2) live API only outside demo mode, with retries and
circuit breaker, 3) synthetic series flagged as estimated.

The origin is stored in `df.attrs["source"]`: "cache", "estimated", "live" or
the specific name set by the live source (for example "nasa_power_gwetroot").
"""
from __future__ import annotations

import logging
import os
from typing import Callable

import pandas as pd

from piper_agent.data.resilience import call_with_retry

logger = logging.getLogger("pier.data.series")

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")


def demo_mode() -> bool:
    return os.environ.get("PIER_DEMO_MODE", "1") == "1"


def get_series(
    name: str,
    column: str,
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    fetch_live: Callable[[], pd.DataFrame | None] | None,
    generate_synthetic: Callable[[], pd.DataFrame],
    cache_dir: str | None = None,
) -> pd.DataFrame:
    """Return a DataFrame [date, `column`] following cache → live → synthetic."""
    cache_dir = cache_dir or os.path.join(CACHE_DIR, name)
    path = os.path.join(cache_dir, f"{lat:.2f}_{lon:.2f}_{start_date}_{end_date}.csv")
    marker = path + ".SYNTHETIC_CACHE.txt"

    # 1) Cache
    if os.path.exists(path):
        df = pd.read_csv(path, parse_dates=["date"])
        if column in df.columns:
            df.attrs["source"] = "estimated" if os.path.exists(marker) else "cache"
            return df

    # 2) Live API (production path only)
    if fetch_live is not None and not demo_mode():
        try:
            df = call_with_retry(fetch_live, description=f"{name} API")
        except RuntimeError as exc:
            logger.warning("Live %s unavailable (%s); using an estimate", name, exc)
            df = None
        if df is not None and not df.empty:
            source = df.attrs.get("source", "live")
            _save(df, path)
            df.attrs["source"] = source
            return df

    # 3) Synthetic, flagged as estimated
    df = generate_synthetic()
    if _save(df, path):
        try:
            with open(marker, "w", encoding="utf-8") as f:
                f.write(f"SYNTHETIC_CACHE: estimated {name}; it does not come from the API.\n")
        except OSError:
            pass
    df.attrs["source"] = "estimated"
    return df


def _save(df: pd.DataFrame, path: str) -> bool:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        df.to_csv(path, index=False)
        return True
    except OSError as exc:
        logger.warning("Could not write the cache %s: %s", path, exc)
        return False


def is_estimated(df: pd.DataFrame) -> bool:
    """True if the series is synthetic (to show the "estimated" badge)."""
    return df.attrs.get("source") == "estimated"


def extraterrestrial_radiation_mm(lat: float, day_of_year):
    """Daily extraterrestrial radiation Ra in mm/day of equivalent evaporation (FAO-56)."""
    import numpy as np

    phi = np.radians(lat)
    j = np.asarray(day_of_year, dtype=float)
    dr = 1 + 0.033 * np.cos(2 * np.pi * j / 365.0)
    delta = 0.409 * np.sin(2 * np.pi * j / 365.0 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(delta), -1.0, 1.0))
    ra_mj = (24 * 60 / np.pi) * 0.0820 * dr * (
        ws * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(ws)
    )
    return np.clip(ra_mj, 0.0, None) * 0.408


__all__ = ["get_series", "is_estimated", "demo_mode", "extraterrestrial_radiation_mm"]
