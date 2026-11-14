"""PIER FastAPI application.

Run:  uvicorn piper_agent.api.main:app --reload
Docs: http://localhost:8000/docs

Auth: ``X-API-Key`` header, enforced only when ``PIER_API_KEY`` is set.
Rate limit: ``PIER_RATE_LIMIT_MAX`` requests per ``PIER_RATE_LIMIT_WINDOW``
seconds per API key (or per client IP). ``/health`` is exempt from both.
"""
from __future__ import annotations

import logging
import os
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from piper_agent.api import services as svc
from piper_agent.api.routes import API_VERSION, protected, public
from piper_agent.api import security

_AUDIT_LOG = security._AUDIT_LOG   # backwards-compatible name from the old single-file API

logger = logging.getLogger("pier.api")

app = FastAPI(
    title="PIER — Extreme-weather Recovery Planner",
    version=API_VERSION,
    description="NASA Space Apps 2026 · Field Shift Challenge (Spec 3). "
                "Detects floods/droughts from IMERG, computes the remaining GDD window "
                "from POWER and recommends rescue crops.",
)

_origins = [o.strip() for o in os.environ.get("PIER_CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Retry-After"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Propagate (or create) a request id; returned in the X-Request-ID header."""
    incoming = request.headers.get("X-Request-ID", "")
    rid = incoming if 0 < len(incoming) <= 64 and incoming.replace("-", "").isalnum() \
        else str(uuid.uuid4())
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


def _error(request: Request, status: int, code: str, message: str, **extra) -> JSONResponse:
    rid = getattr(request.state, "request_id", None)
    return JSONResponse(status_code=status,
                        content={"error": code, "detail": message, "request_id": rid, **extra},
                        headers={"X-Request-ID": rid or ""})


@app.exception_handler(svc.ApiInputError)
async def _input_error(request: Request, exc: svc.ApiInputError):
    return _error(request, 422, "invalid_input", str(exc))


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg")} for e in exc.errors()]
    return _error(request, 422, "validation_error", "Request validation failed", errors=errors)


@app.exception_handler(NotImplementedError)
async def _not_implemented(request: Request, exc: NotImplementedError):
    return _error(request, 501, "not_implemented", str(exc) or "Not implemented")


@app.exception_handler(FileNotFoundError)
async def _missing_data(request: Request, exc: FileNotFoundError):
    logger.error("Data file missing: %s", exc)
    missing = os.path.basename(str(getattr(exc, "filename", "") or exc))
    return _error(request, 503, "data_unavailable",
                  f"Data file '{missing}' not found on the server. If it is a cache file run "
                  "`python piper_agent/data/generate_cache.py`; if it is rescue_crops.csv, start "
                  "the server from the repository root.", missing_file=missing)


@app.exception_handler(ValueError)
async def _value_error(request: Request, exc: ValueError):
    return _error(request, 422, "invalid_input", str(exc))


@app.exception_handler(Exception)
async def _unexpected(request: Request, exc: Exception):
    logger.exception("Unhandled error in %s %s", request.method, request.url.path)
    return _error(request, 500, "internal_error",
                  "Unexpected server error; see server logs with this request_id.")


app.include_router(public)
app.include_router(protected)

__all__ = ["app"]
