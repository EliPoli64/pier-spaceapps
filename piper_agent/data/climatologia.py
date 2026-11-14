"""Almacén versionado de climatologías por región.

Cada región (celda de 0.5°) guarda percentiles mensuales de lluvia y
temperatura en `data/baselines/regiones/{region}_v{VERSION}.json`. Con eso
cualquier corrida puede explicar si un valor es normal, extremo o faltante.

La versión cambia cuando cambia el método de cálculo; el archivo registra
además la fuente de datos y el periodo usados, para poder reproducir un
resultado.
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import date, datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from piper_agent.data import generate_cache as gc
from piper_agent.data.ingestion.pipeline import clave_region, ingerir_punto

logger = logging.getLogger("pier.data.climatologia")

VERSION_BASELINES = "1"
DIR_REGIONES = os.path.join(gc.DIR_BASELINES, "regiones")
ANIOS_CLIMATOLOGIA = 10
MIN_DIAS_POR_MES = 60  # menos que esto: el mes se considera sin datos suficientes

# variable -> (clave del percentil bajo, clave del percentil alto, unidad)
VARIABLES = {
    "lluvia_3d": ("p05", "p95", "mm en 3 días"),
    "lluvia_30d": ("p10", "p90", "mm en 30 días"),
    "tmax": ("p05", "p95", "°C"),
    "tmin": ("p05", "p95", "°C"),
}


def _percentiles(serie: pd.Series) -> dict[str, float]:
    valores = serie.dropna().to_numpy()
    return {
        f"p{p:02d}": round(float(np.percentile(valores, p)), 2)
        for p in (5, 10, 50, 90, 95)
    }


def construir_climatologia(
    power_df: pd.DataFrame,
    lluvia_df: pd.DataFrame,
    lat: float,
    lon: float,
    fuente_datos: str,
) -> dict[str, Any]:
    """Calcula percentiles mensuales de lluvia acumulada y temperatura."""
    power = power_df.copy()
    power["date"] = pd.to_datetime(power["date"])
    lluvia = lluvia_df.copy()
    lluvia["date"] = pd.to_datetime(lluvia["date"])
    lluvia = lluvia.sort_values("date")
    lluvia["lluvia_3d"] = lluvia["precipitation_mm"].rolling(3, min_periods=3).sum()
    lluvia["lluvia_30d"] = lluvia["precipitation_mm"].rolling(30, min_periods=30).sum()

    meses: dict[str, Any] = {}
    for mes in range(1, 13):
        p_mes = power[power["date"].dt.month == mes]
        l_mes = lluvia[lluvia["date"].dt.month == mes]
        if len(p_mes) < MIN_DIAS_POR_MES or l_mes["lluvia_30d"].notna().sum() < MIN_DIAS_POR_MES:
            continue
        meses[str(mes)] = {
            "n_dias": int(len(p_mes)),
            "lluvia_3d": _percentiles(l_mes["lluvia_3d"]),
            "lluvia_30d": _percentiles(l_mes["lluvia_30d"]),
            "tmax": _percentiles(p_mes["T2M_MAX"]),
            "tmin": _percentiles(p_mes["T2M_MIN"]),
        }

    helada = None if gc.es_tropical(lat) else gc._primera_helada_otono(
        power.assign(date=power["date"].dt.strftime("%Y-%m-%d")), lat
    )
    return {
        "version": VERSION_BASELINES,
        "region": clave_region(lat, lon),
        "lat": lat,
        "lon": lon,
        "fuente_datos": fuente_datos,
        "periodo": {
            "inicio": str(power["date"].min().date()),
            "fin": str(power["date"].max().date()),
        },
        "creado": datetime.now(timezone.utc).isoformat(),
        "tropical": gc.es_tropical(lat),
        "primera_helada_otono": helada,
        "meses": meses,
        "nota": "percentiles mensuales; valores típicos de la celda, requieren calibración local",
    }


def ruta_climatologia(lat: float, lon: float, version: str = VERSION_BASELINES) -> str:
    return os.path.join(DIR_REGIONES, f"{clave_region(lat, lon)}_v{version}.json")


def guardar_climatologia(climatologia: dict[str, Any]) -> str:
    os.makedirs(DIR_REGIONES, exist_ok=True)
    ruta = ruta_climatologia(climatologia["lat"], climatologia["lon"], climatologia["version"])
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(climatologia, f, indent=2, ensure_ascii=False)
    return ruta


def cargar_climatologia(lat: float, lon: float, version: str = VERSION_BASELINES) -> dict | None:
    ruta = ruta_climatologia(lat, lon, version)
    if not os.path.exists(ruta):
        return None
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def obtener_climatologia(
    lat: float,
    lon: float,
    hasta: str | None = None,
    demo_mode: bool | None = None,
) -> dict[str, Any]:
    """Climatología de la región: la guardada si existe y sirve; si no, se calcula.

    Una climatología sintética guardada se recalcula cuando se pide por la ruta
    de producción, para no dejar datos sintéticos donde ya puede haber reales.
    """
    if demo_mode is None:
        demo_mode = os.environ.get("PIER_DEMO_MODE", "1") == "1"
    guardada = cargar_climatologia(lat, lon)
    if guardada and (demo_mode or guardada.get("fuente_datos") != "sintetico"):
        return guardada

    fin = date.fromisoformat(hasta) if hasta else date.today()
    inicio = fin.replace(year=fin.year - ANIOS_CLIMATOLOGIA, day=min(fin.day, 28))
    datos = ingerir_punto(lat, lon, inicio.isoformat(), fin.isoformat(), demo_mode=demo_mode)
    climatologia = construir_climatologia(
        datos["power"], datos["lluvia"], lat, lon, datos["fuente_datos"]
    )
    guardar_climatologia(climatologia)
    return climatologia


def clasificar_valor(
    climatologia: dict[str, Any] | None,
    variable: str,
    valor: float | None,
    fecha: str,
) -> dict[str, Any]:
    """Dice si `valor` es normal, extremo o faltante para ese mes y región.

    Returns:
        dict con `estado` ("normal" | "extremo" | "faltante"), `direccion`
        ("alto" | "bajo" | None), los umbrales usados y una `explicacion`.
    """
    if variable not in VARIABLES:
        raise ValueError(f"Variable desconocida: {variable}. Opciones: {sorted(VARIABLES)}")
    clave_bajo, clave_alto, unidad = VARIABLES[variable]
    mes = str(date.fromisoformat(fecha[:10]).month)
    base = {"variable": variable, "valor": valor, "mes": int(mes), "direccion": None}

    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return {**base, "estado": "faltante", "explicacion": f"Sin dato de {variable} para {fecha}."}
    stats = ((climatologia or {}).get("meses") or {}).get(mes, {}).get(variable)
    if not stats:
        return {**base, "estado": "faltante",
                "explicacion": f"Sin climatología suficiente de {variable} para el mes {mes}."}

    bajo, alto, mediana = stats[clave_bajo], stats[clave_alto], stats["p50"]
    resultado = {
        **base, "umbral_bajo": bajo, "umbral_alto": alto, "mediana": mediana,
        "fuente_datos": climatologia.get("fuente_datos"), "version": climatologia.get("version"),
    }
    rango = f"rango habitual del mes: {bajo}–{alto} {unidad}, mediana {mediana}"
    if valor > alto:
        return {**resultado, "estado": "extremo", "direccion": "alto",
                "explicacion": f"{variable} = {valor:.1f}: por encima de lo normal ({rango})."}
    if valor < bajo:
        return {**resultado, "estado": "extremo", "direccion": "bajo",
                "explicacion": f"{variable} = {valor:.1f}: por debajo de lo normal ({rango})."}
    return {**resultado, "estado": "normal",
            "explicacion": f"{variable} = {valor:.1f}: dentro de lo normal ({rango})."}


__all__ = [
    "VERSION_BASELINES", "construir_climatologia", "guardar_climatologia",
    "cargar_climatologia", "obtener_climatologia", "clasificar_valor",
]
