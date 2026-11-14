"""Root-zone soil moisture (SMAP).

Cache first. Outside demo mode SMAP is queried when PIER_SMAP_API_KEY is set;
without a key, the real root-zone wetness from NASA POWER (GWETROOT) is used.
If nothing responds, an estimated series is returned.
"""
from __future__ import annotations

import logging
import os

import numpy as np
import pandas as pd
import requests

from piper_agent.data._series_cache import get_series, is_estimated

logger = logging.getLogger("pier.data.fetch_smap")

SMAP_BASE = os.environ.get("PIER_SMAP_BASE", "https://nsidc.org/api/smap/v1")
SMAP_API_KEY = os.environ.get("PIER_SMAP_API_KEY", "")


def fetch_smap_moisture(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    cache_dir: str | None = None,
    demo_mode: bool | None = None,
) -> pd.DataFrame:
    """Daily root-zone volumetric soil moisture (%).

    Args:
        demo_mode: True never touches the network; None reads PIER_DEMO_MODE.

    Returns:
        DataFrame with columns [date, soil_moisture_vol_pct]. `df.attrs["source"]`
        is "cache", "live", "nasa_power_gwetroot" or "estimated".
    """
    def _live() -> pd.DataFrame | None:
        resp = requests.get(
            f"{SMAP_BASE}/data",
            params={
                "lat": lat, "lon": lon,
                "start_date": start_date, "end_date": end_date,
                "parameter": "sm_rootzone",
            },
            headers={"Authorization": f"Bearer {SMAP_API_KEY}"},
            timeout=15,
        )
        resp.raise_for_status()
        records = resp.json().get("data", [])
        if not records:
            return None
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        return df.rename(columns={"sm_rootzone": "soil_moisture_vol_pct"})[
            ["date", "soil_moisture_vol_pct"]
        ]

    return get_series(
        "smap", "soil_moisture_vol_pct", lat, lon, start_date, end_date,
        fetch_live=_live if SMAP_API_KEY else (
            lambda: _moisture_from_power(lat, lon, start_date, end_date)
        ),
        generate_synthetic=lambda: _synthetic_moisture(lat, start_date, end_date),
        cache_dir=cache_dir,
        demo_mode=demo_mode,
    )


POROSITY_PCT = 45.0  # typical porosity of a loam soil; calibrate locally


def _moisture_from_power(lat: float, lon: float, start_date: str, end_date: str) -> pd.DataFrame:
    """Real root-zone moisture: GWETROOT from NASA POWER (MERRA-2).

    GWETROOT is the saturation fraction (0-1) of the top metre of soil; it is
    converted to volumetric % by multiplying by a typical porosity. Flagged as
    "nasa_power_gwetroot".
    """
    from piper_agent.data.ingestion.pipeline import ingest_point

    # Single real-data entry point: it decides the source and caches the download.
    data = ingest_point(lat, lon, start_date, end_date, demo_mode=False, use_imerg=False)
    power = data["power"]
    if data["fuente_datos"] == "sintetico" or "GWETROOT" not in power.columns:
        raise RuntimeError(f"no real GWETROOT: {data['fallback_reason']}")
    df = pd.DataFrame({
        "date": pd.to_datetime(power["date"]),
        "soil_moisture_vol_pct": (power["GWETROOT"].clip(0, 1) * POROSITY_PCT).round(1),
    })
    df.attrs["source"] = "nasa_power_gwetroot"
    return df


def _synthetic_moisture(lat: float, start_date: str, end_date: str) -> pd.DataFrame:
    """Estimated daily moisture from the latitude band and the season."""
    rng = np.random.default_rng(21)
    days = pd.date_range(start_date, end_date, freq="D")
    abs_lat = abs(lat)
    base = 25.0 if abs_lat > 45 else 20.0 if abs_lat > 20 else 15.0  # vol. %
    doy = days.dayofyear.to_numpy()
    offset = 150 if lat >= 0 else 332
    seasonal = 1.0 + 0.25 * np.sin(2 * np.pi * (doy - offset) / 365.0)
    moisture = np.clip(base * seasonal * rng.normal(1.0, 0.1, size=len(days)), 5.0, 45.0)
    return pd.DataFrame({"date": days, "soil_moisture_vol_pct": np.round(moisture, 1)})


__all__ = ["fetch_smap_moisture", "is_estimated"]
