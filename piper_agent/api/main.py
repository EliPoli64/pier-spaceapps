"""PIER FastAPI production API layer.

Endpoints:
  POST /detect_event   — BR-1, BR-7 event detection
  POST /recommend_crops — BR-2,3,4,10 crop filtering
  POST /generate_plan  — BR-5,6,11 recovery plan
  GET  /health         — health check

Auth: API key via X-API-Key header (optional, enforced when PIER_API_KEY set).
Rate limiting: simple in-memory counter per API key.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import date, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Header, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from piper_agent.agent import run_pier
from piper_agent.tools.confidence_calibration import calibrate_confidence
from piper_agent.tools.search_analogs import search_analogs, analog_calibrated_confidence
from piper_agent.tools.explain_exclusion import explain_all_exclusions
from piper_agent.tools.filter_rescue_crops import filter_rescue_crops
from piper_agent.tools.fetch_market_price import compute_dollar_savings
from piper_agent.tools.plan_rotation import plan_rotation

logger = logging.getLogger("pier.api")

app = FastAPI(title="PIER — Extreme-weather Recovery Planner", version="1.3.0")

API_KEY = os.environ.get("PIER_API_KEY")

# Simple in-memory rate limit: {api_key: [timestamps]}
_rate_limit_store: dict[str, list[float]] = {}
RATE_LIMIT_MAX = 60  # requests per minute
RATE_LIMIT_WINDOW = 60.0


def _check_rate_limit(api_key: str | None) -> None:
    now = time.time()
    key = api_key or "anonymous"
    timestamps = _rate_limit_store.get(key, [])
    timestamps = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    if len(timestamps) >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )
    timestamps.append(now)
    _rate_limit_store[key] = timestamps


def _verify_api_key(x_api_key: str | None) -> None:
    if API_KEY is None:
        return  # auth not configured
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


# ── Request/Response models ─────────────────────────────────────────────

class DetectEventRequest(BaseModel):
    lat: float = Field(..., description="Field latitude")
    lon: float = Field(..., description="Field longitude")
    recent_start: str = Field(..., description="Recent window start (ISO date)")
    recent_end: str = Field(..., description="Recent window end (ISO date)")
    demo_name: str = Field("flood", description="Demo scenario: flood | drought | normal")


class RecommendCropsRequest(BaseModel):
    event_type: str = Field(..., description="flood | drought | none")
    gdd_remaining: float = Field(..., ge=0, description="GDD remaining to frost")
    current_date: str = Field(..., description="Current date (ISO)")
    avg_daily_gdd: float = Field(..., ge=0, description="Average daily GDD")
    farmer_weights: dict[str, float] | None = Field(None, description="BR-10 farmer priority weights")


class GeneratePlanRequest(BaseModel):
    lat: float = Field(..., description="Field latitude")
    lon: float = Field(..., description="Field longitude")
    current_date: str = Field(..., description="Current date (ISO)")
    demo_name: str = Field("flood", description="Demo scenario")
    expected_yield_tons_per_ha: float = Field(1.5, description="Expected yield for savings estimate")
    farmer_weights: dict[str, float] | None = Field(None, description="BR-10 farmer priority weights")


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str


# ── Endpoints ───────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        version="1.3.0",
        timestamp=datetime.utcnow().isoformat() + "Z",
    )


@app.post("/detect_event")
def detect_event_endpoint(
    req: DetectEventRequest,
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _verify_api_key(x_api_key)
    _check_rate_limit(x_api_key)

    request_id = str(uuid.uuid4())
    t0 = time.time()

    try:
        from piper_agent.tools.detect_event import detect_event
        result = detect_event(
            lat=req.lat,
            lon=req.lon,
            recent_start=req.recent_start,
            recent_end=req.recent_end,
            demo_name=req.demo_name,
        )

        # BR-7: calibrate confidence using historical analogs
        analogs = search_analogs(
            event_type=result.event_type,
            lat=req.lat,
            lon=req.lon,
            gdd_remaining=0.0,  # not applicable at detection stage
        )
        calibrated = analog_calibrated_confidence(analogs, result.confidence)

        _log_audit(request_id, "detect_event", {
            "lat": req.lat, "lon": req.lon,
            "recent_start": req.recent_start, "recent_end": req.recent_end,
            "event_type": result.event_type,
            "raw_confidence": result.confidence,
            "calibrated_confidence": calibrated,
            "elapsed_ms": round((time.time() - t0) * 1000, 2),
        })

        return {
            "request_id": request_id,
            "event_type": result.event_type,
            "severity": result.severity,
            "confidence": round(result.confidence, 3),
            "calibrated_confidence": round(calibrated, 3),
            "details": result.details,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("detect_event endpoint failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/recommend_crops")
def recommend_crops_endpoint(
    req: RecommendCropsRequest,
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _verify_api_key(x_api_key)
    _check_rate_limit(x_api_key)

    request_id = str(uuid.uuid4())
    t0 = time.time()

    try:
        from piper_agent.data.cache_loader import load_demo_packet
        # Load crop DB to get all crops for exclusion explanations
        import pandas as pd
        all_crops = pd.read_csv("piper_agent/data/rescue_crops.csv").to_dict("records")

        result = filter_rescue_crops(
            event_type=req.event_type,
            gdd_remaining=req.gdd_remaining,
            current_date=req.current_date,
            avg_daily_gdd=req.avg_daily_gdd,
            farmer_weights=req.farmer_weights,
        )

        # BR-8: exclusion explanations
        excluded = explain_all_exclusions(
            all_crops,
            [c.__dict__ if hasattr(c, "__dict__") else c for c in result],
            event_type=req.event_type,
            gdd_remaining=req.gdd_remaining,
        )

        _log_audit(request_id, "recommend_crops", {
            "event_type": req.event_type,
            "gdd_remaining": req.gdd_remaining,
            "current_date": req.current_date,
            "farmer_weights": req.farmer_weights,
            "n_eligible": len(result),
            "n_excluded": len(excluded),
            "elapsed_ms": round((time.time() - t0) * 1000, 2),
        })

        return {
            "request_id": request_id,
            "event_type": req.event_type,
            "n_eligible": len(result),
            "crops": [
                {
                    "crop": c.crop,
                    "event_match": c.event_match,
                    "gdd_requirement": c.gdd_requirement,
                    "gdd_remaining": c.gdd_remaining,
                    "margin_pct": c.margin_pct,
                    "plant_by_date": c.plant_by_date,
                    "days_until_deadline": c.days_until_deadline,
                    "rescue_confidence": c.rescue_confidence,
                    "composite_score": c.composite_score,
                }
                for c in result
            ],
            "excluded_crops": excluded,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("recommend_crops endpoint failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/generate_plan")
def generate_plan_endpoint(
    req: GeneratePlanRequest,
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _verify_api_key(x_api_key)
    _check_rate_limit(x_api_key)

    request_id = str(uuid.uuid4())
    t0 = time.time()

    try:
        result = run_pier(
            lat=req.lat,
            lon=req.lon,
            current_date=req.current_date,
            demo_mode=True,
            demo_name=req.demo_name,
        )

        rp = result["recovery_plan"]

        # BR-11: dollar savings estimate
        savings = None
        if rp.crops:
            top_crop = rp.crops[0]
            savings = compute_dollar_savings(
                top_crop.crop,
                expected_yield_tons_per_ha=req.expected_yield_tons_per_ha,
            )

        # BR-9/12: rotation plan
        rotation = None
        if rp.crops:
            rotation = plan_rotation(
                rp.crops[0].crop,
                {"farmer_priority": "soil_protection"},
            )

        _log_audit(request_id, "generate_plan", {
            "lat": req.lat, "lon": req.lon,
            "current_date": req.current_date,
            "demo_name": req.demo_name,
            "event_type": rp.event_type,
            "fallback": rp.fallback,
            "n_crops": len(rp.crops),
            "has_rotation": rotation is not None,
            "elapsed_ms": round((time.time() - t0) * 1000, 2),
        })

        return {
            "request_id": request_id,
            "plan_text": rp.plan_text,
            "event_type": rp.event_type,
            "event_confidence": rp.event_confidence,
            "rescue_confidence": rp.rescue_confidence,
            "gdd_accumulated": rp.gdd_accumulated,
            "gdd_remaining": rp.gdd_remaining,
            "frost_date": rp.frost_date,
            "fallback": rp.fallback,
            "crops": [
                {
                    "crop": c.crop,
                    "plant_by_date": c.plant_by_date,
                    "days_until_deadline": c.days_until_deadline,
                    "gdd_requirement": c.gdd_requirement,
                    "rescue_confidence": c.rescue_confidence,
                    "composite_score": c.composite_score,
                }
                for c in rp.crops
            ],
            "dollar_savings": savings,
            "rotation": rotation,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("generate_plan endpoint failed")
        raise HTTPException(status_code=500, detail=str(exc))


# ── Audit logging ───────────────────────────────────────────────────────

_AUDIT_LOG: list[dict[str, Any]] = []


def _log_audit(request_id: str, operation: str, details: dict[str, Any]) -> None:
    """Structured audit log entry for every agent run (BR-13 traceability)."""
    entry = {
        "request_id": request_id,
        "operation": operation,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "details": details,
    }
    _AUDIT_LOG.append(entry)
    logger.info("AUDIT %s %s %s", request_id, operation, json_safe(details))


def json_safe(obj: Any) -> Any:
    """Make an object JSON-safe for logging."""
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


@app.get("/audit/log")
def get_audit_log(
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _verify_api_key(x_api_key)
    return {"audit_entries": _AUDIT_LOG, "count": len(_AUDIT_LOG)}
