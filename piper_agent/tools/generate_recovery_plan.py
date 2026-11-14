"""BR-5, BR-6: generate_recovery_plan — recovery plan generation with separate confidences.

- BR-6: Event detection confidence reported separately from rescue recommendation confidence
- BR-5: If no crop fits the window → cover crop / fallow fallback; explicit "cash crop is lost"
"""
from __future__ import annotations

from datetime import date

from piper_agent.contracts import (
    EventResult,
    GddResult,
    CropRecommendation,
    RecoveryPlan,
)


def generate_recovery_plan(
    event_result: EventResult,
    gdd_result: GddResult,
    crops: list[CropRecommendation],
    current_date: date,
) -> tuple[str, RecoveryPlan]:
    """Generate the natural-language recovery plan with separate confidences.

    Args:
        event_result: output of detect_event (BR-1)
        gdd_result: output of fetch_power_gdd (BR-3)
        crops: output of filter_rescue_crops (BR-2,3,4)
        current_date: "today" as a date

    Returns:
        (plan_text, RecoveryPlan)
    """
    fallback = len(crops) == 0

    # --- BR-6: separate confidences ---
    event_conf_line = (
        f"Event detection: {event_result.event_type}, "
        f"confidence {event_result.confidence:.0%}"
    )
    if crops:
        # Aggregate rescue confidence = mean of individual crop confidences
        agg_rescue_conf = sum(c.rescue_confidence for c in crops) / len(crops)
    else:
        agg_rescue_conf = 0.0
    rescue_conf_line = (
        f"Rescue recommendation confidence: {agg_rescue_conf:.0%} (based on GDD margin)"
    )

    # --- GDD window ---
    gdd_window_lines = [
        f"GDD accumulated to date: {gdd_result.gdd_accumulated:.0f}",
        f"GDD remaining to climatological frost ({gdd_result.frost_date}): "
        f"{gdd_result.gdd_remaining:.0f}",
        "Safety margin: 20% applied to GDD window (late planting / slower emergence)",
    ]

    # --- Crop recommendations ---
    crop_lines = []
    if crops:
        for c in crops:
            crop_lines.append(
                f"- {c.crop}: plant by {c.plant_by_date} "
                f"({c.days_until_deadline} days from now), "
                f"GDD requirement {c.gdd_requirement:.0f}, "
                f"rescue confidence {c.rescue_confidence:.0%}"
            )
        caveat = "Typical GDD values — local calibration required."
    else:
        # --- BR-5: fallback cover crop ---
        crop_lines.append(
            "- Cereal rye (cover crop): fast-establishing soil protection; "
            "plant immediately"
        )
        crop_lines.append(
            "The season's cash crop is lost; this recommendation is soil protection only, "
            "not a cash crop."
        )
        caveat = "Typical GDD values — local calibration required."

    # --- Assemble plan text ---
    parts = [
        "=== PIER Recovery Plan ===",
        event_conf_line,
        rescue_conf_line,
        "",
        "GDD Window:",
    ] + gdd_window_lines + [
        "",
        "Recommendations:",
    ] + crop_lines + [
        "",
        caveat,
    ]
    plan_text = "\n".join(parts)

    recovery_plan = RecoveryPlan(
        event_type=event_result.event_type,
        event_confidence=event_result.confidence,
        rescue_confidence=agg_rescue_conf,
        gdd_accumulated=gdd_result.gdd_accumulated,
        gdd_remaining=gdd_result.gdd_remaining,
        frost_date=gdd_result.frost_date,
        fallback=fallback,
        crops=crops,
        plan_text=plan_text,
    )

    return plan_text, recovery_plan
