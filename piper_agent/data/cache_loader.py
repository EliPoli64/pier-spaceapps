"""Cargador de caché de PIER: punto de entrada único a los datos.

La demo solo sirve datos en caché; Earthdata/POWER en vivo es la ruta de
producción (Spec §8) y se activa con PIER_DEMO_MODE=0.

Patrón "caché primero": si falta un archivo de caché (por ejemplo, en un clon
nuevo: el caché no se sube a git) se genera el sintético en el momento.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pandas as pd

from piper_agent.data.resiliencia import cortacircuito_en_vivo

logger = logging.getLogger("pier.data.cache_loader")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMERS = os.path.join(ROOT, "data", "cache", "imerg")
POWERS = os.path.join(ROOT, "data", "cache", "power")
BASELINES = os.path.join(ROOT, "data", "baselines")
DEMOS = os.path.join(ROOT, "..", "demo")

RUTA_CULTIVOS = Path(ROOT) / "data" / "rescue_crops.csv"

PIER_DEMO_MODE = os.environ.get("PIER_DEMO_MODE", "1") == "1"

# Escenarios demo = todos los demo/*_demo.json (agregar un paquete basta para tener su caché).
ESCENARIOS = tuple(sorted(p.stem[:-5] for p in (Path(ROOT).parent / "demo").glob("*_demo.json")))
FUENTES_VALIDAS = ("sintetico", "nasa_power", "nasa_power+imerg")


def _nombre_base(nombre: str) -> str:
    """Acepta "flood" o "flood_demo" y devuelve "flood"."""
    return nombre[:-5] if nombre.endswith("_demo") else nombre


def _asegurar_cache(demo_name: str, ruta: str) -> None:
    """Si `ruta` no existe, genera el caché sintético del escenario."""
    if os.path.exists(ruta):
        return
    if demo_name not in ESCENARIOS:
        raise FileNotFoundError(f"No hay caché para '{demo_name}' y no es un escenario demo: {ruta}")
    logger.warning("Caché ausente para '%s'; se genera el sintético", demo_name)
    from piper_agent.data.generate_cache import generar_escenario

    generar_escenario(demo_name)


def load_imerg(demo_name: str) -> pd.DataFrame:
    """Lluvia diaria en caché (date, precipitation_mm)."""
    path = os.path.join(IMERS, f"{demo_name}_imerg.csv")
    _asegurar_cache(demo_name, path)
    return pd.read_csv(path, parse_dates=["date"])


def load_power(demo_name: str) -> pd.DataFrame:
    """POWER diario en caché (date, T2M_MAX, T2M_MIN, PRECTOTCORR)."""
    path = os.path.join(POWERS, f"{demo_name}_power.csv")
    _asegurar_cache(demo_name, path)
    return pd.read_csv(path, parse_dates=["date"])


def load_baselines(demo_name: str) -> dict:
    """Baselines en caché (p95, p10, climatological_frost_date, fuente_datos...)."""
    path = os.path.join(BASELINES, f"{demo_name}_baselines.json")
    _asegurar_cache(demo_name, path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_bandas_helada() -> dict:
    """Bandas de primera helada por latitud y hemisferio (baselines/southern_hemisphere.json)."""
    path = os.path.join(BASELINES, "southern_hemisphere.json")
    if not os.path.exists(path):
        from piper_agent.data.generate_cache import escribir_bandas_helada

        escribir_bandas_helada()
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_fuente_datos(demo_name: str) -> str:
    """Origen de los datos del escenario: "sintetico", "nasa_power" o "nasa_power+imerg".

    Devuelve "sintetico" si el caché es sintético o si el cortacircuito de las
    fuentes en vivo está abierto (la ruta de producción cayó al respaldo).
    """
    demo_name = _nombre_base(demo_name)
    try:
        fuente = load_baselines(demo_name).get("fuente_datos", "sintetico")
    except (FileNotFoundError, json.JSONDecodeError):
        return "sintetico"
    if fuente not in FUENTES_VALIDAS:
        return "sintetico"
    if fuente != "sintetico" and cortacircuito_en_vivo.esta_abierto():
        logger.warning("Fuente en vivo no disponible; '%s' se reporta como sintetico", demo_name)
        return "sintetico"
    return fuente


def load_demo_packet(name: str) -> dict:
    """Paquete demo de demo/{name}.json. Acepta "flood" o "flood_demo".

    Además de las claves del JSON agrega `date` (alias de `current_date`) y
    `fuente_datos`.
    """
    base = _nombre_base(name)
    path = os.path.join(DEMOS, f"{base}_demo.json")
    with open(path, encoding="utf-8") as f:
        paquete = json.load(f)
    paquete.setdefault("season_end", None)
    paquete["date"] = paquete.get("current_date")
    paquete["fuente_datos"] = get_fuente_datos(base)
    return paquete


def get_ruta_cultivos() -> Path:
    """Ruta absoluta de rescue_crops.csv (no depende del directorio de trabajo)."""
    return RUTA_CULTIVOS


__all__ = [
    "load_imerg", "load_power", "load_baselines", "load_demo_packet",
    "load_bandas_helada", "get_fuente_datos", "get_ruta_cultivos",
    "RUTA_CULTIVOS", "PIER_DEMO_MODE",
]
