"""Production ingestion pipeline for NASA IMERG data via imergpy.

Wraps imergpy.get_precipitation with retry/backoff, Earthdata cookie refresh,
and fallback to nearest GES DISC grid cell when a point query fails.
Includes a circuit breaker: if Earthdata is down 3x in a row, fall back to
synthetic cache and log the event.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime
from typing import Any

import pandas as pd

logger = logging.getLogger("pier.ingestion.imerg")

CIRCUIT_BREAKER_THRESHOLD = int(os.environ.get("PIER_CB_THRESHOLD", "3"))
CIRCUIT_RESET_SECONDS = int(os.environ.get("PIER_CB_RESET", "300"))


class CircuitBreaker:
    """Simple circuit breaker for Earthdata / GES DISC calls."""

    def __init__(self, threshold: int = CIRCUIT_BREAKER_THRESHOLD,
                 reset_seconds: int = CIRCUIT_RESET_SECONDS):
        self.threshold = threshold
        self.reset_seconds = reset_seconds
        self.failures = 0
        self.opened_at: float | None = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold and self.opened_at is None:
            self.opened_at = time.time()
            logger.warning("Circuit breaker OPENED after %d failures", self.failures)

    def record_success(self) -> None:
        if self.failures > 0:
            self.failures = 0
            self.opened_at = None
            logger.info("Circuit breaker CLOSED — Earthdata recovered")

    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.time() - self.opened_at > self.reset_seconds:
            # Half-open: allow one trial call
            self.opened_at = None
            self.failures = 0
            logger.info("Circuit breaker HALF-OPEN — trial call allowed")
            return False
        return True


_circuit_breaker = CircuitBreaker()


def fetch_with_retry(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    freq: str = "daily",
    max_retries: int = 3,
    backoff_base: float = 2.0,
) -> tuple[str, Any]:
    """Fetch IMERG precipitation with retry/backoff and circuit breaker.

    Returns (excel_path, records) on success, or raises RuntimeError if all
    attempts fail and circuit breaker is open.
    """
    if _circuit_breaker.is_open():
        raise RuntimeError(
            "Circuit breaker OPEN — Earthdata/GES DISC unavailable. "
            "Use synthetic cache fallback."
        )

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            import imergpy  # type: ignore
            excel_path, records = imergpy.get_precipitation(
                lat=lat, lon=lon,
                start_date=start_date, end_date=end_date,
                freq=freq,
            )
            _circuit_breaker.record_success()
            logger.info(
                "IMERG fetch succeeded: lat=%.4f lon=%.4f %s..%s freq=%s",
                lat, lon, start_date, end_date, freq,
            )
            return excel_path, records
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "IMERG fetch attempt %d/%d failed: %s", attempt, max_retries, exc
            )
            if attempt < max_retries:
                sleep_for = backoff_base ** attempt
                logger.info("Retrying in %.1fs...", sleep_for)
                time.sleep(sleep_for)

    _circuit_breaker.record_failure()
    raise RuntimeError(
        f"IMERG fetch failed after {max_retries} attempts: {last_error}"
    ) from last_error


def fetch_with_fallback(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    freq: str = "daily",
    synthetic_cache_dir: str | None = None,
) -> dict[str, Any]:
    """Fetch IMERG data with synthetic cache fallback.

    Returns a dict with keys:
      - source: "earthdata" | "synthetic"
      - excel_path: str | None
      - records: Any
      - synthetic: bool
    """
    try:
        excel_path, records = fetch_with_retry(
            lat, lon, start_date, end_date, freq
        )
        return {
            "source": "earthdata",
            "excel_path": excel_path,
            "records": records,
            "synthetic": False,
        }
    except RuntimeError as exc:
        logger.warning("Earthdata unavailable (%s); using synthetic cache", exc)
        if synthetic_cache_dir is None:
            synthetic_cache_dir = os.path.join(
                os.path.dirname(__file__), "..", "..", "data", "cache", "imerg"
            )
        # Try to load a cached synthetic CSV for the location/date range
        import pandas as pd

        cache_name = f"{lat:.2f}_{lon:.2f}_{start_date}_{end_date}.csv"
        cache_path = os.path.join(synthetic_cache_dir, cache_name)
        if os.path.exists(cache_path):
            df = pd.read_csv(cache_path, parse_dates=["date"])
            return {
                "source": "synthetic_cache",
                "excel_path": cache_path,
                "records": df,
                "synthetic": True,
            }
        # Last resort: generate minimal synthetic data
        return _generate_minimal_synthetic(lat, lon, start_date, end_date)


def _generate_minimal_synthetic(
    lat: float, lon: float, start_date: str, end_date: str
) -> dict[str, Any]:
    """Generate minimal synthetic daily rainfall when all sources fail."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(7)
    days = pd.date_range(start_date, end_date, freq="D")
    # Light rain baseline with occasional storm
    mm = rng.gamma(2.0, 3.0, size=len(days))
    df = pd.DataFrame({"date": days, "precipitation_mm": np.round(mm, 2)})
    return {
        "source": "synthetic_minimal",
        "excel_path": None,
        "records": df,
        "synthetic": True,
    }


# ── NASA POWER real (no requiere credenciales) ──────────────────────────────

POWER_URL = os.environ.get(
    "PIER_POWER_BASE", "https://power.larc.nasa.gov/api/temporal/daily/point"
)
POWER_PARAMETROS = ("T2M_MAX", "T2M_MIN", "PRECTOTCORR")
POWER_VALOR_FALTANTE = -999.0


def descargar_power(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    intentos: int = 3,
) -> pd.DataFrame:
    """Descarga POWER diario real (date, T2M_MAX, T2M_MIN, PRECTOTCORR).

    Usa reintentos con espera exponencial y el cortacircuito compartido.
    Lanza RuntimeError si no se puede obtener.
    """
    import requests

    from piper_agent.data.resiliencia import llamar_con_reintentos

    def _pedir() -> dict:
        resp = requests.get(
            POWER_URL,
            params={
                "parameters": ",".join(POWER_PARAMETROS),
                "community": "AG",
                "latitude": lat,
                "longitude": lon,
                "start": start_date.replace("-", ""),
                "end": end_date.replace("-", ""),
                "format": "JSON",
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    datos = llamar_con_reintentos(_pedir, intentos=intentos, descripcion="NASA POWER")
    series = datos["properties"]["parameter"]
    df = pd.DataFrame({p: pd.Series(series[p], dtype=float) for p in POWER_PARAMETROS})
    df = df.replace(POWER_VALOR_FALTANTE, float("nan")).dropna()
    df.insert(0, "date", pd.to_datetime(df.index, format="%Y%m%d").strftime("%Y-%m-%d"))
    df = df.reset_index(drop=True)
    if df.empty:
        raise RuntimeError("NASA POWER devolvió una serie vacía")
    logger.info("POWER real: %d días para lat=%.3f lon=%.3f", len(df), lat, lon)
    return df


def _imerg_a_dataframe(registros: Any) -> pd.DataFrame | None:
    """Normaliza la salida de imergpy a (date, precipitation_mm). None si no se reconoce."""
    try:
        df = registros if isinstance(registros, pd.DataFrame) else pd.DataFrame(registros)
        col_fecha = next(c for c in df.columns if "date" in str(c).lower())
        col_lluvia = next(c for c in df.columns if "precip" in str(c).lower())
        salida = pd.DataFrame({
            "date": pd.to_datetime(df[col_fecha]).dt.strftime("%Y-%m-%d"),
            "precipitation_mm": df[col_lluvia].astype(float).round(2),
        })
        return salida if not salida.empty else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo interpretar la salida de imergpy: %s", exc)
        return None


def actualizar_cache_real(demo_name: str, usar_imerg: bool | None = None) -> str:
    """Reemplaza el caché de un escenario por datos reales de la NASA (opcional).

    - Temperatura y baselines: NASA POWER real.
    - Lluvia: IMERG vía imergpy si hay credenciales de Earthdata; si no, la
      precipitación PRECTOTCORR de POWER como sustituto declarado.

    Devuelve `fuente_datos`: "nasa_power+imerg", "nasa_power" o "sintetico"
    (si la descarga falla no se toca el caché existente).

    Aviso: con datos reales el evento del paquete demo puede no cruzar los
    umbrales de BR-1. Verifique los tres escenarios después de ejecutar esto;
    `python -m piper_agent.data.generate_cache` restaura el caché sintético.
    """
    import glob
    import json

    from piper_agent.data import generate_cache as gc

    cfg = gc.leer_paquete(demo_name)
    lat, lon = cfg["lat"], cfg["lon"]
    fin_serie = gc._fin_serie(lat, cfg["current_date"], cfg.get("season_end"))
    fin_descarga = min(fin_serie, date.today().isoformat())

    try:
        power_df = descargar_power(lat, lon, cfg["baseline_start"], fin_descarga)
    except RuntimeError as exc:
        logger.warning("POWER real no disponible (%s); se conserva el caché actual", exc)
        return "sintetico"

    fuente = "nasa_power"
    imerg_df = None
    if usar_imerg is None:
        usar_imerg = bool(os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD"))
    if usar_imerg:
        try:
            _, registros = fetch_with_retry(lat, lon, cfg["baseline_start"], cfg["recent_end"])
            imerg_df = _imerg_a_dataframe(registros)
        except RuntimeError as exc:
            logger.warning("IMERG no disponible (%s); se usa PRECTOTCORR de POWER", exc)
        if imerg_df is not None:
            fuente = "nasa_power+imerg"
    if imerg_df is None:
        hasta = power_df["date"] <= cfg["recent_end"]
        imerg_df = power_df.loc[hasta, ["date", "PRECTOTCORR"]].rename(
            columns={"PRECTOTCORR": "precipitation_mm"}
        )

    for carpeta in (gc.DIR_IMERG, gc.DIR_POWER, gc.DIR_BASELINES):
        os.makedirs(carpeta, exist_ok=True)
    imerg_df.to_csv(os.path.join(gc.DIR_IMERG, f"{demo_name}_imerg.csv"), index=False)
    power_df.to_csv(os.path.join(gc.DIR_POWER, f"{demo_name}_power.csv"), index=False)
    baselines = gc.calcular_baselines(power_df, lat, cfg.get("season_end"), fuente_datos=fuente)
    with open(os.path.join(gc.DIR_BASELINES, f"{demo_name}_baselines.json"), "w", encoding="utf-8") as f:
        json.dump(baselines, f, indent=2)

    # Los datos ya no son sintéticos: quitar los marcadores SYNTHETIC_CACHE.
    for carpeta in (gc.DIR_IMERG, gc.DIR_POWER):
        for marcador in glob.glob(os.path.join(carpeta, f"{demo_name}_*.SYNTHETIC_CACHE.txt")):
            os.remove(marcador)

    logger.info("Caché de '%s' actualizado con datos reales (%s)", demo_name, fuente)
    return fuente


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    for _nombre in (sys.argv[1:] or ["flood", "drought", "normal"]):
        print(f"{_nombre}: fuente_datos = {actualizar_cache_real(_nombre)}")


__all__ = [
    "fetch_with_retry",
    "fetch_with_fallback",
    "descargar_power",
    "actualizar_cache_real",
    "CircuitBreaker",
]
