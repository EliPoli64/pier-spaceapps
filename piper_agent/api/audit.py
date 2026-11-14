"""Audit records: everything needed to answer "why did PIER recommend this?".

For every plan the API records the inputs, the resolved scenario, which data
path was taken (cache, live, or live that fell back to cache), the live-source
circuit-breaker state at that moment, which contract keys the agent returned
(and which the API had to fill), the code/contract versions, the provenance of
the cached files, and a human-readable chain of evidence.
"""
from __future__ import annotations

import os
import subprocess
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "1.1"
CONTRACT_KEYS = ("exclusiones", "rotacion", "ahorro", "confianza_calibrada", "suelo",
                 "ola_calor", "fuente_datos")

_PACKAGE = Path(__file__).resolve().parent.parent
_REPO = _PACKAGE.parent


@lru_cache(maxsize=1)
def code_version() -> str | None:
    """Git commit of the running code (PIER_GIT_SHA overrides; None if unknown)."""
    if os.environ.get("PIER_GIT_SHA"):
        return os.environ["PIER_GIT_SHA"][:12]
    try:
        out = subprocess.run(["git", "-C", str(_REPO), "rev-parse", "--short=12", "HEAD"],
                             capture_output=True, text=True, timeout=3)
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def circuit_breaker_state() -> dict[str, Any]:
    """Live-source circuit breaker (data/resiliencia.py), read without mutating it."""
    try:
        from piper_agent.data.resiliencia import cortacircuito_en_vivo as cc
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": f"{type(exc).__name__}"}
    since = getattr(cc, "abierto_desde", None)
    reset = getattr(cc, "segundos_reinicio", 0)
    is_open = since is not None and (time.time() - since) <= reset
    state = {
        "available": True,
        "nombre": getattr(cc, "nombre", "en_vivo"),
        "abierto": is_open,
        "fallos_consecutivos": getattr(cc, "fallos", 0),
        "umbral": getattr(cc, "umbral", None),
        "abierto_desde": (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(since)) if since else None),
    }
    for attr in ("ultimo_exito", "ultimo_fallo"):          # if the data layer records them
        val = getattr(cc, attr, None)
        if val:
            state[attr] = (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(val))
                           if isinstance(val, (int, float)) else str(val))
    return state


def data_path(demo_mode: bool, fuente_datos: str | None) -> str:
    if demo_mode:
        return "cache"
    return "live_fallback_to_cache" if fuente_datos == "sintetico" else "live"


def cache_provenance(demo_name: str | None) -> list[dict[str, Any]]:
    """Cached files a demo run read: path (repo-relative), mtime, synthetic marker."""
    if not demo_name:
        return []
    out = []
    for sub, suffix in (("imerg", "_imerg.csv"), ("power", "_power.csv")):
        f = _PACKAGE / "data" / "cache" / sub / f"{demo_name}{suffix}"
        if not f.exists():
            out.append({"file": str(f.relative_to(_REPO)), "exists": False})
            continue
        marker = f.with_name(f.name.replace(".csv", ".SYNTHETIC_CACHE.txt"))
        out.append({
            "file": str(f.relative_to(_REPO)),
            "exists": True,
            "modified": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(f.stat().st_mtime)),
            "synthetic": marker.exists(),
        })
    return out


def contract_presence(result: dict, response: dict) -> dict[str, list[str]]:
    from_agent = [k for k in CONTRACT_KEYS if result.get(k) is not None]
    by_api = [k for k in CONTRACT_KEYS
              if k not in from_agent and isinstance(response.get(k), dict)
              and response[k].get("origen") == "api_fallback"]
    if (k := "exclusiones") not in from_agent and response.get(k) and \
            any(isinstance(e, dict) and e.get("origen") == "api_fallback" for e in response[k]):
        by_api.append(k)
    missing = [k for k in CONTRACT_KEYS if k not in from_agent and k not in by_api]
    return {"del_agente": from_agent, "rellenadas_por_api": by_api, "ausentes": missing}


def evidence(response: dict) -> list[str]:
    """Plain-language chain of reasons behind the recommendation."""
    out: list[str] = []
    d = response.get("event_details") or {}
    ev = response.get("event_type")
    if "cum3_mm" in d and "flood_threshold_mm" in d:
        out.append(f"Rain: max 3-day total {d['cum3_mm']} mm vs flood threshold "
                   f"{d['flood_threshold_mm']} mm (min of seasonal p95 and 100 mm).")
    if "cum30_mm" in d and "p10_30day_cum" in d:
        out.append(f"Rain: 30-day total {d['cum30_mm']} mm vs drought threshold (p10) "
                   f"{d['p10_30day_cum']} mm.")
    if d.get("window_note"):
        out.append(d["window_note"])
    conf = response.get("event_confidence")
    out.append(f"Event detected: {ev}" + (f" (confidence {round(conf * 100)}%)." if conf is not None else "."))
    if response.get("gdd_remaining") is not None:
        out.append(f"Thermal time: {response.get('gdd_accumulated')} GDD accumulated, "
                   f"{response.get('gdd_remaining')} GDD left before {response.get('frost_date')}; "
                   f"a crop qualifies only if it needs ≤ 80% of what is left.")
    for c in response.get("crops") or []:
        out.append(f"Eligible: {c.get('crop')} — needs {c.get('gdd_requirement')} GDD, "
                   f"plant by {c.get('plant_by_date')}.")
    for e in response.get("exclusiones") or []:
        if isinstance(e, dict) and e.get("explicacion"):
            out.append(f"Excluded: {e['explicacion']}")
    if response.get("fallback") and ev != "none":
        out.append("No crop fits the remaining window: cover crop for soil protection only (BR-5).")
    return out


def build_audit(*, run_id: str, request: dict, result: dict, response: dict,
                api_version: str, elapsed_ms: float) -> dict[str, Any]:
    fuente = response.get("fuente_datos")
    return {
        "run_id": run_id,
        "entradas": request,
        "resuelto": {
            "demo_name": response.get("demo_name"),
            "auto_detectado": response.get("auto_detected"),
            "demo_mode": response.get("demo_mode"),
            "vista": response.get("vista"),
        },
        "datos": {
            "fuente_datos": fuente,
            "ruta": data_path(bool(response.get("demo_mode")), fuente),
            "ultima_actualizacion": response.get("ultima_actualizacion"),
            "cortacircuito": circuit_breaker_state(),
            "archivos_cache": cache_provenance(response.get("demo_name")) if response.get("demo_mode") else [],
        },
        "contrato": {"version": CONTRACT_VERSION, **contract_presence(result, response)},
        "versiones": {"api": api_version, "codigo": code_version()},
        "decision": {
            "event_type": response.get("event_type"),
            "event_confidence": response.get("event_confidence"),
            "rescue_confidence": response.get("rescue_confidence"),
            "fallback": response.get("fallback"),
            "cultivos": [{"crop": c.get("crop"), "plant_by_date": c.get("plant_by_date")}
                         for c in response.get("crops") or []],
        },
        "alertas": [a.get("codigo") for a in response.get("alertas") or []],
        "evidencia": evidence(response),
        "elapsed_ms": elapsed_ms,
    }


__all__ = ["CONTRACT_VERSION", "CONTRACT_KEYS", "code_version", "circuit_breaker_state",
           "data_path", "cache_provenance", "contract_presence", "evidence", "build_audit"]
