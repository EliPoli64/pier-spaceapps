"""SMS/USSD fallback gateway for PIER.

Accepts inbound SMS with lat/lon (and optional date), runs the PIER agent,
and replies with a concise rescue-crop recommendation for low-connectivity,
low-literacy farmers.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

from piper_agent.agent import run_pier

logger = logging.getLogger("pier.ui.sms_gateway")

FORMAT_HINT = "Please send: lat,lon,date"


def parse_sms(body: str) -> dict[str, Any] | None:
    """Parse an inbound SMS for lat/lon (and optional ISO date).

    Accepts formats like:
      - "41.8, -93.6"
      - "41.8,-93.6,2025-05-15"
      - "lat 41.8 lon -93.6"
      - "41.8 -93.6"

    Returns dict with lat, lon, and optional date, or None if unparseable.
    """
    body = body.strip()
    # lat,lon,date (ISO)
    m = re.search(
        r"([\-\d.]+)\s*[,]\s*([\-\d.]+)\s*[,]\s*(\d{4}-\d{2}-\d{2})",
        body,
    )
    if m:
        return {
            "lat": float(m.group(1)),
            "lon": float(m.group(2)),
            "date": m.group(3),
        }

    # Try "lat X lon Y" format
    m = re.search(r"lat\s*([\-\d.]+)\s*lon\s*([\-\d.]+)", body, re.IGNORECASE)
    if m:
        return {"lat": float(m.group(1)), "lon": float(m.group(2))}

    # Try "X, Y" format
    m = re.search(r"([\-\d.]+)\s*[,]\s*([\-\d.]+)", body)
    if m:
        return {"lat": float(m.group(1)), "lon": float(m.group(2))}

    # Try "X Y" format
    m = re.search(r"([\-\d.]+)\s+([\-\d.]+)", body)
    if m:
        return {"lat": float(m.group(1)), "lon": float(m.group(2))}

    return None


def _source_badge_text(demo_mode: bool, fuente_datos: str | None) -> str:
    """Short SMS-safe badge for demo vs production path (M14)."""
    if demo_mode:
        return "[Synthetic]"
    raw = (fuente_datos or "nasa_power").strip().lower()
    if "imerg" in raw:
        return "[Live POWER+IMERG]"
    if "power" in raw or raw.startswith("nasa"):
        return "[Live NASA]"
    return "[Live]"


def format_sms_reply(
    lat: float,
    lon: float,
    current_date: str,
    demo_name: str | None = None,
    max_length: int = 160,
    demo_mode: bool = True,
) -> str:
    """Run PIER and format a concise SMS reply (under max_length chars).

    M14: respects demo_mode and appends a short source badge for Danny's
    `/simulate_sms` (and other callers). Live path may raise NotImplementedError
    until A-team production path lands — callers should catch that.
    """
    result = run_pier(
        lat=lat,
        lon=lon,
        current_date=current_date,
        demo_mode=demo_mode,
        demo_name=demo_name,
    )

    rp = result["recovery_plan"]
    er = result["event_result"]
    fuente = result.get("fuente_datos")
    badge = _source_badge_text(bool(result.get("demo_mode", demo_mode)), fuente)

    # Build concise message
    if rp.fallback:
        msg = (
            f"PIER: {badge} {er.event_type} at ({lat:.1f},{lon:.1f}). "
            f"No crop fits window. Plant cereal rye for soil cover."
        )
    elif rp.crops:
        top = rp.crops[0]
        msg = (
            f"PIER: {badge} {er.event_type} at ({lat:.1f},{lon:.1f}). "
            f"Plant {top.crop} by {top.plant_by_date} "
            f"({top.days_until_deadline}d). "
            f"GDD left: {rp.gdd_remaining:.0f}."
        )
    else:
        msg = (
            f"PIER: {badge} {er.event_type} at ({lat:.1f},{lon:.1f}). "
            f"No extreme event. Normal-season planning."
        )

    if len(msg) > max_length:
        msg = msg[: max_length - 3] + "..."

    logger.info("SMS reply (%d chars): %s", len(msg), msg)
    return msg


def handle_sms(message: str, demo_mode: bool = True) -> str:
    """M8/M14: parse lat,lon,date from message; return ≤160-char reply.

    On bad format returns: "Please send: lat,lon,date"
    """
    parsed = parse_sms(message or "")
    if not parsed or "date" not in parsed:
        return FORMAT_HINT

    reply = format_sms_reply(
        lat=parsed["lat"],
        lon=parsed["lon"],
        current_date=parsed["date"],
        demo_name=None,
        max_length=160,
        demo_mode=demo_mode,
    )
    return reply[:160] if len(reply) > 160 else reply


def handle_inbound_sms(
    from_number: str,
    body: str,
    current_date: str,
    demo_name: str | None = None,
    demo_mode: bool = True,
) -> str:
    """Handle an inbound SMS and return the reply text.

    Args:
        from_number: sender phone number.
        body: SMS message body.
        current_date: ISO date "now".
        demo_name: optional demo scenario.
        demo_mode: True = synthetic cache; False = production path (M14).

    Returns:
        Reply text to send back.
    """
    parsed = parse_sms(body)
    if not parsed:
        return (
            "PIER: Send lat/lon (e.g. '41.8, -93.6') for a rescue-crop "
            "recommendation after extreme weather."
        )

    use_date = parsed.get("date") or current_date or date.today().isoformat()
    return format_sms_reply(
        lat=parsed["lat"],
        lon=parsed["lon"],
        current_date=use_date,
        demo_name=demo_name,
        demo_mode=demo_mode,
    )


__all__ = ["parse_sms", "format_sms_reply", "handle_inbound_sms", "handle_sms"]
