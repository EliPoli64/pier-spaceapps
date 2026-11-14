"""Local calibration: farmer observations per coordinate.

The farmer can report the yield obtained or the damage observed. They are
stored in a personal file per 0.5° cell so future runs are corrected against
local reality and not only against the global climatology.

The files live in `data/cache/calibration/` (outside git: it is personal
data). The folder can be changed with PIER_CALIBRATION_DIR.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from statistics import median
from typing import Any

from piper_agent.data import generate_cache as gc
from piper_agent.data.ingestion.pipeline import region_key

logger = logging.getLogger("pier.data.calibration")

CALIBRATION_VERSION = "1"
MIN_OBSERVATIONS = 3
FACTOR_MIN, FACTOR_MAX = 0.5, 1.5


def _calibration_dir() -> str:
    return os.environ.get(
        "PIER_CALIBRATION_DIR", os.path.join(gc.ROOT_DIR, "data", "cache", "calibration")
    )


def calibration_path(lat: float, lon: float) -> str:
    return os.path.join(_calibration_dir(), f"{region_key(lat, lon)}.json")


def load_observations(lat: float, lon: float) -> list[dict[str, Any]]:
    """Observations stored for the cell of (lat, lon). Empty list if there are none."""
    path = calibration_path(lat, lon)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("observations", [])
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Unreadable calibration file (%s): %s", path, exc)
        return []


def record_observation(
    lat: float,
    lon: float,
    observed_on: str,
    crop: str,
    observed_yield_t_ha: float | None = None,
    expected_yield_t_ha: float | None = None,
    damage_pct: float | None = None,
    event_type: str | None = None,
    predicted_confidence: float | None = None,
    crop_matured: bool | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Store a farmer observation and return it.

    Args:
        observed_on: ISO date of the observation.
        observed_yield_t_ha / expected_yield_t_ha: used for the correction factor.
        damage_pct: observed damage, from 0 to 100.
        event_type: "flood" | "drought" | "none" that PIER had detected.
        predicted_confidence: confidence PIER reported in that run (0-1).
        crop_matured: whether the rescue crop reached maturity.
        note: free text.
    """
    if observed_yield_t_ha is not None and observed_yield_t_ha < 0:
        raise ValueError("The observed yield cannot be negative")
    if damage_pct is not None and not 0 <= damage_pct <= 100:
        raise ValueError("damage_pct must be between 0 and 100")
    if predicted_confidence is not None and not 0 <= predicted_confidence <= 1:
        raise ValueError("predicted_confidence must be between 0 and 1")
    datetime.fromisoformat(observed_on)  # validates the format

    observation = {
        "observed_on": observed_on,
        "crop": crop,
        "observed_yield_t_ha": observed_yield_t_ha,
        "expected_yield_t_ha": expected_yield_t_ha,
        "damage_pct": damage_pct,
        "event_type": event_type,
        "predicted_confidence": predicted_confidence,
        "crop_matured": crop_matured,
        "note": note,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    observations = load_observations(lat, lon) + [observation]
    os.makedirs(_calibration_dir(), exist_ok=True)
    with open(calibration_path(lat, lon), "w", encoding="utf-8") as f:
        json.dump(
            {"version": CALIBRATION_VERSION, "region": region_key(lat, lon),
             "observations": observations},
            f, indent=2, ensure_ascii=False,
        )
    return observation


def correction_factor(lat: float, lon: float, crop: str) -> dict[str, Any]:
    """Local yield factor = median(observed / expected), bounded to [0.5, 1.5].

    With fewer than MIN_OBSERVATIONS it returns factor 1.0 and `calibrated=False`.
    """
    ratios = [
        o["observed_yield_t_ha"] / o["expected_yield_t_ha"]
        for o in load_observations(lat, lon)
        if o.get("crop") == crop
        and o.get("observed_yield_t_ha") is not None
        and o.get("expected_yield_t_ha")
    ]
    if len(ratios) < MIN_OBSERVATIONS:
        return {"factor": 1.0, "calibrated": False, "n_observations": len(ratios)}
    factor = min(FACTOR_MAX, max(FACTOR_MIN, median(ratios)))
    return {"factor": round(factor, 3), "calibrated": True, "n_observations": len(ratios)}


def validation_history(lat: float, lon: float) -> list[dict[str, Any]]:
    """Observations in the format `calibrate_confidence` expects.

    Each item: {event_type, predicted_confidence, actual_outcome}. Only
    observations that carry event, confidence and outcome are included.
    """
    return [
        {
            "event_type": o["event_type"],
            "predicted_confidence": o["predicted_confidence"],
            "actual_outcome": bool(o["crop_matured"]),
        }
        for o in load_observations(lat, lon)
        if o.get("event_type") and o.get("predicted_confidence") is not None
        and o.get("crop_matured") is not None
    ]


__all__ = [
    "record_observation", "load_observations", "correction_factor",
    "validation_history", "calibration_path",
]
