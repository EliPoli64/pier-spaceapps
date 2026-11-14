"""Real ingestion for any coordinate, with a silent fallback.

`ingest_point` returns the daily temperature and rainfall of a point:

- Demo mode (default, PIER_DEMO_MODE=1): never touches the network. Uses the
  cache of the nearest demo scenario or, far from all of them, a synthetic
  series for that latitude.
- Production path (PIER_DEMO_MODE=0): real NASA POWER (no credentials) and,
  when Earthdata credentials are set, IMERG rainfall through imergpy. If
  anything fails it falls back to the demo-mode data without raising and
  records it in `fuente_datos` and `fallback_reason`.
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any

import pandas as pd

from piper_agent.data import cache_loader
from piper_agent.data import generate_cache as gc
from piper_agent.data.ingestion import imerg_etl

logger = logging.getLogger("pier.ingestion.pipeline")

REAL_DIR = os.path.join(gc.ROOT_DIR, "data", "cache", "real")
DEMO_RADIUS_DEGREES = 0.5
REAL_PARAMETERS = ("T2M_MAX", "T2M_MIN", "PRECTOTCORR", "GWETROOT")


def region_key(lat: float, lon: float) -> str:
    """0.5° cell that identifies the region (roughly the POWER resolution)."""
    lat_c = round(lat * 2) / 2
    lon_c = round(lon * 2) / 2
    return f"lat{lat_c:+05.1f}_lon{lon_c:+06.1f}"


def _slice(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    dates = pd.to_datetime(df["date"])
    out = df.loc[(dates >= start) & (dates <= end)].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    return out.reset_index(drop=True)


def _nearest_scenario(lat: float, lon: float) -> str | None:
    """Demo scenario within DEMO_RADIUS_DEGREES; prefers "normal" when several match."""
    candidates = []
    for name in cache_loader.SCENARIOS:
        packet = gc.read_packet(name)
        if abs(packet["lat"] - lat) <= DEMO_RADIUS_DEGREES and abs(packet["lon"] - lon) <= DEMO_RADIUS_DEGREES:
            candidates.append(name)
    if not candidates:
        return None
    return "normal" if "normal" in candidates else candidates[0]


def _fallback(lat: float, lon: float, start: str, end: str, reason: str | None) -> dict[str, Any]:
    """Data without network: nearby demo cache or a synthetic series for the latitude."""
    scenario = _nearest_scenario(lat, lon)
    power = rainfall = None
    if scenario:
        power = _slice(cache_loader.load_power(scenario), start, end)
        rainfall = _slice(cache_loader.load_imerg(scenario), start, end)
    if power is None or power.empty or rainfall.empty:
        scenario = None
        power = gc.generate_power(end, start, lat, season_end=end)
        power = _slice(power, start, end)
        rainfall = power[["date", "PRECTOTCORR"]].rename(columns={"PRECTOTCORR": "precipitation_mm"})
    return {
        "power": power,
        "rainfall": rainfall,
        "fuente_datos": "sintetico",
        "fallback_reason": reason,
        "demo_scenario": scenario,
        "region": region_key(lat, lon),
    }


def _has_earthdata_credentials() -> bool:
    return bool(os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD"))


def ingest_point(
    lat: float,
    lon: float,
    start: str,
    end: str,
    demo_mode: bool | None = None,
    use_imerg: bool | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Daily temperature and rainfall of a point between `start` and `end` (ISO).

    Returns:
        dict with `power` (date, T2M_MAX, T2M_MIN, PRECTOTCORR[, GWETROOT]),
        `rainfall` (date, precipitation_mm), `fuente_datos` ("sintetico",
        "nasa_power" or "nasa_power+imerg"), `fallback_reason` (None when
        there was no fallback), `demo_scenario` and `region`.
    """
    if demo_mode is None:
        demo_mode = os.environ.get("PIER_DEMO_MODE", "1") == "1"
    if demo_mode:
        return _fallback(lat, lon, start, end, reason=None)

    region = region_key(lat, lon)
    real_end = min(end, date.today().isoformat())
    power_path = os.path.join(REAL_DIR, f"{region}_{start}_{real_end}_power.csv")
    rainfall_path = os.path.join(REAL_DIR, f"{region}_{start}_{real_end}_rainfall.csv")
    source_path = os.path.join(REAL_DIR, f"{region}_{start}_{real_end}.source.txt")

    if use_cache and all(os.path.exists(p) for p in (power_path, rainfall_path, source_path)):
        with open(source_path, encoding="utf-8") as f:
            source = f.read().strip()
        return {
            "power": pd.read_csv(power_path), "rainfall": pd.read_csv(rainfall_path),
            "fuente_datos": source, "fallback_reason": None,
            "demo_scenario": None, "region": region,
        }

    try:
        power = imerg_etl.download_power(lat, lon, start, real_end, parameters=REAL_PARAMETERS)
    except RuntimeError as exc:
        logger.warning("Real ingestion unavailable (%s); synthetic fallback", exc)
        return _fallback(lat, lon, start, end, reason=f"NASA POWER unavailable: {exc}")

    source = "nasa_power"
    rainfall = None
    if use_imerg is None:
        use_imerg = _has_earthdata_credentials()
    if use_imerg:
        try:
            _, records = imerg_etl.fetch_with_retry(lat, lon, start, real_end)
            rainfall = imerg_etl._imerg_to_dataframe(records)
        except RuntimeError as exc:
            logger.warning("IMERG unavailable (%s); using POWER PRECTOTCORR", exc)
        if rainfall is not None:
            source = "nasa_power+imerg"
    if rainfall is None:
        rainfall = power[["date", "PRECTOTCORR"]].rename(columns={"PRECTOTCORR": "precipitation_mm"})

    try:
        os.makedirs(REAL_DIR, exist_ok=True)
        power.to_csv(power_path, index=False)
        rainfall.to_csv(rainfall_path, index=False)
        with open(source_path, "w", encoding="utf-8") as f:
            f.write(source)
    except OSError as exc:
        logger.warning("Could not save the real-data cache: %s", exc)

    return {
        "power": power, "rainfall": rainfall.reset_index(drop=True),
        "fuente_datos": source, "fallback_reason": None,
        "demo_scenario": None, "region": region,
    }


__all__ = ["ingest_point", "region_key", "REAL_PARAMETERS"]
