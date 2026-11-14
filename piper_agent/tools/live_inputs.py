"""Live-data inputs for the tools: one call that gives them real (or fallback) data.

The tools keep their cache-based signatures (`demo_name=...`). On the production
path (`demo_mode=False`) they take the same inputs from here instead:

- `ingest_point()` (Erik's single real-data entry point) gives daily temperature
  and rainfall plus the source label (`fuente_datos`) and, when it fell back, why.
- `get_climatology()` gives the regional monthly percentiles, from which the
  thresholds the tools used to read from `*_baselines.json` are built.

This module only READS the data layer; it never decides POWER vs IMERG vs
fallback (that stays in `piper_agent/data/ingestion/pipeline.py`).

PP5: `track_data_source` logs a structured entry when a region's source drops from
real data to "sintetico".
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd

from piper_agent.contracts import DEFAULT_TBASE_C

logger = logging.getLogger("pier.tools.live_inputs")

REAL_SOURCES = ("nasa_power", "nasa_power+imerg")
HISTORY_DAYS = 35  # at least the 30-day drought window plus a margin

_LAST_SOURCE: dict[str, str] = {}


def default_season_start(lat: float, current_date: str) -> str:
    """Rough growing-season start: 1 Apr (north) or 1 Oct (south), never after `current_date`.

    Season detection proper belongs to the climate branch; callers can pass `season_start`.
    """
    today = date.fromisoformat(current_date)
    month, day = (10, 1) if lat < 0 else (4, 1)
    start = date(today.year, month, day)
    if start > today:
        start = date(today.year - 1, month, day)
    return start.isoformat()


def monthly_thresholds(climatology: dict[str, Any], on_date: str) -> dict[str, float]:
    """3-day p95 and 30-day p10 rainfall for the month of `on_date`; empty when the month is missing."""
    month = str(date.fromisoformat(on_date[:10]).month)
    stats = (climatology.get("months") or {}).get(month)
    if not stats:
        return {}
    return {
        "p95_3day_cum_rainfall": stats["rain_3d"]["p95"],
        "p10_30day_cum_rainfall": stats["rain_30d"]["p10"],
    }


def _monthly_gdd_normal(climatology: dict[str, Any]) -> dict[str, float]:
    """Typical GDD per day for each month, from the median Tmax/Tmin of the climatology."""
    out = {}
    for month, stats in (climatology.get("months") or {}).items():
        mean_t = (stats["tmax"]["p50"] + stats["tmin"]["p50"]) / 2.0
        out[month] = round(max(0.0, mean_t - DEFAULT_TBASE_C), 2)
    return out


def build_baselines(climatology: dict[str, Any], on_date: str, source: str) -> dict[str, Any]:
    """Baselines in the shape the tools already read, built from a regional climatology."""
    baselines = {
        **monthly_thresholds(climatology, on_date),
        "climatological_frost_date": climatology.get("first_autumn_frost"),
        "tropical": climatology.get("tropical"),
        "season_end": None,
        "fuente_datos": source,
        "monthly_gdd_normal": _monthly_gdd_normal(climatology),
        # the climatology frost date is already local to the hemisphere: no 182-day shift
        "frost_is_local": True,
        "note": "regional climatology; typical values, local calibration required",
    }
    return baselines


def load_live(
    lat: float,
    lon: float,
    end_date: str,
    season_start: str | None = None,
    demo_mode: bool = False,
) -> dict[str, Any]:
    """Everything the tools need for a coordinate, from the data layer.

    Returns:
        dict with `power`, `rainfall`, `baselines`, `climatology`, `fuente_datos`,
        `fallback_reason`, `region`, `season_start` and `ultima_actualizacion`.
    """
    from piper_agent.data.climatology import get_climatology
    from piper_agent.data.ingestion.pipeline import ingest_point

    season_start = season_start or default_season_start(lat, end_date)
    history_start = (date.fromisoformat(end_date) - timedelta(days=HISTORY_DAYS)).isoformat()
    start = min(season_start, history_start)

    data = ingest_point(lat, lon, start, end_date, demo_mode=demo_mode)
    climatology = get_climatology(lat, lon, until=end_date, demo_mode=demo_mode)
    rainfall = data["rainfall"]
    last = None if rainfall is None or rainfall.empty else str(pd.to_datetime(rainfall["date"]).max().date())
    return {
        "power": data["power"],
        "rainfall": rainfall,
        "baselines": build_baselines(climatology, end_date, data["fuente_datos"]),
        "climatology": climatology,
        "fuente_datos": data["fuente_datos"],
        "fallback_reason": data["fallback_reason"],
        "region": data["region"],
        "season_start": season_start,
        "ultima_actualizacion": last,
    }


def track_data_source(region: str, fuente_datos: str, reason: str | None = None) -> dict[str, Any] | None:
    """PP5: log (and return) a structured entry when a region goes from real data to "sintetico".

    Returns None when nothing changed or when the change was not a degradation.
    """
    previous = _LAST_SOURCE.get(region)
    _LAST_SOURCE[region] = fuente_datos
    if previous in REAL_SOURCES and fuente_datos == "sintetico":
        entry = {
            "event": "data_source_degraded",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "region": region,
            "previous_source": previous,
            "current_source": fuente_datos,
            "reason": reason or "unknown",
        }
        logger.warning("PIER_ALERT %s", json.dumps(entry, ensure_ascii=False))
        return entry
    return None


__all__ = ["load_live", "build_baselines", "monthly_thresholds", "default_season_start",
           "track_data_source", "REAL_SOURCES"]
