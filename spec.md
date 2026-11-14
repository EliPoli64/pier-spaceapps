# Cross-Cutting Context: The Field Shift Challenge

**Original challenge statement**: Farmers around the world navigate shifting temperatures, changing rainfall patterns, water shortages, extreme weather, and declining soil health. These pressures make it difficult to choose crop rotations that protect fields, conserve water, and support long-term resilience. The challenge is to create a decision-support tool that uses NASA Earth observations along with local soil information, crop characteristics, and farmer priorities to help farmers explore rotation strategies that could strengthen soil health and adapt their farms to changing conditions.

Every design decision in the four specs below is traceable to one or more of the challenge's pressure categories:

| Challenge pressure | Spec 1 (Water Budget) | Spec 2 (Irrigation Signal) | Spec 3 (Extreme Weather) | Spec 4 (N Credit) |
|---|---|---|---|---|
| Shifting temperatures | POWER GDD | — | POWER GDD window | POWER frost/GDD window |
| Changing rainfall | POWER P, OpenET ET | POWER P, OpenET ET | IMERG + POWER | POWER GDD |
| Water shortages | OpenET + POWER water budget | SMAP − OpenET residual | Drought detection | — |
| Extreme weather | — | — | IMERG flood/drought | — |
| Declining soil health | Rotation water demand | Irrigation accounting | Rescue-crop soil cover | Cover-crop N cycling |
| Farmer priorities | Weight slider | Alert threshold | Rescue-crop ranking | Dollar savings |
| Local soil information | User soil texture / FC-WP | Soil texture for storage bounds | Optional | C:N ratio for availability factor |


# PIER: POWER + IMERG Extreme-weather Recovery

Extreme weather recovery rotation planner for farmers.

## 1. Context and Problem Framing

**The specific problem**: An extreme event (flood or drought) has just hit. The farmer's planned crop is no longer viable. What can be planted *now* that will stabilize the soil and fit the remaining growing-season window?

**What the agent does**: Detects the event from IMERG rainfall anomaly, computes the remaining thermal-time window from POWER GDD, and recommends rescue crops matched to the event type and remaining window.

**Why this combo is powerful**: It addresses the challenge's “extreme weather” and “declining soil health” pressures simultaneously — the rescue crop is both a salvage decision and a soil-protection decision.

## 2. API Contracts in Detail

### 2.1 IMERG via `imergpy`

**What `imergpy` is**: A Python package and local web interface for downloading NASA GPM IMERG precipitation data through NASA Earthdata / GES DISC .

**Access mechanism**: `imergpy` uses the **GES DISC OTF (on-the-fly) subset download service with `wget` and Earthdata cookies** . It does not have a separate REST API; it wraps the OTF service.

**Authentication**: NASA Earthdata username/password. The Earthdata account must have the **GES DISC application authorized**.

**Python API** :
```python
import imergpy
excel_path, records = imergpy.get_precipitation(
    lat=6.9271, lon=79.8612,
    start_date="2025-11-25", end_date="2025-12-25",
    freq="daily"   # daily, monthly, or half-hourly
)
```

**Output**: An Excel file path and a records object containing daily rainfall values.

**Temporal resolutions**: half-hourly, daily, monthly .

**Limitation**: IMERG itself has no native REST API. All access goes through the GES DISC OTF subset service .

### 2.2 NASA POWER Daily Point API

Same contract as Spec 1, Section 2.2. For this agent, the critical parameters are `T2M_MAX` and `T2M_MIN` (GDD) plus `PRECTOTCORR` (drought context) .

## 3. Data Needed

| Layer | Source | Schema | Purpose |
|---|---|---|---|
| Field location | Lat/lon | — | IMERG and POWER point queries |
| Historical IMERG daily rainfall | `imergpy` | `date, precipitation_mm` | Event detection baseline |
| POWER daily temperature | POWER AG | `date, T2M_MAX, T2M_MIN` | GDD accumulated and remaining |
| POWER climatological frost date | POWER (derived from 10+ years) | `date` | End of growing window |
| Rescue-crop database | Built-in CSV | `crop, waterlogging_tolerance, drought_tolerance, days_to_maturity, min_GDD, planting_window_start, planting_window_end` | Filtering |
| Event type | Derived | `flood` / `drought` / `none` | Rescue-crop filter |

**Crop database fields and business values**:

| Crop | Waterlogging tolerance | Drought tolerance | Days to maturity | GDD base | Typical GDD to maturity |
|---|---|---|---|---|---|
| Sorghum | Medium | High | 90–120 | 10°C | 1400–1800 |
| Millet | Low | High | 60–90 | 10°C | 1000–1400 |
| Buckwheat | Low | Medium | 70–90 | 5°C | 800–1100 |
| Cowpea | Medium | High | 60–90 | 10°C | 900–1300 |
| Cereal rye (cover) | High | Medium | 60–90 (biomass) | 0°C | 600–900 |

## 4. Tech Stack

| Layer | Choice |
|---|---|
| Agent orchestration | Python tool-calling loop |
| IMERG access | `imergpy`  |
| Event detection | Rule-based threshold on IMERG daily rainfall anomaly |
| GDD model | `GDD = max(0, (Tmax+Tmin)/2 − Tbase)` per crop |
| Crop filtering | `pandas` query on the rescue-crop CSV |
| Frontend | Streamlit with a map overlay (Folium) and a recovery-plan card |

## 5. Business Rules

**BR-1. Event detection uses an anomaly threshold, not an absolute threshold.**
A flood is flagged when 3-day cumulative IMERG rainfall exceeds the **95th percentile of the 10-year daily distribution** for that location, *or* exceeds 100 mm in 72 hours, whichever is lower. A drought is flagged when 30-day cumulative rainfall is below the **10th percentile** of the 10-year distribution. Absolute thresholds alone fail in arid and humid regions.

**BR-2. Event type drives the rescue-crop filter — never both filters at once.**
If the event is a flood, filter for waterlogging tolerance ≥ Medium and exclude crops with Low waterlogging tolerance. If the event is a drought, filter for drought tolerance ≥ Medium. Do not apply both filters, because no rescue crop is high in both in the demo database.

**BR-3. The remaining window is GDD-based, not calendar-based.**
`remaining_GDD = GDD_to_climatological_frost − GDD_accumulated_to_date`. A rescue crop is eligible only if `days_to_maturity_GDD ≤ remaining_GDD × 0.8` (20% safety margin for a late planting and slower emergence).

**BR-4. The agent must state the planting deadline explicitly.**
`plant_by_date = current_date + (remaining_GDD − crop_GDD_requirement) / average_daily_GDD`. The agent shows this date for each recommended crop and ranks by latest feasible plant-by date first.

**BR-5. If no crop fits the window, the agent recommends a cover crop or fallow — never a cash crop that will not mature.**
The fallback recommendation is a fast-establishing cover (e.g., cereal rye or buckwheat) to protect the soil, with an explicit statement that the season's cash crop is lost.

**BR-6. Event detection and rescue recommendation are separate agent steps with separate confidence.**
The event detection confidence (based on anomaly magnitude) is reported separately from the rescue recommendation confidence (based on GDD margin). A high-confidence flood does not imply high-confidence rescue options.

## 6. Agent Architecture and Tool Definitions

| Tool | Input | Output | Notes |
|---|---|---|---|
| `detect_event` | lat, lon, recent date range, historical IMERG baseline | `event_type, severity, confidence` | BR-1 |
| `fetch_power_gdd` | lat, lon, season start, current date | `GDD_accumulated, GDD_remaining, frost_date` | POWER |
| `filter_rescue_crops` | event_type, GDD_remaining, current_date | ranked crop list with plant-by dates | BR-2, BR-3, BR-4 |
| `generate_recovery_plan` | filtered crops + caveats | natural-language plan | BR-5, BR-6 |

## 7. Phased Implementation Plan

**Phase 0 — Pre-hack (3–4 hours)**
1. Confirm Earthdata login and GES DISC authorization.
2. Run `imergpy.get_precipitation` for one location and confirm the Excel output.
3. Run a POWER point query for 10 years and compute the 95th/10th percentile baselines.
4. Cache both.

**Phase 1 — Event detection (hours 0–8)**
1. Implement `detect_event` with BR-1.
2. Test on two known events (one flood, one drought) and one normal period.
3. Validate that the normal period returns `event_type = none`.

**Phase 2 — GDD and crop filter (hours 8–16)**
1. Implement `fetch_power_gdd` with frost-date derivation.
2. Build the rescue-crop CSV with the fields in Section 3.
3. Implement `filter_rescue_crops` with BR-2 through BR-4.
4. Validate the fallback path (BR-5) with a late-season date.

**Phase 3 — Agent and UI (hours 16–24)**
1. Wrap tools and implement BR-6 (separate confidences).
2. Build the map + recovery-plan card.
3. Pre-load one flood demo and one drought demo; cache IMERG and POWER responses.

## 8. Demo Scope

Two scenarios: **a flood event** (e.g., a known heavy-rain date in the US Midwest) and **a drought event** (e.g., a known dry spell in the Horn of Africa or South Asia). Pre-fetch IMERG data so the demo does not depend on live Earthdata. Show the agent detecting the event, computing the remaining GDD window, recommending 2–3 rescue crops with plant-by dates, and falling back to a cover crop when the window is too short. **Label the live IMERG connection as a production path and use cached data for the stage.**

## 9. Risk Register and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Earthdata / GES DISC auth not ready | Medium | High | Confirm authorization 48h early; cache IMERG Excel |
| `imergpy` install fails (wget dependency) | Low | Medium | Test install in Phase 0; containerize the environment |
| Anomaly threshold misfires on demo date | Medium | High | Pre-validate both demo events; hardcode the event date if necessary and disclose |
| No rescue crop fits the window | Medium | Low | This is a feature — BR-5 produces a soil-protection recommendation |
| Crop GDD values are regional and wrong for the demo | Medium | Medium | Use region-specific GDD ranges; label as “typical values, local calibration required” |

## 10. Success Metrics

- Event detection correctly classifies the flood demo and the drought demo, and returns `none` for a normal period.
- At least **2 eligible rescue crops** are returned for each demo event.
- The fallback path (cover crop) triggers when the window is too short, and the agent states the cash crop is lost.
- All IMERG responses are served from cache during the demo (verified by network log).
