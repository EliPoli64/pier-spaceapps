"""Ingesta real para cualquier coordenada, con respaldo silencioso.

`ingerir_punto` devuelve temperatura y lluvia diarias de un punto:

- Modo demo (por defecto, PIER_DEMO_MODE=1): nunca toca la red. Usa el caché
  del escenario demo más cercano o, lejos de todos, una serie sintética para
  esa latitud.
- Ruta de producción (PIER_DEMO_MODE=0): NASA POWER real (sin credenciales) y,
  si hay credenciales de Earthdata, lluvia IMERG vía imergpy. Si algo falla,
  cae al mismo respaldo del modo demo sin lanzar error y lo deja registrado en
  `fuente_datos` y `motivo_respaldo`.
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

DIR_REAL = os.path.join(gc.RAIZ, "data", "cache", "real")
RADIO_DEMO_GRADOS = 0.5
PARAMETROS_REALES = ("T2M_MAX", "T2M_MIN", "PRECTOTCORR", "GWETROOT")


def clave_region(lat: float, lon: float) -> str:
    """Celda de 0.5° que identifica la región (resolución aproximada de POWER)."""
    lat_c = round(lat * 2) / 2
    lon_c = round(lon * 2) / 2
    return f"lat{lat_c:+05.1f}_lon{lon_c:+06.1f}"


def _recortar(df: pd.DataFrame, inicio: str, fin: str) -> pd.DataFrame:
    fechas = pd.to_datetime(df["date"])
    salida = df.loc[(fechas >= inicio) & (fechas <= fin)].copy()
    salida["date"] = pd.to_datetime(salida["date"]).dt.strftime("%Y-%m-%d")
    return salida.reset_index(drop=True)


def _escenario_cercano(lat: float, lon: float) -> str | None:
    """Escenario demo a menos de RADIO_DEMO_GRADOS; prefiere "normal" si hay varios."""
    candidatos = []
    for nombre in cache_loader.ESCENARIOS:
        paquete = gc.leer_paquete(nombre)
        if abs(paquete["lat"] - lat) <= RADIO_DEMO_GRADOS and abs(paquete["lon"] - lon) <= RADIO_DEMO_GRADOS:
            candidatos.append(nombre)
    if not candidatos:
        return None
    return "normal" if "normal" in candidatos else candidatos[0]


def _respaldo(lat: float, lon: float, inicio: str, fin: str, motivo: str | None) -> dict[str, Any]:
    """Datos sin red: caché demo cercano o serie sintética para la latitud."""
    escenario = _escenario_cercano(lat, lon)
    power = lluvia = None
    if escenario:
        power = _recortar(cache_loader.load_power(escenario), inicio, fin)
        lluvia = _recortar(cache_loader.load_imerg(escenario), inicio, fin)
    if power is None or power.empty or lluvia.empty:
        escenario = None
        power = gc.generar_power(fin, inicio, lat, season_end=fin)
        power = _recortar(power, inicio, fin)
        lluvia = power[["date", "PRECTOTCORR"]].rename(columns={"PRECTOTCORR": "precipitation_mm"})
    return {
        "power": power,
        "lluvia": lluvia,
        "fuente_datos": "sintetico",
        "motivo_respaldo": motivo,
        "escenario_demo": escenario,
        "region": clave_region(lat, lon),
    }


def _hay_credenciales_earthdata() -> bool:
    return bool(os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD"))


def ingerir_punto(
    lat: float,
    lon: float,
    inicio: str,
    fin: str,
    demo_mode: bool | None = None,
    usar_imerg: bool | None = None,
    usar_cache: bool = True,
) -> dict[str, Any]:
    """Temperatura y lluvia diarias de un punto entre `inicio` y `fin` (ISO).

    Returns:
        dict con `power` (date, T2M_MAX, T2M_MIN, PRECTOTCORR[, GWETROOT]),
        `lluvia` (date, precipitation_mm), `fuente_datos` ("sintetico",
        "nasa_power" o "nasa_power+imerg"), `motivo_respaldo` (None si no hubo
        respaldo), `escenario_demo` y `region`.
    """
    if demo_mode is None:
        demo_mode = os.environ.get("PIER_DEMO_MODE", "1") == "1"
    if demo_mode:
        return _respaldo(lat, lon, inicio, fin, motivo=None)

    region = clave_region(lat, lon)
    fin_real = min(fin, date.today().isoformat())
    ruta_power = os.path.join(DIR_REAL, f"{region}_{inicio}_{fin_real}_power.csv")
    ruta_lluvia = os.path.join(DIR_REAL, f"{region}_{inicio}_{fin_real}_lluvia.csv")
    ruta_fuente = os.path.join(DIR_REAL, f"{region}_{inicio}_{fin_real}.fuente.txt")

    if usar_cache and all(os.path.exists(r) for r in (ruta_power, ruta_lluvia, ruta_fuente)):
        with open(ruta_fuente, encoding="utf-8") as f:
            fuente = f.read().strip()
        return {
            "power": pd.read_csv(ruta_power), "lluvia": pd.read_csv(ruta_lluvia),
            "fuente_datos": fuente, "motivo_respaldo": None,
            "escenario_demo": None, "region": region,
        }

    try:
        power = imerg_etl.descargar_power(lat, lon, inicio, fin_real, parametros=PARAMETROS_REALES)
    except RuntimeError as exc:
        logger.warning("Ingesta real no disponible (%s); respaldo sintético", exc)
        return _respaldo(lat, lon, inicio, fin, motivo=f"NASA POWER no disponible: {exc}")

    fuente = "nasa_power"
    lluvia = None
    if usar_imerg is None:
        usar_imerg = _hay_credenciales_earthdata()
    if usar_imerg:
        try:
            _, registros = imerg_etl.fetch_with_retry(lat, lon, inicio, fin_real)
            lluvia = imerg_etl._imerg_a_dataframe(registros)
        except RuntimeError as exc:
            logger.warning("IMERG no disponible (%s); se usa PRECTOTCORR de POWER", exc)
        if lluvia is not None:
            fuente = "nasa_power+imerg"
    if lluvia is None:
        lluvia = power[["date", "PRECTOTCORR"]].rename(columns={"PRECTOTCORR": "precipitation_mm"})

    try:
        os.makedirs(DIR_REAL, exist_ok=True)
        power.to_csv(ruta_power, index=False)
        lluvia.to_csv(ruta_lluvia, index=False)
        with open(ruta_fuente, "w", encoding="utf-8") as f:
            f.write(fuente)
    except OSError as exc:
        logger.warning("No se pudo guardar el caché real: %s", exc)

    return {
        "power": power, "lluvia": lluvia.reset_index(drop=True),
        "fuente_datos": fuente, "motivo_respaldo": None,
        "escenario_demo": None, "region": region,
    }


__all__ = ["ingerir_punto", "clave_region", "PARAMETROS_REALES"]
