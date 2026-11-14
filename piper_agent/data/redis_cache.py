"""Redis-backed cache layer with filesystem fallback.

Used for caching IMERG/POWER/OpenET/SMAP responses with TTL invalidation
on new satellite overpasses.
"""
from __future__ import annotations

import json
import logging
import os
import pickle
from pathlib import Path
from typing import Any

logger = logging.getLogger("pier.data.redis_cache")

FS_CACHE_ROOT = Path(
    os.environ.get(
        "PIER_FS_CACHE_ROOT",
        str(Path(__file__).resolve().parent / "cache" / "redis_fs"),
    )
)

_redis_client = None


def _get_redis():
    """Lazily connect to Redis. Returns None if unavailable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis  # type: ignore
        _redis_client = redis.Redis(
            host=os.environ.get("PIER_REDIS_HOST", "localhost"),
            port=int(os.environ.get("PIER_REDIS_PORT", "6379")),
            db=int(os.environ.get("PIER_REDIS_DB", "0")),
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=False,
        )
        _redis_client.ping()
        logger.info("Redis cache connected")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis unavailable (%s); using filesystem cache", exc)
        _redis_client = None
    return _redis_client


def _fs_path(key: str) -> Path:
    """Filesystem cache path for a key."""
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
    return FS_CACHE_ROOT / f"{safe}.pkl"


def get(key: str) -> Any | None:
    """Get a value from cache. Returns None if not found."""
    client = _get_redis()
    if client is not None:
        try:
            raw = client.get(key)
            if raw is not None:
                return pickle.loads(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis get failed: %s", exc)
    # Filesystem fallback
    path = _fs_path(key)
    if path.exists():
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception as exc:  # noqa: BLE001
            logger.warning("FS cache read failed: %s", exc)
    return None


def set(key: str, value: Any, ttl: int = 3600) -> None:
    """Set a value in cache with TTL (seconds)."""
    client = _get_redis()
    if client is not None:
        try:
            client.setex(key, ttl, pickle.dumps(value))
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis set failed: %s", exc)
    # Filesystem fallback (no TTL enforcement, but keyed by name)
    path = _fs_path(key)
    try:
        # The folder is created on write, not when the module is imported.
        FS_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(value, f)
    except Exception as exc:  # noqa: BLE001
        logger.warning("FS cache write failed: %s", exc)


def invalidate_prefix(prefix: str) -> int:
    """Invalidate all cache keys starting with prefix. Returns count removed."""
    removed = 0
    client = _get_redis()
    if client is not None:
        try:
            keys = list(client.scan_iter(match=f"{prefix}*"))
            if keys:
                removed += client.delete(*keys)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis invalidate_prefix failed: %s", exc)
    # Filesystem fallback
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in prefix)
    for path in FS_CACHE_ROOT.glob(f"{safe}*"):
        try:
            path.unlink()
            removed += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("FS cache unlink failed: %s", exc)
    logger.info("Invalidated %d cache keys with prefix %r", removed, prefix)
    return removed


def get_json(key: str) -> Any | None:
    """Get a JSON-serializable value from cache."""
    raw = get(key)
    if raw is None:
        return None
    if isinstance(raw, (str, bytes)):
        try:
            return json.loads(raw if isinstance(raw, str) else raw.decode())
        except Exception:  # noqa: BLE001
            return raw
    return raw


def set_json(key: str, value: Any, ttl: int = 3600) -> None:
    """Set a JSON-serializable value in cache."""
    set(key, json.dumps(value), ttl=ttl)


__all__ = ["get", "set", "get_json", "set_json", "invalidate_prefix"]
