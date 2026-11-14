"""BR-2, BR-3, BR-4: filter_rescue_crops — rescue-crop filtering by event type and GDD window.

- BR-2: Event type drives the filter — never both at once.
  flood → waterlogging_tolerance ≥ Medium (exclude Low)
  drought → drought_tolerance ≥ Medium (exclude Low)
- BR-3: GDD-based window — eligible only if gdd_req ≤ gdd_remaining × 0.8 (20% safety margin)
- BR-4: Explicit plant-by date; rank by latest feasible plant-by date first
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from piper_agent.contracts import (
    CropRecommendation,
    SAFETY_MARGIN,
    TOLERANCE_ORDINAL,
)


def filter_rescue_crops(
    event_type: str,
    gdd_remaining: float,
    current_date: str,
    avg_daily_gdd: float,
    crops_csv: str = "piper_agent/data/rescue_crops.csv",
) -> list[CropRecommendation]:
    """Filter and rank rescue crops for the given event and GDD window.

    Args:
        event_type: "flood" | "drought" | "none"
        gdd_remaining: GDD remaining to climatological frost
        current_date: ISO date "now"
        avg_daily_gdd: average daily GDD (for plant-by date calc)
        crops_csv: path to rescue_crops.csv

    Returns:
        List of CropRecommendation ranked by plant_by_date descending (latest first).
        Empty list if no crop eligible (BR-5 fallback handled by caller).
    """
    df = pd.read_csv(crops_csv)

    # Map tolerance text to ordinal
    df["wl_ord"] = df["waterlogging_tolerance"].map(TOLERANCE_ORDINAL)
    df["dt_ord"] = df["drought_tolerance"].map(TOLERANCE_ORDINAL)

    # BR-2: event-type filter, never both at once
    if event_type == "flood":
        df = df[df["wl_ord"] >= TOLERANCE_ORDINAL["Medium"]].copy()
        df["event_match"] = True
    elif event_type == "drought":
        df = df[df["dt_ord"] >= TOLERANCE_ORDINAL["Medium"]].copy()
        df["event_match"] = True
    else:
        # no event → no rescue crop filtering by tolerance
        df["event_match"] = False

    if df.empty:
        return []

    # BR-3: GDD-based eligibility — conservative (max) GDD to maturity
    gdd_limit = gdd_remaining * SAFETY_MARGIN  # 20% safety margin
    df = df[df["gdd_to_maturity_max"] <= gdd_limit].copy()

    if df.empty:
        return []

    current_dt = datetime.fromisoformat(current_date).date()

    results: list[CropRecommendation] = []
    for _, row in df.iterrows():
        gdd_req = float(row["gdd_to_maturity_max"])
        # BR-4: plant_by_date = current_date + (gdd_remaining - gdd_req) / avg_daily_gdd
        if avg_daily_gdd > 0:
            days_available = (gdd_remaining - gdd_req) / avg_daily_gdd
            days_until_deadline = max(0, math.ceil(days_available))
        else:
            days_until_deadline = 0
        plant_by_dt = current_dt + timedelta(days=days_until_deadline)

        # Rescue confidence: headroom beyond the 20% margin
        headroom = gdd_remaining - gdd_req
        margin_buffer = gdd_remaining * 0.2  # the 20% safety margin
        rescue_confidence = min(1.0, max(0.0, headroom / margin_buffer)) if margin_buffer > 0 else 0.0

        margin_pct = (gdd_remaining - gdd_req) / gdd_remaining * 100.0 if gdd_remaining > 0 else 0.0

        results.append(CropRecommendation(
            crop=str(row["crop"]),
            event_match=bool(row["event_match"]),
            gdd_requirement=round(gdd_req, 1),
            gdd_remaining=round(gdd_remaining, 1),
            margin_pct=round(margin_pct, 1),
            plant_by_date=plant_by_dt.isoformat(),
            days_until_deadline=days_until_deadline,
            rescue_confidence=round(rescue_confidence, 3),
        ))

    # BR-4: rank by plant_by_date descending (latest feasible plant-by date first)
    results.sort(key=lambda c: c.plant_by_date, reverse=True)
    return results
