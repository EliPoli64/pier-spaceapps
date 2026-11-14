"""Spec §6: PIER agent — Python tool-calling loop.

Orchestrates the four tools in sequence:
  1. detect_event        (BR-1)
  2. fetch_power_gdd     (BR-3)
  3. filter_rescue_crops (BR-2, BR-3, BR-4)
  4. generate_recovery_plan (BR-5, BR-6)

DEMO_MODE=True (default) → all data from cache (no live NASA calls).
demo_mode=False          → labeled production path (live imergpy/POWER, not implemented here).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from piper_agent.contracts import (
    EventResult,
    GddResult,
    CropRecommendation,
    RecoveryPlan,
)
from piper_agent.tools.detect_event import detect_event
from piper_agent.tools.fetch_power_gdd import fetch_power_gdd
from piper_agent.tools.filter_rescue_crops import filter_rescue_crops
from piper_agent.tools.generate_recovery_plan import generate_recovery_plan
from piper_agent.data.cache_loader import load_demo_packet


def run_pier(
    lat: float,
    lon: float,
    current_date: str,
    demo_mode: bool = True,
    demo_name: str | None = None,
) -> dict[str, Any]:
    """Run the full PIER agent pipeline.

    Args:
        lat, lon: field location.
        current_date: ISO date "now".
        demo_mode: if True, serve all data from cache (demo path).
        demo_name: which demo packet to use ("flood", "drought", "normal").
                   If None, auto-select based on lat/lon matching.

    Returns:
        Structured dict with event_result, gdd_result, crops, recovery_plan, plan_text.
    """
    if not demo_mode:
        # Production path: live imergpy/POWER calls — not implemented in demo stage.
        # Labeled as production path per Spec §8.
        raise NotImplementedError(
            "Live NASA Earthdata/POWER path (demo_mode=False) is a production path. "
            "Use demo_mode=True with cached data for the demo."
        )

    # Auto-select demo packet if not specified
    if demo_name is None:
        pkt = _auto_select_demo(lat, lon)
        demo_name = pkt["name"].replace("_demo", "")

    # Load demo packet for season_start
    packet = load_demo_packet(f"{demo_name}_demo")
    season_start = packet["season_start"]

    # --- Step 1: detect_event (BR-1) ---
    event_result: EventResult = detect_event(
        lat=lat,
        lon=lon,
        recent_start=packet["recent_start"],
        recent_end=packet["recent_end"],
        demo_name=demo_name,
    )

    # --- Step 2: fetch_power_gdd (BR-3) ---
    gdd_result: GddResult = fetch_power_gdd(
        lat=lat,
        lon=lon,
        season_start=season_start,
        current_date=current_date,
        demo_name=demo_name,
    )

    # --- Step 3: filter_rescue_crops (BR-2, BR-3, BR-4) ---
    crops: list[CropRecommendation] = filter_rescue_crops(
        event_type=event_result.event_type,
        gdd_remaining=gdd_result.gdd_remaining,
        current_date=current_date,
        avg_daily_gdd=gdd_result.avg_daily_gdd,
    )

    # --- Step 4: generate_recovery_plan (BR-5, BR-6) ---
    current_dt = datetime.fromisoformat(current_date).date()
    plan_text, recovery_plan = generate_recovery_plan(
        event_result=event_result,
        gdd_result=gdd_result,
        crops=crops,
        current_date=current_dt,
    )
    recovery_plan: RecoveryPlan = recovery_plan

    return {
        "event_result": event_result,
        "gdd_result": gdd_result,
        "crops": crops,
        "recovery_plan": recovery_plan,
        "plan_text": plan_text,
        "demo_mode": demo_mode,
        "demo_name": demo_name,
    }


def _auto_select_demo(lat: float, lon: float) -> dict:
    """Pick a demo packet whose location matches (lat, lon)."""
    for name in ["flood", "drought", "normal"]:
        pkt = load_demo_packet(f"{name}_demo")
        if abs(pkt["lat"] - lat) < 0.5 and abs(pkt["lon"] - lon) < 0.5:
            return pkt
    # Default to flood
    return load_demo_packet("flood_demo")


def plan_text_only(lat: float, lon: float, current_date: str, demo_mode: bool = True, demo_name: str | None = None) -> str:
    """Convenience: run PIER and return just the plan text (for CLI/UI)."""
    result = run_pier(lat, lon, current_date, demo_mode, demo_name)
    return result["plan_text"]
