"""Evapotranspiración real (ETa) de OpenET.

Caché primero. Fuera del modo demo se consulta OpenET si hay
PIER_OPENET_API_KEY; sin clave se calcula ET de referencia (Hargreaves) con
temperaturas reales de NASA POWER. Si nada responde, serie estimada.
"""
from __future__ import annotations

import logging
import os

import numpy as np
import pandas as pd
import requests

from piper_agent.data._series_cache import (
    es_estimado,
    obtener_serie,
    radiacion_extraterrestre_mm,
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
) -> pd.DataFrame:
    """ETa diaria en mm.

    Returns:
        DataFrame con columnas [date, eta_mm]. `df.attrs["fuente"]` vale
        "cache", "en_vivo" o "estimado".
    """
    def _en_vivo() -> pd.DataFrame | None:
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
        registros = resp.json().get("data", [])
        if not registros:
            return None
        df = pd.DataFrame(registros)
        df["date"] = pd.to_datetime(df["date"])
        return df.rename(columns={"eta": "eta_mm"})[["date", "eta_mm"]]

    return obtener_serie(
        "openet", "eta_mm", lat, lon, start_date, end_date,
        pedir_en_vivo=_en_vivo if OPENET_API_KEY else (
            lambda: _et0_desde_power(lat, lon, start_date, end_date)
        ),
        generar_sintetico=lambda: _eta_sintetica(lat, start_date, end_date),
        cache_dir=cache_dir,
    )


def _et0_desde_power(lat: float, lon: float, start_date: str, end_date: str) -> pd.DataFrame:
    """ET de referencia (Hargreaves, FAO-56) con temperaturas reales de NASA POWER.

    Es ET0, no ETa: sirve como cota superior de la evapotranspiración real
    cuando no hay clave de OpenET. Se marca como "nasa_power_hargreaves".
    """
    from piper_agent.data.ingestion.imerg_etl import descargar_power

    power = descargar_power(lat, lon, start_date, end_date, parametros=("T2M_MAX", "T2M_MIN"))
    fechas = pd.to_datetime(power["date"])
    tmax, tmin = power["T2M_MAX"].to_numpy(), power["T2M_MIN"].to_numpy()
    ra = radiacion_extraterrestre_mm(lat, fechas.dt.dayofyear.to_numpy())
    et0 = 0.0023 * ((tmax + tmin) / 2 + 17.8) * np.sqrt(np.clip(tmax - tmin, 0, None)) * ra
    df = pd.DataFrame({"date": fechas, "eta_mm": np.round(np.clip(et0, 0, None), 2)})
    df.attrs["fuente"] = "nasa_power_hargreaves"
    return df


def _eta_sintetica(lat: float, start_date: str, end_date: str) -> pd.DataFrame:
    """ETa diaria estimada según la banda de latitud y la estación."""
    rng = np.random.default_rng(11)
    dias = pd.date_range(start_date, end_date, freq="D")
    abs_lat = abs(lat)
    base = 2.0 if abs_lat > 45 else 4.0 if abs_lat > 20 else 5.5  # mm/día
    doy = dias.dayofyear.to_numpy()
    desfase = 80 if lat >= 0 else 262  # verano invertido en el hemisferio sur
    estacional = 1.0 + 0.3 * np.sin(2 * np.pi * (doy - desfase) / 365.0)
    eta = np.clip(base * estacional * rng.normal(1.0, 0.15, size=len(dias)), 0.0, None)
    return pd.DataFrame({"date": dias, "eta_mm": np.round(eta, 2)})


__all__ = ["fetch_openet_eta", "es_estimado"]
