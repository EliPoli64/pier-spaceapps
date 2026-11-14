"""Reintentos con espera exponencial y cortacircuito para llamadas en vivo.

Lo usan los módulos de datos cuando PIER_DEMO_MODE=0 (ruta de producción).
En modo demo nada de esto se ejecuta: todo sale del caché.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable

logger = logging.getLogger("pier.data.resiliencia")

UMBRAL_FALLOS = int(os.environ.get("PIER_CB_THRESHOLD", "3"))
SEGUNDOS_REINICIO = int(os.environ.get("PIER_CB_RESET", "300"))


class CortaCircuito:
    """Tras `umbral` fallos seguidos se abre y bloquea llamadas durante `segundos_reinicio`."""

    def __init__(self, nombre: str = "en_vivo", umbral: int = UMBRAL_FALLOS,
                 segundos_reinicio: int = SEGUNDOS_REINICIO):
        self.nombre = nombre
        self.umbral = umbral
        self.segundos_reinicio = segundos_reinicio
        self.fallos = 0
        self.abierto_desde: float | None = None

    def registrar_fallo(self, motivo: str = "") -> None:
        self.fallos += 1
        if self.fallos >= self.umbral and self.abierto_desde is None:
            self.abierto_desde = time.time()
            logger.warning(
                "Cortacircuito '%s' ABIERTO tras %d fallos seguidos (%s); se usa caché sintético",
                self.nombre, self.fallos, motivo,
            )

    def registrar_exito(self) -> None:
        if self.fallos or self.abierto_desde is not None:
            logger.info("Cortacircuito '%s' CERRADO: la fuente en vivo respondió", self.nombre)
        self.fallos = 0
        self.abierto_desde = None

    def esta_abierto(self) -> bool:
        if self.abierto_desde is None:
            return False
        if time.time() - self.abierto_desde > self.segundos_reinicio:
            # Semiabierto: se permite una llamada de prueba.
            self.abierto_desde = None
            self.fallos = 0
            return False
        return True


# Cortacircuito compartido por todas las fuentes en vivo de PIER.
cortacircuito_en_vivo = CortaCircuito()


def llamar_con_reintentos(
    funcion: Callable[[], Any],
    intentos: int = 3,
    base_espera: float = 2.0,
    cortacircuito: CortaCircuito | None = None,
    descripcion: str = "llamada en vivo",
    dormir: Callable[[float], None] | None = None,
) -> Any:
    """Ejecuta `funcion` hasta `intentos` veces con espera exponencial.

    Lanza RuntimeError si el cortacircuito está abierto o si fallan todos los intentos.
    """
    cc = cortacircuito if cortacircuito is not None else cortacircuito_en_vivo
    if cc.esta_abierto():
        raise RuntimeError(f"Cortacircuito '{cc.nombre}' abierto; se omite {descripcion}")

    ultimo_error: Exception | None = None
    for intento in range(1, intentos + 1):
        try:
            resultado = funcion()
            cc.registrar_exito()
            return resultado
        except Exception as exc:  # noqa: BLE001
            ultimo_error = exc
            logger.warning("%s: intento %d/%d falló: %s", descripcion, intento, intentos, exc)
            if intento < intentos:
                (dormir or time.sleep)(base_espera ** intento)

    cc.registrar_fallo(str(ultimo_error))
    raise RuntimeError(f"{descripcion} falló tras {intentos} intentos: {ultimo_error}") from ultimo_error


__all__ = ["CortaCircuito", "cortacircuito_en_vivo", "llamar_con_reintentos"]
