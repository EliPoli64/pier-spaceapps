"""BR-3: fetch_power_gdd — Multi-hemisphere, zero-lookahead POWER GDD model.

Computes GDD accumulated to date, projected GDD remaining to season end
(climatological autumn frost in temperate regimes, or rainy-season end in the
tropics), phenological season stage, and climate telemetry contract blocks.

Demo mode uses cache_loader only. With `power` + `baselines` (or `demo_mode=False`)
the tool runs on live data from `live_inputs`; there the observations end today, so
the GDD still to come is projected from the monthly climatology (and labeled).

Strict zero-lookahead guarantee: all observations after ``current_date`` are
filtered out immediately after DataFrame normalization before any calculation.
In demo mode (``demo_mode=True`` / ``api_mode="demo"``) no network calls are
ever attempted.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
import glob
import json
import math
import os
from typing import Any

import numpy as np
import pandas as pd

from piper_agent.config import (
    CLIMATE_FROST_BANDS,
    CLIMATE_UNITS,
    CROP_TBASE,
    DEFAULT_TBASE_C,
    FROST_NORTH_START_DOY,
    FROST_SOUTH_DOY_RANGE,
    FROST_THRESHOLD_C,
    HEAT_WAVE_MIN_DAYS,
    HEAT_WAVE_TMAX_C,
    HEMISPHERE_DEFAULT,
    REPRESENTATIVE_REGIME_COORDINATES,
    SAFETY_MARGIN,
    SEASON_STAGES,
    SEASON_STAGE_THRESHOLDS,
    TROPICAL_LATITUDE,
    VALID_API_MODES,
    VALID_HEMISPHERES,
)
from piper_agent.contracts import GddResult
from piper_agent.data import cache_loader as _cache_loader
from piper_agent.data import calibration as _calibration
from piper_agent.data import climatology as _climatology
from piper_agent.data import generate_cache as _generate_cache
from piper_agent.data.cache_loader import (
    load_baselines,
    load_frost_bands,
    load_power,
)
from piper_agent.data.ingestion import pipeline as _ingestion_pipeline
from piper_agent.data.ingestion.pipeline import ingest_point
from piper_agent.data.soil_lookup import lookup_soil
from piper_agent.tools.confidence_calibration import calibrate_confidence

_DEFAULT_LOAD_POWER = load_power
_DEFAULT_LOAD_BASELINES = load_baselines
_DEFAULT_LOAD_FROST_BANDS = load_frost_bands
_DEFAULT_INGEST_POINT = ingest_point

_POWER_FILL_THRESHOLD = -900.0
_DAYS_IN_YEAR = 365.0


def _call_load_power(name: str) -> pd.DataFrame:
    if load_power is not _DEFAULT_LOAD_POWER:
        return load_power(name)
    return _cache_loader.load_power(name)


def _call_load_baselines(name: str) -> dict[str, Any]:
    if load_baselines is not _DEFAULT_LOAD_BASELINES:
        return load_baselines(name)
    return _cache_loader.load_baselines(name)


def _call_load_frost_bands() -> dict[str, Any]:
    try:
        if load_frost_bands is not _DEFAULT_LOAD_FROST_BANDS:
            return load_frost_bands()
        return _cache_loader.load_frost_bands()
    except Exception:  # noqa: BLE001
        return {
            "note": CLIMATE_FROST_BANDS["note"],
            "tropical_latitude": TROPICAL_LATITUDE,
            "north": list(CLIMATE_FROST_BANDS["north"]),
            "south": list(CLIMATE_FROST_BANDS["south"]),
            "tropical": dict(CLIMATE_FROST_BANDS["tropical"]),
        }


def _call_ingest_point(
    lat: float,
    lon: float,
    start: str,
    end: str,
    demo_mode: bool,
) -> dict[str, Any]:
    fn = (
        ingest_point
        if ingest_point is not _DEFAULT_INGEST_POINT
        else _ingestion_pipeline.ingest_point
    )
    return fn(lat=lat, lon=lon, start=start, end=end, demo_mode=demo_mode)


def _to_json_safe(obj: Any) -> Any:
    """Recursively convert numpy/pandas/date objects to JSON primitives."""
    if isinstance(obj, dict):
        return {str(k): _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_json_safe(v) for v in obj]
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return obj.isoformat()[:10] if isinstance(obj, date) else str(obj)
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        val = float(obj)
        return None if (math.isnan(val) or math.isinf(val)) else val
    if isinstance(obj, np.bool_):
        return bool(obj)
    item = getattr(obj, "item", None)
    if callable(item):
        try:
            return _to_json_safe(item())
        except Exception:  # noqa: BLE001
            pass
    return str(obj)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_replace_year(d: date, year: int) -> date:
    day = min(d.day, calendar.monthrange(year, d.month)[1])
    return date(year, d.month, day)


def _parse_iso_ts(value: str, label: str) -> pd.Timestamp:
    try:
        ts = pd.Timestamp(value)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid {label} date '{value}': {exc}") from exc
    if pd.isna(ts):
        raise ValueError(f"Invalid {label} date '{value}'")
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts.normalize()


def _parse_mmdd(raw: str) -> tuple[int, int] | None:
    if not raw:
        return None
    text = str(raw).strip()[:10]
    parts = text.split("-")
    try:
        if len(parts) == 3:
            return int(parts[1]), int(parts[2])
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return None


def _anchor_mmdd_after(mm: int, dd: int, anchor: pd.Timestamp) -> pd.Timestamp:
    """Anchor MM-DD to `anchor.year`, bumping +1 year if <= `anchor`."""
    year = int(anchor.year)
    max_day = calendar.monthrange(year, mm)[1]
    candidate = pd.Timestamp(date(year, mm, min(dd, max_day)))
    if candidate <= anchor:
        next_year = year + 1
        max_next = calendar.monthrange(next_year, mm)[1]
        candidate = pd.Timestamp(date(next_year, mm, min(dd, max_next)))
    return candidate


def _doy_to_mmdd(doy: float) -> str:
    clamped = max(1, min(365, int(round(doy))))
    ref = date(2025, 1, 1) + timedelta(days=clamped - 1)
    return ref.strftime("%m-%d")


def _mmdd_to_doy(mmdd: str) -> int | None:
    parsed = _parse_mmdd(mmdd)
    if not parsed:
        return None
    mm, dd = parsed
    max_day = calendar.monthrange(2025, mm)[1]
    return date(2025, mm, min(dd, max_day)).timetuple().tm_yday


def _doy_circular_distance(d1: int, d2: int) -> int:
    diff = abs(int(d1) - int(d2))
    return min(diff, 366 - diff)


def _crop_col_slug(crop_name: str) -> str:
    chars = [ch.lower() if ch.isalnum() else "_" for ch in crop_name]
    slug = "".join(chars).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return f"gdd_{slug}"


def _resolve_execution_mode(
    demo_mode: bool,
    api_mode: str | None,
) -> tuple[bool, str]:
    if api_mode is not None:
        mode = str(api_mode).strip().lower()
        if mode not in VALID_API_MODES:
            raise ValueError(
                f"Invalid api_mode '{api_mode}'. "
                f"Expected one of {VALID_API_MODES}."
            )
        effective_demo = mode == "demo"
        return effective_demo, mode
    effective_demo = bool(demo_mode)
    return effective_demo, ("demo" if effective_demo else "live")


def _resolve_hemisphere(
    lat: float,
    hemisphere: str | None,
) -> tuple[str, str, bool]:
    if hemisphere is None:
        requested = HEMISPHERE_DEFAULT
    else:
        requested = str(hemisphere).strip().lower()
        if requested not in VALID_HEMISPHERES:
            raise ValueError(
                f"Invalid hemisphere '{hemisphere}'. "
                f"Expected one of {VALID_HEMISPHERES}."
            )
    if requested == "auto":
        resolved = "south" if float(lat) < 0 else "north"
    else:
        resolved = requested
    is_tropical = abs(float(lat)) < TROPICAL_LATITUDE
    return requested, resolved, is_tropical


def _extract_date_series(work: pd.DataFrame) -> pd.Series:
    cols_lower = {str(c).lower(): c for c in work.columns}
    if "date" in cols_lower:
        raw = work[cols_lower["date"]]
        parsed = pd.to_datetime(raw, errors="coerce")
    elif "yyyymmdd" in cols_lower:
        col = cols_lower["yyyymmdd"]
        parsed = pd.to_datetime(
            work[col].astype(str).str.strip(),
            format="%Y%m%d",
            errors="coerce",
        )
    elif {"year", "mo", "dy"} <= set(cols_lower):
        parsed = pd.to_datetime(
            {
                "year": pd.to_numeric(
                    work[cols_lower["year"]], errors="coerce"
                ),
                "month": pd.to_numeric(
                    work[cols_lower["mo"]], errors="coerce"
                ),
                "day": pd.to_numeric(
                    work[cols_lower["dy"]], errors="coerce"
                ),
            },
            errors="coerce",
        )
    elif {"year", "doy"} <= set(cols_lower):
        years = pd.to_numeric(work[cols_lower["year"]], errors="coerce")
        doys = pd.to_numeric(work[cols_lower["doy"]], errors="coerce")
        codes = years.fillna(-1).astype(int).astype(str) + (
            doys.fillna(-1).astype(int).astype(str).str.zfill(3)
        )
        parsed = pd.to_datetime(codes, format="%Y%j", errors="coerce")
    elif isinstance(work.index, pd.DatetimeIndex):
        parsed = pd.Series(work.index, index=work.index)
    else:
        idx_str = pd.Series(work.index.astype(str), index=work.index)
        parsed = pd.to_datetime(idx_str, format="%Y%m%d", errors="coerce")
        if parsed.isna().all():
            raise ValueError(
                "POWER dataframe must contain 'date', 'YYYYMMDD', "
                "or 'YEAR'/'MO'/'DY' columns."
            )

    if getattr(parsed.dt, "tz", None) is not None:
        parsed = parsed.dt.tz_localize(None)
    return parsed.dt.normalize()


def _normalize_power_dataframe(
    df: pd.DataFrame,
    tbase_c: float = DEFAULT_TBASE_C,
) -> pd.DataFrame:
    """Normalize POWER data, clean fill values, and compute daily GDD.

    Accepts string dates, ``datetime.date``, ``pd.Timestamp``, ``YYYYMMDD``,
    or ``YEAR``/``MO``/``DY`` columns. Replaces NASA POWER fill values
    (``<= -900.0``) with ``np.nan`` without mutating the input DataFrame.
    """
    if df is None or not isinstance(df, pd.DataFrame):
        raise ValueError("power_df must be a pandas DataFrame.")

    work = df.copy()
    if work.empty:
        cols = [
            "date",
            "T2M_MAX",
            "T2M_MIN",
            "PRECTOTCORR",
            "tmean",
            "gdd_daily",
            "doy",
        ]
        for crop_name in CROP_TBASE:
            cols.append(_crop_col_slug(crop_name))
        empty = pd.DataFrame(columns=cols)
        empty["date"] = pd.to_datetime(empty["date"])
        return empty

    work["date"] = _extract_date_series(work)
    work = work.dropna(subset=["date"]).sort_values("date")
    work = work.drop_duplicates(subset=["date"], keep="last")
    work = work.reset_index(drop=True)

    for required in ("T2M_MAX", "T2M_MIN"):
        if required not in work.columns:
            raise ValueError(
                f"POWER dataframe missing required column '{required}'."
            )

    if "PRECTOTCORR" not in work.columns:
        work["PRECTOTCORR"] = np.nan

    weather_cols = ["T2M_MAX", "T2M_MIN", "PRECTOTCORR"]
    if "GWETROOT" in work.columns:
        weather_cols.append("GWETROOT")

    for col in weather_cols:
        series = pd.to_numeric(work[col], errors="coerce").astype(float)
        series = series.mask(series <= _POWER_FILL_THRESHOLD, np.nan)
        work[col] = series

    work.loc[work["PRECTOTCORR"] < 0.0, "PRECTOTCORR"] = np.nan
    if "GWETROOT" in work.columns:
        invalid_gw = (work["GWETROOT"] < 0.0) | (work["GWETROOT"] > 1.5)
        work.loc[invalid_gw, "GWETROOT"] = np.nan

    work["tmean"] = (work["T2M_MAX"] + work["T2M_MIN"]) / 2.0
    work["gdd_daily"] = (work["tmean"] - float(tbase_c)).clip(lower=0.0)
    work["doy"] = work["date"].dt.day_of_year

    for crop_name, crop_base in CROP_TBASE.items():
        col_name = _crop_col_slug(crop_name)
        work[col_name] = (work["tmean"] - float(crop_base)).clip(lower=0.0)

    return work


def _read_local_baseline_dir(
    baseline_dir: str,
    demo_name: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any], str]:
    clean_dir = os.path.normpath(baseline_dir)
    base_name = os.path.basename(clean_dir)

    baselines: dict[str, Any] = {}
    primary_json = os.path.join(clean_dir, f"{base_name}_baselines.json")
    if os.path.exists(primary_json):
        with open(primary_json, encoding="utf-8") as f:
            baselines = json.load(f)
    else:
        candidates = sorted(
            glob.glob(os.path.join(clean_dir, "*_baselines.json"))
        )
        if candidates:
            with open(candidates[0], encoding="utf-8") as f:
                baselines = json.load(f)
        elif demo_name:
            baselines = _call_load_baselines(demo_name)

    local_candidates = [
        (os.path.join(clean_dir, f"{base_name}_power.csv"), "csv"),
        (os.path.join(clean_dir, f"{base_name}_power.parquet"), "parquet"),
        (os.path.join(clean_dir, "power.csv"), "csv"),
        (os.path.join(clean_dir, "power.parquet"), "parquet"),
    ]
    for path, fmt in local_candidates:
        if os.path.exists(path):
            df = (
                pd.read_csv(path)
                if fmt == "csv"
                else pd.read_parquet(path)
            )
            return df, baselines, base_name

    try:
        return _call_load_power(base_name), baselines, base_name
    except FileNotFoundError:
        if demo_name:
            return _call_load_power(demo_name), baselines, demo_name
        raise


def _load_climate_inputs(
    lat: float,
    lon: float,
    season_start_dt: pd.Timestamp,
    current_dt: pd.Timestamp,
    baseline_dir: str | None,
    demo_name: str | None,
    effective_demo: bool,
    power_df: pd.DataFrame | None,
    baselines_override: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    """Load POWER data and baselines without network in demo mode."""
    meta: dict[str, Any] = {
        "source": "sintetico",
        "mode": "demo" if effective_demo else "live",
        "power_used": True,
        "imerg_used": False,
        "fallback_reason": None,
        "cache_used": False,
        "demo_scenario": demo_name,
        "region": _ingestion_pipeline.region_key(float(lat), float(lon)),
    }

    if power_df is not None:
        baselines: dict[str, Any] = {}
        if baselines_override is not None:
            baselines = dict(baselines_override)
        elif demo_name:
            try:
                baselines = _call_load_baselines(demo_name)
            except FileNotFoundError:
                baselines = {}
        attrs_obj = getattr(power_df, "attrs", {})
        attrs_src = attrs_obj.get(
            "fuente_datos",
            attrs_obj.get("source"),
        )
        meta["source"] = str(attrs_src or "custom_dataframe")
        meta["imerg_used"] = meta["source"] == "nasa_power+imerg"
        if attrs_obj.get("fallback_reason"):
            meta["fallback_reason"] = attrs_obj.get("fallback_reason")
        return power_df, baselines, meta

    if effective_demo and demo_name:
        df = _call_load_power(demo_name)
        baselines = _call_load_baselines(demo_name)
        src = str(baselines.get("fuente_datos", "sintetico"))
        meta["source"] = src
        meta["imerg_used"] = src == "nasa_power+imerg"
        meta["cache_used"] = True
        return df, baselines, meta

    if baseline_dir:
        df, baselines, resolved_name = _read_local_baseline_dir(
            baseline_dir, demo_name=demo_name
        )
        src = str(baselines.get("fuente_datos", "sintetico"))
        meta["source"] = src
        meta["imerg_used"] = src == "nasa_power+imerg"
        meta["cache_used"] = True
        meta["demo_scenario"] = demo_name or resolved_name
        return df, baselines, meta

    if not effective_demo:
        ten_yr = _safe_replace_year(
            current_dt.date(), current_dt.year - 10
        )
        ingest_start = min(ten_yr, season_start_dt.date()).isoformat()
        ingested = _call_ingest_point(
            lat=float(lat),
            lon=float(lon),
            start=ingest_start,
            end=current_dt.strftime("%Y-%m-%d"),
            demo_mode=False,
        )
        df = ingested["power"]
        src = str(ingested.get("fuente_datos", "nasa_power"))
        scenario = ingested.get("demo_scenario") or demo_name
        baselines = {}
        if src == "sintetico" and scenario:
            try:
                baselines = _call_load_baselines(scenario)
            except FileNotFoundError:
                baselines = {}
        meta["source"] = src
        meta["imerg_used"] = src == "nasa_power+imerg"
        meta["fallback_reason"] = ingested.get("fallback_reason")
        meta["cache_used"] = bool(src == "sintetico" and scenario)
        meta["demo_scenario"] = scenario
        if ingested.get("region"):
            meta["region"] = ingested["region"]
        return df, baselines, meta

    raise ValueError(
        "Either demo_name, baseline_dir, or power_df must be provided "
        "when demo_mode=True."
    )


def _lookup_band_first_frost(
    lat: float,
    resolved_hemisphere: str,
    frost_bands: dict[str, Any] | None = None,
) -> str:
    bands_src = frost_bands or _call_load_frost_bands()
    hem_bands = (
        bands_src.get(resolved_hemisphere)
        or CLIMATE_FROST_BANDS[resolved_hemisphere]
    )
    abs_lat = abs(float(lat))
    for band in hem_bands:
        if float(band["lat_min"]) <= abs_lat < float(band["lat_max"]):
            return str(band["first_frost"])
    if abs_lat >= float(hem_bands[-1]["lat_max"]):
        return str(hem_bands[-1]["first_frost"])
    return str(hem_bands[0]["first_frost"])


def compute_climatological_frost_date(
    df: pd.DataFrame,
    lat: float,
    hemisphere: str = "auto",
    frost_threshold_c: float = FROST_THRESHOLD_C,
) -> dict[str, Any]:
    """Compute 10-yr historical median first autumn freeze for a site.

    For tropical latitudes (``abs(lat) < TROPICAL_LATITUDE``), returns
    no-frost metadata (``has_climatological_frost=False``).
    """
    _, resolved_hem, is_tropical = _resolve_hemisphere(lat, hemisphere)
    frost_bands = _call_load_frost_bands()
    norm = _normalize_power_dataframe(df)
    valid = norm.dropna(subset=["T2M_MIN"]).copy()
    total_years = (
        int(valid["date"].dt.year.nunique()) if not valid.empty else 0
    )

    if is_tropical:
        trop = frost_bands.get("tropical") or CLIMATE_FROST_BANDS["tropical"]
        default_mmdd = (
            trop["south_default"]
            if resolved_hem == "south"
            else trop["north_default"]
        )
        return {
            "tropical": True,
            "has_climatological_frost": False,
            "climate_regime": "tropical",
            "hemisphere": resolved_hem,
            "frost_threshold_c": float(frost_threshold_c),
            "method": "rainy_season_end",
            "median_doy": None,
            "median_mmdd": None,
            "earliest_mmdd": None,
            "latest_mmdd": None,
            "iqr_days": None,
            "std_days": None,
            "frost_years": 0,
            "total_years": total_years,
            "per_year_first_frost": {},
            "band_first_frost": default_mmdd,
            "band_doy": _mmdd_to_doy(default_mmdd),
            "doy_diff_vs_band": None,
            "units": {"temperature": "degC", "doy": "day_of_year"},
        }

    band_mmdd = _lookup_band_first_frost(lat, resolved_hem, frost_bands)
    band_doy = _mmdd_to_doy(band_mmdd)

    if valid.empty:
        return {
            "tropical": False,
            "has_climatological_frost": True,
            "climate_regime": f"temperate_{resolved_hem}",
            "hemisphere": resolved_hem,
            "frost_threshold_c": float(frost_threshold_c),
            "method": "first_autumn_frost",
            "median_doy": None,
            "median_mmdd": None,
            "earliest_mmdd": None,
            "latest_mmdd": None,
            "iqr_days": None,
            "std_days": None,
            "frost_years": 0,
            "total_years": 0,
            "per_year_first_frost": {},
            "band_first_frost": band_mmdd,
            "band_doy": band_doy,
            "doy_diff_vs_band": None,
            "units": {"temperature": "degC", "doy": "day_of_year"},
        }

    valid["year"] = valid["date"].dt.year
    valid["doy"] = valid["date"].dt.day_of_year
    if resolved_hem == "north":
        autumn = valid[valid["doy"] >= FROST_NORTH_START_DOY]
    else:
        lo, hi = FROST_SOUTH_DOY_RANGE
        autumn = valid[(valid["doy"] > lo) & (valid["doy"] <= hi)]

    freezes = autumn[autumn["T2M_MIN"] <= float(frost_threshold_c)]
    per_year_first: dict[int, str] = {}
    first_doys: list[int] = []
    if not freezes.empty:
        for yr, grp in freezes.groupby("year"):
            idx = grp["date"].idxmin()
            row = grp.loc[idx]
            per_year_first[int(yr)] = row["date"].strftime("%Y-%m-%d")
            first_doys.append(int(row["doy"]))

    if first_doys:
        arr = np.asarray(first_doys, dtype=float)
        med_doy = float(np.median(arr))
        q75, q25 = np.percentile(arr, [75, 25])
        med_mmdd = _doy_to_mmdd(med_doy)
        earliest_mmdd = _doy_to_mmdd(float(np.min(arr)))
        latest_mmdd = _doy_to_mmdd(float(np.max(arr)))
        iqr_days = round(float(q75 - q25), 2)
        std_days = round(float(np.std(arr)), 2)
        doy_diff = (
            round(abs(med_doy - float(band_doy)), 1)
            if band_doy is not None
            else None
        )
    else:
        med_doy = None
        med_mmdd = None
        earliest_mmdd = None
        latest_mmdd = None
        iqr_days = None
        std_days = None
        doy_diff = None

    return {
        "tropical": False,
        "has_climatological_frost": True,
        "climate_regime": f"temperate_{resolved_hem}",
        "hemisphere": resolved_hem,
        "frost_threshold_c": float(frost_threshold_c),
        "method": "first_autumn_frost",
        "median_doy": round(med_doy, 1) if med_doy is not None else None,
        "median_mmdd": med_mmdd,
        "earliest_mmdd": earliest_mmdd,
        "latest_mmdd": latest_mmdd,
        "iqr_days": iqr_days,
        "std_days": std_days,
        "frost_years": len(first_doys),
        "total_years": total_years,
        "per_year_first_frost": per_year_first,
        "band_first_frost": band_mmdd,
        "band_doy": band_doy,
        "doy_diff_vs_band": doy_diff,
        "units": {"temperature": "degC", "doy": "day_of_year"},
    }


def _baseline_matches_temperate_hemisphere(
    baselines: dict[str, Any],
    resolved_hemisphere: str,
) -> bool:
    frost_str = baselines.get("climatological_frost_date")
    if not frost_str:
        return False
    if baselines.get("tropical") is True:
        return False
    if baselines.get("frost_method") in (
        "rainy_season_end",
        "fin_temporada_lluvias",
    ):
        return False
    parsed = _parse_mmdd(str(frost_str))
    if not parsed:
        return False
    mm, _ = parsed

    base_hem = baselines.get("hemisphere")
    if base_hem in ("north", "south"):
        return str(base_hem).lower() == resolved_hemisphere

    method = str(baselines.get("frost_method", ""))
    if method == "southern_autumn_frost":
        return resolved_hemisphere == "south"
    if method == "first_T2M_MIN_<=0_after_day200":
        return resolved_hemisphere == "north"

    if resolved_hemisphere == "south":
        return 3 <= mm <= 8
    return mm >= 8 or mm <= 1


def _resolve_season_end(
    lat: float,
    resolved_hemisphere: str,
    is_tropical: bool,
    season_start_dt: pd.Timestamp,
    baselines: dict[str, Any],
    df_obs: pd.DataFrame,
) -> dict[str, Any]:
    """Resolve season-end date without +182d hacks in tropics/south."""
    frost_bands = _call_load_frost_bands()
    raw_baseline_frost = baselines.get("climatological_frost_date")

    if is_tropical:
        baseline_is_tropical = bool(
            baselines.get("tropical") is True
            or baselines.get("frost_method")
            in ("rainy_season_end", "fin_temporada_lluvias")
            or baselines.get("season_end")
        )
        mmdd_pair = None
        if baseline_is_tropical:
            raw_trop = baselines.get("season_end") or raw_baseline_frost
            mmdd_pair = _parse_mmdd(str(raw_trop or ""))
        if mmdd_pair is None:
            trop_cfg = (
                frost_bands.get("tropical") or CLIMATE_FROST_BANDS["tropical"]
            )
            default_mmdd = (
                trop_cfg["south_default"]
                if resolved_hemisphere == "south"
                else trop_cfg["north_default"]
            )
            mmdd_pair = _parse_mmdd(default_mmdd) or (11, 15)

        season_end_dt = _anchor_mmdd_after(
            mmdd_pair[0], mmdd_pair[1], season_start_dt
        )
        if baseline_is_tropical:
            baseline_date_str = str(
                raw_trop or season_end_dt.strftime("%Y-%m-%d")
            )
        else:
            baseline_date_str = season_end_dt.strftime("%Y-%m-%d")
        return {
            "season_end_dt": season_end_dt,
            "season_end_str": season_end_dt.strftime("%Y-%m-%d"),
            "frost_baseline_date": baseline_date_str,
            "tropical": True,
            "has_climatological_frost": False,
            "climate_regime": "tropical",
            "season_end_method": "rainy_season_end",
            "method": "rainy_season_end",
        }

    # Temperate regime (north or south)
    mmdd_pair = None
    baseline_matches = _baseline_matches_temperate_hemisphere(
        baselines, resolved_hemisphere
    )
    if baseline_matches:
        mmdd_pair = _parse_mmdd(str(raw_baseline_frost))
    elif not raw_baseline_frost and not df_obs.empty:
        hist_frost = compute_climatological_frost_date(
            df_obs, lat, hemisphere=resolved_hemisphere
        )
        if hist_frost.get("frost_years", 0) >= 2 and hist_frost.get(
            "median_mmdd"
        ):
            mmdd_pair = _parse_mmdd(str(hist_frost["median_mmdd"]))

    if mmdd_pair is None:
        band_mmdd = _lookup_band_first_frost(
            lat, resolved_hemisphere, frost_bands
        )
        mmdd_pair = _parse_mmdd(band_mmdd) or (
            (5, 5) if resolved_hemisphere == "south" else (10, 10)
        )

    season_end_dt = _anchor_mmdd_after(
        mmdd_pair[0], mmdd_pair[1], season_start_dt
    )
    if baseline_matches and raw_baseline_frost:
        baseline_date_str = str(raw_baseline_frost)
    else:
        baseline_date_str = season_end_dt.strftime("%Y-%m-%d")
    return {
        "season_end_dt": season_end_dt,
        "season_end_str": season_end_dt.strftime("%Y-%m-%d"),
        "frost_baseline_date": baseline_date_str,
        "tropical": False,
        "has_climatological_frost": True,
        "climate_regime": f"temperate_{resolved_hemisphere}",
        "season_end_method": "climatological_frost",
        "method": "climatological_frost",
    }


def _seasonal_model_tmean(
    doy: int,
    lat: float,
    resolved_hemisphere: str,
    is_tropical: bool,
) -> float:
    """Smooth latitude/hemisphere seasonal temperature curve (degC)."""
    phase = 109.0 if resolved_hemisphere == "north" else 291.5
    sin_term = math.sin(2.0 * math.pi * (float(doy) - phase) / _DAYS_IN_YEAR)
    if is_tropical:
        return 23.0 + 2.0 * sin_term
    abs_lat = abs(float(lat))
    annual_mean = max(-2.0, 27.0 - 0.36 * abs_lat)
    half_amp = min(16.0, max(5.0, 0.35 * abs_lat))
    return annual_mean + half_amp * sin_term


def _estimate_recent_bias(
    df_obs: pd.DataFrame,
    current_dt: pd.Timestamp,
    lat: float,
    resolved_hemisphere: str,
    is_tropical: bool,
) -> float:
    valid = df_obs.dropna(subset=["tmean"])
    if valid.empty:
        return 0.0
    win_start = current_dt - timedelta(days=29)
    recent = valid[valid["date"] >= win_start]
    sample = recent if not recent.empty else valid.tail(30)
    diffs = [
        float(row["tmean"])
        - _seasonal_model_tmean(
            int(row["doy"]), lat, resolved_hemisphere, is_tropical
        )
        for _, row in sample.iterrows()
    ]
    if not diffs:
        return 0.0
    bias = float(np.mean(diffs))
    return max(-6.0, min(6.0, bias))


def _load_local_monthly_tmean(lat: float, lon: float) -> dict[int, float]:
    """Read-only lookup of cached regional climatology (zero network)."""
    try:
        clim = _climatology.load_climatology(float(lat), float(lon))
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(clim, dict):
        return {}
    months = clim.get("months") or {}
    out: dict[int, float] = {}
    for m_str, stats in months.items():
        try:
            tmax_p50 = stats["tmax"]["p50"]
            tmin_p50 = stats["tmin"]["p50"]
            out[int(m_str)] = (float(tmax_p50) + float(tmin_p50)) / 2.0
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _project_future_gdd(
    df_obs: pd.DataFrame,
    season_start_dt: pd.Timestamp,
    current_dt: pd.Timestamp,
    season_end_dt: pd.Timestamp,
    tbase_c: float,
    lat: float,
    lon: float,
    resolved_hemisphere: str,
    is_tropical: bool,
) -> tuple[float, str]:
    """Project GDD from max(current+1, season_start) to season_end - 1.

    Uses strictly historical observations inside ``df_obs`` (< season_start or
    prior years) with a circular DOY window (+-7d, widening to +-15d). Falls
    back to a latitude/hemisphere seasonal curve (plus cached regional monthly
    climatology when present) when prior-year coverage at a DOY is absent.
    """
    if current_dt >= season_end_dt:
        return 0.0, "post_season_zero"

    proj_start = max(current_dt + pd.Timedelta(days=1), season_start_dt)
    proj_end = season_end_dt - pd.Timedelta(days=1)
    if proj_start > proj_end:
        return 0.0, "post_season_zero"

    future_dates = pd.date_range(proj_start, proj_end, freq="D")

    valid_obs = df_obs.dropna(subset=["tmean"]).copy()
    valid_obs["gdd_for_base"] = (
        valid_obs["tmean"] - float(tbase_c)
    ).clip(lower=0.0)

    hist = valid_obs[valid_obs["date"] < season_start_dt]
    if hist.empty:
        hist = valid_obs[valid_obs["date"].dt.year < int(current_dt.year)]

    doy_stats = (
        hist.groupby("doy")["gdd_for_base"].agg(["sum", "count"])
        if not hist.empty
        else pd.DataFrame(columns=["sum", "count"])
    )

    bias = _estimate_recent_bias(
        valid_obs, current_dt, lat, resolved_hemisphere, is_tropical
    )
    monthly_tmean = _load_local_monthly_tmean(lat, lon)

    doy_cache: dict[int, tuple[float, bool]] = {}
    total_projected = 0.0
    used_doy = False
    used_fallback = False

    for f_dt in future_dates:
        target_doy = int(f_dt.day_of_year)
        if target_doy not in doy_cache:
            est_val: float | None = None
            if not doy_stats.empty:
                for radius in (7, 15):
                    near = [
                        int(k)
                        for k in doy_stats.index
                        if _doy_circular_distance(int(k), target_doy) <= radius
                    ]
                    if near:
                        sub = doy_stats.loc[near]
                        cnt = float(sub["count"].sum())
                        if cnt > 0:
                            est_val = float(sub["sum"].sum() / cnt)
                            break
            if est_val is not None:
                doy_cache[target_doy] = (est_val, True)
            else:
                if f_dt.month in monthly_tmean:
                    tmean_est = monthly_tmean[f_dt.month]
                else:
                    tmean_est = (
                        _seasonal_model_tmean(
                            target_doy, lat, resolved_hemisphere, is_tropical
                        )
                        + bias
                    )
                est_gdd = max(0.0, tmean_est - float(tbase_c))
                doy_cache[target_doy] = (est_gdd, False)

        val, from_doy = doy_cache[target_doy]
        total_projected += val
        if from_doy:
            used_doy = True
        else:
            used_fallback = True

    if used_doy and not used_fallback:
        method = "historical_doy_climatology"
    elif used_doy and used_fallback:
        method = "hybrid_doy_and_seasonal"
    else:
        method = "seasonal_curve_fallback"
    return max(0.0, float(total_projected)), method


def detect_season_stage(
    gdd_accumulated: float,
    gdd_remaining: float,
    total_season_gdd: float | None = None,
    current_date: str | None = None,
    season_start: str | None = None,
    season_end: str | None = None,
    is_tropical: bool = False,
    event_type: str | None = None,
) -> dict[str, Any]:
    """Classify phenological season stage and hazard sensitivity window."""
    acc = max(0.0, float(gdd_accumulated))
    rem = max(0.0, float(gdd_remaining))
    total = (
        max(0.0, float(total_season_gdd))
        if total_season_gdd is not None
        else acc + rem
    )

    cur_dt = (
        _parse_iso_ts(current_date, "current_date") if current_date else None
    )
    start_dt = (
        _parse_iso_ts(season_start, "season_start") if season_start else None
    )
    end_dt = _parse_iso_ts(season_end, "season_end") if season_end else None

    days_elapsed = (
        int((cur_dt - start_dt).days)
        if (cur_dt is not None and start_dt is not None)
        else None
    )
    days_remaining = (
        max(0, int((end_dt - cur_dt).days))
        if (cur_dt is not None and end_dt is not None)
        else None
    )
    season_length = (
        max(0, int((end_dt - start_dt).days))
        if (start_dt is not None and end_dt is not None)
        else None
    )

    is_pre_season = bool(
        cur_dt is not None and start_dt is not None and cur_dt < start_dt
    )
    is_post_season = bool(
        cur_dt is not None and end_dt is not None and cur_dt >= end_dt
    )
    is_post_frost = bool(is_post_season and not is_tropical)

    if is_pre_season:
        progress = 0.0
    elif is_post_season:
        progress = min(1.0, acc / total) if total > 0 else 1.0
    elif total > 0:
        progress = max(0.0, acc / total)
    else:
        progress = 0.0

    if is_post_season or progress >= 1.0:
        stage = "post-harvest"
    elif is_pre_season or progress < 0.15:
        stage = "planting"
    elif progress < 0.50:
        stage = "vegetative"
    elif progress < 0.80:
        stage = "flowering"
    else:
        stage = "harvest"

    if stage not in SEASON_STAGES:  # pragma: no cover - defensive invariant
        stage = "vegetative"

    cfg = SEASON_STAGE_THRESHOLDS[stage]
    sensitivity = dict(cfg["hazard_sensitivity"])
    time_progress = (
        round(max(0.0, days_elapsed) / season_length, 4)
        if (days_elapsed is not None and season_length and season_length > 0)
        else None
    )

    frost_note = (
        "No climatological frost risk in tropical regime; window bounded "
        "by rainy-season end."
        if is_tropical
        else (
            f"Temperate frost sensitivity at '{stage}': "
            f"{sensitivity.get('frost', 'medium')}."
        )
    )
    interpretation: dict[str, Any] = {
        "order": int(cfg["order"]),
        "condition": cfg["condition"],
        "stage_description": cfg["description"],
        "primary_hazards": list(cfg["primary_hazards"]),
        "frost_note": frost_note,
        "heat_wave_sensitivity": sensitivity.get("heat_wave", "low"),
        "flood_sensitivity": sensitivity.get("flood", "medium"),
        "drought_sensitivity": sensitivity.get("drought", "medium"),
    }
    if event_type is not None:
        ev = str(event_type).strip().lower()
        interpretation["active_event"] = ev
        interpretation["active_event_sensitivity"] = sensitivity.get(ev, "low")

    return {
        "stage": stage,
        "progress_ratio": round(float(progress), 4),
        "gdd_accumulated": round(acc, 1),
        "gdd_remaining": round(rem, 1),
        "total_season_gdd": round(total, 1),
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "season_length_days": season_length,
        "is_pre_season": is_pre_season,
        "is_post_season": is_post_season,
        "is_post_frost": is_post_frost,
        "window": {
            "season_start": season_start,
            "current_date": current_date,
            "season_end": season_end,
            "season_end_label": (
                "rainy_season_end" if is_tropical else "climatological_frost"
            ),
            "pre_season": is_pre_season,
            "in_season": not is_pre_season and not is_post_season,
            "post_season": is_post_season,
            "days_elapsed": days_elapsed,
            "days_remaining": days_remaining,
            "season_length_days": season_length,
            "time_progress_ratio": time_progress,
        },
        "hazard_sensitivity": sensitivity,
        "hazard_interpretation": interpretation,
    }


def _compute_heat_wave_from_obs(
    df_obs: pd.DataFrame,
    lat: float,
    lon: float,
    current_dt: pd.Timestamp,
) -> dict[str, Any]:
    """Evaluate heat wave over last 30 days strictly within `df_obs`."""
    win_start = current_dt - pd.Timedelta(days=29)
    start_str = win_start.strftime("%Y-%m-%d")
    end_str = current_dt.strftime("%Y-%m-%d")

    recent = df_obs[
        (df_obs["date"] >= win_start) & (df_obs["date"] <= current_dt)
    ].dropna(subset=["T2M_MAX"]).sort_values("date")

    max_consecutive = 0
    streak = 0
    prev_date: pd.Timestamp | None = None
    for _, row in recent.iterrows():
        cur_d = row["date"]
        above = float(row["T2M_MAX"]) > float(HEAT_WAVE_TMAX_C)
        contiguous = (
            prev_date is None or (cur_d - prev_date).days == 1
        )
        if above:
            streak = (streak + 1) if contiguous else 1
            max_consecutive = max(max_consecutive, streak)
        else:
            streak = 0
        prev_date = cur_d

    if recent.empty:
        max_tmax: float | None = None
        event_type = "none"
        confidence = 0.1
    else:
        max_tmax = float(recent["T2M_MAX"].max())
        if max_consecutive >= int(HEAT_WAVE_MIN_DAYS):
            event_type = "heat_wave"
            exceedance = max_tmax - float(HEAT_WAVE_TMAX_C)
            confidence = min(
                1.0,
                max(
                    0.1,
                    0.5 + (exceedance / 10.0) + (max_consecutive / 10.0),
                ),
            )
        else:
            event_type = "none"
            confidence = max(
                0.1,
                1.0 - min(1.0, max_tmax / float(HEAT_WAVE_TMAX_C)),
            )

    confidence = max(0.0, min(1.0, float(confidence)))
    details = {
        "max_consecutive_days_above_threshold": int(max_consecutive),
        "min_consecutive_days": int(HEAT_WAVE_MIN_DAYS),
        "tmax_threshold_c": float(HEAT_WAVE_TMAX_C),
        "max_tmax_c": round(max_tmax, 1) if max_tmax is not None else None,
        "lat": float(lat),
        "lon": float(lon),
        "recent_start": start_str,
        "recent_end": end_str,
    }
    return {
        "event_type": event_type,
        "detected": event_type == "heat_wave",
        "confidence": round(confidence, 3),
        "max_consecutive_days_above_threshold": int(max_consecutive),
        "min_consecutive_days": int(HEAT_WAVE_MIN_DAYS),
        "tmax_threshold_c": float(HEAT_WAVE_TMAX_C),
        "max_tmax_c": round(max_tmax, 1) if max_tmax is not None else None,
        "window_start": start_str,
        "window_end": end_str,
        "valid_days_in_window": int(len(recent)),
        "unit": "degC",
        "lookahead_excluded": True,
        "details": details,
    }


def _sum_valid_precip(
    df_obs: pd.DataFrame,
    start_dt: pd.Timestamp,
    end_dt: pd.Timestamp,
) -> float | None:
    sub = df_obs[
        (df_obs["date"] >= start_dt) & (df_obs["date"] <= end_dt)
    ]["PRECTOTCORR"].dropna()
    if sub.empty:
        return None
    return round(float(sub.sum()), 2)


def _build_soil_telemetry(
    lat: float,
    lon: float,
    season_start_dt: pd.Timestamp,
    current_dt: pd.Timestamp,
    df_obs: pd.DataFrame,
    effective_demo: bool,
) -> dict[str, Any]:
    """Combine soil lookup with observed GWETROOT and precipitation totals."""
    try:
        soil_base = lookup_soil(
            float(lat), float(lon), use_network=not effective_demo
        )
    except Exception:  # noqa: BLE001
        soil_base = {
            "texture_class": "Loam",
            "field_capacity_mm": 180,
            "wilting_point_mm": 90,
            "available_water_mm": 90,
            "organic_matter_pct": 2.5,
            "source": "fallback",
        }

    gwetroot_latest: float | None = None
    gwetroot_mean_14d: float | None = None
    if "GWETROOT" in df_obs.columns:
        gw_valid = df_obs.dropna(subset=["GWETROOT"])
        if not gw_valid.empty:
            gwetroot_latest = round(float(gw_valid["GWETROOT"].iloc[-1]), 3)
            win14 = gw_valid[
                gw_valid["date"] >= current_dt - pd.Timedelta(days=13)
            ]
            if not win14.empty:
                gwetroot_mean_14d = round(float(win14["GWETROOT"].mean()), 3)

    precip_7d = _sum_valid_precip(
        df_obs, current_dt - pd.Timedelta(days=6), current_dt
    )
    precip_30d = _sum_valid_precip(
        df_obs, current_dt - pd.Timedelta(days=29), current_dt
    )
    precip_season = (
        _sum_valid_precip(df_obs, season_start_dt, current_dt)
        if current_dt >= season_start_dt
        else 0.0
    )

    if gwetroot_latest is not None:
        if gwetroot_latest >= 0.8:
            moisture_status = "saturated"
        elif gwetroot_latest <= 0.3:
            moisture_status = "dry"
        else:
            moisture_status = "adequate"
    elif precip_30d is not None:
        if precip_30d >= 180.0:
            moisture_status = "saturated"
        elif precip_30d <= 25.0:
            moisture_status = "dry"
        else:
            moisture_status = "adequate"
    else:
        moisture_status = "unknown"

    return _to_json_safe({
        "texture_class": soil_base.get("texture_class"),
        "field_capacity_mm": soil_base.get("field_capacity_mm"),
        "wilting_point_mm": soil_base.get("wilting_point_mm"),
        "available_water_mm": soil_base.get("available_water_mm"),
        "organic_matter_pct": soil_base.get("organic_matter_pct"),
        "soil_source": soil_base.get("source"),
        "gwetroot_latest": gwetroot_latest,
        "gwetroot_mean_14d": gwetroot_mean_14d,
        "gwetroot_unit": CLIMATE_UNITS["root_zone_soil_wetness"]["unit"],
        "precip_7d_mm": precip_7d,
        "precip_30d_mm": precip_30d,
        "precip_season_mm": precip_season,
        "precipitation_unit": CLIMATE_UNITS["precipitation"]["unit"],
        "moisture_status": moisture_status,
        "lookahead_excluded": True,
    })


def _build_confidence_inputs(
    lat: float,
    lon: float,
    season_start_dt: pd.Timestamp,
    current_dt: pd.Timestamp,
    df_obs: pd.DataFrame,
    projection_method: str,
    source: str,
) -> dict[str, Any]:
    valid_obs = df_obs.dropna(subset=["tmean"])
    history_days = int(len(valid_obs))
    history_years = (
        int(valid_obs["date"].dt.year.nunique()) if not valid_obs.empty else 0
    )

    if current_dt >= season_start_dt:
        expected_days = int((current_dt - season_start_dt).days) + 1
        in_season = valid_obs[
            (valid_obs["date"] >= season_start_dt)
            & (valid_obs["date"] <= current_dt)
        ]
        valid_season_days = int(len(in_season))
        completeness = (
            min(1.0, valid_season_days / expected_days)
            if expected_days > 0
            else 0.0
        )
    else:
        expected_days = 0
        valid_season_days = 0
        completeness = 1.0 if history_days > 0 else 0.0

    has_multiyear = history_years >= 3
    has_gwetroot = bool(
        "GWETROOT" in df_obs.columns and df_obs["GWETROOT"].notna().any()
    )

    raw_score = (
        0.45 * completeness
        + 0.30 * min(1.0, history_years / 5.0)
        + (0.15 if projection_method == "historical_doy_climatology" else 0.05)
        + (0.10 if source != "sintetico" else 0.05)
    )
    raw_score = max(0.0, min(1.0, float(raw_score)))

    try:
        history = _calibration.validation_history(float(lat), float(lon))
    except Exception:  # noqa: BLE001
        history = []

    try:
        calibrated = float(calibrate_confidence(raw_score, "none", history))
    except Exception:  # noqa: BLE001
        calibrated = round(raw_score * 0.9, 3)

    return _to_json_safe({
        "valid_observation_days": valid_season_days,
        "expected_observation_days": expected_days,
        "data_completeness_ratio": round(completeness, 4),
        "history_days": history_days,
        "history_years": history_years,
        "has_multiyear_climatology": has_multiyear,
        "has_real_gwetroot": has_gwetroot,
        "projection_method": projection_method,
        "source": source,
        "raw_climate_confidence": round(raw_score, 3),
        "calibrated_confidence_estimate": round(calibrated, 3),
        "calibration_observations": len(history),
    })


def _compute_per_crop_gdd(
    df_obs: pd.DataFrame,
    season_start_dt: pd.Timestamp,
    current_dt: pd.Timestamp,
    season_end_dt: pd.Timestamp,
    lat: float,
    lon: float,
    resolved_hemisphere: str,
    is_tropical: bool,
    primary_tbase_c: float,
    primary_acc: float,
    primary_rem: float,
) -> dict[str, dict[str, float]]:
    in_season = df_obs[
        (df_obs["date"] >= season_start_dt) & (df_obs["date"] <= current_dt)
    ]
    rem_cache: dict[float, float] = {float(primary_tbase_c): primary_rem}
    acc_cache: dict[float, float] = {float(primary_tbase_c): primary_acc}

    per_crop: dict[str, dict[str, float]] = {}
    for crop_name, crop_base in CROP_TBASE.items():
        base = float(crop_base)
        if base not in acc_cache:
            col = _crop_col_slug(crop_name)
            if col in in_season.columns:
                acc_val = float(in_season[col].sum())
            else:
                acc_val = float(
                    (in_season["tmean"] - base).clip(lower=0.0).sum()
                )
            acc_cache[base] = acc_val

        if base not in rem_cache:
            rem_val, _ = _project_future_gdd(
                df_obs=df_obs,
                season_start_dt=season_start_dt,
                current_dt=current_dt,
                season_end_dt=season_end_dt,
                tbase_c=base,
                lat=lat,
                lon=lon,
                resolved_hemisphere=resolved_hemisphere,
                is_tropical=is_tropical,
            )
            rem_cache[base] = rem_val

        c_acc = acc_cache[base]
        c_rem = rem_cache[base]
        per_crop[crop_name] = {
            "tbase_c": base,
            "gdd_accumulated": round(c_acc, 1),
            "gdd_remaining": round(c_rem, 1),
            "gdd_to_frost": round(c_acc + c_rem, 1),
        }
    return per_crop


def _build_thresholds_contract() -> dict[str, Any]:
    return {
        "frost_threshold_c": float(FROST_THRESHOLD_C),
        "tropical_latitude_deg": float(TROPICAL_LATITUDE),
        "frost_north_start_doy": int(FROST_NORTH_START_DOY),
        "frost_south_doy_range": list(FROST_SOUTH_DOY_RANGE),
        "heat_wave_tmax_c": float(HEAT_WAVE_TMAX_C),
        "heat_wave_min_days": int(HEAT_WAVE_MIN_DAYS),
        "default_tbase_c": float(DEFAULT_TBASE_C),
        "safety_margin": float(SAFETY_MARGIN),
        "crop_tbase_c": {k: float(v) for k, v in CROP_TBASE.items()},
    }


def fetch_power_gdd(
    lat: float,
    lon: float,
    season_start: str,
    current_date: str,
    baseline_dir: str | None = None,
    demo_name: str | None = None,
    hemisphere: str | None = None,
    demo_mode: bool = True,

    api_mode: str | None = None,
    power_df: pd.DataFrame | None = None,
    tbase_c: float = DEFAULT_TBASE_C,
    power: pd.DataFrame | None = None,
    baselines: dict[str, Any] | None = None,

) -> GddResult:
    """Compute GDD accumulated and projected remaining to season end.

    Multi-hemisphere and tropical aware, with strict zero look-ahead:
    all observations after ``current_date`` are excluded before computing any
    GDD, frost, heat-wave, soil, or stage metric.

    Args:
        lat, lon: field coordinates in decimal degrees.
        season_start: ISO date season began.
        current_date: ISO observation cutoff date ("now").
        baseline_dir: optional local baseline directory.
        demo_name: demo scenario key ("flood", "drought", "normal", ...).
        hemisphere: "auto" | "north" | "south" (default auto from lat sign).
        demo_mode: True for cache-only demo mode; False for live ingestion.
        api_mode: optional "demo" | "live" override for ``demo_mode``.
        power_df: optional caller-provided NASA POWER DataFrame.
        tbase_c: crop base temperature in degC (default ``DEFAULT_TBASE_C``).

    Returns:
        GddResult with accumulated, projected remaining, frost/season-end date,
        avg_daily_gdd, resolved hemisphere, and rich telemetry ``details``.
    """
    lat_f = float(lat)
    lon_f = float(lon)
    if not (-90.0 <= lat_f <= 90.0):
        raise ValueError(f"lat must be within [-90, 90], got {lat}")
    if not (-180.0 <= lon_f <= 180.0):
        raise ValueError(f"lon must be within [-180, 180], got {lon}")

    tbase_f = float(tbase_c)
    if math.isnan(tbase_f) or math.isinf(tbase_f):
        raise ValueError(f"tbase_c must be finite, got {tbase_c}")

    effective_demo, mode_label = _resolve_execution_mode(demo_mode, api_mode)
    hem_req, resolved_hem, is_tropical = _resolve_hemisphere(lat_f, hemisphere)

    season_start_dt = _parse_iso_ts(season_start, "season_start")
    current_dt = _parse_iso_ts(current_date, "current_date")

    # Live-path alias from feat/herramientas-vivos (`power=` / `baselines=`).
    if power_df is None and power is not None:
        power_df = power
    caller_baselines = baselines

    raw_df, loaded_baselines, source_meta = _load_climate_inputs(
        lat=lat_f,
        lon=lon_f,
        season_start_dt=season_start_dt,
        current_dt=current_dt,
        baseline_dir=baseline_dir,
        demo_name=demo_name,
        effective_demo=effective_demo,
        power_df=power_df,
        baselines_override=(
            caller_baselines if power_df is not None and caller_baselines is not None else None
        ),
    )
    baselines = dict(loaded_baselines)
    if caller_baselines:
        baselines.update(caller_baselines)

    frost_ref = (
        baselines.get("climatological_frost_date")
        or baselines.get("season_end")
    )
    # Caller passed baselines without a frost/season-end bound → no_data.
    explicit_unbounded = caller_baselines is not None and not frost_ref

    norm_df = _normalize_power_dataframe(raw_df, tbase_c=tbase_f)

    # Q5 zero look-ahead invariant: strictly exclude all future rows first.
    df_obs = norm_df[norm_df["date"] <= current_dt].copy()

    season_info = _resolve_season_end(
        lat=lat_f,
        resolved_hemisphere=resolved_hem,
        is_tropical=is_tropical,
        season_start_dt=season_start_dt,
        baselines=baselines,
        df_obs=df_obs,
    )
    season_end_dt: pd.Timestamp = season_info["season_end_dt"]

    mask_acc = (
        (df_obs["date"] >= season_start_dt) & (df_obs["date"] <= current_dt)
    )
    gdd_series = df_obs.loc[mask_acc, "gdd_daily"].dropna()
    gdd_accumulated = float(gdd_series.sum()) if not gdd_series.empty else 0.0

    normals = baselines.get("monthly_gdd_normal") or None
    if normals and frost_ref and not explicit_unbounded:
        # Live path: observations end today; remaining GDD from monthly normals.
        remaining_days = pd.date_range(
            current_dt + pd.Timedelta(days=1), season_end_dt, freq="D"
        )
        gdd_remaining = float(
            sum(
                float(normals.get(str(d.month), normals.get(d.month, 0.0)) or 0.0)
                for d in remaining_days
            )
        )
        projection_method = "climatological_projection"
        remaining_method = "climatological_projection"
    else:
        gdd_remaining, projection_method = _project_future_gdd(
            df_obs=df_obs,
            season_start_dt=season_start_dt,
            current_dt=current_dt,
            season_end_dt=season_end_dt,
            tbase_c=tbase_f,
            lat=lat_f,
            lon=lon_f,
            resolved_hemisphere=resolved_hem,
            is_tropical=is_tropical,
        )
        # Demo/cache path (or live without monthly normals): label as observed_cache.
        remaining_method = "observed_cache"
    gdd_to_frost = gdd_accumulated + gdd_remaining

    if explicit_unbounded:
        data_status: dict[str, Any] = {
            "status": "no_data",
            "route": "stop",
            "reason": (
                "No frost date or season end for this region; "
                "the GDD window cannot be bounded."
            ),
        }
    elif not bool(mask_acc.any()):
        data_status = {
            "status": "no_data",
            "route": "stop",
            "reason": (
                "No temperature observations between the season start and today."
            ),
        }
    else:
        data_status = {
            "status": "ok",
            "route": "recommend",
            "reason": "GDD window computed.",
        }

    start14 = current_dt - pd.Timedelta(days=13)
    mask_avg = (df_obs["date"] >= start14) & (df_obs["date"] <= current_dt)
    avg_window = df_obs.loc[mask_avg, "gdd_daily"].dropna()
    if not avg_window.empty:
        avg_daily_gdd = float(avg_window.mean())
    elif not gdd_series.empty:
        avg_daily_gdd = float(gdd_series.mean())
    else:
        all_valid = df_obs["gdd_daily"].dropna()
        avg_daily_gdd = float(all_valid.mean()) if not all_valid.empty else 0.0

    season_stage = detect_season_stage(
        gdd_accumulated=gdd_accumulated,
        gdd_remaining=gdd_remaining,
        total_season_gdd=gdd_to_frost,
        current_date=current_dt.strftime("%Y-%m-%d"),
        season_start=season_start_dt.strftime("%Y-%m-%d"),
        season_end=season_info["season_end_str"],
        is_tropical=is_tropical,
    )
    per_crop_gdd = _compute_per_crop_gdd(
        df_obs=df_obs,
        season_start_dt=season_start_dt,
        current_dt=current_dt,
        season_end_dt=season_end_dt,
        lat=lat_f,
        lon=lon_f,
        resolved_hemisphere=resolved_hem,
        is_tropical=is_tropical,
        primary_tbase_c=tbase_f,
        primary_acc=gdd_accumulated,
        primary_rem=gdd_remaining,
    )
    ola_calor = _compute_heat_wave_from_obs(df_obs, lat_f, lon_f, current_dt)
    soil_allow_demo = (
        effective_demo
        or bool(source_meta.get("fallback_reason"))
        or source_meta.get("source") == "sintetico"
    )
    suelo = _build_soil_telemetry(
        lat_f, lon_f, season_start_dt, current_dt, df_obs, soil_allow_demo
    )
    fuente_datos = {
        "source": source_meta["source"],
        "mode": mode_label,
        "power_used": bool(source_meta["power_used"]),
        "imerg_used": bool(source_meta["imerg_used"]),
        "fallback_reason": source_meta["fallback_reason"],
        "cache_used": bool(source_meta["cache_used"]),
        "demo_scenario": source_meta["demo_scenario"],
        "region": source_meta["region"],
        "timestamp": _utc_now_iso(),
    }
    confianza_inputs = _build_confidence_inputs(
        lat=lat_f,
        lon=lon_f,
        season_start_dt=season_start_dt,
        current_dt=current_dt,
        df_obs=df_obs,
        projection_method=projection_method,
        source=fuente_datos["source"],
    )
    thresholds = _build_thresholds_contract()
    units = _to_json_safe(dict(CLIMATE_UNITS))

    agronomic_metadata = {
        "climate_regime": season_info["climate_regime"],
        "hemisphere": resolved_hem,
        "tropical": is_tropical,
        "has_climatological_frost": season_info["has_climatological_frost"],
        "season_end": season_info["season_end_str"],
        "season_end_method": season_info["season_end_method"],
        "season_stage": season_stage["stage"],
        "gdd_progress_ratio": season_stage["progress_ratio"],
        "gdd_accumulated": round(gdd_accumulated, 1),
        "gdd_remaining": round(gdd_remaining, 1),
        "gdd_to_frost": round(gdd_to_frost, 1),
        "avg_daily_gdd": round(avg_daily_gdd, 2),
        "usable_gdd_with_margin": round(gdd_remaining * SAFETY_MARGIN, 1),
        "heat_wave_active": bool(ola_calor.get("detected", False)),
        "moisture_status": suelo.get("moisture_status", "unknown"),
        "data_source": fuente_datos["source"],
        "demo_mode": effective_demo,
        "lookahead_excluded": True,
        "caveat": (
            "Typical climatological thresholds; local calibration required."
        ),
    }

    details: dict[str, Any] = _to_json_safe({
        "gdd_to_frost": round(gdd_to_frost, 1),
        "frost_date": season_info["season_end_str"],
        "frost_baseline_date": season_info["frost_baseline_date"],
        "tbase_c": tbase_f,
        "season_start": season_start,
        "current_date": current_date,
        "lat": lat_f,
        "lon": lon_f,
        "hemisphere_requested": hem_req,
        "hemisphere_resolved": resolved_hem,
        "climate_regime": season_info["climate_regime"],
        "tropical": is_tropical,
        "has_climatological_frost": season_info["has_climatological_frost"],
        "season_end": season_info["season_end_str"],
        "season_end_method": season_info["season_end_method"],
        "method": season_info["method"],
        "projection_method": projection_method,
        "remaining_method": remaining_method,
        "data_status": data_status,
        "lookahead_excluded": True,
        "observations_cutoff_date": current_dt.strftime("%Y-%m-%d"),
        "api_mode": mode_label,
        "demo_mode": effective_demo,
        "season_stage": season_stage,
        "season_stage_name": season_stage["stage"],
        "per_crop_gdd": per_crop_gdd,
        "ola_calor": ola_calor,
        "suelo": suelo,
        "confianza_calibrada_inputs": confianza_inputs,
        "fuente_datos": fuente_datos,
        "units": units,
        "thresholds": thresholds,
        "agronomic_metadata": agronomic_metadata,
    })

    return GddResult(
        gdd_accumulated=round(gdd_accumulated, 1),
        gdd_remaining=round(gdd_remaining, 1),
        frost_date=season_info["season_end_str"],
        avg_daily_gdd=round(avg_daily_gdd, 2),
        hemisphere=resolved_hem,
        details=details,
    )


def build_climate_contract_bundle(
    gdd_result: GddResult,
    event_confidence: float | None = None,
    event_type: str = "none",
) -> dict[str, Any]:
    """Build a JSON-safe climate contract bundle from a ``GddResult``."""
    d = dict(gdd_result.details or {})
    bundle: dict[str, Any] = {
        "gdd_accumulated": float(gdd_result.gdd_accumulated),
        "gdd_remaining": float(gdd_result.gdd_remaining),
        "gdd_to_frost": d.get(
            "gdd_to_frost",
            round(gdd_result.gdd_accumulated + gdd_result.gdd_remaining, 1),
        ),
        "avg_daily_gdd": float(gdd_result.avg_daily_gdd),
        "frost_date": str(gdd_result.frost_date),
        "hemisphere": str(gdd_result.hemisphere),
        "climate_regime": d.get("climate_regime"),
        "tropical": d.get("tropical"),
        "has_climatological_frost": d.get("has_climatological_frost"),
        "season_start": d.get("season_start"),
        "current_date": d.get("current_date"),
        "season_end": d.get("season_end", gdd_result.frost_date),
        "season_end_method": d.get("season_end_method"),
        "season_stage": d.get("season_stage"),
        "per_crop_gdd": d.get("per_crop_gdd"),
        "ola_calor": d.get("ola_calor"),
        "suelo": d.get("suelo"),
        "confianza_calibrada_inputs": d.get("confianza_calibrada_inputs"),
        "fuente_datos": d.get("fuente_datos"),
        "units": d.get("units", dict(CLIMATE_UNITS)),
        "thresholds": d.get("thresholds", _build_thresholds_contract()),
        "agronomic_metadata": d.get("agronomic_metadata"),
    }
    if event_confidence is not None:
        raw_ev = max(0.0, min(1.0, float(event_confidence)))
        lat = d.get("lat")
        lon = d.get("lon")
        try:
            hist = (
                _calibration.validation_history(float(lat), float(lon))
                if (lat is not None and lon is not None)
                else []
            )
            cal_ev = float(
                calibrate_confidence(
                    raw_ev, str(event_type or "none"), hist
                )
            )
        except Exception:  # noqa: BLE001
            cal_ev = raw_ev * 0.9
        bundle["event_confidence_input"] = round(raw_ev, 3)
        bundle["event_confidence_calibrated"] = round(cal_ev, 3)

    return _to_json_safe(bundle)


def _validate_single_site(
    label: str,
    lat: float,
    lon: float,
    hemisphere: str,
    power_df: pd.DataFrame,
    season_start: str,
    current_date: str,
    demo_name: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    is_tropical = abs(float(lat)) < TROPICAL_LATITUDE
    frost_stats = compute_climatological_frost_date(
        power_df, lat=lat, hemisphere=hemisphere
    )
    gdd_res = fetch_power_gdd(
        lat=lat,
        lon=lon,
        season_start=season_start,
        current_date=current_date,
        demo_name=demo_name,
        hemisphere=hemisphere,
        demo_mode=True,
        power_df=None if demo_name else power_df,
    )
    details = gdd_res.details or {}

    if is_tropical:
        if frost_stats["has_climatological_frost"] is not False:
            failures.append(f"{label}: tropical flagged as having frost")
        if details.get("season_end_method") != "rainy_season_end":
            failures.append(f"{label}: tropical season_end_method mismatch")
        if frost_stats["frost_years"] != 0:
            failures.append(f"{label}: unexpected frost years in tropics")
    else:
        if frost_stats["has_climatological_frost"] is not True:
            failures.append(f"{label}: temperate missing frost flag")
        if details.get("season_end_method") != "climatological_frost":
            failures.append(f"{label}: temperate season_end_method mismatch")
        med_doy = frost_stats.get("median_doy")
        if med_doy is None:
            failures.append(f"{label}: no median frost DOY computed")
        else:
            if hemisphere == "north" and med_doy < FROST_NORTH_START_DOY:
                failures.append(
                    f"{label}: north median DOY {med_doy} < "
                    f"{FROST_NORTH_START_DOY}"
                )
            lo, hi = FROST_SOUTH_DOY_RANGE
            if hemisphere == "south" and not (lo < med_doy <= hi):
                failures.append(
                    f"{label}: south median DOY {med_doy} outside ({lo}, {hi}]"
                )
            diff = frost_stats.get("doy_diff_vs_band")
            if diff is not None and diff > 45.0:
                failures.append(
                    f"{label}: median DOY diff vs band {diff} > 45d"
                )

    summary = {
        "lat": float(lat),
        "lon": float(lon),
        "hemisphere": hemisphere,
        "tropical": is_tropical,
        "frost_stats": frost_stats,
        "frost_date": gdd_res.frost_date,
        "season_end_method": details.get("season_end_method"),
        "gdd_accumulated": gdd_res.gdd_accumulated,
        "gdd_remaining": gdd_res.gdd_remaining,
        "season_stage": details.get("season_stage_name"),
    }
    return summary, failures


def validate_hemisphere_frost_baselines(
    extra_sites: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate frost/season-end logic across bands, scenarios, and regimes.

    Runs strictly offline using cached demo data and deterministic synthetic
    series for non-demo latitudes (e.g. Southern Hemisphere).
    """
    failures: list[str] = []
    checks_total = 0
    checks_passed = 0

    # 1. Validate frost bands schema
    bands = _call_load_frost_bands()
    checks_total += 1
    bands_valid = bool(bands.get("north") and bands.get("south"))
    for hem_key in ("north", "south"):
        for b in bands.get(hem_key, []):
            if not {"lat_min", "lat_max", "first_frost"} <= set(b):
                bands_valid = False
    if bands_valid:
        checks_passed += 1
    else:
        failures.append("Frost bands missing required north/south fields")

    # 2. Validate cached demo scenarios
    scenarios_out: dict[str, Any] = {}
    for name in _cache_loader.SCENARIOS:
        checks_total += 1
        pkt = _cache_loader.load_demo_packet(name)
        df = _call_load_power(name)
        hem = "south" if float(pkt["lat"]) < 0 else "north"
        summary, site_fails = _validate_single_site(
            label=f"scenario:{name}",
            lat=float(pkt["lat"]),
            lon=float(pkt["lon"]),
            hemisphere=hem,
            power_df=df,
            season_start=str(pkt["season_start"]),
            current_date=str(pkt["current_date"]),
            demo_name=name,
        )
        scenarios_out[name] = summary
        if not site_fails:
            checks_passed += 1
        failures.extend(site_fails)

    # 3. Validate representative climate regimes (north, south, tropical)
    regimes_out: dict[str, Any] = {}
    for regime_key, cfg in REPRESENTATIVE_REGIME_COORDINATES.items():
        checks_total += 1
        lat = float(cfg["lat"])
        lon = float(cfg["lon"])
        hem = str(cfg["hemisphere"])
        demo_scen = cfg.get("demo_scenario")
        if demo_scen and demo_scen in _cache_loader.SCENARIOS:
            pkt = _cache_loader.load_demo_packet(demo_scen)
            df = _call_load_power(demo_scen)
            s_start = str(pkt["season_start"])
            c_date = str(pkt["current_date"])
        else:
            if hem == "south" and abs(lat) >= TROPICAL_LATITUDE:
                s_start, c_date = "2025-10-01", "2025-12-15"
            else:
                s_start, c_date = "2025-04-01", "2025-05-15"
            df = _generate_cache.generate_power(
                c_date, "2015-01-01", lat, season_end=None
            )
            demo_scen = None

        summary, site_fails = _validate_single_site(
            label=f"regime:{regime_key}",
            lat=lat,
            lon=lon,
            hemisphere=hem,
            power_df=df,
            season_start=s_start,
            current_date=c_date,
            demo_name=demo_scen,
        )
        regimes_out[regime_key] = summary
        if not site_fails:
            checks_passed += 1
        failures.extend(site_fails)

    # 4. Validate Southern Hemisphere cross-year Dec -> Feb continuity
    checks_total += 1
    south_df = _generate_cache.generate_power(
        "2026-04-30", "2015-01-01", -33.9, season_end=None
    )
    dec_res = fetch_power_gdd(
        lat=-33.9,
        lon=18.4,
        season_start="2025-10-01",
        current_date="2025-12-15",
        hemisphere="south",
        demo_mode=True,
        power_df=south_df,
    )
    feb_res = fetch_power_gdd(
        lat=-33.9,
        lon=18.4,
        season_start="2025-10-01",
        current_date="2026-02-15",
        hemisphere="south",
        demo_mode=True,
        power_df=south_df,
    )
    cross_year_ok = (
        dec_res.frost_date == feb_res.frost_date
        and feb_res.gdd_accumulated >= dec_res.gdd_accumulated
        and feb_res.gdd_remaining <= dec_res.gdd_remaining
    )
    if cross_year_ok:
        checks_passed += 1
    else:
        failures.append(
            "Southern Hemisphere Dec->Feb continuity failed: "
            f"dec={dec_res.frost_date}, feb={feb_res.frost_date}"
        )

    # 5. Optional caller-provided extra sites
    extra_out: list[dict[str, Any]] = []
    for idx, site in enumerate(extra_sites or []):
        checks_total += 1
        s_lat = float(site["lat"])
        s_lon = float(site.get("lon", 0.0))
        s_hem = str(
            site.get("hemisphere") or ("south" if s_lat < 0 else "north")
        )
        s_label = str(site.get("name") or f"extra_{idx}")
        s_start = str(
            site.get("season_start")
            or ("2025-10-01" if s_hem == "south" else "2025-04-01")
        )
        s_cur = str(
            site.get("current_date")
            or ("2025-12-15" if s_hem == "south" else "2025-05-15")
        )
        s_df = site.get("power_df")
        if s_df is None:
            s_df = _generate_cache.generate_power(
                s_cur, "2015-01-01", s_lat, season_end=None
            )
        summary, site_fails = _validate_single_site(
            label=f"extra:{s_label}",
            lat=s_lat,
            lon=s_lon,
            hemisphere=s_hem,
            power_df=s_df,
            season_start=s_start,
            current_date=s_cur,
        )
        summary["name"] = s_label
        extra_out.append(summary)
        if not site_fails:
            checks_passed += 1
        failures.extend(site_fails)

    return _to_json_safe({
        "passed": len(failures) == 0,
        "checks_total": checks_total,
        "checks_passed": checks_passed,
        "failures": failures,
        "frost_bands_valid": bands_valid,
        "scenarios": scenarios_out,
        "regimes": regimes_out,
        "cross_year_south_continuity": {
            "passed": cross_year_ok,
            "dec_frost_date": dec_res.frost_date,
            "feb_frost_date": feb_res.frost_date,
            "dec_gdd_accumulated": dec_res.gdd_accumulated,
            "feb_gdd_accumulated": feb_res.gdd_accumulated,
            "dec_gdd_remaining": dec_res.gdd_remaining,
            "feb_gdd_remaining": feb_res.gdd_remaining,
        },
        "extra_sites": extra_out,
        "offline_safe": True,
    })


__all__ = [
    "fetch_power_gdd",
    "compute_climatological_frost_date",
    "validate_hemisphere_frost_baselines",
    "detect_season_stage",
    "build_climate_contract_bundle",
    "load_power",
    "load_baselines",
    "load_frost_bands",
]
