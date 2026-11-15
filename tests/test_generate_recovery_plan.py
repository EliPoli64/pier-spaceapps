"""Smoke tests for Stage 4: generate_recovery_plan (BR-5, BR-6)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date

from piper_agent.contracts import (
    EventResult,
    GddResult,
    CropRecommendation,
)
from piper_agent.tools.generate_recovery_plan import generate_recovery_plan


def _event(etype: str, conf: float) -> EventResult:
    return EventResult(
        event_type=etype,
        severity="high" if conf > 0.7 else "medium",
        confidence=conf,
        details={"cum3_mm": 100.0, "cum30_mm": 50.0},
    )


def _gdd(acc: float, rem: float, frost: str, hemi: str = "north") -> GddResult:
    return GddResult(
        gdd_accumulated=acc,
        gdd_remaining=rem,
        frost_date=frost,
        avg_daily_gdd=15.0,
        hemisphere=hemi,
        details={},
    )


def _crop(name: str, req: float, conf: str = "2025-07-15", rc: float = 0.8) -> CropRecommendation:
    return CropRecommendation(
        crop=name,
        event_match=True,
        gdd_requirement=req,
        gdd_remaining=1000.0,
        margin_pct=20.0,
        plant_by_date=conf,
        days_until_deadline=20,
        rescue_confidence=rc,
    )


def test_flood_plan_separate_confidences():
    plan_text, rp = generate_recovery_plan(
        _event("flood", 0.85),
        _gdd(1500.0, 1000.0, "2025-10-04"),
        [_crop("Cowpea", 1300.0), _crop("Cereal rye (cover)", 900.0)],
        date(2025, 6, 25),
    )
    assert "Event detection: flood" in plan_text
    assert "confidence 85%" in plan_text or "confidence 85 %" in plan_text
    assert "Rescue recommendation confidence" in plan_text
    assert "GDD accumulated to date: 1500" in plan_text
    assert "GDD remaining" in plan_text
    assert "Safety margin: 20%" in plan_text
    assert "Cowpea" in plan_text
    assert "plant by" in plan_text
    assert not rp.fallback


def test_drought_plan_separate_confidences():
    plan_text, rp = generate_recovery_plan(
        _event("drought", 0.90),
        _gdd(1200.0, 600.0, "2025-10-06"),
        [_crop("Millet", 1400.0)],
        date(2025, 1, 30),
    )
    assert "Event detection: drought" in plan_text
    assert "Rescue recommendation confidence" in plan_text
    assert "Millet" in plan_text
    assert not rp.fallback


def test_normal_no_event():
    plan_text, rp = generate_recovery_plan(
        _event("none", 0.95),
        _gdd(1000.0, 800.0, "2025-10-04"),
        [],
        date(2025, 7, 7),
    )
    assert "Event detection: none" in plan_text
    assert rp.fallback is False  # no event is not a lost season (A3): no BR-5 fallback
    assert "cash crop is lost" not in plan_text
    assert "no rescue needed" in plan_text


def test_br5_fallback_cash_crop_lost():
    plan_text, rp = generate_recovery_plan(
        _event("flood", 0.80),
        _gdd(2000.0, 100.0, "2025-09-01"),  # tiny window
        [],
        date(2025, 8, 15),
    )
    assert rp.fallback is True
    assert "cash crop is lost" in plan_text
    assert "soil protection only" in plan_text
    assert "Cereal rye" in plan_text
    assert rp.rescue_confidence == 0.0
