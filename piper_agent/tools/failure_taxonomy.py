"""Failure taxonomy: why a run has no event, told apart so the agent can route it.

Three different situations used to look the same ("nothing to recommend"):

| status      | meaning                                              | route                         |
|-------------|------------------------------------------------------|-------------------------------|
| "no_data"   | the inputs are missing or too sparse to decide       | stop: no recommendation       |
| "conflicting" | two sources, or the observation and the climatology, disagree | continue, lower confidence |
| "normal"    | the data are good and say conditions are normal      | no action needed              |
| "event"     | the data are good and an extreme event was detected  | recommend a rescue            |

`classify_data_state` is a pure function: it never touches the network or the
cache, so every branch can be tested with plain numbers.
"""
from __future__ import annotations

from typing import Any

from piper_agent.config import CONFLICT_ABS_MM, CONFLICT_REL, MIN_WINDOW_COVERAGE

NO_DATA = "no_data"
CONFLICTING = "conflicting"
NORMAL = "normal"
EVENT = "event"

ROUTES = {
    NO_DATA: "stop",
    CONFLICTING: "continue_with_caution",
    NORMAL: "no_action",
    EVENT: "recommend",
}


def _state(status: str, reason: str) -> dict[str, Any]:
    return {"status": status, "reason": reason, "route": ROUTES[status]}


def sources_disagree(first_mm: float, second_mm: float) -> bool:
    """True when two rainfall totals differ by more than the absolute AND relative limits."""
    diff = abs(first_mm - second_mm)
    return diff > CONFLICT_ABS_MM and diff > CONFLICT_REL * max(first_mm, second_mm)


def classify_data_state(
    event_type: str,
    days_observed_30d: int,
    thresholds_available: bool,
    cum3_mm: float | None = None,
    alt_cum3_mm: float | None = None,
    climatology_status: str | None = None,
) -> dict[str, Any]:
    """Classify a detection run as no_data / conflicting / normal / event.

    Args:
        event_type: "flood" | "drought" | "none" as detected.
        days_observed_30d: days with rainfall data in the 30 days ending on the window end.
        thresholds_available: the baselines/climatology give the p95 (3 days) and p10 (30 days).
        cum3_mm: peak 3-day rainfall of the primary source.
        alt_cum3_mm: the same figure from an independent source (e.g. POWER vs IMERG), if any.
        climatology_status: `classify_value(...)["status"]` for the 3-day rainfall ("normal" |
            "extreme" | "missing"), or None when no climatology check was made.
    """
    if not thresholds_available:
        return _state(NO_DATA, "No rainfall thresholds (baselines/climatology) for this place and month.")
    if days_observed_30d < MIN_WINDOW_COVERAGE * 30:
        return _state(NO_DATA, f"Only {days_observed_30d} of the last 30 days have rainfall data "
                               f"(minimum {int(MIN_WINDOW_COVERAGE * 30)}).")

    if cum3_mm is not None and alt_cum3_mm is not None and sources_disagree(cum3_mm, alt_cum3_mm):
        return _state(CONFLICTING, f"Rainfall sources disagree: {cum3_mm:.1f} mm vs {alt_cum3_mm:.1f} mm "
                                   f"in the peak 3 days.")
    if climatology_status == "extreme" and event_type == "none":
        return _state(CONFLICTING, "Detection says normal but the rainfall is extreme for the "
                                   "regional climatology.")
    if climatology_status == "normal" and event_type == "flood":
        return _state(CONFLICTING, "Detection says flood but the 3-day rainfall is normal for the "
                                   "regional climatology.")

    if event_type == "none":
        return _state(NORMAL, "Rainfall is within the normal range; no extreme event.")
    return _state(EVENT, f"{event_type} detected with consistent data.")


__all__ = ["classify_data_state", "sources_disagree", "NO_DATA", "CONFLICTING", "NORMAL", "EVENT", "ROUTES"]
