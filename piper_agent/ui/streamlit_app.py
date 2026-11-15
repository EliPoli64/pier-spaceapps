"""PIER Streamlit app — Extreme-weather Recovery Planner (Spec 3).

Run: streamlit run piper_agent/ui/streamlit_app.py
"""
from __future__ import annotations

import inspect
import sys
from datetime import date, timedelta
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
    TUTORIAL_SLIDES,
    first_present,
    render_crop_table,
    render_excluded_crops,
    render_fuente_datos_badge,
    render_hero,
    render_map,
    render_recovery_plan_card,
    render_rotation,
    render_savings,
    render_summary_metrics,
    render_tutorial_slide,
)
from piper_agent.ui.i18n import t

st.set_page_config(
    page_title="PIER — Extreme-weather Recovery Planner",
    page_icon="\U0001F6E1",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .pier-hero {
      background: linear-gradient(135deg, #0b1f3a 0%, #123b5c 55%, #1f6b4a 100%);
      color: #f8fafc;
      padding: 1.5rem 1.75rem;
      border-radius: 18px;
      margin-bottom: 1.1rem;
      box-shadow: 0 12px 30px rgba(11, 31, 58, 0.28);
    }
    .pier-hero h1 { color: #ffffff; font-size: 1.85rem; margin: 0.15rem 0 0.35rem; }
    .pier-hero p { color: #d7e3f4; margin: 0; font-size: 1rem; }
    .pier-hero-badge {
      display: inline-block; text-transform: uppercase; letter-spacing: 0.08em;
      font-size: 0.7rem; color: #a7f3d0; margin-bottom: 0.3rem;
    }
    .pier-chips { display: flex; flex-wrap: wrap; gap: 0.45rem; margin-top: 0.9rem; }
    .pier-chips span {
      background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.22);
      border-radius: 999px; padding: 0.28rem 0.65rem; font-size: 0.78rem;
    }
    .pier-slide {
      background: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px;
      padding: 2rem 2.2rem; box-shadow: 0 10px 26px rgba(15,23,42,0.08);
      min-height: 280px; margin-bottom: 0.75rem;
    }
    .pier-slide-emoji { font-size: 2.4rem; line-height: 1; margin-bottom: 0.5rem; }
    .pier-slide h2 { margin: 0 0 0.55rem; color: #0f172a; }
    .pier-slide p { color: #334155; font-size: 1.04rem; line-height: 1.6; margin: 0; }
    div[data-testid="stMetric"] {
      background: #ffffff; border: 1px solid #e2e8f0; border-radius: 14px;
      padding: 0.85rem 1rem; box-shadow: 0 6px 18px rgba(15,23,42,0.05);
    }
    div[data-testid="stMetricLabel"] { color: #64748b; }
    div[data-testid="stMetricValue"] { color: #0f172a; }
    .stTabs [data-baseweb="tab-list"] { gap: 0.35rem; }
    .stTabs [data-baseweb="tab"] {
      background: #f1f5f9; border-radius: 999px; padding: 0.35rem 0.9rem;
    }
    .stTabs [aria-selected="true"] { background: #0f172a !important; color: #ffffff !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Session-state defaults and one-shot mode switches run before any widget is created.
def _tomorrow() -> date:
    """Default run date for live data: the day after today."""
    return date.today() + timedelta(days=1)


st.session_state.setdefault("pier_demo_mode", True)
st.session_state.setdefault("pier_scenario_key", "flood")
st.session_state.setdefault("pier_date", _tomorrow())
st.session_state.setdefault("pier_tutorial_active", True)
st.session_state.setdefault("pier_tutorial_slide", 0)
if st.session_state.pop("_pier_go_live", False):
    st.session_state["pier_demo_mode"] = False
    st.session_state["pier_date"] = _tomorrow()

SCENARIO_KEYS = {
    "auto": None,
    "flood": "flood",
    "drought": "drought",
    "normal": "normal",
    "late_flood": "late_flood",
}

PRESETS = (
    ("preset_iowa", 41.8, -93.6),
    ("preset_horn", 9.0, 41.0),
    ("preset_cape", -33.9, 18.4),
)


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


def _on_map_click() -> None:
    """Apply the last map click to the lat/lon widgets before the script reruns."""
    state = st.session_state.get("pier_map_state") or {}
    clicked = state.get("last_clicked") or {}
    if clicked.get("lat") is None or clicked.get("lng") is None:
        return
    lat = round(float(clicked["lat"]), 4)
    lon = round(float(clicked["lng"]), 4)
    if (lat, lon) == st.session_state.get("_pier_last_click"):
        return
    st.session_state["_pier_last_click"] = (lat, lon)
    st.session_state["pier_lat"] = lat
    st.session_state["pier_lon"] = lon
    # A hand-picked place should drive the plan, so leave the cached demo packet.
    st.session_state["_pier_go_live"] = True


def _on_demo_mode_change() -> None:
    """Re-apply the demo packet when demo mode is toggled on; default live dates to tomorrow."""
    st.session_state["_pier_scenario"] = None
    if not st.session_state.get("pier_demo_mode", True):
        st.session_state["pier_date"] = _tomorrow()


def _render_tutorial(lang: str) -> None:
    """Render the tutorial carousel with Back / Next / Skip controls."""
    total = len(TUTORIAL_SLIDES)
    slide = int(st.session_state.get("pier_tutorial_slide", 0))
    slide = max(0, min(slide, total - 1))

    st.markdown(f"#### \U0001F393 {t(lang, 'tutorial_title')}")
    render_tutorial_slide(lang, slide)
    st.progress(
        (slide + 1) / total,
        text=t(lang, "tutorial_progress").format(n=slide + 1, total=total),
    )

    back, nxt, skip = st.columns([1, 1, 2])
    with back:
        if st.button(
            f"\u25C0 {t(lang, 'tutorial_back')}",
            disabled=slide == 0,
            width="stretch",
            key="tutorial_back",
        ):
            st.session_state["pier_tutorial_slide"] = slide - 1
            st.rerun()
    with nxt:
        label = (
            t(lang, "tutorial_next")
            if slide < total - 1
            else t(lang, "tutorial_start")
        )
        if st.button(
            label,
            type="primary",
            width="stretch",
            key="tutorial_next",
        ):
            if slide < total - 1:
                st.session_state["pier_tutorial_slide"] = slide + 1
            else:
                st.session_state["pier_tutorial_active"] = False
            st.rerun()
    with skip:
        if st.button(
            t(lang, "tutorial_skip"),
            width="stretch",
            key="tutorial_skip",
        ):
            st.session_state["pier_tutorial_active"] = False
            st.rerun()


# --- Sidebar ---
tutorial_open = bool(st.session_state.get("pier_tutorial_active", True))

with st.sidebar:
    st.markdown("### \U0001F6E1 PIER")
    lang = st.selectbox(
        f"{t('en', 'language')} / {t('es', 'language')}",
        options=["en", "es"],
        format_func=lambda x: "English" if x == "en" else "Español",
        key="pier_lang",
    )

    if st.button(
        f"\U0001F393 {t(lang, 'tutorial_button')}",
        width="stretch",
        key="open_tutorial",
    ):
        st.session_state["pier_tutorial_active"] = True
        st.session_state["pier_tutorial_slide"] = 0
        st.rerun()

    st.divider()
    st.subheader(f"\U0001F3AC {t(lang, 'demo_scenario')}")
    demo_mode = st.toggle(
        t(lang, "demo_mode"),
        key="pier_demo_mode",
        on_change=_on_demo_mode_change,
    )

    if demo_mode:
        scenario_options = ["auto", "flood", "drought", "normal", "late_flood"]
        scenario_labels = {
            "auto": t(lang, "scenario_auto"),
            "flood": t(lang, "scenario_flood"),
            "drought": t(lang, "scenario_drought"),
            "normal": t(lang, "scenario_normal"),
            "late_flood": t(lang, "scenario_late_flood"),
        }
        scenario = st.selectbox(
            t(lang, "scenario"),
            options=scenario_options,
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
                "late_flood": {"lat": 41.8, "lon": -93.6, "date": date(2025, 8, 28)},
            }.get(scenario, {"lat": 41.8, "lon": -93.6, "date": date(2025, 5, 15)})
            st.session_state["pier_lat"] = defaults["lat"]
            st.session_state["pier_lon"] = defaults["lon"]
            st.session_state["pier_date"] = defaults["date"]
            st.session_state.pop("_pier_last_click", None)
            if demo_name:
                try:
                    pkt = load_demo_packet(f"{demo_name}_demo")
                    st.session_state["pier_lat"] = float(pkt["lat"])
                    st.session_state["pier_lon"] = float(pkt["lon"])
                    st.session_state["pier_date"] = date.fromisoformat(pkt["current_date"])
                except OSError:
                    pass
    else:
        scenario = "auto"
        demo_name = None

    st.divider()
    st.subheader(f"\U0001F4CD {t(lang, 'field_location')}")
    st.caption(t(lang, "sidebar_help"))
    st.caption(f"**{t(lang, 'location_presets')}**")
    preset_cols = st.columns(3)
    for col, (label_key, preset_lat, preset_lon) in zip(preset_cols, PRESETS):
        if col.button(
            t(lang, label_key),
            key=f"preset_{label_key}",
            width="stretch",
        ):
            st.session_state["pier_lat"] = preset_lat
            st.session_state["pier_lon"] = preset_lon
            st.session_state["_pier_go_live"] = True
            st.session_state.pop("_pier_last_click", None)
            st.rerun()

    lat = st.number_input(
        t(lang, "latitude"),
        key="pier_lat",
        min_value=-90.0,
        max_value=90.0,
        step=0.1,
        format="%.2f",
    )
    lon = st.number_input(
        t(lang, "longitude"),
        key="pier_lon",
        min_value=-180.0,
        max_value=180.0,
        step=0.1,
        format="%.2f",
    )
    current_date = st.date_input(t(lang, "current_date"), key="pier_date")
    if demo_mode:
        st.caption(t(lang, "demo_date_note"))
    current_date_str = (
        current_date.isoformat() if current_date else _tomorrow().isoformat()
    )

    # M2: farmer priority weights + expected yield
    st.divider()
    st.subheader(f"\u2696\uFE0F {t(lang, 'farmer_priorities')}")
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

    generate_sidebar = st.button(
        t(lang, "generate"),
        type="primary",
        width="stretch",
        disabled=tutorial_open,
        key="generate_sidebar",
    )

# --- Main ---
render_hero(lang)

if st.session_state.get("pier_tutorial_active", True):
    _render_tutorial(lang)
    st.stop()

result = st.session_state.get("pier_result")
meta = st.session_state.get("pier_result_meta") or {}
pin_matches_result = bool(meta) and (
    abs(float(meta.get("lat", lat)) - float(lat)) <= 1e-4
    and abs(float(meta.get("lon", lon)) - float(lon)) <= 1e-4
    and bool(meta.get("demo_mode")) == bool(demo_mode)
)

map_col, info_col = st.columns([1.75, 1], gap="large")
with map_col:
    st.markdown(f"#### \U0001F5FA\uFE0F {t(lang, 'map_subheader')}")
    st.caption(t(lang, "map_hint"))
    _event_type = (
        getattr(result["event_result"], "event_type", "none")
        if result and pin_matches_result
        else "none"
    )
    _confidence = (
        getattr(result["event_result"], "confidence", 0.0)
        if result and pin_matches_result
        else 0.0
    )
    render_map(
        float(lat),
        float(lon),
        _event_type,
        _confidence,
        lang=lang,
        on_change=_on_map_click,
    )

with info_col:
    st.markdown(f"#### \U0001F4CD {t(lang, 'map_selected')}")
    st.code(f"{float(lat):.4f}, {float(lon):.4f}", language=None)
    st.caption(f"{t(lang, 'current_date')}: {current_date_str}")

    if demo_mode:
        st.caption(t(lang, "demo_location_note"))
        if st.button(
            t(lang, "use_live_data"),
            key="use_live_data",
            width="stretch",
        ):
            st.session_state["_pier_go_live"] = True
            st.rerun()
    else:
        st.caption(t(lang, "live_mode_hint"))

    generate_main = False
    if not result:
        with st.container(border=True):
            st.markdown(f"**{t(lang, 'welcome_title')}**")
            st.write(t(lang, "welcome_body"))
            generate_main = st.button(
                t(lang, "generate"),
                type="primary",
                width="stretch",
                key="generate_main",
                disabled=tutorial_open,
            )

if generate_sidebar or generate_main:
    spinner_text = (
        t(lang, "fetching_live") if not demo_mode else t(lang, "generate")
    )
    try:
        with st.spinner(spinner_text):
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
        st.session_state["pier_result_meta"] = {
            "lat": float(lat),
            "lon": float(lon),
            "date": current_date_str,
            "demo_mode": bool(demo_mode),
            "scenario": scenario,
        }
    except NotImplementedError as e:
        st.error(str(e))
        st.stop()
    except Exception as e:  # noqa: BLE001
        st.error(f"Error: {e}")
        st.stop()
    st.rerun()

if result:
    er = result["event_result"]
    rp = result["recovery_plan"]
    is_demo = bool(result.get("demo_mode", demo_mode))
    fuente = first_present(result, "fuente_datos")

    stale = bool(meta) and (
        abs(float(meta.get("lat", lat)) - float(lat)) > 1e-4
        or abs(float(meta.get("lon", lon)) - float(lon)) > 1e-4
        or meta.get("date") != current_date_str
        or bool(meta.get("demo_mode")) != bool(demo_mode)
        or meta.get("scenario") != scenario
    )
    if stale:
        st.warning(t(lang, "map_stale"))

    render_summary_metrics(result, lang=lang)
    if not is_demo:
        render_fuente_datos_badge(fuente, demo_mode=False, lang=lang)

    crops = result.get("crops") or getattr(rp, "crops", []) or []
    exclusions = first_present(
        result, "exclusiones", "excluciones", "excluded_crops", "exclusion_reasons"
    )
    rotacion = first_present(result, "rotacion", "rotation")
    ahorro = first_present(
        result, "ahorro", "dollar_savings", "estimated_savings_usd_ha"
    )

    tab_overview, tab_crops, tab_excluded, tab_rotation = st.tabs(
        [
            f"\U0001F4CB {t(lang, 'tab_overview')}",
            f"\U0001F331 {t(lang, 'tab_crops')}",
            f"\U0001F6AB {t(lang, 'tab_excluded')}",
            f"\U0001F504 {t(lang, 'tab_rotation')}",
        ]
    )

    with tab_overview:
        render_recovery_plan_card(
            result.get("plan_text", ""),
            rp,
            demo_mode=is_demo,
            fuente_datos=fuente if isinstance(fuente, str) else None,
            lang=lang,
        )

    with tab_crops:
        if crops:
            render_crop_table(crops, lang=lang)
        else:
            st.info(t(lang, "no_crops"))

    with tab_excluded:
        if exclusions:
            render_excluded_crops(exclusions, lang=lang)
        else:
            st.caption(t(lang, "no_exclusions"))

    with tab_rotation:
        has_rotation = False
        if rotacion:
            render_rotation(rotacion, lang=lang)
            has_rotation = True
        if ahorro is not None:
            render_savings(ahorro, lang=lang)
            has_rotation = True
        if not has_rotation:
            st.caption(t(lang, "no_rotation"))
