"""Persistent run store and audit trail for the PIER API (SQLite, stdlib only).

Every ``/generate_plan`` run is stored with its request, full response and an
audit record, so an operator can revisit past plans for a coordinate, export
them, and answer "why did it give this recommendation on this date".

Configuration (environment):
  PIER_API_DB                 path of the SQLite file, or ":memory:".
                              Default: ~/.pier/pier_api.sqlite3
  PIER_STORE_RETENTION_DAYS   runs/audit rows older than this are purged (default 90; 0 = keep)
  PIER_STORE_DISABLED=1       turn persistence off (the API keeps working)

Privacy: coordinates are stored because revisiting a field's plans is the point
of the feature; phone numbers are only ever stored masked; nothing here is sent
anywhere. Rows expire after the retention period.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("pier.api.store")

CELL_DECIMALS = 2          # ~1 km grid used to group runs of the same field

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id             TEXT PRIMARY KEY,
    created_at     TEXT NOT NULL,
    endpoint       TEXT NOT NULL,
    lat            REAL NOT NULL,
    lon            REAL NOT NULL,
    cell           TEXT NOT NULL,
    current_date   TEXT,
    demo_name      TEXT,
    demo_mode      INTEGER,
    fuente_datos   TEXT,
    data_path      TEXT,
    event_type     TEXT,
    fallback       INTEGER,
    top_crop       TEXT,
    request_json   TEXT NOT NULL,
    response_json  TEXT NOT NULL,
    audit_json     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_cell_time ON runs(cell, created_at);
CREATE INDEX IF NOT EXISTS runs_time ON runs(created_at);
CREATE TABLE IF NOT EXISTS audit (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id  TEXT NOT NULL,
    operation   TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    details     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_time ON audit(timestamp);
"""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def cell_for(lat: float, lon: float) -> str:
    return f"{round(lat, CELL_DECIMALS):.{CELL_DECIMALS}f},{round(lon, CELL_DECIMALS):.{CELL_DECIMALS}f}"


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))


class RunStore:
    def __init__(self, path: str | None = None, retention_days: int | None = None):
        self.path = path or os.environ.get("PIER_API_DB") or str(Path.home() / ".pier" / "pier_api.sqlite3")
        self.retention_days = (int(os.environ.get("PIER_STORE_RETENTION_DAYS", "90"))
                               if retention_days is None else retention_days)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self.error: str | None = None

    # ── connection ──────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            if self.path != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, check_same_thread=False, timeout=5)
            conn.row_factory = sqlite3.Row
            conn.executescript(_SCHEMA)
            if self.path != ":memory:":
                conn.execute("PRAGMA journal_mode=WAL")
            self._conn = conn
            self.purge_expired()
        return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def healthy(self) -> tuple[bool, str | None]:
        try:
            with self._lock:
                self._connect().execute("SELECT 1").fetchone()
            return True, None
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"

    # ── writes ──────────────────────────────────────────────────────────
    def save_run(self, *, run_id: str, endpoint: str, lat: float, lon: float,
                 request: dict, response: dict, audit: dict) -> bool:
        crops = response.get("crops") or []
        row = (
            run_id, _utc_now().isoformat(), endpoint, float(lat), float(lon), cell_for(lat, lon),
            response.get("current_date") or request.get("current_date"),
            response.get("demo_name"), int(bool(response.get("demo_mode"))),
            response.get("fuente_datos"), audit.get("datos", {}).get("ruta"),
            response.get("event_type"), int(bool(response.get("fallback"))),
            crops[0].get("crop") if crops else None,
            _dumps(request), _dumps(response), _dumps(audit),
        )
        try:
            with self._lock:
                conn = self._connect()
                conn.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
                conn.commit()
            return True
        except Exception as exc:  # noqa: BLE001
            self.error = f"{type(exc).__name__}: {exc}"
            logger.error("Could not persist run %s: %s", run_id, exc)
            return False

    def log_audit(self, request_id: str, operation: str, timestamp: str, details: dict) -> bool:
        try:
            with self._lock:
                conn = self._connect()
                conn.execute("INSERT INTO audit (request_id, operation, timestamp, details) VALUES (?,?,?,?)",
                             (request_id, operation, timestamp, _dumps(details)))
                conn.commit()
            return True
        except Exception as exc:  # noqa: BLE001
            self.error = f"{type(exc).__name__}: {exc}"
            logger.error("Could not persist audit entry: %s", exc)
            return False

    def purge_expired(self) -> int:
        if not self.retention_days or self._conn is None:
            return 0
        cutoff = (_utc_now() - timedelta(days=self.retention_days)).isoformat()
        cur = self._conn.execute("DELETE FROM runs WHERE created_at < ?", (cutoff,))
        cur2 = self._conn.execute("DELETE FROM audit WHERE timestamp < ?", (cutoff,))
        self._conn.commit()
        return (cur.rowcount or 0) + (cur2.rowcount or 0)

    # ── reads ───────────────────────────────────────────────────────────
    @staticmethod
    def _summary(row: sqlite3.Row) -> dict:
        return {
            "run_id": row["id"], "created_at": row["created_at"], "endpoint": row["endpoint"],
            "lat": row["lat"], "lon": row["lon"], "cell": row["cell"],
            "current_date": row["current_date"], "demo_name": row["demo_name"],
            "demo_mode": bool(row["demo_mode"]), "fuente_datos": row["fuente_datos"],
            "data_path": row["data_path"], "event_type": row["event_type"],
            "fallback": bool(row["fallback"]), "top_crop": row["top_crop"],
        }

    def get_run(self, run_id: str) -> dict | None:
        with self._lock:
            row = self._connect().execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        out = self._summary(row)
        out["request"] = json.loads(row["request_json"])
        out["response"] = json.loads(row["response_json"])
        out["audit"] = json.loads(row["audit_json"])
        return out

    def list_runs(self, *, lat: float | None = None, lon: float | None = None,
                  radius_deg: float = 0.0, since: str | None = None, limit: int = 50) -> list[dict]:
        sql, args = "SELECT * FROM runs WHERE 1=1", []
        if lat is not None and lon is not None:
            if radius_deg > 0:
                sql += " AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?"
                args += [lat - radius_deg, lat + radius_deg, lon - radius_deg, lon + radius_deg]
            else:
                sql += " AND cell = ?"
                args.append(cell_for(lat, lon))
        if since:
            sql += " AND created_at >= ?"
            args.append(since)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(int(limit))
        with self._lock:
            rows = self._connect().execute(sql, args).fetchall()
        return [self._summary(r) for r in rows]

    def audit_entries(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._connect().execute(
                "SELECT request_id, operation, timestamp, details FROM audit ORDER BY seq DESC LIMIT ?",
                (int(limit),)).fetchall()
        return [{"request_id": r["request_id"], "operation": r["operation"],
                 "timestamp": r["timestamp"], "details": json.loads(r["details"])} for r in rows][::-1]

    def last_run_where(self, condition: str) -> dict | None:
        """Most recent run matching a fixed SQL condition (internal use only)."""
        with self._lock:
            row = self._connect().execute(
                f"SELECT * FROM runs WHERE {condition} ORDER BY created_at DESC LIMIT 1").fetchone()
        return self._summary(row) if row else None

    def stats(self) -> dict:
        with self._lock:
            conn = self._connect()
            n_runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            n_audit = conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
            last = conn.execute("SELECT MAX(created_at) FROM runs").fetchone()[0]
        return {"runs": n_runs, "audit_entries": n_audit, "last_run_at": last,
                "retention_days": self.retention_days}


_store: RunStore | None = None
_store_lock = threading.Lock()


def get_store() -> RunStore | None:
    """Process-wide store, or None when persistence is disabled."""
    global _store
    if os.environ.get("PIER_STORE_DISABLED") == "1":
        return None
    with _store_lock:
        wanted = os.environ.get("PIER_API_DB")
        if _store is None or (wanted and wanted != _store.path):
            if _store is not None:
                _store.close()
            _store = RunStore()
        return _store


def reset_store() -> None:
    """Close and forget the current store (tests, config reload)."""
    global _store
    with _store_lock:
        if _store is not None:
            _store.close()
        _store = None


__all__ = ["RunStore", "get_store", "reset_store", "cell_for", "CELL_DECIMALS"]
