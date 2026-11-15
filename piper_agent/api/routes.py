"""PIER API endpoints.

  GET  /health          — liveness (no auth, no rate limit)
  GET  /demos           — available demo scenarios (for the PWA / clients)
  POST /detect_event    — BR-1 event detection (+ BR-7 analog-calibrated confidence)
  POST /recommend_crops — BR-2/3/4/8/10 eligible crops + exclusion reasons
  POST /generate_plan   — full agent run: plan, exclusions, rotation, savings, alerts
  POST /simulate_sms    — D7: farmer SMS in, ≤160-char reply out
  GET  /audit/log       — recent audit entries
  GET  /ready           — readiness: data recency, live path, circuit breaker, store (public)
  GET  /plans           — stored runs for a coordinate (history)
  GET  /plans/export    — that history as CSV / JSON
  GET  /plans/{run_id}  — a stored run (request + response)
  GET  /plans/{run_id}/audit  — why PIER recommended what it did
  GET  /plans/{run_id}/export — one plan as CSV / JSON
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import date, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from piper_agent.api import audit as audit_mod
from piper_agent.api import readiness
from piper_agent.api import services as svc
from piper_agent.api import views
from piper_agent.api.store import get_store
from piper_agent.api.schemas import (
    DetectEventRequest,
    GeneratePlanRequest,
    HealthResponse,
    RecommendCropsRequest,
    SimulateSmsRequest,
    SmsResponse,
)
from piper_agent.api.security import audit_entries, log_audit, mask_phone, rate_limit, verify_api_key
from piper_agent.api.sms import HELP_TEXT, format_reply, parse_sms

API_VERSION = "1.5.0"
logger = logging.getLogger("pier.api.routes")

public = APIRouter()
protected = APIRouter(dependencies=[Depends(verify_api_key), Depends(rate_limit)])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _elapsed_ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 2)


@public.get("/")
def root() -> dict[str, Any]:
    """Public root endpoint for Railway checks and endpoint discovery."""
    return {
        "service": "PIER API",
        "status": "ok",
        "version": API_VERSION,
        "docs": "/docs",
        "health": "/health",
        "ready": "/ready",
        "demos": "/demos",
    }


@public.get("/health", response_model=HealthResponse)
def health(demo_mode: bool | None = Query(None, description="Accepted for healthchecks; ignored")
           ) -> HealthResponse:
    """D9: liveness + whether the live NASA path could be used (no credentials revealed)."""
    return HealthResponse(status="healthy", version=API_VERSION, timestamp=svc.utc_now_iso(),
                          demo_mode_status=svc.demo_mode_status(),
                          demo_mode_default=svc.default_demo_mode())


@protected.get("/demos")
def list_demos() -> dict[str, Any]:
    packets = svc.demo_packets()
    keys = ("name", "label", "lat", "lon", "event_type", "current_date", "season_start",
            "season_end", "description")
    return {
        "count": len(packets),
        "demos": [{**{k: p.get(k) for k in keys if k in p},
                   "demo_name": p.get("name", "").removesuffix("_demo")} for p in packets],
    }


@protected.post("/detect_event")
def detect_event_endpoint(req: DetectEventRequest, request: Request) -> dict[str, Any]:
    from piper_agent.tools.detect_event import detect_event
    from piper_agent.tools.search_analogs import analog_calibrated_confidence, search_analogs

    t0 = time.perf_counter()
    demo_name, auto = svc.resolve_demo_name(req.lat, req.lon, req.demo_name, req.recent_end)
    packet = svc.get_demo_packet(demo_name)
    recent_end = req.recent_end or packet["recent_end"]
    if req.recent_start:
        recent_start = req.recent_start
    elif req.recent_end:
        recent_start = (date.fromisoformat(recent_end) - timedelta(days=6)).isoformat()
    else:
        recent_start = packet["recent_start"]

    result = detect_event(lat=req.lat, lon=req.lon, recent_start=recent_start,
                          recent_end=recent_end, demo_name=demo_name)
    analogs = search_analogs(event_type=result.event_type, lat=req.lat, lon=req.lon,
                             gdd_remaining=0.0)
    calibrated = analog_calibrated_confidence(analogs, result.confidence)

    log_audit(_rid(request), "detect_event", {
        "lat": req.lat, "lon": req.lon, "demo_name": demo_name, "auto_detected": auto,
        "recent_start": recent_start, "recent_end": recent_end,
        "event_type": result.event_type, "raw_confidence": result.confidence,
        "calibrated_confidence": calibrated, "elapsed_ms": _elapsed_ms(t0),
    })
    return {
        "request_id": _rid(request),
        "event_type": result.event_type,
        "severity": result.severity,
        "confidence": round(result.confidence, 3),
        "calibrated_confidence": round(calibrated, 3),
        "n_analogos": len(analogs),
        "demo_name": demo_name,
        "auto_detected": auto,
        "window": {"recent_start": recent_start, "recent_end": recent_end},
        "details": svc.to_jsonable(result.details),
    }


@protected.post("/recommend_crops")
def recommend_crops_endpoint(req: RecommendCropsRequest, request: Request) -> dict[str, Any]:
    from piper_agent.tools.explain_exclusion import explain_all_exclusions
    from piper_agent.tools.filter_rescue_crops import filter_rescue_crops

    t0 = time.perf_counter()
    crops_csv = svc.crops_csv_path()
    kwargs: dict[str, Any] = dict(event_type=req.event_type, gdd_remaining=req.gdd_remaining,
                                  current_date=req.current_date, avg_daily_gdd=req.avg_daily_gdd,
                                  crops_csv=str(crops_csv))
    accepted = svc._accepted_params(filter_rescue_crops)
    if req.weights is not None:
        weight_param = "pesos_agricultor" if "pesos_agricultor" in accepted else "farmer_weights"
        kwargs[weight_param] = req.weights
    result = filter_rescue_crops(**kwargs)

    excluded = explain_all_exclusions(svc.load_all_crops(),
                                      [{"crop": c.crop} for c in result],
                                      event_type=req.event_type, gdd_remaining=req.gdd_remaining)
    log_audit(_rid(request), "recommend_crops", {
        "event_type": req.event_type, "gdd_remaining": req.gdd_remaining,
        "current_date": req.current_date, "pesos_agricultor": req.weights,
        "n_eligible": len(result), "n_excluded": len(excluded), "elapsed_ms": _elapsed_ms(t0),
    })
    return {
        "request_id": _rid(request),
        "event_type": req.event_type,
        "n_eligible": len(result),
        "crops": [svc.serialize_crop(c) for c in result],
        "excluded_crops": excluded,
        "exclusiones": [{"crop": t.split(" excluded")[0].split(" not recommended")[0],
                         "explicacion": t} for t in excluded],
        "pesos_agricultor": req.weights,
    }


def _run_plan(req: GeneratePlanRequest, request_id: str, *, endpoint: str = "generate_plan",
              view: str = "completa") -> dict[str, Any]:
    """Run the agent once, build the full response, persist it with its audit record."""
    t0 = time.perf_counter()
    if req.demo_mode is None:
        req = req.model_copy(update={"demo_mode": svc.default_demo_mode()})
    if req.demo_mode:
        demo_name, auto = svc.resolve_demo_name(req.lat, req.lon, req.demo_name,
                                                req.current_date)
    else:
        demo_name, auto = req.demo_name, False
    result, ignored = svc.call_run_pier(
        lat=req.lat, lon=req.lon, current_date=req.current_date, demo_mode=req.demo_mode,
        demo_name=demo_name, pesos=req.weights,
        rendimiento=req.rendimiento_t_ha or req.expected_yield_tons_per_ha,
    )
    resp = svc.build_plan_response(request_id=request_id, result=result, req=req,
                                   demo_name=demo_name or result.get("demo_name"),
                                   auto_detected=auto, ignored=ignored)
    run_id = str(uuid.uuid4())
    resp.update({"run_id": run_id, "current_date": req.current_date, "vista": view,
                 "contrato": audit_mod.CONTRACT_VERSION})

    store = get_store()
    persisted = False
    if store is not None:
        request_json = svc.to_jsonable(req.model_dump(exclude_none=True))
        record = audit_mod.build_audit(run_id=run_id, request=request_json, result=result,
                                       response=resp, api_version=API_VERSION,
                                       elapsed_ms=_elapsed_ms(t0))
        persisted = store.save_run(run_id=run_id, endpoint=endpoint, lat=req.lat, lon=req.lon,
                                   request=request_json, response=resp, audit=record)
    resp["guardado"] = persisted
    if persisted:
        resp["enlaces"] = {
            "plan": f"/plans/{run_id}",
            "auditoria": f"/plans/{run_id}/audit",
            "export_csv": f"/plans/{run_id}/export?format=csv",
            "historial": f"/plans?lat={req.lat}&lon={req.lon}",
        }
    else:
        resp["alertas"].append({"nivel": "info", "codigo": "SIN_PERSISTENCIA",
                                "mensaje": "This plan was not stored; it cannot be revisited later."})
    return resp


@protected.post("/generate_plan")
def generate_plan_endpoint(
    req: GeneratePlanRequest,
    request: Request,
    demo_mode: bool | None = Query(None, description="D8: overrides the body's demo_mode. "
                                                     "false = live NASA production path"),
    vista: Literal["completa", "demo"] | None = Query(
        None, description="completa = full production payload; demo = stripped hackathon "
                          "payload. Default: PIER_API_VIEW (completa)."),
) -> dict[str, Any]:
    t0 = time.perf_counter()
    if demo_mode is not None:
        req = req.model_copy(update={"demo_mode": demo_mode})
    view = vista or views.default_view()
    resp = _run_plan(req, _rid(request), view=view)
    log_audit(_rid(request), "generate_plan", {
        "run_id": resp["run_id"], "lat": req.lat, "lon": req.lon,
        "current_date": req.current_date,
        "demo_name": resp["demo_name"], "auto_detected": resp["auto_detected"],
        "event_type": resp["event_type"], "fallback": resp["fallback"],
        "n_crops": len(resp["crops"]), "pesos_agricultor": req.weights,
        "rendimiento_t_ha": req.yield_t_ha, "fuente_datos": resp["fuente_datos"],
        "demo_mode": resp["demo_mode"], "vista": view, "guardado": resp["guardado"],
        "n_alertas": len(resp["alertas"]), "elapsed_ms": _elapsed_ms(t0),
    })
    return views.project(resp, view)


@protected.post("/simulate_sms", response_model=SmsResponse)
def simulate_sms_endpoint(req: SimulateSmsRequest, request: Request) -> SmsResponse:
    t0 = time.perf_counter()
    parsed = parse_sms(req.message)
    if parsed is None:
        reply = HELP_TEXT[: req.max_length]
    else:
        current_date = parsed["date"] or req.current_date
        if current_date is None:
            try:
                name, _ = svc.resolve_demo_name(parsed["lat"], parsed["lon"], req.demo_name,
                                                req.current_date)
                current_date = svc.get_demo_packet(name)["current_date"]
            except svc.ApiInputError:
                current_date = None
        if current_date is None:
            reply = "PIER: add a date, e.g. 41.8,-93.6,2025-05-15"
        else:
            try:
                plan_req = GeneratePlanRequest(lat=parsed["lat"], lon=parsed["lon"],
                                               current_date=current_date,
                                               demo_name=req.demo_name)
                reply = format_reply(_run_plan(plan_req, _rid(request), endpoint="simulate_sms"),
                                     req.max_length)
            except svc.ApiInputError:
                reply = "PIER: no data for that location yet. Try 41.8,-93.6 or 9.0,41.0"
    log_audit(_rid(request), "simulate_sms", {
        "from": mask_phone(req.from_number), "parsed": parsed, "reply_len": len(reply),
        "elapsed_ms": _elapsed_ms(t0),
    })
    return SmsResponse(reply=reply, length=len(reply), parsed=parsed, request_id=_rid(request))


@protected.get("/audit/log")
def get_audit_log(limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
    entries = audit_entries(limit)
    return {"audit_entries": entries, "count": len(entries)}


# ── Readiness ────────────────────────────────────────────────────────────────

@public.get("/ready")
def ready() -> JSONResponse:
    """Readiness for production: data recency, live path, circuit breaker, store."""
    report, code = readiness.build_report(API_VERSION)
    return JSONResponse(report, status_code=code)


# ── Stored plans: history, audit, export ─────────────────────────────────────

def _require_store():
    store = get_store()
    if store is None:
        raise HTTPException(status_code=404, detail="Plan storage is disabled (PIER_STORE_DISABLED=1).")
    return store


def _get_run_or_404(run_id: str) -> dict:
    run = _require_store().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No stored plan with run_id '{run_id}'.")
    return run


def _download(content: str, media_type: str, filename: str) -> Response:
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _history(lat, lon, radius_deg, since, limit) -> list[dict]:
    if (lat is None) != (lon is None):
        raise svc.ApiInputError("Pass both lat and lon, or neither.")
    return _require_store().list_runs(lat=lat, lon=lon, radius_deg=radius_deg, since=since,
                                      limit=limit)


@protected.get("/plans")
def list_plans(
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    radius_deg: float = Query(0.0, ge=0, le=5,
                              description="0 = same ~1 km cell (2-decimal grid)"),
    since: str | None = Query(None, description="ISO timestamp lower bound"),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    runs = _history(lat, lon, radius_deg, since, limit)
    return {"count": len(runs), "plans": runs}


@protected.get("/plans/export")
def export_plans(
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    radius_deg: float = Query(0.0, ge=0, le=5),
    since: str | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    format: Literal["csv", "json"] = Query("csv"),
) -> Response:
    runs = _history(lat, lon, radius_deg, since, limit)
    stem = "pier_plans" + (f"_{lat:.2f}_{lon:.2f}" if lat is not None else "")
    if format == "json":
        return _download(json.dumps({"count": len(runs), "plans": runs}, ensure_ascii=False, indent=2),
                         "application/json", f"{stem}.json")
    return _download(views.history_csv(runs), "text/csv; charset=utf-8", f"{stem}.csv")


@protected.get("/plans/{run_id}")
def get_plan(run_id: str,
             vista: Literal["completa", "demo"] | None = Query(None)) -> dict[str, Any]:
    run = _get_run_or_404(run_id)
    run["response"] = views.project(run["response"], vista or views.default_view())
    run.pop("audit", None)
    return run


@protected.get("/plans/{run_id}/audit")
def get_plan_audit(run_id: str) -> dict[str, Any]:
    run = _get_run_or_404(run_id)
    return {"run_id": run_id, "created_at": run["created_at"], **run["audit"]}


@protected.get("/plans/{run_id}/export")
def export_plan(run_id: str, format: Literal["csv", "json"] = Query("csv")) -> Response:
    run = _get_run_or_404(run_id)
    if format == "json":
        return _download(json.dumps(run, ensure_ascii=False, indent=2, default=str),
                         "application/json", f"pier_plan_{run_id}.json")
    return _download(views.plan_csv(run), "text/csv; charset=utf-8", f"pier_plan_{run_id}.csv")


__all__ = ["public", "protected", "API_VERSION"]
