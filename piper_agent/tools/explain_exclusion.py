"""Explanation generator for crop exclusions (BR-8).

Produces human-readable reasons why each crop was filtered out, e.g.:
- "Buckwheat excluded: Low waterlogging tolerance for this flood event."
- "Sorghum excluded: needs 1800 GDD, only 1200 remain."
"""
from __future__ import annotations

TOLERANCE_LABELS = {
    "waterlogging_tolerance": "waterlogging tolerance",
    "drought_tolerance": "drought tolerance",
}

TOLERANCE_WORDS = {
    "Low": "Low",
    "Medium": "Medium",
    "High": "High",
}


def explain_exclusion(
    crop: str,
    event_type: str,
    gdd_remaining: float,
    filter_reason: str,
    filter_details: dict | None = None,
) -> str:
    """Generate a human-readable exclusion reason for a crop.

    Args:
        crop: crop name.
        event_type: "flood" | "drought" | "none".
        gdd_remaining: GDD remaining to climatological frost.
        filter_reason: one of:
            "tolerance_waterlogging", "tolerance_drought", "gdd_window",
            "planting_window", "no_event".
        filter_details: optional extra context dict.

    Returns:
        Human-readable explanation string.
    """
    details = filter_details or {}

    if filter_reason == "tolerance_waterlogging":
        tol = details.get("waterlogging_tolerance", "Low")
        return (
            f"{crop} excluded: {TOLERANCE_WORDS.get(tol, tol)} "
            f"waterlogging tolerance for this {event_type} event "
            f"(needs ≥ Medium)."
        )

    if filter_reason == "tolerance_drought":
        tol = details.get("drought_tolerance", "Low")
        return (
            f"{crop} excluded: {TOLERANCE_WORDS.get(tol, tol)} "
            f"drought tolerance for this {event_type} event "
            f"(needs ≥ Medium)."
        )

    if filter_reason == "gdd_window":
        req = details.get("gdd_requirement", 0)
        limit = details.get("gdd_limit", gdd_remaining * 0.8)
        return (
            f"{crop} excluded: needs {req:.0f} GDD to mature, "
            f"but only {limit:.0f} GDD remain (20% safety margin applied "
            f"to {gdd_remaining:.0f} GDD window)."
        )

    if filter_reason == "planting_window":
        window = details.get("planting_window", "unknown")
        return (
            f"{crop} excluded: planting window {window} has passed "
            f"for the remaining season."
        )

    if filter_reason == "no_event":
        return (
            f"{crop} not recommended: no extreme event detected "
            f"({event_type}); normal-season planning applies."
        )

    return f"{crop} excluded: {filter_reason}."


def exclusion_records(
    all_crops: list[dict],
    eligible_crops: list[dict],
    event_type: str,
    gdd_remaining: float,
) -> list[dict]:
    """One structured record per excluded crop: {crop, motivo, explicacion}.

    `motivo` is the machine-readable reason ("tolerance_waterlogging",
    "tolerance_drought", "gdd_window" or "no_event"); `explicacion` is the text
    `explain_exclusion` builds for it.
    """
    eligible_names = {c.get("crop") for c in eligible_crops}
    records = []

    def add(name: str, reason: str, details: dict | None = None) -> None:
        records.append({
            "crop": name,
            "motivo": reason,
            "explicacion": explain_exclusion(name, event_type, gdd_remaining, reason, details),
        })

    for crop in all_crops:
        name = crop.get("crop", "Unknown")
        if name in eligible_names:
            continue

        if event_type == "flood":
            tol = crop.get("waterlogging_tolerance", "Low")
            if tol == "Low":
                add(name, "tolerance_waterlogging", {"waterlogging_tolerance": tol})
                continue
        elif event_type == "drought":
            tol = crop.get("drought_tolerance", "Low")
            if tol == "Low":
                add(name, "tolerance_drought", {"drought_tolerance": tol})
                continue

        # GDD window check
        req = crop.get("gdd_to_maturity_max", crop.get("gdd_requirement", 0))
        if req > gdd_remaining * 0.8:
            add(name, "gdd_window", {"gdd_requirement": req, "gdd_limit": gdd_remaining * 0.8})
            continue

        add(name, "no_event")

    return records


def explain_all_exclusions(
    all_crops: list[dict],
    eligible_crops: list[dict],
    event_type: str,
    gdd_remaining: float,
) -> list[str]:
    """Generate exclusion explanations for all crops not in the eligible list.

    Args:
        all_crops: full crop database list (dicts with crop, tolerance fields, gdd_requirement).
        eligible_crops: list of eligible CropRecommendation-like dicts.
        event_type: "flood" | "drought" | "none".
        gdd_remaining: GDD remaining.

    Returns:
        List of explanation strings, one per excluded crop.
    """
    return [r["explicacion"] for r in exclusion_records(all_crops, eligible_crops, event_type, gdd_remaining)]


__all__ = ["explain_exclusion", "explain_all_exclusions", "exclusion_records"]
