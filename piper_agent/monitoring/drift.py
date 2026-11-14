"""PIER monitoring & drift detection.

Detects when IMERG/POWER data is stale, when confidence drops below threshold,
or when recommendations fall outside historical norms. Emits structured log
entries for audit and alerting.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("pier.monitoring.drift")

STALE_DATA_THRESHOLD_HOURS = int(os.environ.get("PIER_STALE_DATA_HOURS", "72"))
LOW_CONFIDENCE_THRESHOLD = float(os.environ.get("PIER_LOW_CONFIDENCE", "0.4"))


class DriftAlert:
    """A detected drift or anomaly."""

    def __init__(
        self,
        severity: str,  # "low" | "medium" | "high"
        metric: str,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        self.severity = severity
        self.metric = metric
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "metric": self.metric,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


def check_data_staleness(
    last_data_timestamp: str | None,
    metric_name: str = "IMERG/POWER",
) -> DriftAlert | None:
    """Check if source data is stale beyond the threshold.

    Args:
        last_data_timestamp: ISO timestamp of last successful data fetch.
        metric_name: name of the data source for the alert.

    Returns:
        DriftAlert if stale, None if fresh.
    """
    if not last_data_timestamp:
        return DriftAlert(
            severity="high",
            metric=f"{metric_name}_staleness",
            message=f"{metric_name} data has never been fetched",
            details={"last_timestamp": None},
        )

    try:
        last_dt = datetime.fromisoformat(last_data_timestamp)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
    except Exception as exc:  # noqa: BLE001
        return DriftAlert(
            severity="medium",
            metric=f"{metric_name}_staleness",
            message=f"Could not parse {metric_name} timestamp: {exc}",
            details={"raw": last_data_timestamp},
        )

    age_hours = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600.0
    if age_hours > STALE_DATA_THRESHOLD_HOURS:
        return DriftAlert(
            severity="high" if age_hours > STALE_DATA_THRESHOLD_HOURS * 2 else "medium",
            metric=f"{metric_name}_staleness",
            message=(
                f"{metric_name} data is {age_hours:.1f}h old "
                f"(threshold {STALE_DATA_THRESHOLD_HOURS}h)"
            ),
            details={
                "last_timestamp": last_data_timestamp,
                "age_hours": round(age_hours, 1),
                "threshold_hours": STALE_DATA_THRESHOLD_HOURS,
            },
        )
    return None


def check_confidence_threshold(
    confidence: float,
    operation: str = "detection",
    threshold: float = LOW_CONFIDENCE_THRESHOLD,
) -> DriftAlert | None:
    """Check if a confidence score is below acceptable threshold.

    Args:
        confidence: confidence value in [0, 1].
        operation: name of the operation (e.g., "detection", "rescue").
        threshold: minimum acceptable confidence.

    Returns:
        DriftAlert if below threshold, None if acceptable.
    """
    if confidence < threshold:
        return DriftAlert(
            severity="high" if confidence < threshold * 0.5 else "medium",
            metric=f"{operation}_confidence",
            message=(
                f"{operation} confidence {confidence:.2f} below threshold {threshold:.2f}"
            ),
            details={
                "confidence": confidence,
                "threshold": threshold,
                "operation": operation,
            },
        )
    return None


def check_recommendation_drift(
    n_eligible: int,
    n_excluded: int,
    event_type: str,
) -> DriftAlert | None:
    """Detect when recommendations fall outside historical norms.

    Args:
        n_eligible: number of eligible crops returned.
        n_excluded: number of crops excluded.
        event_type: "flood" | "drought" | "none".

    Returns:
        DriftAlert if anomalous, None if normal.
    """
    if event_type in ("flood", "drought") and n_eligible == 0 and n_excluded > 0:
        # All crops excluded for an extreme event — unusual
        return DriftAlert(
            severity="medium",
            metric="recommendation_drift",
            message=(
                f"No eligible crops for {event_type} event "
                f"despite {n_excluded} candidates"
            ),
            details={
                "event_type": event_type,
                "n_eligible": n_eligible,
                "n_excluded": n_excluded,
            },
        )
    return None


def run_all_checks(
    last_data_timestamp: str | None = None,
    detection_confidence: float | None = None,
    rescue_confidence: float | None = None,
    n_eligible: int | None = None,
    n_excluded: int | None = None,
    event_type: str | None = None,
) -> list[DriftAlert]:
    """Run all monitoring checks and return alerts.

    Returns:
        List of DriftAlert (may be empty).
    """
    alerts: list[DriftAlert] = []

    stale = check_data_staleness(last_data_timestamp)
    if stale:
        alerts.append(stale)

    if detection_confidence is not None:
        det = check_confidence_threshold(detection_confidence, "detection")
        if det:
            alerts.append(det)

    if rescue_confidence is not None:
        res = check_confidence_threshold(rescue_confidence, "rescue")
        if res:
            alerts.append(res)

    if n_eligible is not None and n_excluded is not None and event_type:
        drift = check_recommendation_drift(n_eligible, n_excluded, event_type)
        if drift:
            alerts.append(drift)

    for alert in alerts:
        logger.warning("DRIFT ALERT: %s", alert.to_dict())

    return alerts


__all__ = [
    "DriftAlert",
    "check_data_staleness",
    "check_confidence_threshold",
    "check_recommendation_drift",
    "run_all_checks",
]
