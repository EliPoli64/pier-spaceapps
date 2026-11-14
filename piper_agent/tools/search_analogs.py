"""Historical analog search for PIER.

Searches the IMERG/POWER archive for past events similar to the current
situation (event_type, location, gdd_remaining) and returns matched crops
and outcomes. Used to calibrate confidence and provide precedent.
"""
from __future__ import annotations

import logging
import os
import json
from datetime import date, datetime
from typing import Any

import pandas as pd

logger = logging.getLogger("pier.tools.search_analogs")


def search_analogs(
    event_type: str,
    lat: float,
    lon: float,
    gdd_remaining: float,
    archive_dir: str | None = None,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Search historical analogs for similar events.

    Args:
        event_type: "flood" | "drought" | "none".
        lat, lon: field location.
        gdd_remaining: GDD remaining to climatological frost.
        archive_dir: directory with historical analog JSON files
            (each: {event_type, lat, lon, date, gdd_remaining, matched_crops, outcome}).
        max_results: maximum number of analogs to return.

    Returns:
        List of analog dicts sorted by similarity. Empty list if no history.
    """
    analogs = []

    if archive_dir is None:
        archive_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "analogs"
        )

    if not os.path.isdir(archive_dir):
        logger.info("No analog archive directory at %s", archive_dir)
        return []

    for fname in os.listdir(archive_dir):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(archive_dir, fname)
        try:
            with open(path) as f:
                rec = json.load(f)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read analog %s: %s", fname, exc)
            continue

        # Match on event type
        if rec.get("event_type") != event_type:
            continue

        # Compute similarity score (0-1, higher = more similar)
        sim = 1.0
        # Location similarity: closer = more similar (rough, degrees)
        lat_diff = abs(float(rec.get("lat", lat)) - lat)
        lon_diff = abs(float(rec.get("lon", lon)) - lon)
        loc_sim = max(0.0, 1.0 - (lat_diff + lon_diff) / 20.0)
        sim *= loc_sim

        # GDD similarity
        rec_gdd = float(rec.get("gdd_remaining", gdd_remaining))
        gdd_sim = max(0.0, 1.0 - abs(rec_gdd - gdd_remaining) / max(gdd_remaining, 1.0))
        sim *= gdd_sim

        rec["similarity"] = round(sim, 3)
        analogs.append(rec)

    analogs.sort(key=lambda a: a["similarity"], reverse=True)
    return analogs[:max_results]


def analog_calibrated_confidence(
    analogs: list[dict[str, Any]],
    raw_confidence: float,
) -> float:
    """Derive calibrated confidence from historical analog outcomes.

    Args:
        analogs: list of analog dicts with keys: similarity, actual_outcome (bool).
        raw_confidence: heuristic confidence in [0, 1].

    Returns:
        calibrated confidence in [0, 1].
    """
    if not analogs:
        return raw_confidence

    # Weight outcomes by similarity
    total_weight = 0.0
    weighted_success = 0.0
    for a in analogs:
        w = float(a.get("similarity", 0.1))
        success = 1.0 if a.get("actual_outcome") else 0.0
        total_weight += w
        weighted_success += w * success

    if total_weight <= 0:
        return raw_confidence

    observed_rate = weighted_success / total_weight
    # Blend raw confidence with observed analog rate (70% weight on analogs when available)
    calibrated = 0.3 * raw_confidence + 0.7 * observed_rate
    return max(0.0, min(1.0, calibrated))


__all__ = ["search_analogs", "analog_calibrated_confidence"]
