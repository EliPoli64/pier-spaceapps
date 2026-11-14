"""Lógica común de las series diarias con caché (OpenET, SMAP).

Orden: 1) caché en disco, 2) API en vivo solo fuera del modo demo, con
reintentos y cortacircuito, 3) serie sintética marcada como estimada.

El origen queda en `df.attrs["fuente"]`: "cache", "en_vivo" o "estimado".
"""
from __future__ import annotations

import logging
import os
from typing import Callable

import pandas as pd

from piper_agent.data.resiliencia import llamar_con_reintentos

logger = logging.getLogger("pier.data.series")

DIR_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")


def modo_demo() -> bool:
    return os.environ.get("PIER_DEMO_MODE", "1") == "1"


def obtener_serie(
    nombre: str,
    columna: str,
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    pedir_en_vivo: Callable[[], pd.DataFrame | None] | None,
    generar_sintetico: Callable[[], pd.DataFrame],
    cache_dir: str | None = None,
) -> pd.DataFrame:
    """Devuelve un DataFrame [date, `columna`] siguiendo el orden caché → vivo → sintético."""
    cache_dir = cache_dir or os.path.join(DIR_CACHE, nombre)
    ruta = os.path.join(cache_dir, f"{lat:.2f}_{lon:.2f}_{start_date}_{end_date}.csv")
    marcador = ruta + ".SYNTHETIC_CACHE.txt"

    # 1) Caché
    if os.path.exists(ruta):
        df = pd.read_csv(ruta, parse_dates=["date"])
        if columna in df.columns:
            df.attrs["fuente"] = "estimado" if os.path.exists(marcador) else "cache"
            return df

    # 2) API en vivo (solo ruta de producción)
    if pedir_en_vivo is not None and not modo_demo():
        try:
            df = llamar_con_reintentos(pedir_en_vivo, descripcion=f"API {nombre}")
        except RuntimeError as exc:
            logger.warning("%s en vivo no disponible (%s); se usa estimación", nombre, exc)
            df = None
        if df is not None and not df.empty:
            _guardar(df, ruta)
            df.attrs["fuente"] = "en_vivo"
            return df

    # 3) Sintético, marcado como estimado
    df = generar_sintetico()
    if _guardar(df, ruta):
        try:
            with open(marcador, "w", encoding="utf-8") as f:
                f.write(f"SYNTHETIC_CACHE: {nombre} estimado; no proviene de la API.\n")
        except OSError:
            pass
    df.attrs["fuente"] = "estimado"
    return df


def _guardar(df: pd.DataFrame, ruta: str) -> bool:
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        df.to_csv(ruta, index=False)
        return True
    except OSError as exc:
        logger.warning("No se pudo escribir el caché %s: %s", ruta, exc)
        return False


def es_estimado(df: pd.DataFrame) -> bool:
    """True si la serie es sintética (para mostrar la insignia "estimado")."""
    return df.attrs.get("fuente") == "estimado"


__all__ = ["obtener_serie", "es_estimado", "modo_demo"]
