"""Response views and export formats.

One response is always built in full; a *view* only projects it, so the demo
and production payloads can never drift apart into two code paths.

* ``completa`` (default) — everything, plus ``run_id`` and links to the stored
  run, its audit trail and its exports (production / operators).
* ``demo`` — the stripped payload for the hackathon screen and the PWA: the
  plan, the crops, the important alerts and the data-source badge.
"""
from __future__ import annotations

import csv
import io
import os
from typing import Any, Iterable

VIEWS = ("completa", "demo")

DEMO_KEYS = (
    "request_id", "run_id", "plan_text", "event_type", "event_confidence", "rescue_confidence",
    "gdd_accumulated", "gdd_remaining", "frost_date", "fallback", "no_action_needed",
    "crops", "alertas", "fuente_datos", "demo_mode", "demo_name", "vista", "contrato",
)
DEMO_CROP_KEYS = ("crop", "plant_by_date", "days_until_deadline", "rescue_confidence", "role")
DEMO_ALERT_CODES_ALWAYS = {"SIN_EVENTO", "SIN_CULTIVO_EN_VENTANA", "DATOS_SINTETICOS",
                           "FALLBACK_DATOS_SINTETICOS"}


def default_view() -> str:
    v = os.environ.get("PIER_API_VIEW", "completa").strip().lower()
    return v if v in VIEWS else "completa"


def project(response: dict[str, Any], view: str) -> dict[str, Any]:
    if view != "demo":
        return response
    out = {k: response[k] for k in DEMO_KEYS if k in response}
    out["crops"] = [{k: c[k] for k in DEMO_CROP_KEYS if k in c} for c in response.get("crops") or []]
    out["alertas"] = [a for a in response.get("alertas") or []
                      if a.get("nivel") == "critical" or a.get("codigo") in DEMO_ALERT_CODES_ALWAYS]
    return out


# ── Exports ──────────────────────────────────────────────────────────────────

PLAN_CSV_COLUMNS = (
    "run_id", "created_at", "lat", "lon", "current_date", "demo_name", "fuente_datos",
    "event_type", "event_confidence", "gdd_remaining", "frost_date", "fallback",
    "rank", "crop", "role", "plant_by_date", "days_until_deadline", "gdd_requirement",
    "rescue_confidence", "composite_score",
)
HISTORY_CSV_COLUMNS = (
    "run_id", "created_at", "endpoint", "lat", "lon", "current_date", "demo_name", "demo_mode",
    "fuente_datos", "data_path", "event_type", "fallback", "top_crop",
)


def _csv(rows: Iterable[dict], columns: tuple[str, ...]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in columns})
    return buf.getvalue()


def plan_csv(run: dict) -> str:
    """One row per recommended crop (one row with empty crop fields when there are none)."""
    resp = run["response"]
    base = {
        "run_id": run["run_id"], "created_at": run["created_at"], "lat": run["lat"],
        "lon": run["lon"], "current_date": run["current_date"], "demo_name": run["demo_name"],
        "fuente_datos": resp.get("fuente_datos"), "event_type": resp.get("event_type"),
        "event_confidence": resp.get("event_confidence"), "gdd_remaining": resp.get("gdd_remaining"),
        "frost_date": resp.get("frost_date"), "fallback": resp.get("fallback"),
    }
    crops = resp.get("crops") or []
    rows = [{**base, "rank": i + 1, **c} for i, c in enumerate(crops)] or [base]
    return _csv(rows, PLAN_CSV_COLUMNS)


def history_csv(runs: list[dict]) -> str:
    return _csv(runs, HISTORY_CSV_COLUMNS)


__all__ = ["VIEWS", "default_view", "project", "plan_csv", "history_csv",
           "PLAN_CSV_COLUMNS", "HISTORY_CSV_COLUMNS"]
