"""Adapter between the HTTP layer and the agent / tools.

This is the ONLY module of the API that imports A-team code
(``piper_agent.agent``, ``piper_agent.tools``, ``piper_agent.data``,
``piper_agent.monitoring``). It is written defensively so the API keeps
working while the other branches land, in any merge order:

* ``run_pier`` is called with ``pesos_agricultor`` / ``rendimiento_t_ha``
  only if its signature accepts them (Alina, A4).
* Contract keys (``exclusiones``, ``rotacion``, ``ahorro``,
  ``fuente_datos``, ``confianza_calibrada``, ``suelo``, ``ola_calor``) are
  read with ``.get()``. If the agent does not provide one yet, the API
  fills it from the existing tools and marks it ``"origen": "api_fallback"``
  so nobody mistakes it for the agent's own output. Once the agent fills a
  key, the fallback for it is simply never used.
* The crop CSV path comes from ``cache_loader`` when Erik exports it
  (``get_ruta_cultivos`` / ``RUTA_CULTIVOS``), else from this package's
  location (never from the current working directory).
"""
from __future__ import annotations

import inspect
import json
import logging
import math
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger("pier.api.services")

PACKAGE_DIR = Path(__file__).resolve().parent.parent      # piper_agent/
REPO_ROOT = PACKAGE_DIR.parent
DEFAULT_CROPS_CSV = PACKAGE_DIR / "data" / "rescue_crops.csv"
DEMO_DIR = REPO_ROOT / "demo"
AUTO_DETECT_MAX_DEG = 0.5

FUENTES_VALIDAS = ("sintetico", "nasa_power", "nasa_power+imerg")


_PLACEHOLDER_USERS = {"", "your_username", "your_earthdata_username", "changeme"}

# D10: optional contract keys are omitted from the JSON when the agent has no value.
OPTIONAL_CONTRACT_KEYS = ("exclusiones", "rotacion", "ahorro", "confianza_calibrada", "suelo",
                          "ola_calor", "ultima_actualizacion", "dollar_savings", "rotation",
                          "event_severity", "event_details")


def default_demo_mode() -> bool:
    """Server default for demo mode: PIER_DEMO_MODE=0 enables the production path."""
    import os

    return os.environ.get("PIER_DEMO_MODE", "1").strip() != "0"


def earthdata_configured() -> bool:
    """D9: True when real Earthdata credentials appear to be set (never returns the value)."""
    import os

    user = os.environ.get("EARTHDATA_USERNAME", "").strip()
    return user.lower() not in _PLACEHOLDER_USERS


def demo_mode_status() -> str:
    return "production_path_available" if earthdata_configured() else "active"


class ApiInputError(ValueError):
    """Bad input that the user can fix (→ HTTP 422)."""


# ── Generic helpers ──────────────────────────────────────────────────────────

def utc_now_iso() -> str:
    """D3: timezone-aware UTC timestamp (replaces datetime.utcnow())."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def to_jsonable(obj: Any) -> Any:
    """Recursively convert dataclasses, dates, numpy/pandas scalars, NaN → JSON-safe."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return to_jsonable(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, int):
        return int(obj)
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    item = getattr(obj, "item", None)          # numpy / pandas scalars
    if callable(item):
        try:
            return to_jsonable(item())
        except Exception:  # noqa: BLE001
            pass
    iso = getattr(obj, "isoformat", None)      # pandas Timestamp
    if callable(iso):
        return iso()
    return str(obj)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """``.get`` that works on dicts and on dataclass/objects."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


# ── Paths / demo packets (D2) ────────────────────────────────────────────────

def crops_csv_path() -> Path:
    """Crop database path: Erik's export if present, else package-relative."""
    try:
        from piper_agent.data import cache_loader
    except Exception:  # noqa: BLE001
        return DEFAULT_CROPS_CSV
    getter = getattr(cache_loader, "get_ruta_cultivos", None)
    if callable(getter):
        try:
            return Path(getter())
        except Exception as exc:  # noqa: BLE001
            logger.warning("get_ruta_cultivos() failed (%s); using default path", exc)
    const = getattr(cache_loader, "RUTA_CULTIVOS", None)
    if const:
        return Path(const)
    return DEFAULT_CROPS_CSV


def load_all_crops() -> list[dict[str, Any]]:
    import pandas as pd

    return pd.read_csv(crops_csv_path()).to_dict("records")


@lru_cache(maxsize=1)
def _demo_packets_cached(_mtime_key: float) -> tuple[dict, ...]:
    packets = []
    for p in sorted(DEMO_DIR.glob("*_demo.json")):
        try:
            packets.append(json.loads(p.read_text()))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping unreadable demo packet %s: %s", p.name, exc)
    return tuple(sorted(packets, key=lambda pk: (pk.get("order", 99), pk.get("name", ""))))


def demo_packets() -> list[dict[str, Any]]:
    mtime = max((p.stat().st_mtime for p in DEMO_DIR.glob("*_demo.json")), default=0.0)
    return [dict(p) for p in _demo_packets_cached(mtime)]


def demo_names() -> list[str]:
    return [p["name"].removesuffix("_demo") for p in demo_packets() if "name" in p]


def get_demo_packet(name: str) -> dict[str, Any]:
    from piper_agent.data.cache_loader import load_demo_packet

    return load_demo_packet(f"{name}_demo")


def resolve_demo_name(lat: float, lon: float, demo_name: str | None) -> tuple[str, bool]:
    """Return (demo_name, auto_detected). Raises ApiInputError if impossible.

    Unlike the agent's internal auto-select, a location far from every cached
    dataset is an error instead of silently answering with the flood demo.
    """
    names = demo_names()
    if demo_name is not None:
        name = demo_name.removesuffix("_demo")
        if name not in names:
            raise ApiInputError(f"Unknown demo_name '{demo_name}'. Available: {names}")
        return name, False
    best, best_d = None, float("inf")
    for p in demo_packets():
        d = math.hypot(float(p["lat"]) - lat, float(p["lon"]) - lon)
        if d < best_d:
            best, best_d = p, d
    if best is None or best_d > AUTO_DETECT_MAX_DEG:
        locs = sorted({(p["lat"], p["lon"]) for p in demo_packets()})
        raise ApiInputError(
            f"No cached demo data near ({lat:.2f}, {lon:.2f}). In demo mode use one of "
            f"these locations {locs} or pass demo_name explicitly ({names})."
        )
    return best["name"].removesuffix("_demo"), True


# ── Agent call (D1) ──────────────────────────────────────────────────────────

def _accepted_params(func) -> set[str]:
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return set()
    if any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values()):
        return {"*"}
    return set(sig.parameters)


def call_run_pier(*, lat: float, lon: float, current_date: str, demo_mode: bool,
                  demo_name: str | None, pesos: dict | None, rendimiento: float | None
                  ) -> tuple[dict[str, Any], list[str]]:
    """Call ``run_pier`` with whatever contract parameters it supports.

    Returns (result, ignored_params) so the caller can warn the user when a
    requested option had no effect yet.
    """
    from piper_agent.agent import run_pier

    accepted = _accepted_params(run_pier)
    kwargs: dict[str, Any] = dict(lat=lat, lon=lon, current_date=current_date,
                                  demo_mode=demo_mode, demo_name=demo_name)
    ignored: list[str] = []
    for key, value in (("pesos_agricultor", pesos), ("rendimiento_t_ha", rendimiento)):
        if value is None:
            continue
        if "*" in accepted or key in accepted:
            kwargs[key] = value
        else:
            ignored.append(key)
    return run_pier(**kwargs), ignored


# ── Contract keys with transitional fallbacks ────────────────────────────────

def _crop_name(c: Any) -> str:
    return str(_get(c, "crop", ""))


def get_exclusiones(result: dict, plan: Any, event_type: str, gdd_remaining: float) -> list[dict]:
    """BR-8: list of {crop, motivo, explicacion}."""
    raw = result.get("exclusiones")
    if raw is None:
        raw = _get(plan, "exclusions")
    if raw is not None:
        out = []
        for e in raw:
            if isinstance(e, str):
                out.append({"crop": e.split(" ")[0], "motivo": None, "explicacion": e})
            else:
                out.append({
                    "crop": _get(e, "crop"),
                    "motivo": _get(e, "motivo", _get(e, "reason")),
                    "explicacion": _get(e, "explicacion", _get(e, "explanation")),
                })
        return out

    from piper_agent.tools.explain_exclusion import explain_all_exclusions

    eligible = [{"crop": _crop_name(c)} for c in (result.get("crops") or [])]
    texts = explain_all_exclusions(load_all_crops(), eligible, event_type=event_type,
                                   gdd_remaining=gdd_remaining)
    return [{"crop": t.split(" excluded")[0].split(" not recommended")[0],
             "motivo": None, "explicacion": t, "origen": "api_fallback"} for t in texts]


def dominant_priority(pesos: dict[str, float] | None) -> str:
    """D6: farmer priority used to bias the rotation (highest weight wins)."""
    if not pesos:
        return "soil_protection"
    order = ("soil_protection", "salvage_revenue", "water_conservation")
    return max(order, key=lambda k: (pesos.get(k, 0.0), -order.index(k)))


def get_rotacion(result: dict, plan: Any, pesos: dict | None) -> dict | None:
    """BR-9/12: rescue → main → cover."""
    raw = result.get("rotacion")
    if raw is None:
        raw = _get(plan, "rotation")
    if raw is not None:
        return to_jsonable(raw)
    crops = result.get("crops") or []
    if not crops:
        return None
    from piper_agent.tools.plan_rotation import plan_rotation

    rot = to_jsonable(plan_rotation(_crop_name(crops[0]),
                                    {"farmer_priority": dominant_priority(pesos)}))
    rot["prioridad"] = dominant_priority(pesos)
    rot["origen"] = "api_fallback"
    return rot


def normalize_ahorro(raw: dict | None) -> dict | None:
    """Accept both the old compute_dollar_savings shape and Alina's A5 shape."""
    if not raw:
        return None
    raw = to_jsonable(raw)
    usd = raw.get("usd_por_ha", raw.get("estimated_savings_usd_per_ha"))
    out = dict(raw)
    out.setdefault("usd_por_ha", usd)
    out.setdefault("crop", raw.get("crop"))
    out.setdefault("es_estimado", True)
    return out


def get_ahorro(result: dict, plan: Any, rendimiento: float) -> dict | None:
    """BR-11: estimated USD/ha rescued."""
    raw = result.get("ahorro")
    if raw is None:
        raw = _get(plan, "dollar_savings")
    if raw is not None:
        return normalize_ahorro(raw)
    crops = result.get("crops") or []
    if not crops:
        return None
    from piper_agent.tools.fetch_market_price import compute_dollar_savings

    out = normalize_ahorro(compute_dollar_savings(_crop_name(crops[0]),
                                                  expected_yield_tons_per_ha=rendimiento))
    out["rendimiento_t_ha"] = rendimiento
    out["origen"] = "api_fallback"
    return out


def get_fuente_datos(result: dict, demo_name: str | None, demo_mode: bool) -> str:
    fuente = result.get("fuente_datos")
    if fuente:
        return str(fuente)
    try:
        from piper_agent.data import cache_loader

        getter = getattr(cache_loader, "get_fuente_datos", None)
        if callable(getter) and demo_name:
            return str(getter(demo_name))
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_fuente_datos failed: %s", exc)
    return "sintetico" if demo_mode else "nasa_power"


def get_ultima_actualizacion(result: dict, demo_name: str | None) -> str | None:
    """Date of the newest observation the plan was computed from."""
    if result.get("ultima_actualizacion"):
        return str(result["ultima_actualizacion"])
    if not demo_name:
        return None
    try:
        from piper_agent.data.cache_loader import load_imerg

        return str(to_jsonable(load_imerg(demo_name)["date"].max()))[:10]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read data freshness for %s: %s", demo_name, exc)
        return None


# ── Alerts & monitoring (D4, D5) ─────────────────────────────────────────────

_DRIFT_LEVEL = {"high": "critical", "medium": "warning", "low": "info"}


def _alerta(nivel: str, codigo: str, mensaje: str) -> dict[str, str]:
    return {"nivel": nivel, "codigo": codigo, "mensaje": mensaje}


def run_monitoring(*, event_type: str, event_conf: float, rescue_conf: float,
                   n_eligible: int, n_excluded: int, demo_mode: bool,
                   ultima_actualizacion: str | None) -> list[dict]:
    """D5: drift/staleness/confidence checks from monitoring/drift.py."""
    from piper_agent.monitoring import drift

    alerts = []
    if not demo_mode:
        # Cached demo data is old by design; staleness only matters live.
        alerts.append(drift.check_data_staleness(ultima_actualizacion, "IMERG/POWER"))
    alerts.append(drift.check_confidence_threshold(event_conf, "detection"))
    if event_type != "none":
        alerts.append(drift.check_confidence_threshold(rescue_conf, "rescue"))
    alerts.append(drift.check_recommendation_drift(n_eligible, n_excluded, event_type))
    return [a.to_dict() for a in alerts if a is not None]


def build_alertas(*, plan: Any, fuente: str, demo_mode: bool, auto_detected: bool,
                  demo_name: str, ignored: list[str], drift_alerts: list[dict],
                  fallbacks_used: list[str], current_date: str | None = None,
                  ultima_actualizacion: str | None = None,
                  live_requested: bool = False) -> list[dict]:
    """D4: user-facing validation warnings."""
    out: list[dict] = []
    if live_requested and fuente == "sintetico":
        out.append(_alerta("critical", "FALLBACK_DATOS_SINTETICOS",
                           "Live NASA data was requested but unavailable; the plan uses the "
                           "synthetic cache instead (circuit-breaker fallback)."))
    if current_date and ultima_actualizacion and current_date > ultima_actualizacion[:10]:
        out.append(_alerta("critical", "FECHA_FUERA_DE_DATOS",
                           f"Requested date {current_date} is after the newest available data "
                           f"({ultima_actualizacion[:10]}); results are not reliable for that date."))
    event_type = _get(plan, "event_type")
    if _get(plan, "fallback") and event_type != "none":
        out.append(_alerta("critical", "SIN_CULTIVO_EN_VENTANA",
                           "No rescue crop fits the remaining GDD window; the season's cash crop "
                           "is lost. Cover crop recommended for soil protection only (BR-5)."))
    if event_type == "none":
        out.append(_alerta("info", "SIN_EVENTO",
                           "No extreme weather event detected; the planned crop stands."))
    if fuente == "sintetico" and not live_requested:
        out.append(_alerta("warning", "DATOS_SINTETICOS",
                           "Synthetic demo data (no Earthdata credentials). Not for field decisions."))
    if demo_mode:
        out.append(_alerta("info", "MODO_DEMO", "Demo mode: all data served from cache."))
    if auto_detected:
        out.append(_alerta("info", "DEMO_AUTODETECTADO",
                           f"Location matched the cached '{demo_name}' scenario."))
    effects = {
        "pesos_agricultor": "the crop ranking ignores it (only the API rotation uses it)",
        "rendimiento_t_ha": "only the API savings estimate uses it",
    }
    for p in ignored:
        out.append(_alerta("info", "PARAMETRO_PARCIAL",
                           f"'{p}' is not supported by the agent yet: "
                           f"{effects.get(p, 'it had no effect')}."))
    if fallbacks_used:
        out.append(_alerta("info", "CALCULO_EN_API",
                           "Computed by the API until the agent provides it: "
                           + ", ".join(fallbacks_used) + "."))
    for a in drift_alerts:
        out.append(_alerta(_DRIFT_LEVEL.get(a.get("severity"), "warning"),
                           f"MONITOREO_{str(a.get('metric', '')).upper()}", a.get("message", "")))
    return out


# ── Response builders ────────────────────────────────────────────────────────

def serialize_crop(c: Any) -> dict[str, Any]:
    d = to_jsonable(c) if not isinstance(c, dict) else to_jsonable(dict(c))
    keys = ("crop", "event_match", "role", "gdd_requirement", "gdd_remaining", "margin_pct",
            "plant_by_date", "days_until_deadline", "rescue_confidence", "composite_score",
            "rationale")
    out = {k: d.get(k) for k in keys if k in d}
    for k, v in d.items():          # keep any new field the A-team adds
        out.setdefault(k, v)
    return out


def build_plan_response(*, request_id: str, result: dict, req, demo_name: str,
                        auto_detected: bool, ignored: list[str]) -> dict[str, Any]:
    plan = result["recovery_plan"]
    event = result.get("event_result")
    pesos = req.weights
    event_type = _get(plan, "event_type")
    gdd_remaining = float(_get(plan, "gdd_remaining", 0.0) or 0.0)
    crops = [serialize_crop(c) for c in (result.get("crops") or _get(plan, "crops") or [])]

    serialization_errors: list[str] = []

    def safe(key: str, fn, *args):
        try:
            return fn(*args)
        except Exception as exc:  # noqa: BLE001  (D10: one bad key must not sink the plan)
            logger.exception("Could not serialize contract key %s", key)
            serialization_errors.append(f"{key}: {type(exc).__name__}")
            return None

    exclusiones = safe("exclusiones", get_exclusiones, result, plan, event_type, gdd_remaining) or []
    rotacion = safe("rotacion", get_rotacion, result, plan, pesos)
    ahorro = safe("ahorro", get_ahorro, result, plan, req.yield_t_ha)
    fallbacks_used = [
        name for name, value in (("exclusiones", exclusiones[0] if exclusiones else None),
                                 ("rotacion", rotacion), ("ahorro", ahorro))
        if isinstance(value, dict) and value.get("origen") == "api_fallback"
    ]

    demo_mode = bool(result.get("demo_mode", req.demo_mode))
    fuente = get_fuente_datos(result, demo_name, demo_mode)
    ultima = safe("ultima_actualizacion", get_ultima_actualizacion, result, demo_name)
    drift_alerts = safe("monitoreo", lambda: run_monitoring(
        event_type=event_type,
        event_conf=float(_get(plan, "event_confidence", 0.0) or 0.0),
        rescue_conf=float(_get(plan, "rescue_confidence", 0.0) or 0.0),
        n_eligible=len(crops), n_excluded=len(exclusiones),
        demo_mode=demo_mode, ultima_actualizacion=ultima,
    )) or []
    alertas = build_alertas(plan=plan, fuente=fuente, demo_mode=demo_mode,
                            auto_detected=auto_detected, demo_name=demo_name, ignored=ignored,
                            drift_alerts=drift_alerts, fallbacks_used=fallbacks_used,
                            current_date=req.current_date, ultima_actualizacion=ultima,
                            live_requested=req.demo_mode is False)
    for err in serialization_errors:
        alertas.append(_alerta("warning", "CLAVE_NO_SERIALIZABLE",
                               f"Contract key omitted after an error ({err})."))

    response = {
        "request_id": request_id,
        "plan_text": _get(plan, "plan_text") or result.get("plan_text"),
        "event_type": event_type,
        "event_severity": _get(event, "severity"),
        "event_confidence": _get(plan, "event_confidence"),
        "rescue_confidence": _get(plan, "rescue_confidence"),
        "confianza_calibrada": to_jsonable(result.get("confianza_calibrada")),
        "gdd_accumulated": _get(plan, "gdd_accumulated"),
        "gdd_remaining": gdd_remaining,
        "frost_date": _get(plan, "frost_date"),
        "fallback": bool(_get(plan, "fallback", False)),
        "no_action_needed": bool(_get(plan, "no_action_needed", event_type == "none")),
        "crops": crops,
        "exclusiones": exclusiones,
        "rotacion": rotacion,
        "ahorro": ahorro,
        "suelo": to_jsonable(result.get("suelo")),
        "ola_calor": to_jsonable(result.get("ola_calor")),
        "fuente_datos": fuente,
        "ultima_actualizacion": ultima,
        "demo_mode": demo_mode,
        "demo_name": demo_name,
        "auto_detected": auto_detected,
        "pesos_agricultor": pesos,
        "rendimiento_t_ha": req.yield_t_ha,
        "alertas": alertas,
        "monitoreo": {"checked_at": utc_now_iso(), "alertas": drift_alerts},
        "event_details": to_jsonable(_get(event, "details")),
        # Legacy English keys kept for existing clients (contract rule: never rename).
        "dollar_savings": ahorro,
        "rotation": rotacion,
    }
    for key in OPTIONAL_CONTRACT_KEYS:          # D10
        if response.get(key) is None:
            response.pop(key, None)
    return response


__all__ = [
    "OPTIONAL_CONTRACT_KEYS",
    "demo_mode_status",
    "earthdata_configured",
    "default_demo_mode",
    "ApiInputError",
    "utc_now_iso",
    "to_jsonable",
    "crops_csv_path",
    "load_all_crops",
    "demo_packets",
    "demo_names",
    "get_demo_packet",
    "resolve_demo_name",
    "call_run_pier",
    "dominant_priority",
    "get_exclusiones",
    "get_rotacion",
    "get_ahorro",
    "normalize_ahorro",
    "get_fuente_datos",
    "run_monitoring",
    "build_alertas",
    "serialize_crop",
    "build_plan_response",
]
