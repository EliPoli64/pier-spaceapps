"""Actual evapotranspiration (ETa) from OpenET.

Cache first. Outside demo mode OpenET is queried when PIER_OPENET_API_KEY is
set; without a key, reference ET (Hargreaves) is computed from real NASA POWER
temperatures. If nothing responds, an estimated series is returned.
"""
from __future__ import annotations

import logging
import os

import numpy as np
import pandas as pd
import requests

from piper_agent.data._series_cache import (
    extraterrestrial_radiation_mm,
    get_series,
    is_estimated,
)

logger = logging.getLogger("pier.data.fetch_openet")

OPENET_BASE = os.environ.get("PIER_OPENET_BASE", "https://api.openet.io/api/v1")
OPENET_API_KEY = os.environ.get("PIER_OPENET_API_KEY", "")


def fetch_openet_eta(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    cache_dir: str | None = None,
    demo_mode: bool | None = None,
) -> pd.DataFrame:
    """Daily ETa in mm.

    Args:
        demo_mode: True never touches the network; None reads PIER_DEMO_MODE.

    Returns:
        DataFrame with columns [date, eta_mm]. `df.attrs["source"]` is "cache",
        "live", "nasa_power_hargreaves" or "estimated".
    """
    def _live() -> pd.DataFrame | None:
        resp = requests.get(
            f"{OPENET_BASE}/eta",
            params={
                "lat": lat, "lon": lon,
                "start_date": start_date, "end_date": end_date,
                "network": "ensemble", "units": "mm",
            },
            headers={"Authorization": f"Bearer {OPENET_API_KEY}"},
            timeout=15,
        )
        resp.raise_for_status()
        records = resp.json().get("data", [])
        if not records:
            return None
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        return df.rename(columns={"eta": "eta_mm"})[["date", "eta_mm"]]

    return get_series(
        "openet", "eta_mm", lat, lon, start_date, end_date,
        fetch_live=_live if OPENET_API_KEY else (
            lambda: _et0_from_power(lat, lon, start_date, end_date)
        ),
        generate_synthetic=lambda: _synthetic_eta(lat, start_date, end_date),
        cache_dir=cache_dir,
        demo_mode=demo_mode,
    )


def _et0_from_power(lat: float, lon: float, start_date: str, end_date: str) -> pd.DataFrame:
    """Reference ET (Hargreaves, FAO-56) from real NASA POWER temperatures.

    This is ET0, not ETa: it works as an upper bound of actual
    evapotranspiration when there is no OpenET key. Flagged as
    "nasa_power_hargreaves".
    """
    from piper_agent.data.ingestion.pipeline import ingest_point

    # Single real-data entry point: it decides the source and caches the download.
    data = ingest_point(lat, lon, start_date, end_date, demo_mode=False, use_imerg=False)
    if data["fuente_datos"] == "sintetico":
        raise RuntimeError(f"no real temperatures: {data['fallback_reason']}")
    power = data["power"]
    dates = pd.to_datetime(power["date"])
    tmax, tmin = power["T2M_MAX"].to_numpy(), power["T2M_MIN"].to_numpy()
    ra = extraterrestrial_radiation_mm(lat, dates.dt.dayofyear.to_numpy())
    et0 = 0.0023 * ((tmax + tmin) / 2 + 17.8) * np.sqrt(np.clip(tmax - tmin, 0, None)) * ra
    df = pd.DataFrame({"date": dates, "eta_mm": np.round(np.clip(et0, 0, None), 2)})
    df.attrs["source"] = "nasa_power_hargreaves"
    return df


def _synthetic_eta(lat: float, start_date: str, end_date: str) -> pd.DataFrame:
    """Estimated daily ETa from the latitude band and the season."""
    rng = np.random.default_rng(11)
    days = pd.date_range(start_date, end_date, freq="D")
    abs_lat = abs(lat)
    base = 2.0 if abs_lat > 45 else 4.0 if abs_lat > 20 else 5.5  # mm/day
    doy = days.dayofyear.to_numpy()
    offset = 80 if lat >= 0 else 262  # summer is reversed in the Southern Hemisphere
    seasonal = 1.0 + 0.3 * np.sin(2 * np.pi * (doy - offset) / 365.0)
    eta = np.clip(base * seasonal * rng.normal(1.0, 0.15, size=len(days)), 0.0, None)
    return pd.DataFrame({"date": days, "eta_mm": np.round(eta, 2)})


__all__ = ["fetch_openet_eta", "is_estimated"]
