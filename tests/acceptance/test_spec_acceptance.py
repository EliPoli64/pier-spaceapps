"""Q2 — Acceptance tests: Spec §10 success metrics + business-rule invariants.

Only the stable contract is used: ``run_pier(...)`` / its result dict and
``load_demo_packet``. Each test is either:

* a requirement that already holds (must stay green), or
* a known gap, marked ``@gap(owner, task, why)`` — it turns into XPASS
  when the owner's branch fixes it (then delete the marker).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from conftest import REPO_ROOT, gap

from piper_agent.agent import run_pier
from piper_agent.data.cache_loader import load_demo_packet

CROPS_CSV = Path(REPO_ROOT) / "piper_agent" / "data" / "rescue_crops.csv"
LATE_SEASON_DATE = "2025-09-30"          # Iowa, after the climatological frost window
COVER_CROPS = ("Cereal rye", "Buckwheat")


def scenario(name: str, current_date: str | None = None, **kw) -> dict:
    pkt = load_demo_packet(f"{name}_demo")
    return run_pier(lat=pkt["lat"], lon=pkt["lon"],
                    current_date=current_date or pkt["current_date"],
                    demo_mode=True, demo_name=name, **kw)


def crops_db() -> pd.DataFrame:
    return pd.read_csv(CROPS_CSV)


def _plan(res: dict):
    return res["recovery_plan"]


# ═════════════════════ Spec §10 — success metrics (must hold) ═════════════════

@pytest.mark.parametrize("name,expected", [("flood", "flood"), ("drought", "drought"),
                                           ("normal", "none")])
def test_s10_event_classification(name, expected):
    assert scenario(name)["event_result"].event_type == expected


@pytest.mark.parametrize("name", ["flood", "drought"])
def test_s10_at_least_two_rescue_crops(name):
    crops = scenario(name)["crops"]
    assert len(crops) >= 2, [c.crop for c in crops]


def test_q7_late_flood_packet_shows_fallback():
    res = scenario("late_flood")
    assert res["event_result"].event_type == "flood"
    assert _plan(res).fallback is True and res["crops"] == []
    assert "cash crop is lost" in res["plan_text"]


def test_q6_autodetect_by_date():
    pkt = load_demo_packet("flood_demo")
    def auto(d):
        return run_pier(lat=pkt["lat"], lon=pkt["lon"], current_date=d, demo_mode=True)
    assert auto("2025-05-15")["event_result"].event_type == "flood"
    assert auto("2025-06-25")["event_result"].event_type == "none"
    assert auto("2025-08-28")["demo_name"] == "late_flood"


def test_q6_date_after_data_is_noted_in_plan():
    res = scenario("flood", "2025-09-30")
    assert "Note: Rainfall data for this demo ends" in res["plan_text"]


def test_s10_fallback_when_window_too_short():
    res = scenario("flood", LATE_SEASON_DATE)
    plan = _plan(res)
    assert plan.fallback is True
    assert res["crops"] == []
    assert "cash crop is lost" in res["plan_text"]
    assert any(c in res["plan_text"] for c in COVER_CROPS)


@pytest.mark.parametrize("name", ["flood", "drought", "normal"])
def test_s10_demo_is_cache_only(name, no_network):
    scenario(name)
    assert no_network == [], f"network calls attempted: {no_network}"


def test_s10_late_season_is_cache_only(no_network):
    scenario("flood", LATE_SEASON_DATE)
    assert no_network == []


# ═════════════════════ Business rules (must hold) ═════════════════════════════

def test_br2_flood_excludes_low_waterlogging():
    low = set(crops_db().query("waterlogging_tolerance == 'Low'")["crop"])
    assert not {c.crop for c in scenario("flood")["crops"]} & low


def test_br2_drought_excludes_low_drought_tolerance():
    low = set(crops_db().query("drought_tolerance == 'Low'")["crop"])
    assert not {c.crop for c in scenario("drought")["crops"]} & low


@pytest.mark.parametrize("name", ["flood", "drought"])
def test_br3_gdd_safety_margin(name):
    for c in scenario(name)["crops"]:
        assert c.gdd_requirement <= 0.8 * c.gdd_remaining + 1e-6, c


@pytest.mark.parametrize("name", ["flood", "drought"])
def test_br4_explicit_plant_by_and_latest_first(name):
    res = scenario(name)
    today = date.fromisoformat(load_demo_packet(f"{name}_demo")["current_date"])
    dates = [c.plant_by_date for c in res["crops"]]
    assert dates == sorted(dates, reverse=True)
    for c in res["crops"]:
        assert c.plant_by_date == (today + timedelta(days=c.days_until_deadline)).isoformat()
        assert c.plant_by_date in res["plan_text"]


@pytest.mark.parametrize("name", ["flood", "drought", "normal"])
def test_br6_separate_confidences(name):
    text = scenario(name)["plan_text"]
    assert "Event detection:" in text
    assert "Rescue recommendation confidence" in text
    plan = _plan(scenario(name))
    assert 0.0 <= plan.event_confidence <= 1.0 and 0.0 <= plan.rescue_confidence <= 1.0


def test_br8_every_excluded_crop_has_a_reason():
    from piper_agent.tools.explain_exclusion import explain_all_exclusions

    res = scenario("flood")
    all_crops = crops_db().to_dict("records")
    reasons = explain_all_exclusions(all_crops, [{"crop": c.crop} for c in res["crops"]],
                                     "flood", res["gdd_result"].gdd_remaining)
    assert len(reasons) == len(all_crops) - len(res["crops"])
    assert all(r.strip() for r in reasons)


def test_br10_weights_change_the_order():
    from piper_agent.tools.filter_rescue_crops import filter_rescue_crops

    kw = dict(event_type="flood", gdd_remaining=2000.0, current_date="2025-05-15",
              avg_daily_gdd=15.0, crops_csv=str(CROPS_CSV))
    soil = [c.crop for c in filter_rescue_crops(**kw, farmer_weights={"soil_protection": 1})]
    revenue = [c.crop for c in filter_rescue_crops(**kw, farmer_weights={"salvage_revenue": 1})]
    assert soil != revenue


# ═════════════════════ Known gaps (xfail until the owner's branch lands) ═══════

@gap("Alina", "A3", "No event must not say the cash crop is lost nor trigger the BR-5 fallback.")
def test_gap_normal_scenario_is_not_a_fallback():
    res = scenario("normal")
    assert _plan(res).fallback is False
    assert "cash crop is lost" not in res["plan_text"]


@gap("Alina", "A4", "run_pier must return the contract keys for B-team.")
def test_gap_run_pier_returns_contract_keys():
    res = scenario("flood")
    for key in ("exclusiones", "rotacion", "ahorro", "fuente_datos"):
        assert res.get(key) is not None, key


@gap("Alina", "A4", "run_pier must accept pesos_agricultor and rendimiento_t_ha.")
def test_gap_run_pier_accepts_weights_and_yield():
    res = scenario("flood", pesos_agricultor={"soil_protection": 1.0}, rendimiento_t_ha=2.0)
    assert res["crops"][0].crop.startswith("Cereal rye")


@gap("Alina", "A7", "Rescue confidence saturates at 100% for every crop in typical cases.")
def test_gap_confidence_not_saturated():
    confs = [c.rescue_confidence for c in scenario("flood")["crops"]]
    assert max(confs) < 1.0 or len(set(confs)) > 1


@gap("Alina", "A8", "Rotation must not repeat the rescue crop as the final cover.")
def test_gap_rotation_does_not_repeat_rescue_crop():
    from piper_agent.tools.plan_rotation import plan_rotation

    for crop in crops_db()["crop"]:
        seq = plan_rotation(crop, {})["rotation_sequence"]
        assert seq[-1] != seq[0], seq


def test_q6_detection_follows_current_date():
    res = scenario("normal", "2025-06-15")
    details = res["event_result"].details
    end = details.get("recent_end") or details.get("current_date")
    assert end == "2025-06-15", details


@gap("Neithan", "Q5", "GDD remaining is summed from FUTURE observations in the "
     "cache (look-ahead). On the decision date only climatology is known: truncating the "
     "data after current_date must not change the answer.")
def test_gap_gdd_remaining_has_no_lookahead(monkeypatch):
    import piper_agent.tools.fetch_power_gdd as gdd_mod

    full = gdd_mod.fetch_power_gdd(lat=41.8, lon=-93.6, season_start="2025-04-01",
                                   current_date="2025-05-15", demo_name="flood")
    real_load = gdd_mod.load_power

    def truncated(name):
        df = real_load(name)
        return df[pd.to_datetime(df["date"]) <= "2025-05-15"].copy()

    monkeypatch.setattr(gdd_mod, "load_power", truncated)
    cut = gdd_mod.fetch_power_gdd(lat=41.8, lon=-93.6, season_start="2025-04-01",
                                  current_date="2025-05-15", demo_name="flood")
    assert cut.gdd_remaining > 0
    assert abs(cut.gdd_remaining - full.gdd_remaining) / max(full.gdd_remaining, 1) < 0.25


def test_tropical_drought_demo_is_plausible():
    res = scenario("drought")
    assert res["gdd_result"].gdd_accumulated > 0
    assert max(c.days_until_deadline for c in res["crops"]) > 0


@gap("Neithan", "N1", "Tropics (|lat| < 23.5) have no climatological frost; the season "
     "ends with the rains and the method must be recorded in details.")
def test_gap_tropics_have_no_frost():
    details = scenario("drought")["gdd_result"].details or {}
    method = str(details.get("season_end_method") or details.get("method") or "")
    assert method in ("fin_temporada_lluvias", "rainy_season_end"), details


@pytest.mark.parametrize("name", ["flood", "drought", "normal", "late_flood"])
def test_packets_have_season_end(name):
    """season_end is present in every packet; tropical sites (no frost) must set it."""
    pkt = load_demo_packet(f"{name}_demo")
    assert "season_end" in pkt
    if abs(pkt["lat"]) < 23.5:
        assert pkt["season_end"], pkt


def test_q7_fallback_has_its_own_demo_packet():
    packets = list((Path(REPO_ROOT) / "demo").glob("*_demo.json"))
    names = {p.stem.removesuffix("_demo") for p in packets}
    assert names - {"flood", "drought", "normal"}, names


@gap("Alina", "A2/D2", "filter_rescue_crops defaults crops_csv to a cwd-relative path; "
     "run_pier fails outside the repo root.")
def test_gap_run_pier_works_from_any_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert scenario("flood")["crops"]


def test_requirements_complete():
    req = (Path(REPO_ROOT) / "requirements.txt").read_text().lower()
    for pkg in ("fastapi", "uvicorn", "pytest", "httpx"):
        assert pkg in req, pkg


def test_fresh_clone_runs_without_manual_cache(tmp_path):
    dst = tmp_path / "clone"
    shutil.copytree(REPO_ROOT, dst, ignore=shutil.ignore_patterns(
        ".git", "cache", "baselines", "__pycache__", ".pytest_cache"))
    proc = subprocess.run(
        [sys.executable, "-m", "piper_agent", "--lat", "41.8", "--lon", "-93.6",
         "--date", "2025-05-15", "--demo-name", "flood"],
        cwd=dst, capture_output=True, text=True, timeout=180,
        env={**os.environ, "PYTHONPATH": str(dst)},
    )
    assert proc.returncode == 0, proc.stderr[-500:]
    assert "Event detection" in proc.stdout
