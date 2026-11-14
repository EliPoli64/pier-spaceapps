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


def _weather_alert_lines(heat_wave: dict | None, frost: dict | None) -> list[str]:
    """One line per active weather alert (heat wave, frost); empty when there is none."""
    lines = []
    if heat_wave and heat_wave.get("event_type") == "heat_wave":
        d = heat_wave.get("details", {})
        lines.append(
            f"- Heat wave: max {d.get('max_tmax_c')} °C, {d.get('max_consecutive_days_above_threshold')} "
            f"consecutive days above {d.get('tmax_threshold_c')} °C "
            f"(confidence {heat_wave.get('confidence', 0):.0%}). "
            "Heat stress risk at flowering: irrigate or mulch if possible."
        )
    if frost and frost.get("event_type") == "frost":
        d = frost.get("details", {})
        lines.append(
            f"- Frost: min {d.get('min_tmin_c')} °C, {d.get('frost_days')} frost day(s) "
            f"from {d.get('first_frost_date')} (confidence {frost.get('confidence', 0):.0%}). "
            "Protect emerged crops; the GDD window may end earlier than the climatological frost date."
        )
    return lines


def _evidence_lines(evidence: list[dict]) -> list[str]:
    """`- item: tag; tag; ...` per evidence entry."""
    return [f"- {e.get('item')}: " + "; ".join(str(t) for t in e.get("tags", [])) for e in evidence]


def generate_recovery_plan(
    event_result: EventResult,
    gdd_result: GddResult,
    crops: list[CropRecommendation],
    current_date: date,
    data_status: dict | None = None,
    heat_wave: dict | None = None,
    frost: dict | None = None,
    evidence: list[dict] | None = None,
) -> tuple[str, RecoveryPlan]:
    """Generate the natural-language recovery plan with separate confidences.

    Args:
        event_result: output of detect_event (BR-1)
        gdd_result: output of fetch_power_gdd (BR-3)
        crops: output of filter_rescue_crops (BR-2,3,4)
        current_date: "today" as a date
        data_status: failure-taxonomy state ({"status": "no_data" | "conflicting" |
            "normal" | "event", "reason": ...}); None behaves as before.
        heat_wave: output of `detect_heat_wave`; a "heat_wave" event adds a weather alert.
        frost: output of `detect_frost`; a "frost" event adds a weather alert.
        evidence: list of {"item", "tags"} (the agent's `evidencia`); printed as the
            evidence behind the event and behind every recommendation.

    Returns:
        (plan_text, RecoveryPlan)
    """
    status = (data_status or {}).get("status")
    # BR-5 (cover-crop fallback) only applies when an event destroyed the cash crop.
    # No event, or no data to say so, is not a lost season.
    no_action = event_result.event_type == "none"
    fallback = len(crops) == 0 and not no_action and status != "no_data"

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
    if status == "no_data":
        crop_lines.append(
            f"- Insufficient data to decide: {data_status.get('reason', 'inputs missing')} "
            "No rescue recommendation issued; retry when data are available."
        )
        caveat = "No recommendation: the data do not support one."
    elif no_action and not crops:
        crop_lines.append(
            "- No extreme event detected: no rescue needed, the planned crop stands. "
            "Keep monitoring rainfall and temperature."
        )
        caveat = "Typical GDD values — local calibration required."
    elif crops:
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

    if status == "conflicting":
        crop_lines.append(
            f"WARNING — conflicting data: {data_status.get('reason')} "
            "Confidence was lowered; confirm in the field before acting."
        )

    # --- Weather alerts: heat wave and frost (independent of the rainfall event) ---
    alert_lines = _weather_alert_lines(heat_wave, frost)

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
    ] + crop_lines
    if alert_lines:
        parts += ["", "Weather alerts:"] + alert_lines
    parts += ["", caveat]
    if evidence:
        parts += ["", "Evidence:"] + _evidence_lines(evidence)
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
