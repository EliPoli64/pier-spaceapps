"""Rescue → rotation planner (BR-9, BR-12).

Suggests the next season's crop based on what the rescue crop leaves behind
(N fixation from cowpea, residue cover from rye, etc.). Outputs a 3-crop
sequence (rescue → main → cover) with cumulative soil-health scoring.
"""
from __future__ import annotations

from typing import Any

# What each crop contributes to the next season
CROP_LEGACY = {
    "Sorghum": {
        "n_fixation_kg_ha": 0,
        "residue_cover_pct": 60,
        "soil_health_impact": "moderate",
        "best_follow_crops": ["Cowpea", "Cereal rye (cover)"],
    },
    "Millet": {
        "n_fixation_kg_ha": 0,
        "residue_cover_pct": 50,
        "soil_health_impact": "moderate",
        "best_follow_crops": ["Cowpea", "Cereal rye (cover)"],
    },
    "Buckwheat": {
        "n_fixation_kg_ha": 0,
        "residue_cover_pct": 40,
        "soil_health_impact": "low",
        "best_follow_crops": ["Cowpea", "Sorghum"],
    },
    "Cowpea": {
        "n_fixation_kg_ha": 60,
        "residue_cover_pct": 55,
        "soil_health_impact": "high",
        "best_follow_crops": ["Sorghum", "Millet"],
    },
    "Cereal rye (cover)": {
        "n_fixation_kg_ha": 0,
        "residue_cover_pct": 80,
        "soil_health_impact": "very_high",
        "best_follow_crops": ["Cowpea", "Sorghum", "Millet"],
    },
}

# Soil-health score contribution per crop (0-100)
SOIL_HEALTH_SCORE = {
    "Sorghum": 55,
    "Millet": 50,
    "Buckwheat": 40,
    "Cowpea": 75,
    "Cereal rye (cover)": 90,
}

# Typical GDD remaining after each crop type (rough, for feasibility)
CROP_SEASON_LENGTH_DAYS = {
    "Sorghum": 105,
    "Millet": 75,
    "Buckwheat": 80,
    "Cowpea": 75,
    "Cereal rye (cover)": 75,
}


def plan_rotation(
    rescue_crop: str,
    next_season_constraints: dict[str, Any] | None,
) -> dict[str, Any]:
    """Plan a 3-crop rotation sequence starting with the rescue crop.

    Args:
        rescue_crop: the recommended rescue crop name.
        next_season_constraints: optional dict with keys:
            - season_length_days: days remaining in next season
            - water_available_mm: irrigation/rainfall available
            - soil_texture: texture class
            - farmer_priority: "soil_protection" | "salvage_revenue" | "water_conservation"

    Returns:
        dict with keys: rotation_sequence (list of 3 crops), soil_health_score,
        n_fixation_total_kg_ha, residue_cover_avg_pct, rationale.
    """
    constraints = next_season_constraints or {}
    farmer_priority = constraints.get("farmer_priority", "soil_protection")

    if rescue_crop not in CROP_LEGACY:
        # Unknown crop — default fallback
        rescue_crop = "Cereal rye (cover)"

    rescue_legacy = CROP_LEGACY[rescue_crop]

    # Choose main crop (season 2) based on rescue crop's legacy + farmer priority
    follow_crops = rescue_legacy["best_follow_crops"]

    # If farmer wants salvage revenue, prefer higher-value crops
    if farmer_priority == "salvage_revenue":
        # Sorghum and Cowpea have higher market value
        revenue_order = ["Cowpea", "Sorghum", "Millet", "Cereal rye (cover)", "Buckwheat"]
        main_crop = next((c for c in revenue_order if c in follow_crops), follow_crops[0])
    elif farmer_priority == "water_conservation":
        # Prefer lower-irrigation crops
        water_order = ["Millet", "Sorghum", "Cowpea", "Buckwheat", "Cereal rye (cover)"]
        main_crop = next((c for c in water_order if c in follow_crops), follow_crops[0])
    else:  # soil_protection
        main_crop = follow_crops[0]

    # Choose cover crop (season 3) — always a cover for soil protection
    cover_crop = "Cereal rye (cover)"
    if main_crop == "Cereal rye (cover)":
        cover_crop = "Cowpea"  # alternate to N-fix after rye

    rotation_sequence = [rescue_crop, main_crop, cover_crop]

    # Compute cumulative soil-health score
    soil_score = sum(SOIL_HEALTH_SCORE.get(c, 50) for c in rotation_sequence) / len(rotation_sequence)
    n_fixation = sum(CROP_LEGACY.get(c, {}).get("n_fixation_kg_ha", 0) for c in rotation_sequence)
    residue_avg = sum(CROP_LEGACY.get(c, {}).get("residue_cover_pct", 50) for c in rotation_sequence) / len(rotation_sequence)

    # Build rationale
    rationale_parts = [
        f"Rescue crop {rescue_crop} leaves {rescue_legacy['n_fixation_kg_ha']} kg/ha N and "
        f"{rescue_legacy['residue_cover_pct']}% residue cover.",
        f"Follow with {main_crop} (suited after {rescue_crop}).",
        f"Finish with {cover_crop} for soil protection and organic matter.",
    ]
    if n_fixation > 0:
        rationale_parts.append(f"Total N fixation across rotation: ~{n_fixation} kg/ha.")

    return {
        "rotation_sequence": rotation_sequence,
        "soil_health_score": round(soil_score, 1),
        "n_fixation_total_kg_ha": n_fixation,
        "residue_cover_avg_pct": round(residue_avg, 1),
        "rationale": " ".join(rationale_parts),
        "rescue_crop_legacy": rescue_legacy,
    }


__all__ = ["plan_rotation", "CROP_LEGACY", "SOIL_HEALTH_SCORE"]
