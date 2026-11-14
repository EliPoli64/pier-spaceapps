"""UI components for PIER Streamlit app: Folium map, recovery-plan card, cache badge."""
from __future__ import annotations

import folium
from folium import IFrame
import streamlit as st
from streamlit.components.v1 import html as st_html

EVENT_COLORS = {"flood": "blue", "drought": "orange", "none": "green"}


def event_marker_color(event_type: str) -> str:
    return EVENT_COLORS.get(event_type, "gray")


def render_map(lat: float, lon: float, event_type: str, event_confidence: float) -> None:
    """Render a Folium map centered on the field with an event-colored marker."""
    color = event_marker_color(event_type)
    popup_text = (
        f"Field location<br>"
        f"Event: {event_type}<br>"
        f"Detection confidence: {event_confidence:.0%}"
    )
    m = folium.Map(location=[lat, lon], zoom_start=8, tiles="OpenStreetMap")
    folium.Marker(
        [lat, lon],
        popup=folium.Popup(popup_text, max_width=250),
        icon=folium.Icon(color=color, icon="info-sign"),
    ).add_to(m)
    folium.CircleMarker(
        [lat, lon],
        radius=10,
        color=color,
        fill=True,
        fill_opacity=0.6,
    ).add_to(m)

    # Render as HTML string to avoid streamlit-folium dependency
    m_html = m._repr_html_()
    st_html(m_html, height=400)


def render_cache_badge(demo_mode: bool) -> None:
    """Render a badge indicating demo (cached) vs live (production) mode."""
    if demo_mode:
        st.markdown(
            '<span style="background:#e7f3fe; border:1px solid #2196f3; '
            'border-radius:4px; padding:4px 8px; font-size:0.85em; color:#0c5460;">'
            '\u25cf Demo mode — data cached (no live Earthdata call)</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span style="background:#fff3e0; border:1px solid #ff9800; '
            'border-radius:4px; padding:4px 8px; font-size:0.85em; color:#8a5a00;">'
            '\u25cf Live NASA data (production path)</span>',
            unsafe_allow_html=True,
        )


def render_recovery_plan_card(plan_text: str, recovery_plan) -> None:
    """Render the recovery plan as a bordered card."""
    st.markdown("---")
    st.subheader("\U0001F6E1 Recovery Plan")

    # Cache badge
    render_cache_badge(getattr(recovery_plan, "demo_mode", True))

    # Event + confidence (BR-6 separate lines)
    st.markdown(f"**Event:** {recovery_plan.event_type}")
    st.markdown(f"**Detection confidence:** {recovery_plan.event_confidence:.0%}")
    st.markdown(f"**Rescue confidence:** {recovery_plan.rescue_confidence:.0%} (GDD margin)")

    # GDD window
    st.markdown("**GDD Window:**")
    st.markdown(f"- Accumulated: {recovery_plan.gdd_accumulated:.0f}")
    st.markdown(f"- Remaining to frost ({recovery_plan.frost_date}): {recovery_plan.gdd_remaining:.0f}")
    st.markdown("- Safety margin: 20% applied")

    # Recommendations
    st.markdown("**Recommendations:**")
    if recovery_plan.fallback:
        st.error("\u26a0 **BR-5 Fallback:** No crop fits the window. Cover crop recommended.")
        st.markdown("- Cereal rye (cover crop): fast-establishing soil protection")
        st.markdown("**The season's cash crop is lost; soil protection only.**")
    else:
        for c in recovery_plan.crops:
            st.markdown(
                f"- **{c.crop}**: plant by {c.plant_by_date} "
                f"({c.days_until_deadline} days), "
                f"GDD {c.gdd_requirement:.0f}, confidence {c.rescue_confidence:.0%}"
            )

    st.caption("Typical GDD values — local calibration required.")
    st.markdown("```")
    st.markdown(plan_text)
    st.markdown("```")
