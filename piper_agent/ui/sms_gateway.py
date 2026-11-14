"""SMS/USSD fallback gateway for PIER.

Accepts inbound SMS with lat/lon, runs the PIER agent, and replies with a
concise rescue-crop recommendation for low-connectivity, low-literacy farmers.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from piper_agent.agent import run_pier

logger = logging.getLogger("pier.ui.sms_gateway")


def parse_sms(body: str) -> dict[str, Any] | None:
    """Parse an inbound SMS for lat/lon.

    Accepts formats like:
      - "41.8, -93.6"
      - "lat 41.8 lon -93.6"
      - "41.8 -93.6"

    Returns dict with lat, lon or None if unparseable.
    """
    body = body.strip()
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


def format_sms_reply(
    lat: float,
    lon: float,
    current_date: str,
    demo_name: str | None = None,
    max_length: int = 160,
) -> str:
    """Run PIER and format a concise SMS reply (under max_length chars).

    Returns a plain-text SMS message.
    """
    result = run_pier(
        lat=lat,
        lon=lon,
        current_date=current_date,
        demo_mode=True,
        demo_name=demo_name,
    )

    rp = result["recovery_plan"]
    er = result["event_result"]

    # Build concise message
    if rp.fallback:
        msg = (
            f"PIER: {er.event_type} event at ({lat:.1f},{lon:.1f}). "
            f"No crop fits window. Plant cereal rye for soil cover. "
            f"Cash crop lost - soil protection only."
        )
    elif rp.crops:
        top = rp.crops[0]
        msg = (
            f"PIER: {er.event_type} at ({lat:.1f},{lon:.1f}). "
            f"Plant {top.crop} by {top.plant_by_date} "
            f"({top.days_until_deadline} days). "
            f"GDD remaining: {rp.gdd_remaining:.0f}."
        )
    else:
        msg = (
            f"PIER: {er.event_type} at ({lat:.1f},{lon:.1f}). "
            f"No extreme event detected. Normal-season planning."
        )

    # Truncate if too long
    if len(msg) > max_length:
        msg = msg[: max_length - 3] + "..."

    logger.info("SMS reply (%d chars): %s", len(msg), msg)
    return msg


def handle_inbound_sms(
    from_number: str,
    body: str,
    current_date: str,
    demo_name: str | None = None,
) -> str:
    """Handle an inbound SMS and return the reply text.

    Args:
        from_number: sender phone number.
        body: SMS message body.
        current_date: ISO date "now".
        demo_name: optional demo scenario.

    Returns:
        Reply text to send back.
    """
    parsed = parse_sms(body)
    if not parsed:
        return (
            "PIER: Send lat/lon (e.g. '41.8, -93.6') for a rescue-crop "
            "recommendation after extreme weather."
        )

    return format_sms_reply(
        lat=parsed["lat"],
        lon=parsed["lon"],
        current_date=current_date,
        demo_name=demo_name,
    )


__all__ = ["parse_sms", "format_sms_reply", "handle_inbound_sms"]
