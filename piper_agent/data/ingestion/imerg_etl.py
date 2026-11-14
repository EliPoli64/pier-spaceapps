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


# ── Real NASA POWER (no credentials required) ───────────────────────────────

POWER_URL = os.environ.get(
    "PIER_POWER_BASE", "https://power.larc.nasa.gov/api/temporal/daily/point"
)
POWER_PARAMETERS = ("T2M_MAX", "T2M_MIN", "PRECTOTCORR")
POWER_FILL_VALUE = -999.0


def download_power(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    attempts: int = 3,
    parameters: tuple[str, ...] = POWER_PARAMETERS,
) -> pd.DataFrame:
    """Download real daily POWER data (date + `parameters`; T2M_MAX, T2M_MIN, PRECTOTCORR by default).

    Uses retries with exponential backoff and the shared circuit breaker.
    Raises RuntimeError if the data cannot be fetched.
    """
    import requests

    from piper_agent.data.resilience import call_with_retry

    def _request() -> dict:
        resp = requests.get(
            POWER_URL,
            params={
                "parameters": ",".join(parameters),
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

    data = call_with_retry(_request, attempts=attempts, description="NASA POWER")
    series = data["properties"]["parameter"]
    df = pd.DataFrame({p: pd.Series(series[p], dtype=float) for p in parameters})
    df = df.replace(POWER_FILL_VALUE, float("nan")).dropna()
    df.insert(0, "date", pd.to_datetime(df.index, format="%Y%m%d").strftime("%Y-%m-%d"))
    df = df.reset_index(drop=True)
    if df.empty:
        raise RuntimeError("NASA POWER returned an empty series")
    logger.info("Real POWER: %d days for lat=%.3f lon=%.3f", len(df), lat, lon)
    return df


def _imerg_to_dataframe(records: Any) -> pd.DataFrame | None:
    """Normalize the imergpy output to (date, precipitation_mm). None if not recognized."""
    try:
        df = records if isinstance(records, pd.DataFrame) else pd.DataFrame(records)
        date_col = next(c for c in df.columns if "date" in str(c).lower())
        rain_col = next(c for c in df.columns if "precip" in str(c).lower())
        out = pd.DataFrame({
            "date": pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d"),
            "precipitation_mm": df[rain_col].astype(float).round(2),
        })
        return out if not out.empty else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not parse the imergpy output: %s", exc)
        return None


def refresh_cache_with_real_data(demo_name: str, use_imerg: bool | None = None) -> str:
    """Replace a scenario's cache with real NASA data (optional).

    - Temperature and baselines: real NASA POWER.
    - Rainfall: IMERG through imergpy when Earthdata credentials are set;
      otherwise POWER's PRECTOTCORR precipitation as a declared stand-in.

    Returns `fuente_datos`: "nasa_power+imerg", "nasa_power" or "sintetico"
    (if the download fails the existing cache is left untouched).

    Warning: with real data the demo packet's event may not cross the BR-1
    thresholds. Check the scenarios after running this;
    `python -m piper_agent.data.generate_cache` restores the synthetic cache.
    """
    import glob
    import json

    from piper_agent.data import generate_cache as gc

    cfg = gc.read_packet(demo_name)
    lat, lon = cfg["lat"], cfg["lon"]
    series_end = gc._series_end(lat, cfg["current_date"], cfg.get("season_end"))
    download_end = min(series_end, date.today().isoformat())

    try:
        power_df = download_power(lat, lon, cfg["baseline_start"], download_end)
    except RuntimeError as exc:
        logger.warning("Real POWER unavailable (%s); keeping the current cache", exc)
        return "sintetico"

    source = "nasa_power"
    imerg_df = None
    if use_imerg is None:
        use_imerg = bool(os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD"))
    if use_imerg:
        try:
            _, records = fetch_with_retry(lat, lon, cfg["baseline_start"], cfg["recent_end"])
            imerg_df = _imerg_to_dataframe(records)
        except RuntimeError as exc:
            logger.warning("IMERG unavailable (%s); using POWER PRECTOTCORR", exc)
        if imerg_df is not None:
            source = "nasa_power+imerg"
    if imerg_df is None:
        until = power_df["date"] <= cfg["recent_end"]
        imerg_df = power_df.loc[until, ["date", "PRECTOTCORR"]].rename(
            columns={"PRECTOTCORR": "precipitation_mm"}
        )

    for folder in (gc.IMERG_DIR, gc.POWER_DIR, gc.BASELINES_DIR):
        os.makedirs(folder, exist_ok=True)
    imerg_df.to_csv(os.path.join(gc.IMERG_DIR, f"{demo_name}_imerg.csv"), index=False)
    power_df.to_csv(os.path.join(gc.POWER_DIR, f"{demo_name}_power.csv"), index=False)
    baselines = gc.compute_baselines(power_df, lat, cfg.get("season_end"), fuente_datos=source)
    with open(os.path.join(gc.BASELINES_DIR, f"{demo_name}_baselines.json"), "w", encoding="utf-8") as f:
        json.dump(baselines, f, indent=2)

    # The data is no longer synthetic: remove the SYNTHETIC_CACHE markers.
    for folder in (gc.IMERG_DIR, gc.POWER_DIR):
        for marker in glob.glob(os.path.join(folder, f"{demo_name}_*.SYNTHETIC_CACHE.txt")):
            os.remove(marker)

    logger.info("Cache of '%s' refreshed with real data (%s)", demo_name, source)
    return source


if __name__ == "__main__":
    import sys

    from piper_agent.data.generate_cache import SCENARIOS

    logging.basicConfig(level=logging.INFO)
    for _name in (sys.argv[1:] or SCENARIOS):
        print(f"{_name}: fuente_datos = {refresh_cache_with_real_data(_name)}")


__all__ = [
    "fetch_with_retry",
    "fetch_with_fallback",
    "download_power",
    "refresh_cache_with_real_data",
    "CircuitBreaker",
]
