"""Tests for feat/api-backend (PLAN_SEIS_PERSONAS.md, Danny: D1–D7)."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from piper_agent.api import security, services  # noqa: E402
from piper_agent.api.main import app  # noqa: E402
from piper_agent.api.sms import format_reply, parse_sms  # noqa: E402

client = TestClient(app)

FLOOD = {"lat": 41.8, "lon": -93.6, "current_date": "2025-05-15", "demo_name": "flood"}


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    monkeypatch.delenv("PIER_API_KEY", raising=False)
    security.reset_rate_limits()
    yield
    security.reset_rate_limits()


# ── D1: /generate_plan contract ──────────────────────────────────────────────

def test_generate_plan_accepts_null_demo_name_and_autodetects():
    body = {**FLOOD, "demo_name": None}
    r = client.post("/generate_plan", json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["demo_name"] == "flood"
    assert d["auto_detected"] is True
    assert any(a["codigo"] == "DEMO_AUTODETECTADO" for a in d["alertas"])


def test_generate_plan_serializes_contract_keys():
    d = client.post("/generate_plan", json=FLOOD).json()
    for key in ("exclusiones", "rotacion", "ahorro", "fuente_datos", "demo_mode", "alertas",
                "ultima_actualizacion", "monitoreo", "crops", "plan_text",
                "dollar_savings", "rotation"):       # legacy keys kept
        assert key in d, key
    assert d["demo_mode"] is True
    assert d["fuente_datos"] in services.FUENTES_VALIDAS
    assert isinstance(d["exclusiones"], list) and d["exclusiones"]
    assert all("explicacion" in e for e in d["exclusiones"])
    assert d["dollar_savings"] == d["ahorro"]
    assert d["ahorro"]["usd_por_ha"] > 0


def test_generate_plan_far_location_is_422_not_flood():
    r = client.post("/generate_plan", json={"lat": 0.0, "lon": 0.0, "current_date": "2025-05-15"})
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_input"


@pytest.mark.parametrize("body", [
    {**FLOOD, "lat": 95},
    {**FLOOD, "lon": -200},
    {**FLOOD, "current_date": "15/05/2025"},
    {**FLOOD, "pesos_agricultor": {"banana": 1}},
    {**FLOOD, "pesos_agricultor": {"soil_protection": -1}},
    {**FLOOD, "rendimiento_t_ha": 0},
])
def test_generate_plan_validation_errors(body):
    r = client.post("/generate_plan", json=body)
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "validation_error"


def test_unknown_demo_name_is_422():
    r = client.post("/generate_plan", json={**FLOOD, "demo_name": "tsunami"})
    assert r.status_code == 422


def test_live_mode_is_501():
    r = client.post("/generate_plan", json={**FLOOD, "demo_mode": False})
    assert r.status_code == 501


def test_pesos_and_rendimiento_flow_into_rotation_and_savings():
    body = {**FLOOD, "pesos_agricultor": {"salvage_revenue": 1.0}, "rendimiento_t_ha": 2.0}
    d = client.post("/generate_plan", json=body).json()
    assert d["pesos_agricultor"] == {"salvage_revenue": 1.0}
    assert d["rendimiento_t_ha"] == 2.0
    if d["ahorro"] and d["ahorro"].get("origen") == "api_fallback":
        assert d["ahorro"]["rendimiento_t_ha"] == 2.0


def test_no_partial_param_alert_when_not_requested():
    d = client.post("/generate_plan", json=FLOOD).json()
    assert not any(a["codigo"] == "PARAMETRO_PARCIAL" for a in d["alertas"])


def test_uses_agent_contract_keys_when_present(monkeypatch):
    """When Alina's run_pier returns the contract keys, the API must not recompute them."""

    @dataclass
    class FakePlan:
        event_type: str = "flood"
        event_confidence: float = 0.9
        rescue_confidence: float = 0.7
        gdd_accumulated: float = 400.0
        gdd_remaining: float = 1500.0
        frost_date: str = "2025-10-15"
        fallback: bool = False
        crops: list = field(default_factory=list)
        plan_text: str = "fake plan"

    seen = {}

    def fake_run_pier(lat, lon, current_date, demo_mode=True, demo_name=None,
                      pesos_agricultor=None, rendimiento_t_ha=None):
        seen.update(pesos=pesos_agricultor, rend=rendimiento_t_ha)
        return {
            "recovery_plan": FakePlan(),
            "event_result": None,
            "crops": [{"crop": "Cowpea", "plant_by_date": "2025-06-12",
                       "days_until_deadline": 28, "rescue_confidence": 0.7}],
            "exclusiones": [{"crop": "Millet", "motivo": "tolerance_waterlogging",
                             "explicacion": "Millet excluded: Low waterlogging tolerance."}],
            "rotacion": {"rotation_sequence": ["Cowpea", "Sorghum", "Cereal rye (cover)"]},
            "ahorro": {"crop": "Cowpea", "usd_por_ha": 750.0, "net_savings_usd": 700.0},
            "fuente_datos": "nasa_power",
            "demo_mode": True,
        }

    import piper_agent.agent as agent_mod
    monkeypatch.setattr(agent_mod, "run_pier", fake_run_pier)
    body = {**FLOOD, "pesos_agricultor": {"soil_protection": 1}, "rendimiento_t_ha": 2.5}
    d = client.post("/generate_plan", json=body).json()

    assert seen == {"pesos": {"soil_protection": 1.0}, "rend": 2.5}
    assert d["exclusiones"][0]["motivo"] == "tolerance_waterlogging"
    assert "origen" not in d["rotacion"]
    assert d["ahorro"]["net_savings_usd"] == 700.0
    assert d["fuente_datos"] == "nasa_power"
    codes = [a["codigo"] for a in d["alertas"]]
    assert "PARAMETRO_PARCIAL" not in codes
    assert "CALCULO_EN_API" not in codes
    assert "DATOS_SINTETICOS" not in codes


# ── D4 / D5: alerts and monitoring ───────────────────────────────────────────

def test_late_date_triggers_fallback_alert():
    d = client.post("/generate_plan", json={**FLOOD, "current_date": "2025-09-30"}).json()
    if d["fallback"]:
        assert any(a["codigo"] == "SIN_CULTIVO_EN_VENTANA" for a in d["alertas"])


def test_date_after_data_is_flagged():
    d = client.post("/generate_plan", json={**FLOOD, "current_date": "2030-01-01"}).json()
    assert any(a["codigo"] == "FECHA_FUERA_DE_DATOS" for a in d["alertas"])


def test_normal_event_has_no_lost_crop_alert():
    body = {"lat": 41.8, "lon": -93.6, "current_date": "2025-07-07", "demo_name": "normal"}
    d = client.post("/generate_plan", json=body).json()
    codes = [a["codigo"] for a in d["alertas"]]
    assert "SIN_EVENTO" in codes
    assert "SIN_CULTIVO_EN_VENTANA" not in codes
    assert d["no_action_needed"] is True


def test_monitoring_block_present_and_no_staleness_in_demo():
    d = client.post("/generate_plan", json=FLOOD).json()
    assert "checked_at" in d["monitoreo"]
    assert not any("staleness" in a["metric"] for a in d["monitoreo"]["alertas"])


# ── D2: crop path independent of cwd ────────────────────────────────────────

def test_recommend_crops_works_from_other_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = client.post("/recommend_crops", json={"event_type": "drought", "gdd_remaining": 2000,
                                              "current_date": "2025-01-30", "avg_daily_gdd": 12})
    assert r.status_code == 200, r.text
    assert r.json()["n_eligible"] >= 2
    assert services.crops_csv_path().is_absolute()


def test_recommend_crops_accepts_pesos_alias():
    r = client.post("/recommend_crops", json={
        "event_type": "flood", "gdd_remaining": 2000, "current_date": "2025-05-15",
        "avg_daily_gdd": 15, "pesos_agricultor": {"soil_protection": 1}})
    assert r.status_code == 200
    assert r.json()["crops"][0]["crop"] == "Cereal rye (cover)"


def test_recommend_crops_rejects_bad_event_type():
    r = client.post("/recommend_crops", json={"event_type": "tornado", "gdd_remaining": 1,
                                              "current_date": "2025-01-01", "avg_daily_gdd": 1})
    assert r.status_code == 422


# ── D3: timezone-aware timestamps ────────────────────────────────────────────

def test_health_timestamp_is_utc_aware():
    d = client.get("/health").json()
    assert d["timestamp"].endswith("Z")
    assert "+00:00" not in d["timestamp"]


def test_detect_event_defaults_and_window():
    r = client.post("/detect_event", json={"lat": 41.8, "lon": -93.6})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["event_type"] == "flood"
    assert d["window"]["recent_end"] == "2025-05-15"
    assert "n_analogos" in d


def test_detect_event_rejects_reversed_window():
    r = client.post("/detect_event", json={"lat": 41.8, "lon": -93.6, "demo_name": "flood",
                                           "recent_start": "2025-05-20", "recent_end": "2025-05-10"})
    assert r.status_code == 422


# ── D7: /simulate_sms ────────────────────────────────────────────────────────

@pytest.mark.parametrize("msg,expected", [
    ("41.8,-93.6,2025-05-15", (41.8, -93.6, "2025-05-15")),
    ("lat 9.0 lon 41.0 fecha 2025-01-30", (9.0, 41.0, "2025-01-30")),
    ("41.8 -93.6", (41.8, -93.6, None)),
    ("Hola estoy en 9.0, 41.0", (9.0, 41.0, None)),
])
def test_parse_sms_formats(msg, expected):
    p = parse_sms(msg)
    assert (p["lat"], p["lon"], p["date"]) == expected


@pytest.mark.parametrize("msg", ["", "hola", "95,10", "41.8,-93.6,2025-13-40"])
def test_parse_sms_rejects(msg):
    assert parse_sms(msg) is None


def test_simulate_sms_reply_fits():
    r = client.post("/simulate_sms", json={"message": "41.8,-93.6,2025-05-15",
                                           "from_number": "+50688887777"})
    assert r.status_code == 200
    d = r.json()
    assert d["reply"].startswith("PIER:")
    assert d["length"] == len(d["reply"]) <= 160
    log = client.get("/audit/log").json()["audit_entries"]
    sms_entries = [e for e in log if e["operation"] == "simulate_sms"]
    assert sms_entries and sms_entries[-1]["details"]["from"] == "***777"


def test_simulate_sms_without_date_uses_demo_date():
    d = client.post("/simulate_sms", json={"message": "9.0 41.0"}).json()
    assert d["reply"].startswith("PIER:")
    assert "send lat" not in d["reply"]


def test_simulate_sms_help_and_unknown_location():
    assert "send lat,lon" in client.post("/simulate_sms", json={"message": "hola"}).json()["reply"]
    reply = client.post("/simulate_sms", json={"message": "10,10,2025-05-15"}).json()["reply"]
    assert "no data for that location" in reply


def test_format_reply_respects_max_length():
    plan = {"event_type": "flood", "fallback": False, "fuente_datos": "sintetico",
            "crops": [{"crop": "Cereal rye (cover)", "plant_by_date": "2025-07-12",
                       "days_until_deadline": 58, "rescue_confidence": 0.9},
                      {"crop": "Cowpea", "plant_by_date": "2025-06-12"}]}
    for n in (40, 80, 160):
        assert len(format_reply(plan, n)) <= n


# ── Auth, rate limit, request id, audit ──────────────────────────────────────

def test_api_key_enforced_when_configured(monkeypatch):
    monkeypatch.setenv("PIER_API_KEY", "secret-123")
    assert client.post("/generate_plan", json=FLOOD).status_code == 401
    assert client.post("/generate_plan", json=FLOOD,
                       headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.post("/generate_plan", json=FLOOD,
                       headers={"X-API-Key": "secret-123"}).status_code == 200
    assert client.get("/health").status_code == 200       # health stays public


def test_rate_limit_returns_429_with_retry_after(monkeypatch):
    monkeypatch.setattr(security, "RATE_LIMIT_MAX", 3)
    codes = [client.get("/demos").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    r = client.get("/demos")
    assert int(r.headers["Retry-After"]) >= 1
    assert client.get("/health").status_code == 200       # exempt


def test_request_id_propagates():
    r = client.post("/generate_plan", json=FLOOD, headers={"X-Request-ID": "abc-123"})
    assert r.headers["X-Request-ID"] == "abc-123"
    assert r.json()["request_id"] == "abc-123"


def test_audit_log_is_bounded_and_limited():
    for _ in range(3):
        client.get("/demos")
        client.post("/generate_plan", json=FLOOD)
    d = client.get("/audit/log", params={"limit": 2}).json()
    assert d["count"] == 2
    assert security._AUDIT_LOG.maxlen == security.AUDIT_MAX_ENTRIES


def test_demos_endpoint_lists_packets():
    d = client.get("/demos").json()
    assert d["count"] >= 3
    assert {"flood", "drought", "normal"} <= {x["demo_name"] for x in d["demos"]}


def test_errors_do_not_leak_tracebacks(monkeypatch):
    import piper_agent.agent as agent_mod

    def boom(*a, **k):
        raise RuntimeError("secret internal path /home/x")
    monkeypatch.setattr(agent_mod, "run_pier", boom)
    r = TestClient(app, raise_server_exceptions=False).post("/generate_plan", json=FLOOD)
    assert r.status_code == 500
    assert "secret" not in r.text
    assert r.json()["request_id"]


@pytest.mark.xfail(strict=False, reason=(
    "A-team (tools/filter_rescue_crops.py): default crops_csv is relative to the cwd and "
    "run_pier does not pass it, so /generate_plan fails when the server is not started from "
    "the repo root. Fix: default to Path(__file__).resolve().parents[1]/'data'/'rescue_crops.csv' "
    "or cache_loader.get_ruta_cultivos()."))
def test_generate_plan_works_from_other_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = client.post("/generate_plan", json=FLOOD)
    assert r.status_code == 200, r.text


def test_missing_file_error_names_the_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = TestClient(app, raise_server_exceptions=False).post("/generate_plan", json=FLOOD)
    if r.status_code == 503:
        assert r.json()["missing_file"] == "rescue_crops.csv"


# ── D8: demo_mode query parameter ────────────────────────────────────────────

def test_demo_mode_query_param_overrides_body():
    r = client.post("/generate_plan", params={"demo_mode": "false"}, json=FLOOD)
    assert r.status_code == 501                     # live path not implemented by the agent yet
    r = client.post("/generate_plan", params={"demo_mode": "true"},
                    json={**FLOOD, "demo_mode": False})
    assert r.status_code == 200
    assert r.json()["demo_mode"] is True


def test_demo_mode_default_follows_env(monkeypatch):
    monkeypatch.setenv("PIER_DEMO_MODE", "0")
    assert client.post("/generate_plan", json=FLOOD).status_code == 501
    monkeypatch.setenv("PIER_DEMO_MODE", "1")
    assert client.post("/generate_plan", json=FLOOD).json()["demo_mode"] is True


def test_live_request_with_synthetic_fallback_is_flagged(monkeypatch):
    import piper_agent.agent as agent_mod
    real = agent_mod.run_pier

    def fallback_run_pier(lat, lon, current_date, demo_mode=True, demo_name=None):
        res = real(lat, lon, current_date, True, "flood")
        res.update(demo_mode=False, fuente_datos="sintetico")   # circuit breaker fell back
        return res

    monkeypatch.setattr(agent_mod, "run_pier", fallback_run_pier)
    d = client.post("/generate_plan", params={"demo_mode": "false"}, json=FLOOD).json()
    codes = [a["codigo"] for a in d["alertas"]]
    assert "FALLBACK_DATOS_SINTETICOS" in codes
    assert "DATOS_SINTETICOS" not in codes


# ── D9: /health demo_mode_status ─────────────────────────────────────────────

@pytest.mark.parametrize("user,expected", [
    (None, "active"),
    ("your_username", "active"),
    ("your_earthdata_username", "active"),
    ("real_farmer_42", "production_path_available"),
])
def test_health_demo_mode_status(monkeypatch, user, expected):
    if user is None:
        monkeypatch.delenv("EARTHDATA_USERNAME", raising=False)
    else:
        monkeypatch.setenv("EARTHDATA_USERNAME", user)
    r = client.get("/health", params={"demo_mode": "true"})
    assert r.status_code == 200
    d = r.json()
    assert d["demo_mode_status"] == expected
    assert "real_farmer_42" not in r.text            # never reveal the username
    assert isinstance(d["demo_mode_default"], bool)


# ── D10: None contract keys are omitted, bad keys do not crash ───────────────

def test_none_contract_keys_are_omitted():
    body = {"lat": 41.8, "lon": -93.6, "current_date": "2025-07-07", "demo_name": "normal"}
    d = client.post("/generate_plan", json=body).json()
    for key in ("suelo", "ola_calor", "confianza_calibrada", "rotacion", "ahorro",
                "rotation", "dollar_savings"):
        assert key not in d, key
    assert "fuente_datos" in d and "alertas" in d


def test_failing_contract_key_is_dropped_not_500(monkeypatch):
    def broken(*a, **k):
        raise TypeError("unexpected shape")
    monkeypatch.setattr(services, "get_rotacion", broken)
    r = client.post("/generate_plan", json=FLOOD)
    assert r.status_code == 200
    d = r.json()
    assert "rotacion" not in d
    assert any(a["codigo"] == "CLAVE_NO_SERIALIZABLE" for a in d["alertas"])
