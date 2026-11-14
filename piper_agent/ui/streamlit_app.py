"""PIER Streamlit app — Extreme-weather Recovery Planner (Spec 3).

Run: streamlit run piper_agent/ui/streamlit_app.py
"""
from __future__ import annotations

import inspect
import sys
from datetime import date
from pathlib import Path
from typing import Any

# Allow `streamlit run piper_agent/ui/streamlit_app.py` without installing the package
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from piper_agent.agent import run_pier
from piper_agent.data.cache_loader import load_demo_packet
from piper_agent.ui.components import (
    first_present,
    render_crop_table,
    render_excluded_crops,
    render_fuente_datos_badge,
    render_map,
    render_recovery_plan_card,
    render_rotation,
    render_savings,
)
from piper_agent.ui.i18n import t

st.set_page_config(page_title="PIER — Extreme-weather Recovery Planner", page_icon="\U0001F6E1")

SCENARIO_KEYS = {
    "auto": None,
    "flood": "flood",
    "drought": "drought",
    "normal": "normal",
}


def _call_run_pier(
    *,
    lat: float,
    lon: float,
    current_date: str,
    demo_mode: bool,
    demo_name: str | None,
    pesos_agricultor: dict[str, float],
    rendimiento_t_ha: float,
) -> dict[str, Any]:
    """Call run_pier, passing farmer weights / yield only if the signature accepts them."""
    params = inspect.signature(run_pier).parameters
    kwargs: dict[str, Any] = {
        "lat": lat,
        "lon": lon,
        "current_date": current_date,
        "demo_mode": demo_mode,
        "demo_name": demo_name,
    }
    if "pesos_agricultor" in params:
        kwargs["pesos_agricultor"] = pesos_agricultor
    elif "farmer_weights" in params:
        kwargs["farmer_weights"] = pesos_agricultor
    if "rendimiento_t_ha" in params:
        kwargs["rendimiento_t_ha"] = rendimiento_t_ha
    elif "expected_yield_tons_per_ha" in params:
        kwargs["expected_yield_tons_per_ha"] = rendimiento_t_ha
    return run_pier(**kwargs)


# --- Sidebar ---
with st.sidebar:
    lang = st.selectbox(
        "Language / Idioma",
        options=["en", "es"],
        format_func=lambda x: "English" if x == "en" else "Español",
        key="pier_lang",
    )

    st.header(t(lang, "demo_scenario"))
    demo_mode = st.toggle(t(lang, "demo_mode"), value=True)

    scenario_options = ["auto", "flood", "drought", "normal"]
    scenario_labels = {
        "auto": t(lang, "scenario_auto"),
        "flood": t(lang, "scenario_flood"),
        "drought": t(lang, "scenario_drought"),
        "normal": t(lang, "scenario_normal"),
    }
    scenario = st.selectbox(
        t(lang, "scenario"),
        options=scenario_options,
        index=1,  # Flood demo — ready for recording
        format_func=lambda k: scenario_labels[k],
        key="pier_scenario_key",
    )
    demo_name = SCENARIO_KEYS[scenario]

    # Sync lat/lon/date when scenario changes (M1)
    if st.session_state.get("_pier_scenario") != scenario:
        st.session_state["_pier_scenario"] = scenario
        defaults = {
            "auto": {"lat": 41.8, "lon": -93.6, "date": date(2025, 5, 15)},
            "flood": {"lat": 41.8, "lon": -93.6, "date": date(2025, 5, 15)},
            "drought": {"lat": 9.0, "lon": 41.0, "date": date(2025, 1, 30)},
            "normal": {"lat": 41.8, "lon": -93.6, "date": date(2025, 7, 7)},
        }[scenario]
        st.session_state["pier_lat"] = defaults["lat"]
        st.session_state["pier_lon"] = defaults["lon"]
        st.session_state["pier_date"] = defaults["date"]
        if demo_name:
            try:
                pkt = load_demo_packet(f"{demo_name}_demo")
                st.session_state["pier_lat"] = float(pkt["lat"])
                st.session_state["pier_lon"] = float(pkt["lon"])
                st.session_state["pier_date"] = date.fromisoformat(pkt["current_date"])
            except OSError:
                pass

    st.header(t(lang, "field_location"))
    lat = st.number_input(t(lang, "latitude"), key="pier_lat", step=0.1, format="%.2f")
    lon = st.number_input(t(lang, "longitude"), key="pier_lon", step=0.1, format="%.2f")
    current_date = st.date_input(t(lang, "current_date"), key="pier_date")
    current_date_str = (
        current_date.isoformat() if current_date else date(2025, 5, 15).isoformat()
    )

    # M2: farmer priority weights + expected yield
    st.header(t(lang, "farmer_priorities"))
    soil_protection = st.slider(t(lang, "soil_protection"), 0.0, 1.0, 0.4, 0.05)
    salvage_revenue = st.slider(t(lang, "salvage_revenue"), 0.0, 1.0, 0.3, 0.05)
    water_conservation = st.slider(t(lang, "water_conservation"), 0.0, 1.0, 0.3, 0.05)
    rendimiento_t_ha = st.number_input(
        t(lang, "expected_yield"),
        min_value=0.0,
        value=2.0,
        step=0.1,
        format="%.1f",
    )
    pesos_agricultor = {
        "soil_protection": float(soil_protection),
        "salvage_revenue": float(salvage_revenue),
        "water_conservation": float(water_conservation),
    }

    generate = st.button(t(lang, "generate"), type="primary")

st.title(f"\U0001F6E1 {t(lang, 'page_title')}")
st.caption(t(lang, "caption"))

# --- Main ---
if generate:
    try:
        result = _call_run_pier(
            lat=float(lat),
            lon=float(lon),
            current_date=current_date_str,
            demo_mode=demo_mode,
            demo_name=demo_name,
            pesos_agricultor=pesos_agricultor,
            rendimiento_t_ha=float(rendimiento_t_ha),
        )
        st.session_state["pier_result"] = result
    except NotImplementedError as e:
        st.error(str(e))
        st.stop()
    except Exception as e:  # noqa: BLE001
        st.error(f"Error: {e}")
        st.stop()

result = st.session_state.get("pier_result")
if result:
    er = result["event_result"]
    rp = result["recovery_plan"]
    is_demo = bool(result.get("demo_mode", demo_mode))

    fuente = first_present(result, "fuente_datos")
    # M7/M12: always show data-source badge; live path also surfaces fuente in the card (M13)
    render_fuente_datos_badge(fuente, demo_mode=is_demo, lang=lang)

    st.subheader(f"\U0001F4CD {t(lang, 'map_subheader')}")
    render_map(float(lat), float(lon), er.event_type, er.confidence)

    render_recovery_plan_card(
        result.get("plan_text", ""),
        rp,
        demo_mode=is_demo,
        fuente_datos=fuente if isinstance(fuente, str) else None,
        lang=lang,
    )

    crops = result.get("crops") or getattr(rp, "crops", []) or []
    render_crop_table(crops, lang=lang)

    exclusions = first_present(
        result, "exclusiones", "excluciones", "excluded_crops", "exclusion_reasons"
    )
    render_excluded_crops(exclusions, lang=lang)

    rotacion = first_present(result, "rotacion", "rotation")
    render_rotation(rotacion, lang=lang)

    ahorro = first_present(
        result, "ahorro", "dollar_savings", "estimated_savings_usd_ha"
    )
    render_savings(ahorro, lang=lang)
else:
    st.info(t(lang, "empty_prompt"))
