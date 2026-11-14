"""Shared data contracts between PIER stages.

Only Stage 0 / Branch A modifies this file. All later stages import from it.
"""
from dataclasses import dataclass
from typing import Literal, Optional
from datetime import date

EventType = Literal["flood", "drought", "none"]
Tolerance = Literal["Low", "Medium", "High"]

TOLERANCE_ORDINAL = {"Low": 1, "Medium": 2, "High": 3}
DEFAULT_TBASE_C = 10.0
SAFETY_MARGIN = 0.8

# Per-crop GDD base temperatures (Spec §3)
CROP_TBASE = {
    "Sorghum": 10.0,
    "Millet": 10.0,
    "Buckwheat": 5.0,
    "Cowpea": 10.0,
    "Cereal rye (cover)": 0.0,
}


@dataclass
class EventResult:
    event_type: EventType
    severity: str            # "low" | "medium" | "high"
    confidence: float        # 0..1, anomaly-magnitude based (BR-6)
    details: dict            # cum3, cum30, flood_threshold, p10, p95


@dataclass
class GddResult:
    gdd_accumulated: float
    gdd_remaining: float
    frost_date: str          # ISO date
    avg_daily_gdd: float
    details: dict


@dataclass
class CropRecommendation:
    crop: str
    event_match: bool
    gdd_requirement: float   # conservative max GDD to maturity
    gdd_remaining: float
    margin_pct: float
    plant_by_date: str       # ISO date (BR-4)
    days_until_deadline: int
    rescue_confidence: float # 0..1, GDD-margin based (BR-6)
    composite_score: float | None = None  # 0..1, farmer-priority composite (BR-10)


@dataclass
class RecoveryPlan:
    event_type: EventType
    event_confidence: float
    rescue_confidence: float
    gdd_accumulated: float
    gdd_remaining: float
    frost_date: str
    fallback: bool           # True when BR-5 cover-crop path triggers
    crops: list
    plan_text: str
