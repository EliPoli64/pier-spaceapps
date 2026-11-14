"""API key auth, per-client rate limiting and the bounded audit log."""
from __future__ import annotations

import hmac
import logging
import os
import threading
import time
from collections import deque
from typing import Any

from fastapi import Header, HTTPException, Request, status

from piper_agent.api.services import to_jsonable, utc_now_iso

logger = logging.getLogger("pier.api")

RATE_LIMIT_MAX = int(os.environ.get("PIER_RATE_LIMIT_MAX", "60"))       # requests …
RATE_LIMIT_WINDOW = float(os.environ.get("PIER_RATE_LIMIT_WINDOW", "60"))  # … per seconds
AUDIT_MAX_ENTRIES = int(os.environ.get("PIER_AUDIT_MAX", "1000"))
_MAX_TRACKED_CLIENTS = 10_000

_lock = threading.Lock()
_rate_store: dict[str, deque[float]] = {}
_AUDIT_LOG: deque[dict[str, Any]] = deque(maxlen=AUDIT_MAX_ENTRIES)


def configured_api_key() -> str | None:
    """Read at call time so the key can be set/rotated without re-importing."""
    return os.environ.get("PIER_API_KEY") or None


def verify_api_key(x_api_key: str | None = Header(default=None)) -> str | None:
    expected = configured_api_key()
    if expected is None:
        return x_api_key
    if not x_api_key or not hmac.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid or missing API key",
                            headers={"WWW-Authenticate": "ApiKey"})
    return x_api_key


def _client_key(request: Request, api_key: str | None) -> str:
    if api_key:
        return "key:" + api_key[-6:]
    host = request.client.host if request.client else "unknown"
    return "ip:" + host


def rate_limit(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    """Sliding-window limiter, per API key (or per client IP when anonymous)."""
    now = time.monotonic()
    key = _client_key(request, x_api_key)
    with _lock:
        if key not in _rate_store and len(_rate_store) >= _MAX_TRACKED_CLIENTS:
            for k in [k for k, q in _rate_store.items() if not q or now - q[-1] > RATE_LIMIT_WINDOW]:
                del _rate_store[k]
        q = _rate_store.setdefault(key, deque())
        while q and now - q[0] >= RATE_LIMIT_WINDOW:
            q.popleft()
        if len(q) >= RATE_LIMIT_MAX:
            retry = max(1, int(RATE_LIMIT_WINDOW - (now - q[0])) + 1)
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                detail="Rate limit exceeded",
                                headers={"Retry-After": str(retry)})
        q.append(now)


def reset_rate_limits() -> None:
    with _lock:
        _rate_store.clear()


def mask_phone(number: str | None) -> str | None:
    if not number:
        return None
    digits = [c for c in number if c.isdigit()]
    return ("***" + "".join(digits[-3:])) if len(digits) >= 3 else "***"


def log_audit(request_id: str, operation: str, details: dict[str, Any]) -> None:
    """Structured audit entry for every agent run (bounded in memory)."""
    entry = {"request_id": request_id, "operation": operation,
             "timestamp": utc_now_iso(), "details": to_jsonable(details)}
    with _lock:
        _AUDIT_LOG.append(entry)
    logger.info("AUDIT %s %s %s", request_id, operation, entry["details"])


def audit_entries(limit: int = 100) -> list[dict[str, Any]]:
    with _lock:
        items = list(_AUDIT_LOG)
    return items[-limit:]


__all__ = [
    "RATE_LIMIT_MAX",
    "RATE_LIMIT_WINDOW",
    "verify_api_key",
    "rate_limit",
    "reset_rate_limits",
    "mask_phone",
    "log_audit",
    "audit_entries",
    "configured_api_key",
]
