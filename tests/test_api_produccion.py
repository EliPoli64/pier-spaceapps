"""Next-wave API (Danny): run store, exports, audit trail, readiness, views, auth."""
from __future__ import annotations

import csv
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from piper_agent.api import security  # noqa: E402
from piper_agent.api.main import app  # noqa: E402
from piper_agent.api.store import RunStore, cell_for, reset_store  # noqa: E402

client = TestClient(app)
FLOOD = {"lat": 41.8, "lon": -93.6, "current_date": "2025-05-15", "demo_name": "flood"}
LATE = {"lat": 41.8, "lon": -93.6, "current_date": "2025-08-28", "demo_name": "late_flood"}


@pytest.fixture(autouse=True)
def fresh_store(tmp_path, monkeypatch):
    monkeypatch.setenv("PIER_API_DB", str(tmp_path / "runs.sqlite3"))
    for var in ("PIER_API_KEY", "PIER_API_KEYS", "PIER_REQUIRE_API_KEY", "PIER_STORE_DISABLED",
                "PIER_API_VIEW", "EARTHDATA_USERNAME"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("PIER_DEMO_MODE", "1")
    reset_store()
    security.reset_rate_limits()
    yield
    reset_store()


def plan(body=FLOOD, **params):
    r = client.post("/generate_plan", json=body, params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ── Per-coordinate storage ───────────────────────────────────────────────────

def test_plan_is_stored_and_retrievable():
    d = plan()
    assert d["guardado"] is True and d["run_id"]
    assert d["enlaces"]["auditoria"] == f"/plans/{d['run_id']}/audit"
    r = client.get(f"/plans/{d['run_id']}").json()
    assert r["response"]["plan_text"] == d["plan_text"]
    assert r["request"]["lat"] == 41.8 and r["cell"] == cell_for(41.8, -93.6)
    assert "audit" not in r


def test_history_by_coordinate_newest_first():
    a, b = plan(FLOOD), plan(LATE)
    plan({"lat": 9.0, "lon": 41.0, "current_date": "2025-01-30", "demo_name": "drought"})
    h = client.get("/plans", params={"lat": 41.8, "lon": -93.6}).json()
    assert [p["run_id"] for p in h["plans"]] == [b["run_id"], a["run_id"]]
    assert h["plans"][0]["fallback"] is True and h["plans"][1]["top_crop"]
    near = client.get("/plans", params={"lat": 41.81, "lon": -93.61, "radius_deg": 0.05}).json()
    assert near["count"] == 2
    assert client.get("/plans").json()["count"] == 3


def test_history_requires_both_coordinates():
    assert client.get("/plans", params={"lat": 41.8}).status_code == 422


def test_unknown_run_is_404():
    assert client.get("/plans/does-not-exist").status_code == 404
    assert client.get("/plans/does-not-exist/audit").status_code == 404


def test_run_ids_unique_even_with_same_request_id():
    h = {"X-Request-ID": "same-id"}
    r1 = client.post("/generate_plan", json=FLOOD, headers=h).json()
    r2 = client.post("/generate_plan", json=FLOOD, headers=h).json()
    assert r1["run_id"] != r2["run_id"]
    assert client.get("/plans", params={"lat": 41.8, "lon": -93.6}).json()["count"] == 2


def test_store_disabled_still_serves_plans(monkeypatch):
    monkeypatch.setenv("PIER_STORE_DISABLED", "1")
    d = plan()
    assert d["guardado"] is False and "enlaces" not in d
    assert any(a["codigo"] == "SIN_PERSISTENCIA" for a in d["alertas"])
    assert client.get("/plans").status_code == 404


def test_retention_purges_old_rows(tmp_path):
    s = RunStore(str(tmp_path / "r.sqlite3"), retention_days=30)
    s.save_run(run_id="old", endpoint="t", lat=1, lon=2, request={}, response={}, audit={})
    s._conn.execute("UPDATE runs SET created_at = '2000-01-01T00:00:00+00:00'")
    s._conn.commit()
    s.save_run(run_id="new", endpoint="t", lat=1, lon=2, request={}, response={}, audit={})
    assert s.purge_expired() == 1
    assert [r["run_id"] for r in s.list_runs()] == ["new"]


# ── Exports ──────────────────────────────────────────────────────────────────

def test_plan_export_csv_one_row_per_crop():
    d = plan()
    r = client.get(f"/plans/{d['run_id']}/export", params={"format": "csv"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert [row["crop"] for row in rows] == [c["crop"] for c in d["crops"]]
    assert rows[0]["rank"] == "1" and rows[0]["event_type"] == "flood"


def test_plan_export_csv_fallback_has_one_row():
    d = plan(LATE)
    rows = list(csv.DictReader(io.StringIO(client.get(f"/plans/{d['run_id']}/export").text)))
    assert len(rows) == 1 and rows[0]["crop"] == "" and rows[0]["fallback"] == "True"


def test_plan_export_json_round_trip():
    d = plan()
    j = client.get(f"/plans/{d['run_id']}/export", params={"format": "json"}).json()
    assert j["run_id"] == d["run_id"] and j["audit"]["evidencia"]


def test_history_export_csv_and_json():
    plan(FLOOD), plan(LATE)
    r = client.get("/plans/export", params={"lat": 41.8, "lon": -93.6})
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 2 and {"run_id", "fuente_datos", "data_path"} <= set(rows[0])
    assert 'filename="pier_plans_41.80_-93.60.csv"' in r.headers["content-disposition"]
    j = client.get("/plans/export", params={"format": "json"}).json()
    assert j["count"] == 2


# ── Audit trail ──────────────────────────────────────────────────────────────

def test_audit_explains_the_recommendation():
    d = plan()
    a = client.get(f"/plans/{d['run_id']}/audit").json()
    assert a["entradas"]["lat"] == 41.8 and a["entradas"]["current_date"] == "2025-05-15"
    assert a["datos"]["fuente_datos"] == "sintetico" and a["datos"]["ruta"] == "cache"
    assert a["datos"]["cortacircuito"]["available"] is True
    assert "abierto" in a["datos"]["cortacircuito"]
    files = a["datos"]["archivos_cache"]
    assert files and all(f["exists"] and f["synthetic"] for f in files)
    c = a["contrato"]
    assert set(c) >= {"version", "del_agente", "rellenadas_por_api", "ausentes"}
    assert "rotacion" in c["rellenadas_por_api"] or "rotacion" in c["del_agente"]
    assert a["versiones"]["api"]
    ev = " ".join(a["evidencia"])
    assert "3-day total" in ev and "Eligible:" in ev and "Excluded:" in ev
    assert a["decision"]["cultivos"][0]["crop"] == d["crops"][0]["crop"]


def test_audit_records_live_fallback_path(monkeypatch):
    import piper_agent.agent as agent_mod
    real = agent_mod.run_pier

    def fake(lat, lon, current_date, demo_mode=True, demo_name=None):
        res = real(lat, lon, current_date, True, "flood")
        res.update(demo_mode=False, fuente_datos="sintetico")
        return res

    monkeypatch.setattr(agent_mod, "run_pier", fake)
    d = plan(FLOOD, demo_mode="false")
    a = client.get(f"/plans/{d['run_id']}/audit").json()
    assert a["datos"]["ruta"] == "live_fallback_to_cache"
    assert a["datos"]["archivos_cache"] == []
    ready = client.get("/ready").json()
    assert ready["en_vivo"]["ultimo_respaldo_a_cache"]


def test_audit_log_is_persistent_across_store_reopen():
    plan()
    reset_store()                       # simulates a server restart (same DB file)
    security._AUDIT_LOG.clear()
    entries = client.get("/audit/log").json()["audit_entries"]
    assert any(e["operation"] == "generate_plan" for e in entries)


# ── Readiness ────────────────────────────────────────────────────────────────

def test_ready_reports_sources_and_store():
    plan()
    r = client.get("/ready")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] in ("ready", "degraded")
    assert {x["demo_name"] for x in d["datasets"]} >= {"flood", "drought", "normal", "late_flood"}
    flood = next(x for x in d["datasets"] if x["demo_name"] == "flood")
    assert flood["imerg"]["en_cache"] and flood["imerg"]["sintetico"]
    assert flood["imerg"]["dato_mas_reciente"] == "2025-05-15"
    assert d["almacenamiento"]["ok"] and d["almacenamiento"]["runs"] >= 1
    assert d["en_vivo"]["credenciales_configuradas"] is False
    assert "abierto" in d["en_vivo"]["cortacircuito"]


def test_ready_degraded_when_breaker_open_and_no_credentials(monkeypatch):
    import time as _t
    from piper_agent.data.resiliencia import cortacircuito_en_vivo as cc

    monkeypatch.setattr(cc, "abierto_desde", _t.time())
    monkeypatch.setenv("PIER_DEMO_MODE", "0")
    d = client.get("/ready").json()
    assert d["status"] == "degraded"
    text = " ".join(d["degradaciones"])
    assert "circuit breaker is OPEN" in text and "without Earthdata credentials" in text


def test_ready_not_ready_without_crop_db(monkeypatch, tmp_path):
    from piper_agent.api import services as svc
    monkeypatch.setattr(svc, "crops_csv_path", lambda: tmp_path / "missing.csv")
    r = client.get("/ready")
    assert r.status_code == 503 and r.json()["status"] == "not_ready"


def test_ready_is_public_even_with_api_key(monkeypatch):
    monkeypatch.setenv("PIER_API_KEY", "k")
    assert client.get("/ready").status_code in (200, 503)


# ── Views (demo vs production payload) ───────────────────────────────────────

def test_demo_view_is_stripped_projection_of_full():
    full = plan()
    demo = plan(vista="demo")
    assert demo["vista"] == "demo" and full["vista"] == "completa"
    assert set(demo) < set(full)
    for k in ("exclusiones", "rotacion", "monitoreo", "event_details", "enlaces"):
        assert k in full and k not in demo
    assert demo["plan_text"] == full["plan_text"]
    assert set(demo["crops"][0]) <= {"crop", "plant_by_date", "days_until_deadline",
                                     "rescue_confidence", "role"}
    assert all(a["nivel"] == "critical" or a["codigo"] in
               ("SIN_EVENTO", "SIN_CULTIVO_EN_VENTANA", "DATOS_SINTETICOS",
                "FALLBACK_DATOS_SINTETICOS") for a in demo["alertas"])


def test_default_view_from_env(monkeypatch):
    monkeypatch.setenv("PIER_API_VIEW", "demo")
    assert plan()["vista"] == "demo"


def test_stored_run_keeps_full_payload_even_for_demo_view():
    d = plan(vista="demo")
    stored = client.get(f"/plans/{d['run_id']}", params={"vista": "completa"}).json()
    assert "exclusiones" in stored["response"]


def test_contract_version_in_response():
    assert plan()["contrato"] and plan(vista="demo")["contrato"]


# ── Auth hardening ───────────────────────────────────────────────────────────

def test_production_without_key_is_closed(monkeypatch):
    monkeypatch.setenv("PIER_DEMO_MODE", "0")
    r = client.get("/plans")
    assert r.status_code == 503 and "API key required" in r.json()["detail"]
    assert client.get("/health").status_code == 200


def test_multiple_keys_for_rotation(monkeypatch):
    monkeypatch.setenv("PIER_API_KEYS", "old-key, new-key")
    assert client.get("/plans", headers={"X-API-Key": "old-key"}).status_code == 200
    assert client.get("/plans", headers={"X-API-Key": "new-key"}).status_code == 200
    assert client.get("/plans", headers={"X-API-Key": "nope"}).status_code == 401


def test_require_key_can_be_forced_in_demo(monkeypatch):
    monkeypatch.setenv("PIER_REQUIRE_API_KEY", "1")
    assert client.get("/plans").status_code == 503
