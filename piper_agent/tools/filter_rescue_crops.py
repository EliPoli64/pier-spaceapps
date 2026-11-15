"""BR-2, BR-3, BR-4, BR-8, BR-10: filter_rescue_crops — rescue-crop filtering by event type, GDD window, and farmer priorities.

- BR-2: Event type drives the filter — never both at once.
  flood → waterlogging_tolerance ≥ Medium (exclude Low)
  drought → drought_tolerance ≥ Medium (exclude Low)
- BR-3: GDD-based window — eligible only if gdd_req ≤ gdd_remaining × 0.8 (20% safety margin)
- BR-4: Explicit plant-by date; rank by latest feasible plant-by date first
- BR-8: Exclusion explanations are available via explain_exclusion
- BR-10: Farmer priorities re-rank eligible crops by composite score
"""
from __future__ import annotations

import math
import os
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from piper_agent.contracts import (
    CropRecommendation,
    SAFETY_MARGIN,
    TOLERANCE_ORDINAL,
)

DEFAULT_CROPS_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "rescue_crops.csv")


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """Normalize farmer weights to sum to 1.0."""
    total = sum(weights.values())
    if total <= 0:
        return {"soil_protection": 1.0 / 3, "salvage_revenue": 1.0 / 3, "water_conservation": 1.0 / 3}
    return {k: v / total for k, v in weights.items()}


def _composite_score(
    row: pd.Series,
    weights: dict[str, float],
    event_type: str,
    gdd_remaining: float,
) -> float:
    """Compute composite score from farmer weights and crop attributes.

    Criteria (each 0-1):
      - soil_protection: residue_cover_pct / 100 (higher = better soil cover)
      - salvage_revenue: market_value_usd_ton / max_market_value (higher = more revenue)
      - water_conservation: 1 - irrigation_requirement_mm / max_irrigation (lower water need = better)
    """
    max_market = 600.0  # approximate max across crop DB
    max_irrigation = 500.0  # approximate max across crop DB

    soil_prot = float(row.get("residue_cover_pct", 50)) / 100.0
    salvage = float(row.get("market_value_usd_ton", 200)) / max_market
    water_cons = 1.0 - (float(row.get("irrigation_requirement_mm", 300)) / max_irrigation)

    score = (
        weights.get("soil_protection", 1/3) * soil_prot
        + weights.get("salvage_revenue", 1/3) * salvage
        + weights.get("water_conservation", 1/3) * water_cons
    )
    return max(0.0, min(1.0, score))


def filter_rescue_crops(
    event_type: str,
    gdd_remaining: float,
    current_date: str,
    avg_daily_gdd: float,
    crops_csv: str | None = None,
    farmer_weights: dict[str, float] | None = None,
) -> list[CropRecommendation]:
    """Filter and rank rescue crops for the given event and GDD window.

    Args:
        event_type: "flood" | "drought" | "none"
        gdd_remaining: GDD remaining to climatological frost
        current_date: ISO date "now"
        avg_daily_gdd: average daily GDD (for plant-by date calc)
        crops_csv: path to rescue_crops.csv (default: the one next to the data layer,
            independent of the working directory)
        farmer_weights: optional dict with keys soil_protection, salvage_revenue,
            water_conservation (each 0-1). If provided, re-ranks by composite
            score (BR-10) instead of plant-by date.

    Returns:
        List of CropRecommendation. Empty list if no crop eligible
        (BR-5 fallback handled by caller).
    """
    df = pd.read_csv(crops_csv or DEFAULT_CROPS_CSV)

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

        # Rescue confidence: how much of the window the crop leaves free. Every eligible crop
        # already clears the 20% margin, so confidence runs from 0.5 (just clears it) to 1.0
        # (needs 30% or less of the window); the old headroom ratio was always >= 1.
        headroom = gdd_remaining - gdd_req
        free_share = headroom / gdd_remaining if gdd_remaining > 0 else 0.0
        rescue_confidence = min(1.0, max(0.0, 0.5 + 0.5 * (free_share - 0.2) / 0.5))

        margin_pct = (gdd_remaining - gdd_req) / gdd_remaining * 100.0 if gdd_remaining > 0 else 0.0

        # BR-10: composite score from farmer weights
        weights = _normalize_weights(farmer_weights or {})
        composite_score = _composite_score(row, weights, event_type, gdd_remaining)

        results.append(CropRecommendation(
            crop=str(row["crop"]),
            event_match=bool(row["event_match"]),
            gdd_requirement=round(gdd_req, 1),
            gdd_remaining=round(gdd_remaining, 1),
            margin_pct=round(margin_pct, 1),
            plant_by_date=plant_by_dt.isoformat(),
            days_until_deadline=days_until_deadline,
            rescue_confidence=round(rescue_confidence, 3),
            composite_score=round(composite_score, 3),
        ))

    # BR-10: if farmer weights provided, rank by composite score desc;
    # otherwise BR-4: rank by plant_by_date descending (latest first)
    if farmer_weights:
        results.sort(key=lambda c: c.composite_score, reverse=True)
    else:
        results.sort(key=lambda c: c.plant_by_date, reverse=True)
    return results
