"""PIER Streamlit app — Extreme-weather Recovery Planner (Spec 3).

Run: streamlit run piper_agent/ui/streamlit_app.py
"""
from __future__ import annotations

import streamlit as st

from piper_agent.agent import run_pier, plan_text_only
from piper_agent.ui.components import render_map, render_recovery_plan_card, render_cache_badge

st.set_page_config(page_title="PIER — Extreme-weather Recovery Planner", page_icon="\U0001F6E1")

st.title("\U0001F6E1 PIER — Extreme-weather Recovery Planner")
st.caption("POWER + IMERG rescue-crop planner for farmers (Spec 3 · Extreme Weather)")

# --- Sidebar ---
with st.sidebar:
    st.header("Field location")
    lat = st.number_input("Latitude", value=41.8, step=0.1, format="%.2f")
    lon = st.number_input("Longitude", value=-93.6, step=0.1, format="%.2f")
    current_date = st.date_input("Current date")
    current_date_str = current_date.isoformat() if current_date else "2025-05-15"

    st.header("Demo scenario")
    demo_mode = st.toggle("Demo mode (cached data)", value=True)
    scenario = st.selectbox(
        "Scenario",
        ["Auto-detect", "Flood demo (Iowa)", "Drought demo (Horn of Africa)", "Normal demo (Iowa)"],
        index=0,
    )

    scenario_to_name = {
        "Auto-detect": None,
        "Flood demo (Iowa)": "flood",
        "Drought demo (Horn of Africa)": "drought",
        "Normal demo (Iowa)": "normal",
    }
    demo_name = scenario_to_name[scenario]

    generate = st.button("Generate recovery plan", type="primary")

# --- Main ---
if generate or "pier_result" not in st.session_state:
    if generate:
        try:
            result = run_pier(
                lat=float(lat),
                lon=float(lon),
                current_date=current_date_str,
                demo_mode=demo_mode,
                demo_name=demo_name,
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
        rp = result["recovery_plan"]
        er = result["event_result"]

        # Map
        st.subheader("\U0001F4CD Field Location")
        render_map(float(lat), float(lon), er.event_type, er.confidence)

        # Recovery plan card
        render_recovery_plan_card(result["plan_text"], rp)

else:
    st.info("Enter field location and click **Generate recovery plan**.")
