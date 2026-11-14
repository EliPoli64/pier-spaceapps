"""Spec §6: PIER agent — Python tool-calling loop.

Orchestrates the four tools in sequence:
  1. detect_event        (BR-1)
  2. fetch_power_gdd     (BR-3)
  3. filter_rescue_crops (BR-2, BR-3, BR-4)
  4. generate_recovery_plan (BR-5, BR-6)

and fills the contract keys downstream code reads with `.get()`:
`exclusiones`, `rotacion`, `ahorro`, `confianza_calibrada`, `suelo`, `ola_calor`,
`fuente_datos` (plus `helada`, `estado_datos`, `evidencia`, `ultima_actualizacion`).
Heat-wave and frost alerts and the evidence tags are also printed in `plan_text`.

DEMO_MODE=True (default) → all data from cache (no live NASA calls).
demo_mode=False          → labeled production path: the data come from
                           `ingest_point()` / `get_climatology()` through `tools.live_inputs`;
                           without credentials or network they fall back to synthetic
                           data and `fuente_datos` / `fallback_reason` say so.

The failure taxonomy (no data / conflicting data / normal / event) decides the route:
no data → no recommendation, conflicting → recommendation with lowered confidence,
normal → no action needed.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from piper_agent.config import (
    CONFLICT_CONFIDENCE_FACTOR,
    DEFAULT_YIELD_T_HA,
    MIN_HISTORY_FOR_CALIBRATION,
)
from piper_agent.contracts import (
    EventResult,
    GddResult,
    CropRecommendation,
    RecoveryPlan,
)
from piper_agent.tools.detect_event import detect_event, detect_frost, detect_heat_wave
from piper_agent.tools.failure_taxonomy import CONFLICTING, NO_DATA
from piper_agent.tools.fetch_power_gdd import fetch_power_gdd
from piper_agent.tools.filter_rescue_crops import filter_rescue_crops
from piper_agent.tools.generate_recovery_plan import generate_recovery_plan
from piper_agent.tools.live_inputs import track_data_source
from piper_agent.data.cache_loader import ESCENARIOS, load_demo_packet
from piper_agent.data.soil_lookup import lookup_soil

logger = logging.getLogger("pier.agent")

EVENT_WINDOW_DAYS = 7  # BR-1: look for the 3-day peak in the last week ending today


def run_pier(
    lat: float,
    lon: float,
    current_date: str,
    demo_mode: bool = True,
    demo_name: str | None = None,
    pesos_agricultor: dict[str, float] | None = None,
    rendimiento_t_ha: float | None = None,
    season_start: str | None = None,
) -> dict[str, Any]:
    """Run the full PIER agent pipeline.

    Args:
        lat, lon: field location.
        current_date: ISO date "now".
        demo_mode: if True, serve all data from cache (demo path).
        demo_name: which demo packet to use ("flood", "drought", "normal").
                   If None, auto-select based on lat/lon matching.
        pesos_agricultor: farmer priorities {soil_protection, salvage_revenue,
                   water_conservation}; re-ranks the crops (BR-10) and biases the rotation.
        rendimiento_t_ha: expected yield for the savings estimate (default 1.5 t/ha).
        season_start: ISO date; production path only (default: 1 Apr north / 1 Oct south).

    Returns:
        Structured dict with event_result, gdd_result, crops, recovery_plan, plan_text and
        the contract keys. Every contract key may be None: read them with `.get()`.
    """
    rendimiento = rendimiento_t_ha if rendimiento_t_ha else DEFAULT_YIELD_T_HA

    if demo_mode:
        src = _demo_source(lat, lon, current_date, demo_name)
    else:
        src = _live_source(lat, lon, current_date, season_start)
    demo_name = src["demo_name"]

    # --- Step 1: detect_event (BR-1) ---
    event_result: EventResult = detect_event(
        lat=lat, lon=lon, recent_start=src["recent_start"], recent_end=src["recent_end"],
        **src["detect_kwargs"],
    )
    event_result.details["requested_date"] = current_date
    if src["window_note"]:
        event_result.details["window_note"] = src["window_note"]

    # --- Failure taxonomy: conflicting data lower the confidence ---
    state: dict[str, Any] = dict(event_result.details.get("data_status") or {})
    if state.get("status") == CONFLICTING:
        before = event_result.confidence
        event_result.confidence = round(before * CONFLICT_CONFIDENCE_FACTOR, 3)
        event_result.details["confidence"] = event_result.confidence
        event_result.details["confidence_before_conflict"] = round(before, 3)

    # --- Step 2: fetch_power_gdd (BR-3) ---
    hemisphere = "south" if lat < 0 else "north"
    gdd_result: GddResult = fetch_power_gdd(
        lat=lat, lon=lon, season_start=src["season_start"], current_date=current_date,
        hemisphere=hemisphere, **src["gdd_kwargs"],
    )
    gdd_state = (gdd_result.details or {}).get("data_status") or {}
    if gdd_state.get("status") == NO_DATA:
        state = dict(gdd_state)

    # --- Step 3: filter_rescue_crops (BR-2, BR-3, BR-4) ---
    # No event or no data: there is nothing to rescue, so nothing is ranked.
    crops: list[CropRecommendation] = []
    if event_result.event_type != "none" and state.get("status") != NO_DATA:
        crops = filter_rescue_crops(
            event_type=event_result.event_type,
            gdd_remaining=gdd_result.gdd_remaining,
            current_date=current_date,
            avg_daily_gdd=gdd_result.avg_daily_gdd,
            farmer_weights=pesos_agricultor,
        )

    # --- Weather alerts and evidence tags (printed in the plan and returned as keys) ---
    fuente = src["fuente_datos"]
    ola_calor = _safe("ola_calor", detect_heat_wave, lat, lon, src["recent_start"], src["recent_end"],
                      power=src["power"])
    helada = _safe("helada", detect_frost, lat, lon, src["recent_start"], src["recent_end"],
                   power=src["power"])
    evidencia = _safe("evidencia", _build_evidencia, event_result, gdd_result, crops, fuente, state)

    # --- Step 4: generate_recovery_plan (BR-5, BR-6) ---
    current_dt = datetime.fromisoformat(current_date).date()
    plan_text, recovery_plan = generate_recovery_plan(
        event_result=event_result,
        gdd_result=gdd_result,
        crops=crops,
        current_date=current_dt,
        data_status=state,
        heat_wave=ola_calor,
        frost=helada,
        evidence=evidencia,
    )
    recovery_plan: RecoveryPlan = recovery_plan
    if src["window_note"]:
        plan_text = f"{plan_text}\nNote: {src['window_note']}"
        recovery_plan.plan_text = plan_text

    result: dict[str, Any] = {
        "event_result": event_result,
        "gdd_result": gdd_result,
        "crops": crops,
        "recovery_plan": recovery_plan,
        "plan_text": plan_text,
        "demo_mode": demo_mode,
        "demo_name": demo_name,
        # contract keys (read with .get() downstream)
        "fuente_datos": fuente,
        "fallback_reason": src["fallback_reason"],
        "ultima_actualizacion": src["ultima_actualizacion"],
        "estado_datos": state,
        "cambio_fuente": _safe("cambio_fuente", track_data_source,
                               src["region"], fuente, src["fallback_reason"]),
    }
    priority = dominant_priority(pesos_agricultor)
    result["exclusiones"] = _safe("exclusiones", _build_exclusiones, crops, event_result, gdd_result, state)
    result["rotacion"] = _safe("rotacion", _build_rotacion, crops, recovery_plan, priority)
    result["ahorro"] = _safe("ahorro", _build_ahorro, crops, rendimiento, current_date)
    result["confianza_calibrada"] = _safe(
        "confianza_calibrada", _build_confianza, lat, lon, event_result, recovery_plan)
    result["suelo"] = _safe("suelo", lookup_soil, lat, lon, demo_mode=demo_mode)
    result["ola_calor"] = ola_calor
    result["helada"] = helada
    result["evidencia"] = evidencia
    return result


def _safe(key: str, fn, *args, **kwargs):
    """A contract key that cannot be built must not sink the plan: log it and return None."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Contract key %s could not be built: %s: %s", key, type(exc).__name__, exc)
        return None


# ── Data sources ─────────────────────────────────────────────────────────────

def _demo_source(lat: float, lon: float, current_date: str, demo_name: str | None) -> dict[str, Any]:
    """Cache path: the tools load their own data by `demo_name`."""
    from piper_agent.data.cache_loader import load_imerg, load_power

    if demo_name is None:
        pkt = _auto_select_demo(lat, lon, current_date)
        demo_name = pkt["name"].replace("_demo", "")
    packet = load_demo_packet(f"{demo_name}_demo")
    recent_start, recent_end, window_note = _detection_window(packet, current_date)
    return {
        "demo_name": demo_name,
        "season_start": packet["season_start"],
        "recent_start": recent_start,
        "recent_end": recent_end,
        "window_note": window_note,
        "detect_kwargs": {"demo_name": demo_name},
        "gdd_kwargs": {"demo_name": demo_name},
        "power": load_power(demo_name),
        "fuente_datos": packet.get("fuente_datos", "sintetico"),
        "fallback_reason": None,
        "region": demo_name,
        "ultima_actualizacion": str(load_imerg(demo_name)["date"].max())[:10],
    }


def _live_source(lat: float, lon: float, current_date: str, season_start: str | None) -> dict[str, Any]:
    """Production path: data from the ingestion layer; it falls back to synthetic data, labeled."""
    from piper_agent.tools.live_inputs import load_live

    live = load_live(lat, lon, current_date, season_start=season_start, demo_mode=False)
    end = date.fromisoformat(current_date)
    alt_rainfall = None
    if live["fuente_datos"] == "nasa_power+imerg":
        # IMERG is the primary rainfall; POWER's own rainfall is the independent check.
        alt_rainfall = live["power"][["date", "PRECTOTCORR"]].rename(
            columns={"PRECTOTCORR": "precipitation_mm"})
    return {
        "demo_name": None,
        "season_start": live["season_start"],
        "recent_start": (end - timedelta(days=EVENT_WINDOW_DAYS - 1)).isoformat(),
        "recent_end": current_date,
        "window_note": None,
        "detect_kwargs": {"rainfall": live["rainfall"], "baselines": live["baselines"],
                          "alt_rainfall": alt_rainfall, "climatology": live["climatology"]},
        "gdd_kwargs": {"power": live["power"], "baselines": live["baselines"]},
        "power": live["power"],
        "fuente_datos": live["fuente_datos"],
        "fallback_reason": live["fallback_reason"],
        "region": live["region"],
        "ultima_actualizacion": live["ultima_actualizacion"],
    }


# ── Contract-key builders ────────────────────────────────────────────────────

def dominant_priority(pesos: dict[str, float] | None) -> str:
    """Farmer priority with the highest weight (ties: soil, revenue, water)."""
    if not pesos:
        return "soil_protection"
    order = ("soil_protection", "salvage_revenue", "water_conservation")
    return max(order, key=lambda k: (pesos.get(k, 0.0), -order.index(k)))


def _build_exclusiones(crops, event_result, gdd_result, state) -> list[dict]:
    """BR-8: why each crop was left out ([] when nothing was evaluated)."""
    if event_result.event_type == "none" or state.get("status") == NO_DATA:
        return []
    from piper_agent.tools.explain_exclusion import exclusion_records
    from piper_agent.tools.filter_rescue_crops import DEFAULT_CROPS_CSV

    all_crops = pd.read_csv(DEFAULT_CROPS_CSV).to_dict("records")
    return exclusion_records(all_crops, [{"crop": c.crop} for c in crops],
                             event_result.event_type, gdd_result.gdd_remaining)


def _build_rotacion(crops, recovery_plan, priority) -> dict | None:
    """BR-9/12: rescue → main → cover. With the BR-5 fallback the rescue crop is the cover rye."""
    from piper_agent.tools.plan_rotation import plan_rotation

    if crops:
        rescue = crops[0].crop
    elif recovery_plan.fallback:
        rescue = "Cereal rye (cover)"
    else:
        return None
    rotation = plan_rotation(rescue, {"farmer_priority": priority})
    rotation["prioridad"] = priority
    return rotation


def _build_ahorro(crops, rendimiento: float, current_date: str) -> dict | None:
    """BR-11: estimated USD/ha rescued by the top crop (None when nothing is rescued)."""
    if not crops:
        return None
    from piper_agent.tools.fetch_market_price import compute_dollar_savings

    ahorro = compute_dollar_savings(crops[0].crop, expected_yield_tons_per_ha=rendimiento,
                                    date_str=current_date)
    ahorro["usd_por_ha"] = ahorro["estimated_savings_usd_per_ha"]
    ahorro["rendimiento_t_ha"] = rendimiento
    ahorro["es_estimado"] = True
    return ahorro


def _build_confianza(lat: float, lon: float, event_result, recovery_plan) -> dict[str, Any]:
    """Calibrated confidences: conformal with local history, analogs with archived events,
    and the raw value (labeled `no_history`) otherwise."""
    from piper_agent.data.calibration import validation_history
    from piper_agent.tools.confidence_calibration import calibrate_confidence
    from piper_agent.tools.search_analogs import analog_calibrated_confidence, search_analogs

    event_type = event_result.event_type
    history = [h for h in validation_history(lat, lon) if h.get("event_type") == event_type]
    raw_event, raw_rescue = event_result.confidence, recovery_plan.rescue_confidence
    if len(history) >= MIN_HISTORY_FOR_CALIBRATION:
        method = "conformal"
        evento = calibrate_confidence(raw_event, event_type, history)
        rescate = calibrate_confidence(raw_rescue, event_type, history)
    else:
        analogs = search_analogs(event_type, lat, lon, recovery_plan.gdd_remaining)
        if analogs:
            method = "analogs"
            evento = analog_calibrated_confidence(analogs, raw_event)
            rescate = analog_calibrated_confidence(analogs, raw_rescue)
        else:
            method = "no_history"
            evento, rescate = raw_event, raw_rescue
    return {
        "evento": round(evento, 3), "rescate": round(rescate, 3),
        "evento_bruta": round(raw_event, 3), "rescate_bruta": round(raw_rescue, 3),
        "metodo": method, "calibrado": method != "no_history", "n_observaciones": len(history),
    }


def _build_evidencia(event_result, gdd_result, crops, fuente: str, state: dict) -> list[dict]:
    """Evidence tags for the event and for every recommended crop."""
    d = event_result.details
    event_tags = [f"source:{fuente}", f"data_status:{state.get('status', 'unknown')}"]
    if "cum3_mm" in d:
        event_tags.append(f"cum3_mm:{d['cum3_mm']}/threshold:{d.get('flood_threshold_mm')}")
    if "cum30_mm" in d:
        event_tags.append(f"cum30_mm:{d['cum30_mm']}/p10:{d.get('p10_30day_cum')}")
    out = [{"item": "event", "tags": event_tags}]
    for c in crops:
        out.append({"item": c.crop, "tags": [
            f"source:{fuente}",
            f"gdd_margin_pct:{c.margin_pct}",
            f"gdd_requirement:{c.gdd_requirement}/remaining:{c.gdd_remaining}",
            f"remaining_method:{(gdd_result.details or {}).get('remaining_method')}",
            f"plant_by:{c.plant_by_date}",
        ]})
    return out


def _detection_window(packet: dict, current_date: str) -> tuple[str, str, str | None]:
    """BR-1 window: the last EVENT_WINDOW_DAYS days ending on ``current_date``.

    Cached rainfall for a demo ends on the packet's ``recent_end``. A later date is
    evaluated on the newest available week instead, and the returned note says so
    (the plan text and the API surface it).
    """
    today = date.fromisoformat(current_date)
    data_end = date.fromisoformat(packet["recent_end"])
    end = min(today, data_end)
    note = None
    if today > data_end:
        note = (f"Rainfall data for this demo ends {data_end.isoformat()}; "
                f"event detection uses the week ending on that date.")
    start = end - timedelta(days=EVENT_WINDOW_DAYS - 1)
    return start.isoformat(), end.isoformat(), note


def _auto_select_demo(lat: float, lon: float, current_date: str | None = None) -> dict:
    """Pick the demo packet for (lat, lon) whose data best covers ``current_date``.

    Several packets can share a location (Iowa: flood, normal, late_flood). The
    choice depends on the date, never on the expected event: the first packet
    whose rainfall data reaches ``current_date``; if none does, the one with the
    newest data. Falls back to the flood demo when no packet is near.
    """
    here = []
    for name in ESCENARIOS:
        pkt = load_demo_packet(f"{name}_demo")
        if abs(pkt["lat"] - lat) < 0.5 and abs(pkt["lon"] - lon) < 0.5:
            here.append(pkt)
    if not here:
        return load_demo_packet("flood_demo")
    if current_date is None:
        return min(here, key=lambda p: p.get("current_date", ""))
    covering = [p for p in here if p["recent_end"] >= current_date]
    if covering:
        return min(covering, key=lambda p: p["recent_end"])
    return max(here, key=lambda p: p["recent_end"])


def plan_text_only(lat: float, lon: float, current_date: str, demo_mode: bool = True, demo_name: str | None = None) -> str:
    """Convenience: run PIER and return just the plan text (for CLI/UI)."""
    result = run_pier(lat, lon, current_date, demo_mode, demo_name)
    return result["plan_text"]
