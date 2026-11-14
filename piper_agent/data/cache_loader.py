"""PIER cache loader: the single entry point to the data.

The demo only serves cached data; live Earthdata/POWER is the production path
(Spec §8) and is enabled with PIER_DEMO_MODE=0.

Cache-first pattern: if a cache file is missing (for example in a fresh clone:
the cache is not committed to git) the synthetic one is generated on the spot.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pandas as pd

from piper_agent.data import resilience

logger = logging.getLogger("pier.data.cache_loader")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMERS = os.path.join(ROOT, "data", "cache", "imerg")
POWERS = os.path.join(ROOT, "data", "cache", "power")
BASELINES = os.path.join(ROOT, "data", "baselines")
DEMOS = os.path.join(ROOT, "..", "demo")

CROPS_PATH = Path(ROOT) / "data" / "rescue_crops.csv"

PIER_DEMO_MODE = os.environ.get("PIER_DEMO_MODE", "1") == "1"

# Demo scenarios = every demo/*_demo.json (adding a packet is enough to get its cache).
SCENARIOS = tuple(sorted(p.stem[:-5] for p in (Path(ROOT).parent / "demo").glob("*_demo.json")))
VALID_SOURCES = ("sintetico", "nasa_power", "nasa_power+imerg")  # contract values of `fuente_datos`


def _base_name(name: str) -> str:
    """Accept "flood" or "flood_demo" and return "flood"."""
    return name[:-5] if name.endswith("_demo") else name


def _ensure_cache(demo_name: str, path: str) -> None:
    """If `path` does not exist, generate the scenario's synthetic cache."""
    if os.path.exists(path):
        return
    if demo_name not in SCENARIOS:
        raise FileNotFoundError(f"No cache for '{demo_name}' and it is not a demo scenario: {path}")
    logger.warning("Cache missing for '%s'; generating the synthetic one", demo_name)
    from piper_agent.data.generate_cache import generate_scenario

    generate_scenario(demo_name)


def load_imerg(demo_name: str) -> pd.DataFrame:
    """Cached daily rainfall (date, precipitation_mm)."""
    path = os.path.join(IMERS, f"{demo_name}_imerg.csv")
    _ensure_cache(demo_name, path)
    return pd.read_csv(path, parse_dates=["date"])


def load_power(demo_name: str) -> pd.DataFrame:
    """Cached daily POWER data (date, T2M_MAX, T2M_MIN, PRECTOTCORR)."""
    path = os.path.join(POWERS, f"{demo_name}_power.csv")
    _ensure_cache(demo_name, path)
    return pd.read_csv(path, parse_dates=["date"])


def load_baselines(demo_name: str) -> dict:
    """Cached baselines (p95, p10, climatological_frost_date, fuente_datos...)."""
    path = os.path.join(BASELINES, f"{demo_name}_baselines.json")
    _ensure_cache(demo_name, path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_frost_bands() -> dict:
    """First-frost bands by latitude and hemisphere (baselines/southern_hemisphere.json)."""
    from piper_agent.data.generate_cache import write_frost_bands

    path = os.path.join(BASELINES, "southern_hemisphere.json")
    if not os.path.exists(path):
        write_frost_bands()
    with open(path, encoding="utf-8") as f:
        bands = json.load(f)
    if "north" not in bands:  # file written by an older version with other key names
        write_frost_bands()
        with open(path, encoding="utf-8") as f:
            bands = json.load(f)
    return bands


def get_data_source(demo_name: str) -> str:
    """Origin of the scenario's data: "sintetico", "nasa_power" or "nasa_power+imerg".

    Returns "sintetico" when the cache is synthetic or when the circuit breaker
    of the live sources is open (the production path fell back).
    """
    demo_name = _base_name(demo_name)
    try:
        source = load_baselines(demo_name).get("fuente_datos", "sintetico")
    except (FileNotFoundError, json.JSONDecodeError):
        return "sintetico"
    if source not in VALID_SOURCES:
        return "sintetico"
    if source != "sintetico" and resilience.live_circuit_breaker.is_open():
        logger.warning("Live source unavailable; '%s' is reported as sintetico", demo_name)
        return "sintetico"
    return source


def load_demo_packet(name: str) -> dict:
    """Demo packet from demo/{name}.json. Accepts "flood" or "flood_demo".

    Besides the JSON keys it adds `date` (alias of `current_date`) and
    `fuente_datos`.
    """
    base = _base_name(name)
    path = os.path.join(DEMOS, f"{base}_demo.json")
    with open(path, encoding="utf-8") as f:
        packet = json.load(f)
    packet.setdefault("season_end", None)
    packet["date"] = packet.get("current_date")
    packet["fuente_datos"] = get_data_source(base)
    return packet


def get_crops_path() -> Path:
    """Absolute path of rescue_crops.csv (independent of the working directory)."""
    return CROPS_PATH


# Names already used by callers outside piper_agent/data (agent, API); kept as aliases.
ESCENARIOS = SCENARIOS
RUTA_CULTIVOS = CROPS_PATH
get_ruta_cultivos = get_crops_path
get_fuente_datos = get_data_source

__all__ = [
    "load_imerg", "load_power", "load_baselines", "load_demo_packet",
    "load_frost_bands", "get_data_source", "get_crops_path",
    "CROPS_PATH", "SCENARIOS", "PIER_DEMO_MODE",
    "ESCENARIOS", "RUTA_CULTIVOS", "get_ruta_cultivos", "get_fuente_datos",
]
