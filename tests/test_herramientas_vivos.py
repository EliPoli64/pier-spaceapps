"""Tests for the live-data tools: failure taxonomy, live inputs, contract keys (A10), source alert (A11).

Every test runs offline: live data are built in memory or come from the `offline_live`
fixture (tests/conftest.py), and demo-mode behavior is left unchanged.
"""
from __future__ import annotations

import json
import logging
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from piper_agent.agent import dominant_priority, run_pier  # noqa: E402
from piper_agent.contracts import EventResult  # noqa: E402
from piper_agent.tools import live_inputs  # noqa: E402
from piper_agent.tools.detect_event import detect_event, detect_heat_wave  # noqa: E402
from piper_agent.tools.explain_exclusion import exclusion_records  # noqa: E402
from piper_agent.tools.failure_taxonomy import classify_data_state, sources_disagree  # noqa: E402
from piper_agent.tools.fetch_power_gdd import fetch_power_gdd  # noqa: E402

CONTRACT_KEYS = ("exclusiones", "rotacion", "ahorro", "confianza_calibrada", "suelo",
                 "ola_calor", "fuente_datos")

BASELINES = {"p95_3day_cum_rainfall": 40.0, "p10_30day_cum_rainfall": 30.0}


def _rain(values: list[float], end: str = "2025-06-30") -> pd.DataFrame:
    dates = pd.date_range(end=end, periods=len(values), freq="D")
    return pd.DataFrame({"date": dates, "precipitation_mm": values})


def _detect(rainfall, baselines=BASELINES, **kw) -> EventResult:
    return detect_event(41.8, -93.6, "2025-06-24", "2025-06-30", rainfall=rainfall,
                        baselines=baselines, **kw)


# ── Failure taxonomy (pure function) ─────────────────────────────────────────

def test_taxonomy_no_data_without_thresholds():
    s = classify_data_state("none", 30, thresholds_available=False)
    assert (s["status"], s["route"]) == ("no_data", "stop")


def test_taxonomy_no_data_with_sparse_window():
    assert classify_data_state("none", 10, True)["status"] == "no_data"


def test_taxonomy_conflicting_sources():
    s = classify_data_state("flood", 30, True, cum3_mm=90.0, alt_cum3_mm=20.0)
    assert (s["status"], s["route"]) == ("conflicting", "continue_with_caution")


def test_taxonomy_conflicting_with_climatology():
    assert classify_data_state("none", 30, True, climatology_status="extreme")["status"] == "conflicting"
    assert classify_data_state("flood", 30, True, climatology_status="normal")["status"] == "conflicting"


def test_taxonomy_normal_and_event():
    assert classify_data_state("none", 30, True)["status"] == "normal"
    assert classify_data_state("drought", 30, True)["status"] == "event"


def test_sources_disagree_needs_absolute_and_relative_gap():
    assert not sources_disagree(5.0, 12.0)      # relative gap but only 7 mm
    assert not sources_disagree(100.0, 95.0)    # small relative gap
    assert sources_disagree(100.0, 40.0)


# ── detect_event on live data ────────────────────────────────────────────────

def test_detect_event_flood_from_injected_rainfall():
    rain = _rain([1.0] * 27 + [30.0, 40.0, 30.0])
    result = _detect(rain)
    assert result.event_type == "flood"
    assert result.details["data_status"]["status"] == "event"


def test_detect_event_normal_from_injected_rainfall():
    result = _detect(_rain([3.0] * 30))
    assert result.event_type == "none"
    assert result.details["data_status"]["status"] == "normal"


def test_detect_event_missing_rain_is_no_data_not_drought():
    """Ten days of data used to read as a 30-day deficit, i.e. 'drought'."""
    result = _detect(_rain([0.0] * 10))
    assert result.event_type == "none" and result.confidence == 0.0
    assert result.details["data_status"]["status"] == "no_data"


def test_detect_event_without_thresholds_is_no_data():
    result = _detect(_rain([3.0] * 30), baselines={})
    assert result.details["data_status"]["status"] == "no_data"


def test_detect_event_independent_source_conflict():
    rain = _rain([1.0] * 27 + [30.0, 40.0, 30.0])
    alt = _rain([1.0] * 30)
    assert _detect(rain, alt_rainfall=alt).details["data_status"]["status"] == "conflicting"


def test_detect_event_climatology_cross_check():
    climatology = {"fuente_datos": "nasa_power", "version": "1", "months": {
        "6": {"rain_3d": {"p05": 1, "p10": 2, "p50": 10, "p90": 120, "p95": 150}}}}
    rain = _rain([1.0] * 27 + [30.0, 40.0, 30.0])   # flood by the baselines, normal for the climatology
    assert _detect(rain, climatology=climatology).details["data_status"]["status"] == "conflicting"


def test_detect_event_demo_path_reports_its_status():
    result = detect_event(41.8, -93.6, "2025-05-09", "2025-05-15", demo_name="flood")
    assert result.details["data_status"]["status"] == "event"


def test_heat_wave_accepts_injected_power():
    dates = pd.date_range("2025-06-24", periods=7)
    power = pd.DataFrame({"date": dates, "T2M_MAX": [38.0] * 7, "T2M_MIN": [22.0] * 7})
    out = detect_heat_wave(41.8, -93.6, "2025-06-24", "2025-06-30", power=power)
    assert out["event_type"] == "heat_wave"
    assert out["details"]["data_status"] == "event"


# ── fetch_power_gdd on live data ─────────────────────────────────────────────

def _power(days: int = 90, end: str = "2025-06-30") -> pd.DataFrame:
    dates = pd.date_range(end=end, periods=days, freq="D")
    return pd.DataFrame({"date": dates, "T2M_MAX": 26.0, "T2M_MIN": 14.0})


def test_gdd_live_projects_the_remaining_gdd_from_the_climatology():
    baselines = {"climatological_frost_date": "2025-10-15", "frost_is_local": True,
                 "monthly_gdd_normal": {str(m): 10.0 for m in range(1, 13)}}
    out = fetch_power_gdd(41.8, -93.6, "2025-04-01", "2025-06-30", power=_power(), baselines=baselines)
    assert out.details["remaining_method"] == "climatological_projection"
    assert out.gdd_remaining == pytest.approx(10.0 * 107)   # Jul 1 .. Oct 15
    assert out.gdd_accumulated > 0
    assert out.details["data_status"]["status"] == "ok"


def test_gdd_live_without_frost_reference_is_no_data():
    out = fetch_power_gdd(41.8, -93.6, "2025-04-01", "2025-06-30", power=_power(),
                          baselines={"climatological_frost_date": None})
    assert out.details["data_status"]["status"] == "no_data"


def test_gdd_demo_path_unchanged():
    out = fetch_power_gdd(41.8, -93.6, "2025-04-01", "2025-05-15", demo_name="flood")
    assert out.details["remaining_method"] == "observed_cache"
    assert out.gdd_remaining > 0


# ── Exclusions ───────────────────────────────────────────────────────────────

def test_exclusion_records_carry_a_machine_readable_reason():
    crops = [{"crop": "Millet", "waterlogging_tolerance": "Low", "gdd_to_maturity_max": 1400},
             {"crop": "Sorghum", "waterlogging_tolerance": "Medium", "gdd_to_maturity_max": 9000}]
    records = exclusion_records(crops, [], "flood", 1500.0)
    assert [(r["crop"], r["motivo"]) for r in records] == [
        ("Millet", "tolerance_waterlogging"), ("Sorghum", "gdd_window")]
    assert all(r["explicacion"] for r in records)


# ── A10 (PP4): run_pier returns every contract key; downstream reads with .get() ─────

def test_a10_run_pier_returns_every_contract_key():
    res = run_pier(41.8, -93.6, "2025-05-15", demo_mode=True, demo_name="flood")
    for key in CONTRACT_KEYS:
        assert res.get(key) is not None, key
    assert res["fuente_datos"] == "sintetico"
    assert res["exclusiones"] and {"crop", "motivo", "explicacion"} <= set(res["exclusiones"][0])
    assert len(res["rotacion"]["rotation_sequence"]) == 3
    assert res["ahorro"]["usd_por_ha"] > 0 and res["ahorro"]["es_estimado"] is True
    assert {"evento", "rescate", "metodo", "calibrado"} <= set(res["confianza_calibrada"])
    assert res["suelo"]["texture_class"] and res["ola_calor"]["event_type"] in ("heat_wave", "none")


def test_a10_every_key_is_json_serializable_with_the_api_helper():
    from piper_agent.api.services import to_jsonable

    res = run_pier(41.8, -93.6, "2025-05-15", demo_mode=True, demo_name="flood")
    for key in CONTRACT_KEYS + ("estado_datos", "evidencia"):
        json.dumps(to_jsonable(res.get(key)))


def test_a10_normal_scenario_has_nothing_to_rescue():
    res = run_pier(41.8, -93.6, "2025-07-07", demo_mode=True, demo_name="normal")
    assert res["estado_datos"]["status"] == "normal"
    assert res["crops"] == [] and res["recovery_plan"].fallback is False
    assert res["rotacion"] is None and res["ahorro"] is None and res["exclusiones"] == []
    assert res["fuente_datos"] and res["suelo"]


def test_a10_a_failing_key_is_dropped_not_fatal(monkeypatch):
    import piper_agent.agent as agent_mod

    def broken(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(agent_mod, "lookup_soil", broken)
    res = run_pier(41.8, -93.6, "2025-05-15", demo_mode=True, demo_name="flood")
    assert res.get("suelo") is None and res["crops"]


def test_pesos_and_rendimiento_change_the_result():
    soil = run_pier(41.8, -93.6, "2025-05-15", True, "flood", pesos_agricultor={"soil_protection": 1.0})
    money = run_pier(41.8, -93.6, "2025-05-15", True, "flood",
                     pesos_agricultor={"salvage_revenue": 1.0}, rendimiento_t_ha=3.0)
    assert soil["crops"][0].crop != money["crops"][0].crop
    assert money["rotacion"]["prioridad"] == "salvage_revenue"
    assert money["ahorro"]["rendimiento_t_ha"] == 3.0


def test_dominant_priority():
    assert dominant_priority(None) == "soil_protection"
    assert dominant_priority({"water_conservation": 0.7, "salvage_revenue": 0.2}) == "water_conservation"


def test_rescue_confidence_is_not_saturated():
    res = run_pier(41.8, -93.6, "2025-05-15", True, "flood")
    confs = [c.rescue_confidence for c in res["crops"]]
    assert max(confs) < 1.0 or len(set(confs)) > 1


# ── Production path (offline) ────────────────────────────────────────────────

def test_live_run_without_network_is_labeled_synthetic(offline_live):
    res = run_pier(41.8, -93.6, "2025-06-25", demo_mode=False)
    assert res["demo_mode"] is False and res["demo_name"] is None
    assert res["fuente_datos"] == "sintetico"
    assert res["fallback_reason"]
    assert res["estado_datos"]["status"] in ("event", "normal", "conflicting", "no_data")
    for key in CONTRACT_KEYS:
        assert key in res


def test_live_season_start_default_follows_the_hemisphere():
    assert live_inputs.default_season_start(41.8, "2025-06-25") == "2025-04-01"
    assert live_inputs.default_season_start(41.8, "2025-02-01") == "2024-04-01"
    assert live_inputs.default_season_start(-33.0, "2025-02-01") == "2024-10-01"


def test_live_tools_can_fetch_their_own_data(offline_live):
    event = detect_event(41.8, -93.6, "2025-06-19", "2025-06-25", demo_mode=False)
    assert event.details["data_status"]["status"] in ("event", "normal", "conflicting", "no_data")
    gdd = fetch_power_gdd(41.8, -93.6, "2025-04-01", "2025-06-25", demo_mode=False)
    assert gdd.details["remaining_method"] in ("climatological_projection", "observed_cache")


def test_conflicting_data_lower_the_confidence(monkeypatch):
    import piper_agent.agent as agent_mod

    real = agent_mod.detect_event

    def conflicting(**kw):
        res = real(**kw)
        res.details["data_status"] = {"status": "conflicting", "route": "continue_with_caution",
                                      "reason": "sources disagree"}
        return res

    monkeypatch.setattr(agent_mod, "detect_event", conflicting)
    res = run_pier(41.8, -93.6, "2025-05-15", True, "flood")
    ev = res["event_result"]
    assert ev.confidence == pytest.approx(ev.details["confidence_before_conflict"] * 0.6, abs=0.01)
    assert "conflicting data" in res["plan_text"]


def test_no_data_issues_no_recommendation(monkeypatch):
    import piper_agent.agent as agent_mod

    def empty(**kw):
        return EventResult("none", "low", 0.0, {"data_status": {
            "status": "no_data", "route": "stop", "reason": "no rain data"}})

    monkeypatch.setattr(agent_mod, "detect_event", empty)
    res = run_pier(41.8, -93.6, "2025-05-15", True, "flood")
    assert res["crops"] == [] and res["recovery_plan"].fallback is False
    assert "Insufficient data" in res["plan_text"]


# ── A11 (PP5): alert when the source degrades ────────────────────────────────

def test_a11_alert_when_real_source_falls_back(caplog):
    live_inputs._LAST_SOURCE.clear()
    assert live_inputs.track_data_source("r1", "nasa_power") is None
    with caplog.at_level(logging.WARNING, logger="pier.tools.live_inputs"):
        entry = live_inputs.track_data_source("r1", "sintetico", "NASA POWER unavailable: timeout")
    assert entry["previous_source"] == "nasa_power" and entry["current_source"] == "sintetico"
    assert entry["reason"] == "NASA POWER unavailable: timeout" and entry["timestamp"].endswith("Z")
    record = next(r for r in caplog.records if "PIER_ALERT" in r.getMessage())
    assert json.loads(record.getMessage().split("PIER_ALERT ", 1)[1])["event"] == "data_source_degraded"


def test_a11_no_alert_without_degradation():
    live_inputs._LAST_SOURCE.clear()
    assert live_inputs.track_data_source("r2", "sintetico") is None
    assert live_inputs.track_data_source("r2", "sintetico") is None      # synthetic -> synthetic
    live_inputs._LAST_SOURCE["r2"] = "nasa_power"
    assert live_inputs.track_data_source("r2", "nasa_power+imerg") is None  # real -> real


def test_a11_run_pier_reports_the_source_change(offline_live):
    live_inputs._LAST_SOURCE.clear()
    from piper_agent.data.ingestion.pipeline import region_key

    live_inputs._LAST_SOURCE[region_key(41.8, -93.6)] = "nasa_power"
    res = run_pier(41.8, -93.6, "2025-06-25", demo_mode=False)
    assert res["cambio_fuente"]["previous_source"] == "nasa_power"
