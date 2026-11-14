"""Calibración local: observaciones del agricultor por coordenada.

El agricultor puede reportar el rendimiento obtenido o el daño observado. Se
guardan en un archivo personal por celda de 0.5° para que corridas futuras se
corrijan contra la realidad local y no solo contra la climatología global.

Los archivos viven en `data/cache/calibracion/` (fuera de git: son datos
personales). Se puede cambiar con PIER_CALIBRACION_DIR.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from statistics import median
from typing import Any

from piper_agent.data import generate_cache as gc
from piper_agent.data.ingestion.pipeline import clave_region

logger = logging.getLogger("pier.data.calibracion")

VERSION_CALIBRACION = "1"
MIN_OBSERVACIONES = 3
FACTOR_MIN, FACTOR_MAX = 0.5, 1.5


def _dir_calibracion() -> str:
    return os.environ.get(
        "PIER_CALIBRACION_DIR", os.path.join(gc.RAIZ, "data", "cache", "calibracion")
    )


def ruta_calibracion(lat: float, lon: float) -> str:
    return os.path.join(_dir_calibracion(), f"{clave_region(lat, lon)}.json")


def cargar_observaciones(lat: float, lon: float) -> list[dict[str, Any]]:
    """Observaciones guardadas para la celda de (lat, lon). Lista vacía si no hay."""
    ruta = ruta_calibracion(lat, lon)
    if not os.path.exists(ruta):
        return []
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f).get("observaciones", [])
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Archivo de calibración ilegible (%s): %s", ruta, exc)
        return []


def registrar_observacion(
    lat: float,
    lon: float,
    fecha: str,
    cultivo: str,
    rendimiento_observado_t_ha: float | None = None,
    rendimiento_esperado_t_ha: float | None = None,
    dano_pct: float | None = None,
    evento: str | None = None,
    confianza_predicha: float | None = None,
    cultivo_maduro: bool | None = None,
    nota: str | None = None,
) -> dict[str, Any]:
    """Guarda una observación del agricultor y la devuelve.

    Args:
        fecha: fecha ISO de la observación.
        rendimiento_observado_t_ha / rendimiento_esperado_t_ha: para el factor de corrección.
        dano_pct: daño observado, de 0 a 100.
        evento: "flood" | "drought" | "none" que PIER había detectado.
        confianza_predicha: confianza que PIER reportó en esa corrida (0-1).
        cultivo_maduro: si el cultivo de rescate llegó a madurar.
        nota: texto libre.
    """
    if rendimiento_observado_t_ha is not None and rendimiento_observado_t_ha < 0:
        raise ValueError("El rendimiento observado no puede ser negativo")
    if dano_pct is not None and not 0 <= dano_pct <= 100:
        raise ValueError("dano_pct debe estar entre 0 y 100")
    if confianza_predicha is not None and not 0 <= confianza_predicha <= 1:
        raise ValueError("confianza_predicha debe estar entre 0 y 1")
    datetime.fromisoformat(fecha)  # valida el formato

    observacion = {
        "fecha": fecha,
        "cultivo": cultivo,
        "rendimiento_observado_t_ha": rendimiento_observado_t_ha,
        "rendimiento_esperado_t_ha": rendimiento_esperado_t_ha,
        "dano_pct": dano_pct,
        "evento": evento,
        "confianza_predicha": confianza_predicha,
        "cultivo_maduro": cultivo_maduro,
        "nota": nota,
        "registrado": datetime.now(timezone.utc).isoformat(),
    }
    observaciones = cargar_observaciones(lat, lon) + [observacion]
    os.makedirs(_dir_calibracion(), exist_ok=True)
    with open(ruta_calibracion(lat, lon), "w", encoding="utf-8") as f:
        json.dump(
            {"version": VERSION_CALIBRACION, "region": clave_region(lat, lon),
             "observaciones": observaciones},
            f, indent=2, ensure_ascii=False,
        )
    return observacion


def factor_correccion(lat: float, lon: float, cultivo: str) -> dict[str, Any]:
    """Factor local de rendimiento = mediana(observado / esperado), acotado a [0.5, 1.5].

    Con menos de MIN_OBSERVACIONES devuelve factor 1.0 y `calibrado=False`.
    """
    razones = [
        o["rendimiento_observado_t_ha"] / o["rendimiento_esperado_t_ha"]
        for o in cargar_observaciones(lat, lon)
        if o.get("cultivo") == cultivo
        and o.get("rendimiento_observado_t_ha") is not None
        and o.get("rendimiento_esperado_t_ha")
    ]
    if len(razones) < MIN_OBSERVACIONES:
        return {"factor": 1.0, "calibrado": False, "n_observaciones": len(razones)}
    factor = min(FACTOR_MAX, max(FACTOR_MIN, median(razones)))
    return {"factor": round(factor, 3), "calibrado": True, "n_observaciones": len(razones)}


def historial_validacion(lat: float, lon: float) -> list[dict[str, Any]]:
    """Observaciones en el formato que espera `calibrate_confidence`.

    Cada elemento: {event_type, predicted_confidence, actual_outcome}. Solo se
    incluyen las observaciones que traen evento, confianza y resultado.
    """
    return [
        {
            "event_type": o["evento"],
            "predicted_confidence": o["confianza_predicha"],
            "actual_outcome": bool(o["cultivo_maduro"]),
        }
        for o in cargar_observaciones(lat, lon)
        if o.get("evento") and o.get("confianza_predicha") is not None
        and o.get("cultivo_maduro") is not None
    ]


__all__ = [
    "registrar_observacion", "cargar_observaciones", "factor_correccion",
    "historial_validacion", "ruta_calibracion",
]
