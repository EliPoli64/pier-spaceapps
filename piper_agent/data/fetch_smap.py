"""Humedad del suelo en la zona de raíces (SMAP).

Caché primero. Fuera del modo demo se consulta SMAP si hay PIER_SMAP_API_KEY;
sin clave se usa la humedad real de la zona de raíces de NASA POWER (GWETROOT).
Si nada responde, serie estimada.
"""
from __future__ import annotations

import logging
import os

import numpy as np
import pandas as pd
import requests

from piper_agent.data._series_cache import es_estimado, obtener_serie

logger = logging.getLogger("pier.data.fetch_smap")

SMAP_BASE = os.environ.get("PIER_SMAP_BASE", "https://nsidc.org/api/smap/v1")
SMAP_API_KEY = os.environ.get("PIER_SMAP_API_KEY", "")


def fetch_smap_moisture(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    cache_dir: str | None = None,
) -> pd.DataFrame:
    """Humedad volumétrica diaria de la zona de raíces (%).

    Returns:
        DataFrame con columnas [date, soil_moisture_vol_pct]. `df.attrs["fuente"]`
        vale "cache", "en_vivo" o "estimado".
    """
    def _en_vivo() -> pd.DataFrame | None:
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
        registros = resp.json().get("data", [])
        if not registros:
            return None
        df = pd.DataFrame(registros)
        df["date"] = pd.to_datetime(df["date"])
        return df.rename(columns={"sm_rootzone": "soil_moisture_vol_pct"})[
            ["date", "soil_moisture_vol_pct"]
        ]

    return obtener_serie(
        "smap", "soil_moisture_vol_pct", lat, lon, start_date, end_date,
        pedir_en_vivo=_en_vivo if SMAP_API_KEY else (
            lambda: _humedad_desde_power(lat, lon, start_date, end_date)
        ),
        generar_sintetico=lambda: _humedad_sintetica(lat, start_date, end_date),
        cache_dir=cache_dir,
    )


POROSIDAD_PCT = 45.0  # porosidad típica de un suelo franco; calibrar localmente


def _humedad_desde_power(lat: float, lon: float, start_date: str, end_date: str) -> pd.DataFrame:
    """Humedad de la zona de raíces real: GWETROOT de NASA POWER (MERRA-2).

    GWETROOT es la fracción de saturación (0-1) del primer metro de suelo; se
    convierte a % volumétrico multiplicando por una porosidad típica. Se marca
    como "nasa_power_gwetroot".
    """
    from piper_agent.data.ingestion.imerg_etl import descargar_power

    power = descargar_power(lat, lon, start_date, end_date, parametros=("GWETROOT",))
    df = pd.DataFrame({
        "date": pd.to_datetime(power["date"]),
        "soil_moisture_vol_pct": (power["GWETROOT"].clip(0, 1) * POROSIDAD_PCT).round(1),
    })
    df.attrs["fuente"] = "nasa_power_gwetroot"
    return df


def _humedad_sintetica(lat: float, start_date: str, end_date: str) -> pd.DataFrame:
    """Humedad diaria estimada según la banda de latitud y la estación."""
    rng = np.random.default_rng(21)
    dias = pd.date_range(start_date, end_date, freq="D")
    abs_lat = abs(lat)
    base = 25.0 if abs_lat > 45 else 20.0 if abs_lat > 20 else 15.0  # % vol.
    doy = dias.dayofyear.to_numpy()
    desfase = 150 if lat >= 0 else 332
    estacional = 1.0 + 0.25 * np.sin(2 * np.pi * (doy - desfase) / 365.0)
    humedad = np.clip(base * estacional * rng.normal(1.0, 0.1, size=len(dias)), 5.0, 45.0)
    return pd.DataFrame({"date": dias, "soil_moisture_vol_pct": np.round(humedad, 1)})


__all__ = ["fetch_smap_moisture", "es_estimado"]
