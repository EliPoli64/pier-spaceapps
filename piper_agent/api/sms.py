"""D7: SMS simulation for the API (``POST /simulate_sms``).

Parses a farmer's text message and builds an SMS-length reply from
``run_pier``. Kept inside ``piper_agent/api`` so the endpoint does not
depend on ``ui/sms_gateway.py`` (Matias's branch), which is being
rewritten in parallel. Accepted formats (case-insensitive, Spanish or
English):

    41.8,-93.6,2025-05-15
    41.8 -93.6 2025-05-15
    lat 41.8 lon -93.6 fecha 2025-05-15
    41.8; -93.6
"""
from __future__ import annotations

import re
from typing import Any

DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
NUM_RE = re.compile(r"(?<![\w.])[-+]?\d{1,3}(?:\.\d+)?(?![\w.])")
KEYWORD_RE = re.compile(r"\b(lat|lon|lng|latitud|longitud|fecha|date)\b\s*[:=]?", re.I)
HELP_TEXT = "PIER: send lat,lon,date e.g. 41.8,-93.6,2025-05-15 / envie lat,lon,fecha"


def parse_sms(body: str) -> dict[str, Any] | None:
    """Extract lat, lon and an optional ISO date. None if not parseable/valid."""
    if not body or not body.strip():
        return None
    text = body.strip()
    m = DATE_RE.search(text)
    date_str = m.group(1) if m else None
    if m:
        text = text[: m.start()] + " " + text[m.end():]
    text = KEYWORD_RE.sub(" ", text)
    text = re.sub(r"[;,]", " ", text)          # separators (decimal commas not supported)
    nums = [float(x) for x in NUM_RE.findall(text)]
    if len(nums) < 2:
        return None
    lat, lon = nums[0], nums[1]
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    if date_str:
        from datetime import date

        try:
            date.fromisoformat(date_str)
        except ValueError:
            return None
    return {"lat": lat, "lon": lon, "date": date_str}


def _fit(parts: list[str], max_length: int) -> str:
    """Join parts with spaces, dropping trailing parts (then cutting on a word) to fit."""
    out = ""
    for p in parts:
        candidate = (out + " " + p).strip()
        if len(candidate) <= max_length:
            out = candidate
        elif not out:
            out = candidate[: max_length - 1].rsplit(" ", 1)[0] + "…"
            break
        else:
            break
    return out


def format_reply(plan_response: dict[str, Any], max_length: int = 160) -> str:
    """Build the SMS from a /generate_plan response dict (most important info first)."""
    ev = plan_response.get("event_type")
    crops = plan_response.get("crops") or []
    if ev == "none":
        parts = ["PIER: no flood/drought detected.", "Keep your planned crop."]
    elif plan_response.get("fallback") or not crops:
        parts = [f"PIER: {ev.upper() if ev else 'EVENT'}.", "No crop fits the season left.",
                 "Plant cereal rye now to protect soil.", "Cash crop lost."]
    else:
        top = crops[0]
        parts = [f"PIER: {str(ev).upper()}.",
                 f"Plant {top.get('crop')} by {top.get('plant_by_date')}"
                 f" ({top.get('days_until_deadline')}d)."]
        if len(crops) > 1:
            parts.append(f"Alt: {crops[1].get('crop')} by {crops[1].get('plant_by_date')}.")
        conf = top.get("rescue_confidence")
        if conf is not None:
            parts.append(f"Conf {round(float(conf) * 100)}%.")
    if plan_response.get("fuente_datos") == "sintetico":
        parts.append("(demo data)")
    return _fit(parts, max_length)


__all__ = ["parse_sms", "format_reply", "HELP_TEXT"]
