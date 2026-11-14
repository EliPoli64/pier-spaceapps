"""UI components for PIER Streamlit app: Folium map, recovery-plan card, badges, tables."""
from __future__ import annotations

from typing import Any

import folium
import streamlit as st
from streamlit.components.v1 import html as st_html

from piper_agent.ui.i18n import t

EVENT_COLORS = {"flood": "blue", "drought": "orange", "none": "green"}

FUENTE_LABELS = {
    "synthetic": "fuente_synthetic",
    "synthetic_cache": "fuente_synthetic",
    "sintetico": "fuente_synthetic",
    "cache": "fuente_synthetic",
    "nasa_power": "fuente_power",
    "power": "fuente_power",
    "nasa_power_imerg": "fuente_power_imerg",
    "nasa_power+imerg": "fuente_power_imerg",
    "power+imerg": "fuente_power_imerg",
    "power_imerg": "fuente_power_imerg",
}


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

    m_html = m._repr_html_()
    st_html(m_html, height=400)


def render_cache_badge(demo_mode: bool, lang: str = "en") -> None:
    """Render a badge indicating demo (cached) vs live (production) mode."""
    if demo_mode:
        label = t(lang, "demo_badge")
        st.markdown(
            '<span style="background:#e7f3fe; border:1px solid #2196f3; '
            'border-radius:4px; padding:4px 8px; font-size:0.85em; color:#0c5460;">'
            f"\u25cf {label}</span>",
            unsafe_allow_html=True,
        )
    else:
        label = t(lang, "live_badge")
        st.markdown(
            '<span style="background:#fff3e0; border:1px solid #ff9800; '
            'border-radius:4px; padding:4px 8px; font-size:0.85em; color:#8a5a00;">'
            f"\u25cf {label}</span>",
            unsafe_allow_html=True,
        )


def render_fuente_datos_badge(
    fuente_datos: str | None,
    *,
    demo_mode: bool = True,
    lang: str = "en",
) -> None:
    """M7: data-source badge from agent `fuente_datos` (with demo fallback)."""
    raw = (fuente_datos or ("synthetic" if demo_mode else "unknown")).strip().lower()
    key = FUENTE_LABELS.get(raw)
    label = t(lang, key) if key else (fuente_datos or raw)
    st.markdown(
        '<span style="background:#e8f5e9; border:1px solid #4caf50; '
        'border-radius:4px; padding:4px 8px; font-size:0.85em; color:#1b5e20;">'
        f"\u25cf {label}</span>",
        unsafe_allow_html=True,
    )


def _attr(obj: Any, *names: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        for n in names:
            if n in obj and obj[n] is not None:
                return obj[n]
        return default
    for n in names:
        if hasattr(obj, n):
            val = getattr(obj, n)
            if val is not None:
                return val
    return default


def first_present(result: dict[str, Any], *keys: str) -> Any:
    """Return the first non-None value among result keys (contract aliases)."""
    for k in keys:
        if k in result and result[k] is not None:
            return result[k]
    return None


def render_recovery_plan_card(
    plan_text: str,
    recovery_plan,
    *,
    demo_mode: bool = True,
    fuente_datos: str | None = None,
    lang: str = "en",
) -> None:
    """Render the recovery plan with three visual states (crops / BR-5 / no event).

    M12/M13: demo vs live badges; when live, also show fuente_datos + Earthdata footer.
    """
    st.markdown("---")
    st.subheader(f"\U0001F6E1 {t(lang, 'recovery_plan')}")

    # M12: Synthetic cache vs Live NASA production-path badge
    render_cache_badge(demo_mode, lang=lang)
    # M13: when production path, also show fuente_datos in the plan card
    if not demo_mode:
        render_fuente_datos_badge(fuente_datos, demo_mode=False, lang=lang)

    st.markdown(f"**{t(lang, 'event')}:** {recovery_plan.event_type}")
    st.markdown(
        f"**{t(lang, 'detection_confidence')}:** {recovery_plan.event_confidence:.0%}"
    )
    st.markdown(
        f"**{t(lang, 'rescue_confidence')}:** {recovery_plan.rescue_confidence:.0%} (GDD margin)"
    )

    st.markdown(f"**{t(lang, 'gdd_window')}:**")
    st.markdown(f"- {t(lang, 'gdd_accumulated')}: {recovery_plan.gdd_accumulated:.0f}")
    st.markdown(
        f"- {t(lang, 'gdd_remaining')} ({recovery_plan.frost_date}): "
        f"{recovery_plan.gdd_remaining:.0f}"
    )
    st.markdown(f"- {t(lang, 'safety_margin')}")

    st.markdown(f"**{t(lang, 'recommendations')}:**")
    crops = list(recovery_plan.crops or [])
    if recovery_plan.fallback:
        st.error(f"\u26a0 **{t(lang, 'fallback_title')}**")
        st.markdown(f"- {t(lang, 'fallback_rye')}")
        st.markdown(f"**{t(lang, 'fallback_cash_lost')}**")
    elif crops:
        for c in crops:
            st.markdown(
                f"- **{_attr(c, 'crop')}**: plant by {_attr(c, 'plant_by_date')} "
                f"({_attr(c, 'days_until_deadline')} days), "
                f"GDD {_attr(c, 'gdd_requirement', default=0):.0f}, "
                f"confidence {_attr(c, 'rescue_confidence', default=0):.0%}"
            )
    else:
        st.info(t(lang, "no_event"))

    st.caption(t(lang, "gdd_caption"))
    st.code(plan_text or recovery_plan.plan_text or "", language=None)
    # M13: production-path transparency footer
    if not demo_mode:
        st.caption(t(lang, "live_footer"))


def render_crop_table(crops: list, lang: str = "en") -> None:
    """M3: crop table with deadline, days left, GDD margin, confidence, composite score."""
    if not crops:
        return
    st.subheader(t(lang, "crop_table"))
    rows = []
    for c in crops:
        margin = _attr(c, "margin_pct", "gdd_margin")
        if margin is None:
            margin_str = "—"
        elif isinstance(margin, float) and abs(margin) <= 1.5:
            margin_str = f"{margin:.0%}"
        else:
            margin_str = f"{margin}"
        conf = _attr(c, "rescue_confidence", "confidence", default=None)
        conf_str = f"{conf:.0%}" if isinstance(conf, (int, float)) else "—"
        score = _attr(c, "composite_score")
        score_str = f"{score:.2f}" if isinstance(score, (int, float)) else "—"
        rows.append(
            {
                t(lang, "col_crop"): _attr(c, "crop", default="—"),
                t(lang, "col_deadline"): _attr(c, "plant_by_date", "deadline", default="—"),
                t(lang, "col_days_left"): _attr(c, "days_until_deadline", "days_left", default="—"),
                t(lang, "col_gdd_margin"): margin_str,
                t(lang, "col_confidence"): conf_str,
                t(lang, "col_composite"): score_str,
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_excluded_crops(exclusions: Any, lang: str = "en") -> None:
    """M4: excluded crops and why (only if list non-empty)."""
    if not exclusions:
        return
    items = exclusions if isinstance(exclusions, list) else [exclusions]
    if not items:
        return
    st.subheader(t(lang, "excluded_title"))
    for item in items:
        if isinstance(item, dict):
            crop = item.get("crop") or item.get("name") or ""
            reason = item.get("reason") or item.get("why") or item.get("explanation") or str(item)
            st.markdown(f"- **{crop}**: {reason}" if crop else f"- {reason}")
        else:
            st.markdown(f"- {item}")


def render_rotation(rotacion: Any, lang: str = "en") -> None:
    """M5: suggested rotation rescue → main → cover + soil-health / N."""
    if not rotacion or not isinstance(rotacion, dict):
        return
    seq = rotacion.get("rotation_sequence") or rotacion.get("sequence")
    if not seq and not any(
        k in rotacion for k in ("rescue", "main", "cover", "soil_health_score")
    ):
        return
    st.subheader(t(lang, "rotation_title"))
    if seq and len(seq) >= 3:
        st.markdown(
            f"**{t(lang, 'rotation_rescue')}** → **{t(lang, 'rotation_main')}** → "
            f"**{t(lang, 'rotation_cover')}**: {seq[0]} → {seq[1]} → {seq[2]}"
        )
    else:
        rescue = rotacion.get("rescue") or rotacion.get("rescue_crop")
        main = rotacion.get("main") or rotacion.get("main_crop")
        cover = rotacion.get("cover") or rotacion.get("cover_crop")
        if rescue or main or cover:
            st.markdown(
                f"**{t(lang, 'rotation_rescue')}** → **{t(lang, 'rotation_main')}** → "
                f"**{t(lang, 'rotation_cover')}**: {rescue} → {main} → {cover}"
            )
    soil = rotacion.get("soil_health_score") or rotacion.get("soil_health")
    n_fix = rotacion.get("n_fixation_total_kg_ha") or rotacion.get("fixed_nitrogen")
    if soil is not None:
        st.markdown(f"- **{t(lang, 'soil_health')}:** {soil}")
    if n_fix is not None:
        st.markdown(f"- **{t(lang, 'n_fixation')}:** {n_fix}")
    rationale = rotacion.get("rationale")
    if rationale:
        st.caption(str(rationale))


def render_savings(ahorro: Any, lang: str = "en") -> None:
    """M6: estimated savings USD/ha."""
    if ahorro is None:
        return
    st.subheader(t(lang, "savings_title"))
    if isinstance(ahorro, dict):
        value = (
            ahorro.get("estimated_savings_usd_per_ha")
            or ahorro.get("usd_per_ha")
            or ahorro.get("savings_usd_ha")
            or ahorro.get("value")
        )
        if value is not None:
            st.markdown(f"**{value}** {t(lang, 'usd_per_ha')}")
        note = ahorro.get("note")
        if note:
            st.caption(str(note))
        else:
            st.caption(t(lang, "savings_caption"))
    else:
        st.markdown(f"**{ahorro}** {t(lang, 'usd_per_ha')}")
        st.caption(t(lang, "savings_caption"))
