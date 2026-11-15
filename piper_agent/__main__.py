"""CLI entry point: python -m piper_agent --lat LAT --lon LON --date DATE."""
from __future__ import annotations

import argparse
import calendar
from dataclasses import asdict
from datetime import date, timedelta
import inspect
import json
import sys
from typing import Any

import numpy as np
import pandas as pd

from piper_agent.agent import run_pier
from piper_agent.config import (
    API_MODE_DEFAULT,
    HEMISPHERE_DEFAULT,
    TROPICAL_LATITUDE,
    VALID_API_MODES,
    VALID_HEMISPHERES,
)
from piper_agent.contracts import (
    CropRecommendation,
    EventResult,
    GddResult,
    RecoveryPlan,
)
from piper_agent.data.cache_loader import (
    SCENARIOS,
    get_crops_path,
    load_demo_packet,
)
from piper_agent.data.ingestion.pipeline import ingest_point
from piper_agent.tools.detect_event import FLOOD_ABSOLUTE_MM, detect_event
from piper_agent.tools.fetch_power_gdd import (
    build_climate_contract_bundle,
    fetch_power_gdd,
)
from piper_agent.tools.filter_rescue_crops import filter_rescue_crops
from piper_agent.tools.generate_recovery_plan import generate_recovery_plan

EVENT_WINDOW_DAYS = 7


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PIER — Extreme-weather Recovery Planner (Spec 3)"
    )
    parser.add_argument(
        "--lat", type=float, required=True, help="Field latitude"
    )
    parser.add_argument(
        "--lon", type=float, required=True, help="Field longitude"
    )
    parser.add_argument(
        "--date", type=str, required=True, help="Current date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        default=True,
        help="Use cached demo data (default: True)",
    )
    parser.add_argument(
        "--no-demo",
        action="store_true",
        default=False,
        help=(
            "Attempt live NASA POWER/IMERG path with offline synthetic "
            "fallback"
        ),
    )
    parser.add_argument(
        "--demo-name",
        type=str,
        choices=list(SCENARIOS),
        default=None,
        help="Select a specific demo scenario",
    )
    parser.add_argument(
        "--hemisphere",
        type=str,
        choices=list(VALID_HEMISPHERES),
        default=HEMISPHERE_DEFAULT,
        help="Hemisphere override: auto, north, or south",
    )
    parser.add_argument(
        "--api-mode",
        type=str,
        choices=list(VALID_API_MODES),
        default=None,
        help=(
            "Data source mode: demo (offline cache, default) or live "
            "(NASA POWER/IMERG with fallback)"
        ),
    )
    parser.add_argument(
        "--season-start",
        type=str,
        default=None,
        help=(
            "Optional planting/season start YYYY-MM-DD "
            "(defaults to agent regime inference)"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help=(
            "Emit structured JSON output including agronomic_metadata, "
            "per_crop_gdd, ola_calor, suelo, season_stage, and fuente_datos"
        ),
    )
    return parser


def _resolve_modes(args: argparse.Namespace) -> tuple[str, bool]:
    """Resolve effective API mode and demo_mode flag from CLI arguments."""
    if args.no_demo:
        effective_api_mode = "live"
    elif args.api_mode is not None:
        effective_api_mode = args.api_mode
    else:
        effective_api_mode = API_MODE_DEFAULT
    demo_mode = effective_api_mode == "demo" and args.demo and not args.no_demo
    return effective_api_mode, demo_mode


def _validate_inputs(
    lat: float,
    lon: float,
    current_date: str,
    season_start: str | None,
) -> None:
    if not (-90.0 <= float(lat) <= 90.0):
        raise ValueError(f"lat must be within [-90, 90], got {lat}")
    if not (-180.0 <= float(lon) <= 180.0):
        raise ValueError(f"lon must be within [-180, 180], got {lon}")
    date.fromisoformat(current_date)
    if season_start is not None:
        date.fromisoformat(season_start)


def _resolve_hemisphere_label(lat: float, hemisphere: str) -> str:
    if hemisphere == "auto":
        return "south" if float(lat) < 0 else "north"
    return hemisphere


def _infer_season_start(
    lat: float,
    current_date: str,
    resolved_hemisphere: str,
) -> str:
    """Infer default planting start date matching climate regime rules."""
    cur_dt = date.fromisoformat(current_date)
    if abs(float(lat)) < TROPICAL_LATITUDE:
        if cur_dt.month <= 2:
            return f"{cur_dt.year - 1}-11-01"
        return f"{cur_dt.year}-04-01"
    if resolved_hemisphere == "south":
        start_year = cur_dt.year if cur_dt.month >= 9 else cur_dt.year - 1
        return f"{start_year}-10-01"
    return f"{cur_dt.year}-04-01"


def _detection_window(
    max_available_date: str | None,
    current_date: str,
) -> tuple[str, str, str | None]:
    """Return 7-day BR-1 window clamped to available rainfall observations."""
    today = date.fromisoformat(current_date)
    note = None
    if max_available_date:
        data_end = date.fromisoformat(str(max_available_date)[:10])
        end = min(today, data_end)
        if today > data_end:
            note = (
                f"Rainfall data ends {data_end.isoformat()}; "
                "event detection uses the week ending on that date."
            )
    else:
        end = today
    start = end - timedelta(days=EVENT_WINDOW_DAYS - 1)
    return start.isoformat(), end.isoformat(), note


def _detect_event_from_rainfall(
    lat: float,
    lon: float,
    rainfall_df: pd.DataFrame,
    current_date: str,
) -> tuple[EventResult, str | None]:
    """Compute BR-1 event directly from ingested daily rainfall series."""
    df = rainfall_df.copy()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
        df["precipitation_mm"] = pd.to_numeric(
            df["precipitation_mm"], errors="coerce"
        ).fillna(0.0)
        cutoff_ts = pd.Timestamp(current_date)
        df = df.dropna(subset=["date"])
        df = df[df["date"] <= cutoff_ts].sort_values("date")
        df = df.reset_index(drop=True)

    max_date_str = (
        df["date"].max().strftime("%Y-%m-%d") if not df.empty else None
    )
    recent_start, recent_end, window_note = _detection_window(
        max_date_str, current_date
    )

    if df.empty:
        cum3 = 0.0
        cum30 = 0.0
        p95_cum3 = 50.0
        p10_cum30 = 50.0
    else:
        recent_mask = (df["date"] >= recent_start) & (df["date"] <= recent_end)
        recent = df.loc[recent_mask, "precipitation_mm"]
        cum3 = (
            float(recent.rolling(3, min_periods=1).sum().max())
            if not recent.empty
            else 0.0
        )

        end_dt = date.fromisoformat(recent_end)
        start30_dt = end_dt - timedelta(days=29)
        mask30 = (df["date"] >= pd.Timestamp(start30_dt)) & (
            df["date"] <= pd.Timestamp(recent_end)
        )
        cum30 = float(df.loc[mask30, "precipitation_mm"].sum())

        hist = df[df["date"] < pd.Timestamp(start30_dt)]
        base_series = (
            hist["precipitation_mm"]
            if len(hist) >= 60
            else df["precipitation_mm"]
        )
        if len(base_series) >= 30:
            p95_cum3 = float(
                np.percentile(
                    base_series.rolling(3, min_periods=1).sum().to_numpy(),
                    95,
                )
            )
            p10_cum30 = float(
                np.percentile(
                    base_series.rolling(30, min_periods=1).sum().to_numpy(),
                    10,
                )
            )
        else:
            p95_cum3 = 50.0
            p10_cum30 = 50.0

    flood_threshold = min(p95_cum3, FLOOD_ABSOLUTE_MM)
    if flood_threshold > 0 and cum3 > flood_threshold:
        event_type = "flood"
        ratio = cum3 / flood_threshold
        confidence = min(1.0, max(0.1, 0.6 + (ratio - 1.0) * 0.4))
    elif p10_cum30 > 0 and cum30 < p10_cum30:
        event_type = "drought"
        ratio = (p10_cum30 - cum30) / p10_cum30
        confidence = min(1.0, max(0.1, 0.6 + ratio * 0.4))
    else:
        event_type = "none"
        anomaly = max(
            cum3 / flood_threshold if flood_threshold > 0 else 0.0,
            cum30 / p10_cum30 if p10_cum30 > 0 else 0.0,
        )
        confidence = max(0.1, 1.0 - min(1.0, anomaly))

    confidence = max(0.0, min(1.0, float(confidence)))
    if confidence >= 0.75:
        severity = "high"
    elif confidence >= 0.40:
        severity = "medium"
    else:
        severity = "low"

    details: dict[str, Any] = {
        "cum3_mm": round(cum3, 2),
        "cum30_mm": round(cum30, 2),
        "flood_threshold_mm": round(flood_threshold, 2),
        "p95_3day_cum": round(p95_cum3, 2),
        "p10_30day_cum": round(p10_cum30, 2),
        "lat": float(lat),
        "lon": float(lon),
        "recent_start": recent_start,
        "recent_end": recent_end,
        "confidence": round(confidence, 3),
        "severity": severity,
    }
    return (
        EventResult(
            event_type=event_type,
            severity=severity,
            confidence=confidence,
            details=details,
        ),
        window_note,
    )


def _call_run_pier(
    args: argparse.Namespace,
    demo_mode: bool,
    effective_api_mode: str,
) -> dict[str, Any]:
    """Invoke `run_pier`, forwarding or applying CLI climate overrides."""
    params = set(inspect.signature(run_pier).parameters)
    kwargs: dict[str, Any] = {
        "lat": args.lat,
        "lon": args.lon,
        "current_date": args.date,
        "demo_mode": demo_mode,
        "demo_name": args.demo_name,
    }
    if "hemisphere" in params:
        kwargs["hemisphere"] = args.hemisphere
    if "season_start" in params and args.season_start is not None:
        kwargs["season_start"] = args.season_start
    if "api_mode" in params:
        kwargs["api_mode"] = effective_api_mode

    result = run_pier(**kwargs)

    # Apply --season-start, --hemisphere, or Southern growing-season inference.
    target_hem = _resolve_hemisphere_label(args.lat, args.hemisphere)
    prev_gdd: GddResult = result["gdd_result"]
    prev_season_str = str((prev_gdd.details or {}).get("season_start") or "")
    prev_month = (
        date.fromisoformat(prev_season_str).month if prev_season_str else 0
    )
    req_month = date.fromisoformat(args.date).month
    need_season_override = (
        args.season_start is not None and "season_start" not in params
    )
    need_hem_override = (
        args.hemisphere != "auto"
        and "hemisphere" not in params
        and prev_gdd.hemisphere != args.hemisphere
    )
    need_south_season_fix = (
        args.season_start is None
        and target_hem == "south"
        and abs(args.lat) >= TROPICAL_LATITUDE
        and prev_month in (3, 4, 5)
        and (req_month >= 9 or req_month <= 5)
    )
    if demo_mode and (
        need_season_override or need_hem_override or need_south_season_fix
    ):
        event_result: EventResult = result["event_result"]
        if args.season_start is not None:
            eff_season_start = args.season_start
        elif need_south_season_fix or (
            need_hem_override and target_hem == "south"
        ):
            eff_season_start = _infer_season_start(
                args.lat, args.date, target_hem
            )
        else:
            eff_season_start = prev_season_str or _infer_season_start(
                args.lat, args.date, target_hem
            )
        gdd_result = fetch_power_gdd(
            lat=args.lat,
            lon=args.lon,
            season_start=eff_season_start,
            current_date=args.date,
            demo_name=result.get("demo_name"),
            hemisphere=args.hemisphere,
            demo_mode=True,
            api_mode=effective_api_mode,
        )
        crops = filter_rescue_crops(
            event_type=event_result.event_type,
            gdd_remaining=gdd_result.gdd_remaining,
            current_date=args.date,
            avg_daily_gdd=gdd_result.avg_daily_gdd,
            crops_csv=str(get_crops_path()),
        )
        plan_text, recovery_plan = generate_recovery_plan(
            event_result=event_result,
            gdd_result=gdd_result,
            crops=crops,
            current_date=date.fromisoformat(args.date),
        )
        window_note = event_result.details.get("window_note")
        if window_note:
            plan_text = f"{plan_text}\nNote: {window_note}"
            recovery_plan.plan_text = plan_text
        result = {
            **result,
            "gdd_result": gdd_result,
            "crops": crops,
            "recovery_plan": recovery_plan,
            "plan_text": plan_text,
        }

    return result


def _run_live_or_fallback(args: argparse.Namespace) -> dict[str, Any]:
    """Run live NASA POWER/IMERG ingestion with offline synthetic fallback."""
    resolved_hem = _resolve_hemisphere_label(args.lat, args.hemisphere)
    eff_season_start = args.season_start or _infer_season_start(
        args.lat, args.date, resolved_hem
    )

    cur_dt = date.fromisoformat(args.date)
    season_dt = date.fromisoformat(eff_season_start)
    ten_yr_day = min(
        cur_dt.day, calendar.monthrange(cur_dt.year - 10, cur_dt.month)[1]
    )
    ten_yr_ago = date(cur_dt.year - 10, cur_dt.month, ten_yr_day)
    ingest_start = min(ten_yr_ago, season_dt).isoformat()

    ingest = ingest_point(
        lat=args.lat,
        lon=args.lon,
        start=ingest_start,
        end=args.date,
        demo_mode=False,
    )
    source = str(ingest.get("fuente_datos") or "sintetico")
    fallback_reason = ingest.get("fallback_reason")
    scenario = (
        (args.demo_name or ingest.get("demo_scenario"))
        if source == "sintetico"
        else None
    )

    window_note: str | None = None
    if source == "sintetico" and scenario in SCENARIOS:
        packet = load_demo_packet(f"{scenario}_demo")
        recent_start, recent_end, window_note = _detection_window(
            packet.get("recent_end"), args.date
        )
        event_result = detect_event(
            lat=args.lat,
            lon=args.lon,
            recent_start=recent_start,
            recent_end=recent_end,
            demo_name=scenario,
        )
    else:
        event_result, window_note = _detect_event_from_rainfall(
            args.lat,
            args.lon,
            ingest["rainfall"],
            args.date,
        )

    event_result.details["requested_date"] = args.date
    if window_note:
        event_result.details["window_note"] = window_note

    raw_power = ingest.get("power")
    power_df = raw_power.copy() if raw_power is not None else None
    if power_df is not None:
        power_df.attrs["fuente_datos"] = source
        if fallback_reason:
            power_df.attrs["fallback_reason"] = fallback_reason

    gdd_result = fetch_power_gdd(
        lat=args.lat,
        lon=args.lon,
        season_start=eff_season_start,
        current_date=args.date,
        demo_name=scenario,
        hemisphere=args.hemisphere,
        demo_mode=False,
        api_mode="live",
        power_df=power_df,
    )

    details = gdd_result.details if gdd_result.details is not None else {}
    fuente_meta = dict(details.get("fuente_datos") or {})
    fuente_meta["source"] = source
    fuente_meta["mode"] = "live"
    fuente_meta["imerg_used"] = source == "nasa_power+imerg"
    fuente_meta["fallback_reason"] = fallback_reason
    fuente_meta["cache_used"] = bool(source == "sintetico" and scenario)
    fuente_meta["demo_scenario"] = scenario
    if ingest.get("region"):
        fuente_meta["region"] = ingest["region"]
    details["fuente_datos"] = fuente_meta
    if isinstance(details.get("agronomic_metadata"), dict):
        details["agronomic_metadata"]["data_source"] = source
    gdd_result.details = details

    crops = filter_rescue_crops(
        event_type=event_result.event_type,
        gdd_remaining=gdd_result.gdd_remaining,
        current_date=args.date,
        avg_daily_gdd=gdd_result.avg_daily_gdd,
        crops_csv=str(get_crops_path()),
    )
    plan_text, recovery_plan = generate_recovery_plan(
        event_result=event_result,
        gdd_result=gdd_result,
        crops=crops,
        current_date=cur_dt,
    )
    if window_note:
        plan_text = f"{plan_text}\nNote: {window_note}"
        recovery_plan.plan_text = plan_text

    return {
        "event_result": event_result,
        "gdd_result": gdd_result,
        "crops": crops,
        "recovery_plan": recovery_plan,
        "plan_text": plan_text,
        "demo_mode": False,
        "demo_name": scenario,
        "fuente_datos": fuente_meta,
        "fallback_reason": fallback_reason,
    }


def _extract_fuente_dict(
    result: dict[str, Any],
    bundle: dict[str, Any],
) -> dict[str, Any]:
    bundle_fuente = bundle.get("fuente_datos")
    fuente: dict[str, Any] = (
        dict(bundle_fuente) if isinstance(bundle_fuente, dict) else {}
    )
    raw = result.get("fuente_datos")
    if isinstance(raw, dict):
        fuente.update(raw)
    elif isinstance(raw, str) and raw:
        fuente["source"] = raw
    if result.get("fallback_reason") and not fuente.get("fallback_reason"):
        fuente["fallback_reason"] = result["fallback_reason"]
    return fuente


def _build_json_payload(
    result: dict[str, Any],
    effective_api_mode: str,
    requested_hemisphere: str,
) -> dict[str, Any]:
    event_result: EventResult = result["event_result"]
    gdd_result: GddResult = result["gdd_result"]
    crops: list[CropRecommendation] = result["crops"]
    recovery_plan: RecoveryPlan = result["recovery_plan"]

    bundle = build_climate_contract_bundle(
        gdd_result,
        event_confidence=event_result.confidence,
        event_type=event_result.event_type,
    )
    fuente_datos = _extract_fuente_dict(result, bundle)
    bundle["fuente_datos"] = fuente_datos

    return {
        "demo_mode": bool(result.get("demo_mode", True)),
        "api_mode": effective_api_mode,
        "demo_name": result.get("demo_name"),
        "hemisphere_requested": requested_hemisphere,
        "hemisphere": gdd_result.hemisphere,
        "plan_text": result["plan_text"],
        "event_result": asdict(event_result),
        "gdd_result": asdict(gdd_result),
        "crops": [asdict(c) for c in crops],
        "recovery_plan": asdict(recovery_plan),
        "climate_contract": bundle,
        "agronomic_metadata": bundle.get("agronomic_metadata"),
        "per_crop_gdd": bundle.get("per_crop_gdd"),
        "ola_calor": bundle.get("ola_calor"),
        "suelo": bundle.get("suelo"),
        "season_stage": bundle.get("season_stage"),
        "fuente_datos": fuente_datos,
        "fallback_reason": fuente_datos.get("fallback_reason"),
        "units": bundle.get("units"),
        "thresholds": bundle.get("thresholds"),
    }


def _format_text_output(
    result: dict[str, Any],
    demo_mode: bool,
    effective_api_mode: str,
    requested_hemisphere: str,
    season_start_override: str | None,
) -> str:
    plan_text = str(result["plan_text"])
    gdd_result: GddResult = result["gdd_result"]
    details = gdd_result.details or {}
    fuente = _extract_fuente_dict(
        result, {"fuente_datos": details.get("fuente_datos")}
    )
    source_label = fuente.get("source") or "sintetico"
    fallback_reason = fuente.get("fallback_reason") or result.get(
        "fallback_reason"
    )

    lines = [plan_text]
    if not demo_mode:
        lines.append("")
        lines.append(
            f"Data Source / Fuente de Datos: {source_label} "
            f"(mode={effective_api_mode})"
        )
        if fallback_reason:
            lines.append(f"Fallback Reason: {fallback_reason}")
    elif requested_hemisphere != "auto" or season_start_override is not None:
        lines.append("")
        lines.append(
            f"Hemisphere: {gdd_result.hemisphere} | "
            f"Data Source / Fuente de Datos: {source_label}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    effective_api_mode, demo_mode = _resolve_modes(args)

    try:
        _validate_inputs(args.lat, args.lon, args.date, args.season_start)
        # Live CLI path owns ingestion + climate JSON contract (monkeypatched
        # via `ingest_point` in tests). Demo path goes through `run_pier`.
        if not demo_mode:
            try:
                result = _run_live_or_fallback(args)
            except NotImplementedError:
                result = _call_run_pier(args, demo_mode, effective_api_mode)
        else:
            try:
                result = _call_run_pier(args, demo_mode, effective_api_mode)
            except NotImplementedError:
                result = _run_live_or_fallback(args)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        payload = _build_json_payload(
            result,
            effective_api_mode=effective_api_mode,
            requested_hemisphere=args.hemisphere,
        )
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(
            _format_text_output(
                result,
                demo_mode=demo_mode,
                effective_api_mode=effective_api_mode,
                requested_hemisphere=args.hemisphere,
                season_start_override=args.season_start,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
