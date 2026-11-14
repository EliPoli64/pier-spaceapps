"""Conformal confidence calibration for PIER.

Replaces heuristic confidence with calibrated confidence intervals using
conformal prediction. Given historical validation cases
(event_type, predicted_confidence, actual_outcome), compute calibrated
confidence so that "80% confidence" means the outcome occurs ~80% of the time.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger("pier.tools.confidence_calibration")


def calibrate_confidence(
    raw_confidence: float,
    event_type: str,
    validation_history: list[dict[str, Any]],
    alpha: float = 0.2,
) -> float:
    """Calibrate a raw confidence score using conformal prediction.

    Args:
        raw_confidence: heuristic confidence in [0, 1].
        event_type: "flood" | "drought" | "none".
        validation_history: list of dicts with keys:
            event_type, predicted_confidence, actual_outcome (bool: did event occur / crop mature).
        alpha: target miscoverage rate (default 0.2 → 80% confidence interval).

    Returns:
        calibrated_confidence in [0, 1].
    """
    # Filter history for this event type
    relevant = [
        h for h in validation_history
        if h.get("event_type") == event_type
    ]

    if len(relevant) < 5:
        # Not enough history — return raw confidence with a small conservatism penalty
        logger.info(
            "Insufficient history for %s (%d cases); returning raw confidence",
            event_type, len(relevant),
        )
        return max(0.0, min(1.0, raw_confidence * 0.9))

    # Compute conformity scores: |predicted - actual| for each case
    conformity_scores = []
    for h in relevant:
        pred = float(h.get("predicted_confidence", 0.5))
        actual = 1.0 if h.get("actual_outcome") else 0.0
        conformity_scores.append(abs(pred - actual))
    conformity_scores = np.array(conformity_scores)

    # Conformal quantile: (1 - alpha) * (n + 1) / n quantile
    n = len(conformity_scores)
    q_level = min(1.0, (1.0 - alpha) * (n + 1) / n)
    q = float(np.quantile(conformity_scores, q_level))

    # Calibrated confidence = raw_confidence - conformity penalty
    calibrated = raw_confidence - q
    calibrated = max(0.0, min(1.0, calibrated))

    logger.info(
        "Calibrated %s confidence: raw=%.3f → calibrated=%.3f (n=%d, q=%.3f)",
        event_type, raw_confidence, calibrated, n, q,
    )
    return calibrated


def reliability_data(
    validation_history: list[dict[str, Any]],
    n_bins: int = 10,
) -> list[dict[str, Any]]:
    """Compute reliability plot data: bin predictions, compute observed frequency.

    Returns list of dicts: {bin_center, predicted_mean, observed_frequency, count}.
    """
    if not validation_history:
        return []

    bins = []
    for i in range(n_bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        in_bin = [
            h for h in validation_history
            if lo <= float(h.get("predicted_confidence", 0.5)) < hi
            or (i == n_bins - 1 and float(h.get("predicted_confidence", 0.5)) == 1.0)
        ]
        if not in_bin:
            continue
        pred_mean = float(np.mean([float(h.get("predicted_confidence", 0.5)) for h in in_bin]))
        obs_freq = float(np.mean([1.0 if h.get("actual_outcome") else 0.0 for h in in_bin]))
        bins.append({
            "bin_center": (lo + hi) / 2,
            "predicted_mean": round(pred_mean, 3),
            "observed_frequency": round(obs_freq, 3),
            "count": len(in_bin),
        })
    return bins


def calibration_error(
    validation_history: list[dict[str, Any]],
) -> float:
    """Expected calibration error (ECE): weighted average of |predicted - observed| per bin."""
    bins = reliability_data(validation_history)
    if not bins:
        return 0.0
    total = sum(b["count"] for b in bins)
    ece = sum(
        (b["count"] / total) * abs(b["predicted_mean"] - b["observed_frequency"])
        for b in bins
    )
    return round(float(ece), 4)


__all__ = ["calibrate_confidence", "reliability_data", "calibration_error"]
