"""BR-1: detect_event — IMERG rainfall anomaly event detection.

Event detection uses an anomaly threshold, not an absolute threshold.
- Flood: 3-day cumulative IMERG rainfall > min(p95 of 3-day cum baseline, 100mm)
- Drought: 30-day cumulative rainfall < p10 of 30-day cum baseline
- None: otherwise

Confidence is anomaly-magnitude based (0-1).
Uses cache_loader only — no live imergpy calls in demo mode.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from piper_agent.config import MIN_WINDOW_COVERAGE
from piper_agent.contracts import EventResult, EventType
from piper_agent.data.cache_loader import load_baselines, load_imerg
from piper_agent.tools.failure_taxonomy import classify_data_state

FLOOD_ABSOLUTE_MM = 100.0


def _severity(confidence: float) -> str:
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.40:
        return "medium"
    return "low"


def detect_event(
    lat: float,
    lon: float,
    recent_start: str,
    recent_end: str,
    baseline_dir: str | None = None,
    demo_name: str | None = None,
    demo_mode: bool = True,
    rainfall: pd.DataFrame | None = None,
    baselines: dict[str, Any] | None = None,
    alt_rainfall: pd.DataFrame | None = None,
    climatology: dict[str, Any] | None = None,
) -> EventResult:
    """Detect flood/drought/none from IMERG daily rainfall anomaly.

    Data source, in order: `rainfall` + `baselines` given by the caller (live path),
    `demo_name` / `baseline_dir` (cache), or, with `demo_mode=False` and nothing
    else, a live fetch through `live_inputs.load_live`.

    Args:
        lat, lon: field location (informational for the cache path).
        recent_start, recent_end: ISO dates for the recent event window.
        baseline_dir: directory with baseline JSON (used if demo_name not given).
        demo_name: demo key ("flood", "drought", "normal") to load cached data.
        demo_mode: False lets the tool fetch live data when no source was given.
        rainfall: DataFrame [date, precipitation_mm] from the live path.
        baselines: thresholds dict (p95_3day_cum_rainfall, p10_30day_cum_rainfall).
        alt_rainfall: the same rainfall from an independent source, to detect conflicts.
        climatology: regional climatology; adds a normal/extreme cross-check.

    Returns:
        EventResult with event_type, severity, confidence, details. `details["data_status"]`
        carries the failure taxonomy (no_data / conflicting / normal / event).
    """
    if rainfall is None and not demo_name and not baseline_dir and not demo_mode:
        from piper_agent.tools.live_inputs import load_live

        live = load_live(lat, lon, recent_end, demo_mode=False)
        rainfall, baselines, climatology = live["rainfall"], live["baselines"], live["climatology"]

    # Load rainfall data
    if rainfall is not None:
        df = rainfall.copy()
        df["date"] = pd.to_datetime(df["date"])
        baselines = baselines or {}
    elif demo_name:
        df = load_imerg(demo_name)
        baselines = load_baselines(demo_name)
    elif baseline_dir:
        import json
        import os
        df = load_imerg(os.path.basename(baseline_dir))
        with open(os.path.join(baseline_dir, f"{os.path.basename(baseline_dir)}_baselines.json")) as f:
            baselines = json.load(f)
    else:
        raise ValueError("Either demo_name or baseline_dir must be provided")

    df = df.sort_values("date").reset_index(drop=True)

    # BR-1: 3-day cumulative over recent window; 30-day cumulative ending at recent_end
    mask = (df["date"] >= recent_start) & (df["date"] <= recent_end)
    recent = df.loc[mask]
    cum3 = float(recent["precipitation_mm"].rolling(3, min_periods=1).sum().max())

    # 30-day window ending at recent_end (regardless of recent_start)
    end_dt = datetime.fromisoformat(recent_end).date()
    start30_dt = end_dt - timedelta(days=29)
    mask30 = (df["date"] >= pd.Timestamp(start30_dt)) & (df["date"] <= pd.Timestamp(recent_end))
    recent30 = df.loc[mask30]
    cum30 = float(recent30["precipitation_mm"].sum())

    days_observed_30d = int(recent30["precipitation_mm"].notna().sum())
    thresholds_ok = (baselines.get("p95_3day_cum_rainfall") is not None
                     and baselines.get("p10_30day_cum_rainfall") is not None)
    if recent.empty or not thresholds_ok or days_observed_30d < MIN_WINDOW_COVERAGE * 30:
        # Failure taxonomy: not enough to decide. Never report "drought" from missing rain.
        state = classify_data_state("none", days_observed_30d, thresholds_ok and not recent.empty)
        return EventResult(
            event_type="none", severity="low", confidence=0.0,
            details={"lat": lat, "lon": lon, "recent_start": recent_start, "recent_end": recent_end,
                     "days_observed_30d": days_observed_30d, "data_status": state,
                     "confidence": 0.0, "severity": "low"},
        )

    # Baseline thresholds
    p95_cum3 = float(baselines["p95_3day_cum_rainfall"])
    p10_cum30 = float(baselines["p10_30day_cum_rainfall"])

    # BR-1: flood threshold = min(p95, 100mm)
    flood_threshold = min(p95_cum3, FLOOD_ABSOLUTE_MM)

    event_type: EventType = "none"
    details: dict[str, Any] = {
        "cum3_mm": round(cum3, 2),
        "cum30_mm": round(cum30, 2),
        "flood_threshold_mm": round(flood_threshold, 2),
        "p95_3day_cum": round(p95_cum3, 2),
        "p10_30day_cum": round(p10_cum30, 2),
        "lat": lat,
        "lon": lon,
        "recent_start": recent_start,
        "recent_end": recent_end,
    }

    if cum3 > flood_threshold:
        event_type = "flood"
        # Confidence: threshold ≈ 0.6, 2x threshold ≈ 1.0
        ratio = cum3 / flood_threshold if flood_threshold > 0 else 0.0
        confidence = min(1.0, max(0.1, 0.6 + (ratio - 1.0) * 0.4))
    elif cum30 < p10_cum30:
        event_type = "drought"
        # Confidence: based on deficit magnitude
        ratio = (p10_cum30 - cum30) / p10_cum30 if p10_cum30 > 0 else 0.0
        confidence = min(1.0, max(0.1, 0.6 + ratio * 0.4))
    else:
        event_type = "none"
        anomaly = max(cum3 / flood_threshold if flood_threshold > 0 else 0,
                      cum30 / p10_cum30 if p10_cum30 > 0 else 0)
        confidence = max(0.1, 1.0 - min(1.0, anomaly))

    confidence = max(0.0, min(1.0, confidence))
    severity = _severity(confidence)
    details["confidence"] = round(confidence, 3)
    details["severity"] = severity
    details["days_observed_30d"] = days_observed_30d

    # Failure taxonomy: independent source and regional climatology cross-checks
    alt_cum3 = None
    if alt_rainfall is not None:
        alt = alt_rainfall.copy()
        alt["date"] = pd.to_datetime(alt["date"])
        alt_recent = alt.loc[(alt["date"] >= recent_start) & (alt["date"] <= recent_end)]
        if not alt_recent.empty:
            alt_cum3 = float(alt_recent["precipitation_mm"].rolling(3, min_periods=1).sum().max())
            details["alt_cum3_mm"] = round(alt_cum3, 2)
    clim_status = None
    if climatology is not None:
        from piper_agent.data.climatology import classify_value

        clim_status = classify_value(climatology, "rain_3d", cum3, recent_end)["status"]
    details["data_status"] = classify_data_state(
        event_type, days_observed_30d, True, cum3_mm=cum3, alt_cum3_mm=alt_cum3,
        climatology_status=clim_status,
    )

    return EventResult(
        event_type=event_type,
        severity=severity,
        confidence=confidence,
        details=details,
    )


def detect_heat_wave(
    lat: float,
    lon: float,
    recent_start: str,
    recent_end: str,
    demo_name: str | None = None,
    tmax_threshold_c: float = 35.0,
    min_consecutive_days: int = 3,
    power: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Detect heat-wave events from POWER T2M_MAX data.

    A heat wave is flagged when T2M_MAX exceeds `tmax_threshold_c` for
    `min_consecutive_days` or more consecutive days.

    Args:
        lat, lon: field location.
        recent_start, recent_end: ISO date range.
        demo_name: demo key for cached POWER data.
        power: DataFrame [date, T2M_MAX, ...] from the live path (used instead of the cache).
        tmax_threshold_c: temperature threshold in Celsius (default 35°C).
        min_consecutive_days: minimum consecutive days above threshold.

    Returns:
        dict with keys: event_type ("heat_wave" | "none"), confidence, details.
    """
    from piper_agent.data.cache_loader import load_power

    if power is not None:
        df = power.copy()
    elif demo_name:
        df = load_power(demo_name)
    else:
        raise ValueError("demo_name or power must be provided for heat wave detection")

    df = df.sort_values("date").reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"])

    mask = (df["date"] >= recent_start) & (df["date"] <= recent_end)
    recent = df.loc[mask].copy()

    # Count consecutive days above threshold
    recent["above_threshold"] = recent["T2M_MAX"] > tmax_threshold_c
    max_consecutive = 0
    current_streak = 0
    for above in recent["above_threshold"]:
        if above:
            current_streak += 1
            max_consecutive = max(max_consecutive, current_streak)
        else:
            current_streak = 0

    event_type = "heat_wave" if max_consecutive >= min_consecutive_days else "none"
    data_status = ("no_data" if recent.empty else "event" if event_type == "heat_wave" else "normal")

    # Confidence based on magnitude and duration
    if event_type == "heat_wave":
        max_tmax = float(recent["T2M_MAX"].max())
        exceedance = max_tmax - tmax_threshold_c
        confidence = min(1.0, max(0.1, 0.5 + (exceedance / 10.0) + (max_consecutive / 10.0)))
    else:
        max_tmax = float(recent["T2M_MAX"].max()) if not recent.empty else 0.0
        confidence = max(0.1, 1.0 - min(1.0, max_tmax / tmax_threshold_c))

    confidence = max(0.0, min(1.0, confidence))

    return {
        "event_type": event_type,
        "confidence": round(confidence, 3),
        "details": {
            "max_consecutive_days_above_threshold": max_consecutive,
            "min_consecutive_days": min_consecutive_days,
            "tmax_threshold_c": tmax_threshold_c,
            "max_tmax_c": round(max_tmax, 1),
            "lat": lat,
            "lon": lon,
            "recent_start": recent_start,
            "recent_end": recent_end,
            "data_status": data_status,
        },
    }


def detect_frost(
    lat: float,
    lon: float,
    recent_start: str,
    recent_end: str,
    demo_name: str | None = None,
    tmin_threshold_c: float = 0.0,
    power: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Detect a frost event from POWER T2M_MIN data.

    A frost is flagged when T2M_MIN is at or below `tmin_threshold_c` on any day of the
    window. It matters for the season: a frost before the climatological date shortens
    the GDD window and can kill an emerged crop.

    Args:
        lat, lon: field location.
        recent_start, recent_end: ISO date range.
        demo_name: demo key for cached POWER data.
        tmin_threshold_c: minimum temperature at or below which a day counts as frost.
        power: DataFrame [date, T2M_MIN, ...] from the live path (used instead of the cache).

    Returns:
        dict with keys: event_type ("frost" | "none"), confidence, details (min_tmin_c,
        frost_days, first_frost_date, data_status).
    """
    from piper_agent.data.cache_loader import load_power

    if power is not None:
        df = power.copy()
    elif demo_name:
        df = load_power(demo_name)
    else:
        raise ValueError("demo_name or power must be provided for frost detection")

    df["date"] = pd.to_datetime(df["date"])
    recent = df.loc[(df["date"] >= recent_start) & (df["date"] <= recent_end)]
    frost_days = recent.loc[recent["T2M_MIN"] <= tmin_threshold_c]

    if recent.empty:
        event_type, data_status, confidence, min_tmin = "none", "no_data", 0.0, None
    else:
        min_tmin = float(recent["T2M_MIN"].min())
        if frost_days.empty:
            event_type, data_status = "none", "normal"
            confidence = max(0.1, min(1.0, (min_tmin - tmin_threshold_c) / 10.0))
        else:
            event_type, data_status = "frost", "event"
            confidence = min(1.0, 0.6 + (tmin_threshold_c - min_tmin) / 10.0)

    return {
        "event_type": event_type,
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
        "details": {
            "min_tmin_c": None if min_tmin is None else round(min_tmin, 1),
            "tmin_threshold_c": tmin_threshold_c,
            "frost_days": int(len(frost_days)),
            "first_frost_date": None if frost_days.empty else frost_days["date"].min().strftime("%Y-%m-%d"),
            "lat": lat,
            "lon": lon,
            "recent_start": recent_start,
            "recent_end": recent_end,
            "data_status": data_status,
        },
    }


__all__ = ["detect_event", "detect_heat_wave", "detect_frost", "FLOOD_ABSOLUTE_MM"]

