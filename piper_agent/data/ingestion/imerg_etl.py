"""Production ingestion pipeline for NASA IMERG data via imergpy.

Wraps imergpy.get_precipitation with retry/backoff, Earthdata cookie refresh,
and fallback to nearest GES DISC grid cell when a point query fails.
Includes a circuit breaker: if Earthdata is down 3x in a row, fall back to
synthetic cache and log the event.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlparse

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


def earthdata_status() -> dict[str, Any]:
    """Whether the IMERG path can be attempted, and why not when it cannot.

    Never raises and never reveals the credentials. Keys: `credentials_set`,
    `imergpy_installed`, `circuit_open`, `available`, `reason` (None when available).
    """
    import importlib.util

    credentials_set = bool(
        os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD")
    )
    imergpy_installed = importlib.util.find_spec("imergpy") is not None
    circuit_open = _circuit_breaker.is_open()
    if not credentials_set:
        reason = "Earthdata credentials not set (EARTHDATA_USERNAME / EARTHDATA_PASSWORD)"
    elif not imergpy_installed:
        reason = "imergpy is not installed"
    elif circuit_open:
        reason = "Earthdata circuit breaker is open after repeated failures"
    else:
        reason = None
    return {
        "credentials_set": credentials_set,
        "imergpy_installed": imergpy_installed,
        "circuit_open": circuit_open,
        "available": reason is None,
        "reason": reason,
    }


def _format_imerg_datetime(value: str) -> str:
    """Normalize ISO dates/datetimes to a format imergpy accepts (YYYY-MM[-DD[ HH:MM]])."""
    text = str(value).strip().replace("T", " ")
    if len(text) > 16:
        text = text[:16]
    return text


_AUTH_ERROR_MARKERS = (
    "web page",
    "earthdata",
    "access was denied",
    "authorized",
    "unauthorized",
    "forbidden",
    "401",
    "403",
)


def _is_auth_error(exc: Exception) -> bool:
    """True when an IMERG error indicates Earthdata auth or GES DISC authorization failure."""
    if type(exc).__name__ == "DownloadAuthError":
        return True
    msg = str(exc).lower()
    return any(marker in msg for marker in _AUTH_ERROR_MARKERS)


def _probe_earthdata_access(
    imergpy_mod: Any,
    lat: float,
    lon: float,
    start_dt: str,
    end_dt: str,
    username: str,
    password: str,
    run_type: str,
    freq: str,
) -> None:
    """Test a single IMERG granule before running a multi-day loop.

    imergpy.get_precipitation catches per-day DownloadError and continues
    looping across every day in the range, which would make dozens or hundreds
    of slow HTTP requests if Earthdata login or GES DISC authorization fails.
    """
    downloader_cls = getattr(
        getattr(imergpy_mod, "downloader", None), "EarthdataDownloader", None
    )
    if downloader_cls is None:
        return

    start_d = pd.to_datetime(start_dt).to_pydatetime()
    end_d = pd.to_datetime(end_dt).to_pydatetime()
    if (end_d - start_d).days <= 1:
        return

    probe_d = max(start_d, end_d - timedelta(days=2))
    dl = downloader_cls(username, password, timeout=15, retries=1)
    fd, tmp_nc = tempfile.mkstemp(suffix=".nc4")
    os.close(fd)
    try:
        dl.download_granule(lat, lon, probe_d, tmp_nc, run_type=run_type, freq=freq)
    except Exception as exc:  # noqa: BLE001
        if _is_auth_error(exc):
            raise
        # A 404 on one probe date ("File not available") is not an auth failure.
    finally:
        if os.path.exists(tmp_nc):
            os.remove(tmp_nc)


CMR_GRANULES_URL = os.environ.get(
    "PIER_CMR_GRANULES_URL",
    "https://cmr.earthdata.nasa.gov/search/granules.json",
)

_IMERG_SHORTNAMES = {
    ("daily", "early"): "GPM_3IMERGDE",
    ("daily", "late"): "GPM_3IMERGDL",
    ("daily", "final"): "GPM_3IMERGDF",
    ("hhr", "early"): "GPM_3IMERGHHE",
    ("hhr", "late"): "GPM_3IMERGHHL",
    ("hhr", "final"): "GPM_3IMERGHH",
    ("monthly", "final"): "GPM_3IMERGM",
}


def _extract_cmr_data_url(entry: dict[str, Any]) -> str | None:
    """Return the HTTPS data granule link from a CMR granule entry."""
    links = entry.get("links") or []
    for link in links:
        href = str(link.get("href") or "")
        rel = str(link.get("rel") or "")
        if (
            href.startswith("https://")
            and rel.endswith("data#")
            and not href.endswith((".xml", ".dmrpp"))
        ):
            return href
    for link in links:
        href = str(link.get("href") or "")
        if href.startswith("https://") and href.lower().endswith((".nc4", ".nc", ".hdf5", ".h5")):
            return href
    return None


def _cmr_search_granules(
    shortname: str, start_dt: str, end_dt: str
) -> list[dict[str, Any]]:
    """Query NASA CMR for IMERG granules regardless of V07/V08 version suffix."""
    import requests

    start_iso = start_dt[:10]
    end_iso = end_dt[:10]
    if len(start_iso) == 7:
        start_iso = f"{start_iso}-01"
    if len(end_iso) == 7:
        end_iso = f"{end_iso}-28"

    granules: list[dict[str, Any]] = []
    for page in range(1, 6):
        resp = requests.get(
            CMR_GRANULES_URL,
            params={
                "short_name": shortname,
                "temporal": f"{start_iso}T00:00:00Z,{end_iso}T23:59:59Z",
                "page_size": 200,
                "page_num": page,
                "sort_key": "start_date",
            },
            timeout=15,
        )
        resp.raise_for_status()
        entries = (resp.json().get("feed") or {}).get("entry") or []
        for entry in entries:
            data_url = _extract_cmr_data_url(entry)
            if not data_url:
                continue
            path = urlparse(data_url).path
            m = re.search(rf"{re.escape(shortname)}\.(\d+)", path)
            dataset_version = m.group(1) if m else ("08" if ".V08" in path else "07")
            granules.append({
                "time_start": entry.get("time_start"),
                "data_url": data_url,
                "granule_path": path,
                "shortname": shortname,
                "dataset_version": dataset_version,
            })
        if len(entries) < 200:
            break
    return granules


def _build_otf_url(
    lat: float,
    lon: float,
    granule_path: str,
    shortname: str,
    dataset_version: str,
) -> str:
    """Build a GES DISC OTF point-subset URL from a CMR-discovered granule path."""
    min_lat, max_lat = max(-90.0, float(lat) - 0.1), min(90.0, float(lat) + 0.1)
    min_lon, max_lon = max(-180.0, float(lon) - 0.1), min(180.0, float(lon) + 0.1)
    bbox = quote(f"{min_lat},{min_lon},{max_lat},{max_lon}", safe="")
    label = quote(f"{os.path.basename(granule_path)}.SUB.nc4", safe="")
    filename_enc = quote(granule_path, safe="")
    return (
        "https://gpm1.gesdisc.eosdis.nasa.gov/daac-bin/OTF/HTTP_services.cgi?"
        f"FILENAME={filename_enc}&SERVICE=L34RS_GPM&LABEL={label}&BBOX={bbox}"
        f"&VERSION=1.02&VARIABLES=precipitation&SHORTNAME={shortname}"
        f"&DATASET_VERSION={dataset_version}&FORMAT=nc4%2F"
    )


def _download_with_session(
    session: Any,
    url: str,
    out_path: str,
    invalid_reason_fn: Any,
    auth_error_cls: type[Exception],
    auth_message: str,
) -> None:
    """Stream `url` into `out_path` and verify it is binary NetCDF/HDF5 data."""
    resp = session.get(url, stream=True, timeout=30)
    if resp.status_code in (401, 403):
        raise auth_error_cls(auth_message)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} from {url}")
    first_bytes = b""
    bytes_written = 0
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                if not first_bytes:
                    first_bytes = chunk[:2048]
                bytes_written += len(chunk)
                f.write(chunk)
    if invalid_reason_fn is not None:
        reason = invalid_reason_fn(
            resp.headers.get("Content-Type", ""), first_bytes, bytes_written
        )
        if reason:
            try:
                os.remove(out_path)
            except OSError:
                pass
            raise RuntimeError(reason)


IMERG_DOWNLOAD_WORKERS = max(1, int(os.environ.get("PIER_IMERG_WORKERS", "8")))


def _fetch_single_cmr_granule(
    gran: dict[str, Any],
    dl_session: Any,
    extract_fn: Any,
    lat: float,
    lon: float,
    freq: str,
    used_run_type: str,
    invalid_reason_fn: Any,
    auth_error_cls: type[Exception],
    auth_message: str,
) -> dict[str, Any]:
    """Download and extract rainfall for one CMR granule (OTF with direct URL fallback)."""
    fd, tmp_nc = tempfile.mkstemp(suffix=".nc4")
    os.close(fd)
    otf_url = _build_otf_url(
        lat, lon, gran["granule_path"], gran["shortname"], gran["dataset_version"]
    )
    try:
        try:
            _download_with_session(
                dl_session, otf_url, tmp_nc, invalid_reason_fn,
                auth_error_cls, auth_message,
            )
        except Exception as otf_exc:  # noqa: BLE001
            if _is_auth_error(otf_exc):
                raise
            # OTF can reject newer V08 collections; fall back to direct granule URL.
            _download_with_session(
                dl_session, gran["data_url"], tmp_nc, invalid_reason_fn,
                auth_error_cls, auth_message,
            )

        dt = pd.to_datetime(gran["time_start"]).to_pydatetime().replace(tzinfo=None)
        row = extract_fn(tmp_nc, lat, lon, method="nearest", freq=freq, current_dt=dt)
        row["IMERG_Version"] = f"V{gran['dataset_version']}"
        row["Run_Type"] = used_run_type
        for key in ("Start_Time", "End_Time"):
            if hasattr(row.get(key), "isoformat"):
                row[key] = row[key].isoformat()
            elif key in row:
                row[key] = str(row[key])
        return row
    finally:
        if os.path.exists(tmp_nc):
            os.remove(tmp_nc)


def _fetch_via_cmr(
    imergpy_mod: Any,
    lat: float,
    lon: float,
    start_dt: str,
    end_dt: str,
    username: str,
    password: str,
    run_type: str,
    freq: str,
    target_dir: str,
) -> tuple[str, list[dict[str, Any]]] | None:
    """Discover IMERG granules via NASA CMR (V07/V08+) and extract point rainfall.

    Returns `(excel_path, records)` when CMR + imergpy downloader/processor are
    available; returns `None` when `imergpy` is a test mock without `downloader`
    and `processor`, or when CMR itself is unreachable so `imergpy.get_precipitation`
    can be attempted as a fallback.
    """
    dl_mod = getattr(imergpy_mod, "downloader", None)
    proc_mod = getattr(imergpy_mod, "processor", None)
    downloader_cls = getattr(dl_mod, "EarthdataDownloader", None)
    extract_fn = getattr(proc_mod, "extract_precipitation", None)
    if downloader_cls is None or extract_fn is None:
        return None

    shortname = _IMERG_SHORTNAMES.get((freq, run_type))
    if not shortname:
        return None

    candidates = [(run_type, shortname)]
    if freq == "daily" and run_type == "early":
        candidates.extend([
            ("late", _IMERG_SHORTNAMES[("daily", "late")]),
            ("final", _IMERG_SHORTNAMES[("daily", "final")]),
        ])

    granules: list[dict[str, Any]] = []
    used_run_type = run_type
    try:
        for cand_run, cand_short in candidates:
            granules = _cmr_search_granules(cand_short, start_dt, end_dt)
            if granules:
                used_run_type = cand_run
                break
    except Exception as exc:  # noqa: BLE001
        logger.warning("NASA CMR granule lookup failed (%s); falling back to imergpy", exc)
        return None

    if not granules:
        raise ValueError(
            f"No IMERG granules found in NASA CMR for {start_dt}..{end_dt} ({shortname})"
        )

    invalid_reason_fn = getattr(dl_mod, "_invalid_download_reason", None)
    auth_error_cls = getattr(dl_mod, "DownloadAuthError", RuntimeError)
    auth_message = getattr(dl_mod, "EARTHDATA_AUTH_MESSAGE", "Earthdata auth failed")

    # Initialize the first downloader on the main thread so ~/.netrc writes once safely.
    primary_dl = downloader_cls(username, password, timeout=30, retries=1)
    ordered_rows: list[dict[str, Any] | None] = [None] * len(granules)
    failures: list[str] = []

    if len(granules) == 1 or IMERG_DOWNLOAD_WORKERS == 1:
        for idx, gran in enumerate(granules):
            try:
                ordered_rows[idx] = _fetch_single_cmr_granule(
                    gran, primary_dl.session, extract_fn, lat, lon, freq,
                    used_run_type, invalid_reason_fn, auth_error_cls, auth_message,
                )
            except Exception as exc:  # noqa: BLE001
                if _is_auth_error(exc):
                    raise
                failures.append(f"{gran.get('time_start')}: {exc}")
    else:
        thread_state = threading.local()
        init_lock = threading.Lock()
        abort_event = threading.Event()
        max_workers = min(IMERG_DOWNLOAD_WORKERS, len(granules))

        def _worker(idx_gran: tuple[int, dict[str, Any]]) -> tuple[int, dict[str, Any] | None, str | None, Exception | None]:
            idx, gran = idx_gran
            if abort_event.is_set():
                return idx, None, None, None
            dl = getattr(thread_state, "dl", None)
            if dl is None:
                with init_lock:
                    dl = downloader_cls(username, password, timeout=30, retries=1)
                thread_state.dl = dl
            try:
                row = _fetch_single_cmr_granule(
                    gran, dl.session, extract_fn, lat, lon, freq,
                    used_run_type, invalid_reason_fn, auth_error_cls, auth_message,
                )
                return idx, row, None, None
            except Exception as exc:  # noqa: BLE001
                if _is_auth_error(exc):
                    abort_event.set()
                    return idx, None, None, exc
                return idx, None, f"{gran.get('time_start')}: {exc}", None

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for idx, row, err_msg, auth_exc in pool.map(_worker, enumerate(granules)):
                if auth_exc is not None:
                    raise auth_exc
                if row is not None:
                    ordered_rows[idx] = row
                elif err_msg is not None:
                    failures.append(err_msg)

    results = [r for r in ordered_rows if r is not None]

    if not results:
        raise RuntimeError(
            f"CMR IMERG download failed ({len(granules)} granules): {'; '.join(failures[:3])}"
        )

    os.makedirs(target_dir, exist_ok=True)
    excel_path = os.path.join(
        target_dir,
        f"IMERG_{used_run_type}_{freq}_{lat:.2f}_{lon:.2f}_{start_dt[:10]}_to_{end_dt[:10]}.xlsx",
    )
    try:
        pd.DataFrame(results).to_excel(excel_path, index=False)
    except Exception:  # noqa: BLE001
        excel_path = ""
    return excel_path, results


def fetch_with_retry(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    freq: str = "daily",
    max_retries: int = 3,
    backoff_base: float = 2.0,
    run_type: str = "early",
    out_dir: str | None = None,
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

    try:
        import imergpy  # type: ignore
    except ImportError as exc:
        # A missing package will not fix itself: fail at once, without retries.
        raise RuntimeError(f"imergpy is not installed: {exc}") from exc

    username = (os.environ.get("EARTHDATA_USERNAME") or "").strip()
    password = os.environ.get("EARTHDATA_PASSWORD") or ""
    if not username or not password:
        raise RuntimeError(
            "Earthdata credentials not set (EARTHDATA_USERNAME / EARTHDATA_PASSWORD)"
        )

    target_dir = out_dir or os.path.join(tempfile.gettempdir(), "pier_imerg")
    start_dt = _format_imerg_datetime(start_date)
    end_dt = _format_imerg_datetime(end_date)

    try:
        cmr_result = _fetch_via_cmr(
            imergpy, lat, lon, start_dt, end_dt, username, password,
            run_type, freq, target_dir,
        )
        if cmr_result is not None:
            _circuit_breaker.record_success()
            logger.info(
                "IMERG fetch succeeded via CMR: lat=%.4f lon=%.4f %s..%s freq=%s (%d records)",
                lat, lon, start_date, end_date, freq, len(cmr_result[1]),
            )
            return cmr_result
    except Exception as exc:  # noqa: BLE001
        logger.warning("IMERG CMR fetch failed: %s", exc)
        _circuit_breaker.record_failure()
        raise RuntimeError(f"IMERG fetch failed: {exc}") from exc

    try:
        _probe_earthdata_access(
            imergpy, lat, lon, start_dt, end_dt, username, password, run_type, freq
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("IMERG Earthdata auth probe failed: %s", exc)
        _circuit_breaker.record_failure()
        raise RuntimeError(f"IMERG fetch failed: {exc}") from exc

    last_error: Exception | None = None
    attempts_made = 0
    for attempt in range(1, max_retries + 1):
        attempts_made = attempt
        try:
            excel_path, records = imergpy.get_precipitation(
                lat=lat,
                lon=lon,
                start_datetime=start_dt,
                end_datetime=end_dt,
                username=username,
                password=password,
                run_type=run_type,
                freq=freq,
                out_dir=target_dir,
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
            # Auth, signature, and validation errors are deterministic; do not retry.
            if isinstance(exc, (TypeError, ValueError)) or _is_auth_error(exc):
                break
            if attempt < max_retries:
                sleep_for = backoff_base ** attempt
                logger.info("Retrying in %.1fs...", sleep_for)
                time.sleep(sleep_for)

    _circuit_breaker.record_failure()
    raise RuntimeError(
        f"IMERG fetch failed after {attempts_made} attempts: {last_error}"
    ) from last_error


def fetch_with_fallback(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    freq: str = "daily",
    synthetic_cache_dir: str | None = None,
    demo_mode: bool | None = None,
) -> dict[str, Any]:
    """Fetch IMERG data with synthetic cache fallback.

    In demo mode (argument, or PIER_DEMO_MODE when None) and when Earthdata is
    not usable (see `earthdata_status`) no live call is attempted.

    Returns a dict with keys:
      - source: "earthdata" | "synthetic"
      - excel_path: str | None
      - records: Any
      - synthetic: bool
    """
    if demo_mode is None:
        demo_mode = os.environ.get("PIER_DEMO_MODE", "1") == "1"
    try:
        if demo_mode:
            raise RuntimeError("demo mode: live Earthdata call skipped")
        status = earthdata_status()
        if not status["available"]:
            raise RuntimeError(status["reason"])
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


def _pick_date_column(columns: Any) -> Any:
    """Locate the date/start-time column in imergpy records or test mocks."""
    cols = list(columns)
    for needle in ("date", "start_time", "start time"):
        match = next((c for c in cols if needle in str(c).lower()), None)
        if match is not None:
            return match
    match = next(
        (c for c in cols if "time" in str(c).lower() and "end" not in str(c).lower()),
        None,
    )
    if match is None:
        raise KeyError(f"No date/time column found in {cols}")
    return match


def _imerg_to_dataframe(records: Any) -> pd.DataFrame | None:
    """Normalize the imergpy output to (date, precipitation_mm). None if not recognized."""
    try:
        df = records if isinstance(records, pd.DataFrame) else pd.DataFrame(records)
        if df.empty:
            return None
        date_col = _pick_date_column(df.columns)
        rain_col = next(c for c in df.columns if "precip" in str(c).lower())
        out = pd.DataFrame({
            "date": pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d"),
            "precipitation_mm": pd.to_numeric(df[rain_col], errors="coerce"),
        }).dropna(subset=["date", "precipitation_mm"])
        if out.empty:
            return None
        if out["date"].duplicated().any():
            out = out.groupby("date", as_index=False, sort=False)["precipitation_mm"].sum()
        out["precipitation_mm"] = out["precipitation_mm"].round(2)
        return out.reset_index(drop=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not parse the imergpy output: %s", exc)
        return None


def refresh_cache_with_real_data(demo_name: str, use_imerg: bool | None = None) -> str:
    """Replace a scenario's cache with real NASA data. Runs only when called explicitly.

    The download goes through `pipeline.ingest_point`, the single real-data
    entry point, which decides POWER vs IMERG vs fallback:
    - Temperature and baselines: real NASA POWER.
    - Rainfall: IMERG through imergpy when Earthdata is usable; otherwise
      POWER's PRECTOTCORR precipitation as a declared stand-in.

    Returns `fuente_datos`: "nasa_power+imerg", "nasa_power" or "sintetico"
    (if the download fails the existing cache is left untouched).

    Nothing in demo mode calls this function. With real data the demo packet's
    event may not cross the BR-1 thresholds, so check the scenarios afterwards;
    `python -m piper_agent.data.generate_cache` restores the synthetic cache.
    """
    import glob
    import json

    from piper_agent.data import generate_cache as gc
    from piper_agent.data.ingestion.pipeline import ingest_point

    cfg = gc.read_packet(demo_name)
    lat, lon = cfg["lat"], cfg["lon"]
    series_end = gc._series_end(lat, cfg["current_date"], cfg.get("season_end"))
    download_end = min(series_end, date.today().isoformat())

    data = ingest_point(
        lat, lon, cfg["baseline_start"], download_end,
        demo_mode=False, use_imerg=use_imerg, use_cache=False,
    )
    source = data["fuente_datos"]
    if source == "sintetico":
        logger.warning(
            "Real data unavailable (%s); keeping the current cache of '%s'",
            data["fallback_reason"], demo_name,
        )
        return "sintetico"

    power_df = data["power"][["date", *POWER_PARAMETERS]]
    rainfall = data["rainfall"]
    imerg_df = rainfall.loc[rainfall["date"] <= cfg["recent_end"], ["date", "precipitation_mm"]]

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
    "earthdata_status",
    "CircuitBreaker",
]
