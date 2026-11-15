"""Soil texture lookup for PIER.

Looks up soil texture class, field capacity, and wilting point from
SoilGrids / ISRIC (or user override). Falls back to climate-zone estimates
when the API is unavailable.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import requests

logger = logging.getLogger("pier.data.soil_lookup")

SOILGRIDS_BASE = os.environ.get(
    "PIER_SOILGRIDS_BASE", "https://rest.isric.org/soilgrids/v2.0/properties/query"
)

# SoilGrids has been intermittently slow / down (500 / >15s hangs).
# Keep the timeout short so an optional soil enrichment never stalls a live plan
# past frontend request timeouts, and cache/cool down failed lookups.
SOILGRIDS_TIMEOUT = float(os.environ.get("PIER_SOILGRIDS_TIMEOUT", "5"))
SOILGRIDS_CACHE_TTL = float(os.environ.get("PIER_SOILGRIDS_CACHE_TTL", "21600"))
SOILGRIDS_COOLDOWN = float(os.environ.get("PIER_SOILGRIDS_COOLDOWN", "120"))

_SOIL_LOCK = threading.Lock()
_SOILGRIDS_CACHE: dict[tuple[float, float], tuple[float, dict[str, Any] | None]] = {}
_SOILGRIDS_COOLDOWN_UNTIL: float = 0.0


# Climate-zone fallback estimates (texture_class, field_capacity_mm, wilting_point_mm)
# Based on USDA texture class typical values. mm values are per-meter depth approximations.
CLIMATE_ZONE_DEFAULTS = {
    "arid": ("Sandy loam", 120, 60),
    "semi_arid": ("Loam", 180, 90),
    "temperate": ("Silt loam", 220, 110),
    "humid": ("Clay loam", 260, 140),
    "tropical": ("Sandy clay loam", 200, 110),
    "montane": ("Loam", 190, 95),
}


def _climate_zone_from_lat(lat: float) -> str:
    """Very rough climate-zone guess from latitude (fallback only)."""
    abs_lat = abs(lat)
    if abs_lat > 60:
        return "montane"
    if abs_lat > 30:
        return "temperate"
    if abs_lat > 15:
        return "semi_arid"
    if abs_lat > 5:
        return "tropical"
    return "arid"


def _soilgrids_query(lat: float, lon: str | float) -> dict[str, Any] | None:
    """Query SoilGrids for soil properties. Returns None on failure."""
    try:
        params = {
            "lat": lat,
            "lon": lon,
            "property": ["bldfie", "silt", "clay", "sand", "ocd", "phh2o"],
            "depth": ["0-5cm"],
        }
        resp = requests.get(SOILGRIDS_BASE, params=params, timeout=SOILGRIDS_TIMEOUT)
        if resp.status_code != 200:
            logger.info("SoilGrids returned %s; using climate-zone estimate", resp.status_code)
            return None
        data = resp.json()
        # Extract mean values for top layer
        props = data.get("properties", {}).get("layers", [])
        result: dict[str, Any] = {}
        for layer in props:
            name = layer.get("name", "")
            values = layer.get("depths", [{}])[0].get("values", {})
            result[name] = values.get("mean")
        return result
    except Exception as exc:  # noqa: BLE001
        logger.info("SoilGrids lookup unavailable (%s); using climate-zone estimate", exc)
        return None


_DEFAULT_SOILGRIDS_QUERY = _soilgrids_query


def clear_soil_cache() -> None:
    """Reset the in-memory SoilGrids cache and outage cooldown."""
    global _SOILGRIDS_COOLDOWN_UNTIL
    with _SOIL_LOCK:
        _SOILGRIDS_CACHE.clear()
        _SOILGRIDS_COOLDOWN_UNTIL = 0.0


def _soilgrids_lookup_cached(lat: float, lon: float) -> dict[str, Any] | None:
    """Query SoilGrids with per-coordinate caching and a short outage cooldown."""
    global _SOILGRIDS_COOLDOWN_UNTIL
    if _soilgrids_query is not _DEFAULT_SOILGRIDS_QUERY:
        return _soilgrids_query(lat, lon)

    key = (round(float(lat), 3), round(float(lon), 3))
    now = time.monotonic()
    with _SOIL_LOCK:
        cached = _SOILGRIDS_CACHE.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]
        if now < _SOILGRIDS_COOLDOWN_UNTIL:
            return None

    props = _soilgrids_query(lat, lon)
    now = time.monotonic()
    with _SOIL_LOCK:
        if props:
            _SOILGRIDS_CACHE[key] = (now + SOILGRIDS_CACHE_TTL, props)
        else:
            _SOILGRIDS_COOLDOWN_UNTIL = now + SOILGRIDS_COOLDOWN
    return props


def lookup_soil_timeout() -> float:
    """Current SoilGrids request timeout (seconds)."""
    return SOILGRIDS_TIMEOUT



def _texture_from_grids(props: dict[str, Any] | None) -> str | None:
    """Derive USDA texture class from sand/silt/clay percentages."""
    if not props:
        return None
    sand = props.get("sand")
    silt = props.get("silt")
    clay = props.get("clay")
    if sand is None or silt is None or clay is None:
        return None
    # SoilGrids values are in cg/kg (centigrams per kilogram) → convert to %
    sand_pct = sand / 10.0 if sand and sand > 10 else sand
    silt_pct = silt / 10.0 if silt and silt > 10 else silt
    clay_pct = clay / 10.0 if clay and clay > 10 else clay
    total = sand_pct + silt_pct + clay_pct
    if total <= 0:
        return None
    sand_pct = sand_pct / total * 100
    silt_pct = silt_pct / total * 100
    clay_pct = clay_pct / total * 100

    # USDA texture triangle (simplified)
    if clay_pct >= 40:
        if sand_pct <= 45:
            return "Clay"
        return "Sandy clay"
    if clay_pct >= 27:
        if sand_pct <= 20:
            return "Silty clay loam"
        if sand_pct <= 45:
            return "Clay loam"
        return "Sandy clay loam"
    if clay_pct >= 7:
        if silt_pct >= 50:
            return "Silt loam"
        if sand_pct <= 52:
            return "Loam"
        return "Sandy loam"
    if silt_pct >= 50:
        return "Silt loam"
    if sand_pct >= 85:
        return "Sand"
    return "Loamy sand"


def _field_capacity_wilting(texture: str | None) -> tuple[int, int]:
    """Return (field_capacity_mm, wilting_point_mm) for a texture class."""
    table = {
        "Sand": (60, 30),
        "Loamy sand": (90, 45),
        "Sandy loam": (120, 60),
        "Loam": (180, 90),
        "Silt loam": (220, 110),
        "Sandy clay loam": (200, 110),
        "Clay loam": (260, 140),
        "Silty clay loam": (280, 160),
        "Sandy clay": (240, 140),
        "Silty clay": (300, 170),
        "Clay": (320, 190),
    }
    return table.get(texture, (180, 90))


# Typical organic matter (%) per texture class; indicative values.
ORGANIC_MATTER_PCT = {
    "Sand": 0.8, "Loamy sand": 1.0, "Sandy loam": 1.5, "Loam": 2.5,
    "Silt loam": 3.0, "Sandy clay loam": 2.0, "Clay loam": 3.0,
    "Silty clay loam": 3.5, "Sandy clay": 2.0, "Silty clay": 3.5, "Clay": 3.5,
}


def _complete(result: dict[str, Any]) -> dict[str, Any]:
    """Add organic matter, available water and the Spanish contract aliases (docs/contratos.md)."""
    fc = result["field_capacity_mm"]
    wp = result["wilting_point_mm"]
    result["organic_matter_pct"] = ORGANIC_MATTER_PCT.get(result["texture_class"], 2.5)
    result["available_water_mm"] = fc - wp
    result["textura"] = result["texture_class"]
    result["campo_capacidad_mm"] = fc
    result["punto_marchitez_mm"] = wp
    return result


def lookup_soil(
    lat: float,
    lon: float,
    user_texture: str | None = None,
    use_network: bool | None = None,
    demo_mode: bool | None = None,
) -> dict[str, Any]:
    """Look up soil texture and water-holding properties.

    Args:
        lat: field latitude.
        lon: field longitude.
        user_texture: optional user-provided texture class override.
        use_network: if True, query SoilGrids; by default only outside demo mode.
        demo_mode: True makes no network calls; None reads PIER_DEMO_MODE.
            Ignored when `use_network` is given explicitly.

    Returns:
        dict with keys: texture_class, field_capacity_mm, wilting_point_mm,
        source ("user" | "soilgrids" | "climate_zone_estimate"), lat, lon,
        organic_matter_pct, available_water_mm (field capacity - wilting point)
        and the contract aliases textura, campo_capacidad_mm, punto_marchitez_mm.
    """
    if use_network is None:
        if demo_mode is None:
            demo_mode = os.environ.get("PIER_DEMO_MODE", "1") == "1"
        use_network = not demo_mode

    if user_texture:
        fc, wp = _field_capacity_wilting(user_texture)
        return _complete({
            "texture_class": user_texture,
            "field_capacity_mm": fc,
            "wilting_point_mm": wp,
            "source": "user",
            "lat": lat,
            "lon": lon,
        })

    props = _soilgrids_lookup_cached(float(lat), float(lon)) if use_network else None
    texture = _texture_from_grids(props) if props else None

    if texture:
        fc, wp = _field_capacity_wilting(texture)
        return _complete({
            "texture_class": texture,
            "field_capacity_mm": fc,
            "wilting_point_mm": wp,
            "source": "soilgrids",
            "lat": lat,
            "lon": lon,
        })

    # Fallback to climate-zone estimate
    zone = _climate_zone_from_lat(lat)
    texture, fc, wp = CLIMATE_ZONE_DEFAULTS[zone]
    logger.info(
        "Using climate-zone estimate (%s) for lat=%.4f lon=%.4f", zone, lat, lon
    )
    return _complete({
        "texture_class": texture,
        "field_capacity_mm": fc,
        "wilting_point_mm": wp,
        "source": "climate_zone_estimate",
        "zone": zone,
        "lat": lat,
        "lon": lon,
    })


__all__ = [
    "lookup_soil",
    "CLIMATE_ZONE_DEFAULTS",
    "lookup_soil_timeout",
    "clear_soil_cache",
]
