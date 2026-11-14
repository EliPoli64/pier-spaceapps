"""Readiness report for ``GET /ready``.

``/health`` answers "is the process alive?". ``/ready`` answers "can it give a
trustworthy plan right now, and from what data?":

* per demo dataset: cache present, synthetic or real, newest observation date;
* live path: credentials configured, circuit-breaker state, last run that used
  live data and last run that fell back to the cache (from the run store);
* run store: writable, row counts, retention;
* static inputs: crop database and demo packets.

``status`` is ``ready`` / ``degraded`` (works, with caveats listed in
``degradaciones``) / ``not_ready`` (cannot produce plans → HTTP 503).
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from piper_agent.api import audit, services as svc
from piper_agent.api.store import get_store

_PACKAGE = Path(__file__).resolve().parent.parent
LIVE_STALE_DAYS = int(os.environ.get("PIER_STALE_DATA_HOURS", "72")) / 24


def _newest_date(csv_path: Path) -> str | None:
    try:
        return str(pd.read_csv(csv_path, usecols=["date"])["date"].max())[:10]
    except Exception:  # noqa: BLE001
        return None


def dataset_status(name: str) -> dict[str, Any]:
    out: dict[str, Any] = {"demo_name": name}
    for sub, suffix in (("imerg", "_imerg.csv"), ("power", "_power.csv")):
        f = _PACKAGE / "data" / "cache" / sub / f"{name}{suffix}"
        marker = f.with_name(f.name.replace(".csv", ".SYNTHETIC_CACHE.txt"))
        out[sub] = {"en_cache": f.exists(),
                    "sintetico": marker.exists() if f.exists() else None,
                    "dato_mas_reciente": _newest_date(f) if f.exists() else None}
    try:
        out["fuente_datos"] = svc.data_source_for(name) or "desconocida"
    except Exception:  # noqa: BLE001
        out["fuente_datos"] = "desconocida"
    return out


def build_report(api_version: str) -> tuple[dict[str, Any], int]:
    degraded: list[str] = []
    blocking: list[str] = []

    crops_ok = svc.crops_csv_path().exists()
    names = svc.demo_names()
    if not crops_ok:
        blocking.append("rescue_crops.csv not found")
    if not names:
        blocking.append("no demo packets in demo/")

    datasets = [dataset_status(n) for n in names]
    missing = [d["demo_name"] for d in datasets if not (d["imerg"]["en_cache"] and d["power"]["en_cache"])]
    if missing:
        degraded.append(f"cache not generated yet for {missing} (it is generated on first use)")

    demo_default = svc.default_demo_mode()
    breaker = audit.circuit_breaker_state()
    if breaker.get("abierto"):
        degraded.append("live-source circuit breaker is OPEN: live requests fall back to the cache")
    creds = svc.earthdata_configured()
    if not demo_default and not creds:
        degraded.append("production mode without Earthdata credentials: live data unavailable")

    store = get_store()
    store_info: dict[str, Any] = {"habilitado": store is not None}
    last_live = last_fallback = None
    if store is not None:
        ok, err = store.healthy()
        store_info["ok"] = ok
        if ok:
            store_info.update(store.stats())
            last_live = store.last_run_where("data_path = 'live'")
            last_fallback = store.last_run_where("data_path = 'live_fallback_to_cache'")
        else:
            store_info["error"] = err
            degraded.append("run store unavailable: plans are not persisted")

    if last_live and not demo_default:
        age = (date.today() - date.fromisoformat(last_live["created_at"][:10])).days
        if age > LIVE_STALE_DAYS:
            degraded.append(f"last successful live run was {age} days ago")

    status = "not_ready" if blocking else ("degraded" if degraded else "ready")
    report = {
        "status": status,
        "checked_at": svc.utc_now_iso(),
        "version": api_version,
        "contrato": audit.CONTRACT_VERSION,
        "codigo": audit.code_version(),
        "demo_mode_default": demo_default,
        "demo_mode_status": svc.demo_mode_status(),
        "entradas_estaticas": {"rescue_crops_csv": crops_ok, "demo_packets": names},
        "datasets": datasets,
        "en_vivo": {
            "credenciales_configuradas": creds,
            "cortacircuito": breaker,
            "ultima_corrida_en_vivo": (last_live or {}).get("created_at"),
            "ultimo_respaldo_a_cache": (last_fallback or {}).get("created_at"),
        },
        "almacenamiento": store_info,
        "degradaciones": degraded,
        "bloqueos": blocking,
    }
    return report, (503 if blocking else 200)


__all__ = ["build_report", "dataset_status"]
