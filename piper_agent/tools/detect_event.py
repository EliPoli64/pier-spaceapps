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

import pandas as pd

from piper_agent.contracts import EventResult, EventType
from piper_agent.data.cache_loader import load_baselines, load_imerg

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
) -> EventResult:
    """Detect flood/drought/none from IMERG daily rainfall anomaly.

    Args:
        lat, lon: field location (informational; data loaded by demo_name).
        recent_start, recent_end: ISO dates for the recent event window.
        baseline_dir: directory with baseline JSON (used if demo_name not given).
        demo_name: demo key ("flood", "drought", "normal") to load cached data.

    Returns:
        EventResult with event_type, severity, confidence, details.
    """
    # Load cached IMERG data
    if demo_name:
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

    # Baseline thresholds
    p95_cum3 = float(baselines.get("p95_3day_cum_rainfall", 50.0))
    p10_cum30 = float(baselines.get("p10_30day_cum_rainfall", 50.0))

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
) -> dict[str, Any]:
    """Detect heat-wave events from POWER T2M_MAX data.

    A heat wave is flagged when T2M_MAX exceeds `tmax_threshold_c` for
    `min_consecutive_days` or more consecutive days.

    Args:
        lat, lon: field location.
        recent_start, recent_end: ISO date range.
        demo_name: demo key for cached POWER data.
        tmax_threshold_c: temperature threshold in Celsius (default 35°C).
        min_consecutive_days: minimum consecutive days above threshold.

    Returns:
        dict with keys: event_type ("heat_wave" | "none"), confidence, details.
    """
    from piper_agent.data.cache_loader import load_power

    if demo_name:
        df = load_power(demo_name)
    else:
        raise ValueError("demo_name must be provided for heat wave detection")

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
        },
    }


__all__ = ["detect_event", "detect_heat_wave", "FLOOD_ABSOLUTE_MM"]

