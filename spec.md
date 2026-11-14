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
| Data fidelity | Baseline climatology | Baseline climatology | 10-yr percentile baselines | Baseline climatology |
| Agent intelligence | — | — | Conformal confidence, analog search | — |
| Decision depth | Rotation sequencing | — | Rescue → next-season rotation | Multi-season N credit |
| Operational resilience | API + monitoring | API + monitoring | FastAPI + Redis + drift alerts | API + monitoring |
| UX / field readiness | Mobile PWA | Mobile PWA | Mobile PWA, SMS fallback | Mobile PWA |


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
| Soil texture & FC-WP | SoilGrids / ISRIC + user input | `location, texture_class, field_capacity_mm, wilting_point_mm` | Water-stress bounds, irrigation screening |
| OpenET ETa | OpenET API | `date, eta_mm` | Actual evapotranspiration for water-shortage context |
| SMAP soil moisture | SMAP / GES DISC | `date, soil_moisture_vol_pct` | Root-zone moisture for drought severity |
| Market prices | Local market API | `crop, currency, price_per_unit, date` | Dollar savings estimate |
| Historical analogs | Derived from IMERG/POWER archive | `event_type, location, year, matched_crops, outcome` | Analog search, confidence calibration |
| Conformal confidence set | Derived from validation | `crop, event_type, gdd_remaining, calibrated_confidence` | Calibrated confidence intervals |

**Crop database fields and business values**:

| Crop | Waterlogging tolerance | Drought tolerance | Days to maturity | GDD base | Typical GDD to maturity |
|---|---|---|---|---|---|
| Sorghum | Medium | High | 90–120 | 10°C | 1400–1800 |
| Millet | Low | High | 60–90 | 10°C | 1000–1400 |
| Buckwheat | Low | Medium | 70–90 | 5°C | 800–1100 |
| Cowpea | Medium | High | 60–90 | 10°C | 900–1300 |
| Cereal rye (cover) | High | Medium | 60–90 (biomass) | 0°C | 600–900 |

**Extended crop attributes (post-MVP)**:

| Attribute | Purpose |
|---|---|
| N_fixation_kg_ha | N credit contribution (links to Spec 4) |
| residue_cover_pct | Soil protection rating (links to declining soil health) |
| heat_stress_tmax_c | Threshold above which maturity is penalized |
| market_value_usd_ton | Dollar savings calculation |
| seed_availability_regional | Whether seed is obtainable locally in time |
| irrigation_requirement_mm | Water need for water-shortage screening |

## 4. Tech Stack

| Layer | Choice |
|---|---|
| Agent orchestration | Python tool-calling loop (MVP) → LangGraph / custom reasoning agent (post-MVP) |
| IMERG access | `imergpy` (MVP) → production ETL with retry/backoff, cookie refresh, Redis cache (post-MVP) |
| Event detection | Rule-based threshold on IMERG daily rainfall anomaly (MVP) → conformal-calibrated confidence (post-MVP) |
| GDD model | `GDD = max(0, (Tmax+Tmin)/2 − Tbase)` per crop (MVP) → per-region TBASE + heat-stress penalty (post-MVP) |
| Crop filtering | `pandas` query on the rescue-crop CSV (MVP) → weighted multi-criteria scoring with farmer priorities (post-MVP) |
| Frontend | Streamlit with a map overlay (Folium) and a recovery-plan card (MVP) → mobile PWA + SMS fallback (post-MVP) |
| API | None (MVP) → FastAPI with `/detect`, `/recommend`, `/plan` endpoints (post-MVP) |
| Cache | Local CSV (MVP demo) → Redis cache with invalidation on new IMERG/POWER overpasses (post-MVP) |
| Monitoring | None (MVP) → drift detection, staleness alerts, request tracing (post-MVP) |

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

**BR-7. Confidence is calibrated, not heuristic.**
Event detection and rescue recommendation confidence must be calibrated against historical validation data (conformal prediction or reliability plots). "80% confidence" means the outcome occurs ~80% of the time in similar cases.

**BR-8. Explanations are required for every exclusion.**
When a crop is filtered out, the agent must state the reason (e.g., "Buckwheat excluded: Low waterlogging tolerance for this flood event" or "Sorghum excluded: needs 1800 GDD, only 1200 remain").

**BR-9. Rescue → rotation linkage.**
After recommending a rescue crop, the agent must suggest the next season's crop based on what the rescue crop leaves behind (N fixation from cowpea, residue cover from rye, etc.), linking to Spec 4 (N credit) and Spec 1 (water budget).

**BR-10. Farmer priorities re-rank.**
A weighting slider (soil protection vs. salvage revenue vs. water conservation) re-ranks eligible crops by a composite score, not just latest plant-by date.

**BR-11. Dollar savings estimate.**
Each recommendation includes an estimated dollar value (rescued crop revenue vs. total loss) using local market prices, where available.

**BR-12. Multi-season rotation output.**
The agent outputs not just the immediate rescue crop but a short rotation sequence (rescue → main → cover) with cumulative soil-health scoring.

## 6. Agent Architecture and Tool Definitions

| Tool | Input | Output | Notes |
|---|---|---|---|
| `detect_event` | lat, lon, recent date range, historical IMERG baseline | `event_type, severity, confidence` | BR-1, BR-7 |
| `fetch_power_gdd` | lat, lon, season start, current date | `GDD_accumulated, GDD_remaining, frost_date` | POWER |
| `filter_rescue_crops` | event_type, GDD_remaining, current_date, farmer_weights | ranked crop list with plant-by dates + exclusion reasons | BR-2, BR-3, BR-4, BR-8, BR-10 |
| `generate_recovery_plan` | filtered crops + caveats | natural-language plan | BR-5, BR-6, BR-11 |
| `lookup_soil` | lat, lon | `texture_class, field_capacity_mm, wilting_point_mm` | SoilGrids/ISRIC + user input |
| `fetch_openet_eta` | lat, lon, date range | `date, eta_mm` | Actual evapotranspiration |
| `fetch_smap_moisture` | lat, lon, date range | `date, soil_moisture_vol_pct` | Root-zone moisture |
| `fetch_market_price` | crop, region, date | `price_per_unit, currency` | Dollar savings (BR-11) |
| `search_analogs` | event_type, location, gdd_remaining | `historical_matches, calibrated_confidence` | BR-7 confidence calibration |
| `plan_rotation` | rescue_crop, next_season_constraints | `rotation_sequence, soil_health_score` | BR-9, BR-12 |
| `generate_recovery_plan` (extended) | all above + rotation | multi-season plan text | BR-12 |

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

**Post-MVP success metrics (v1.1+)**:

- Confidence calibration: reliability plot shows predicted confidence within ±5% of observed frequency across ≥100 validation cases.
- Explanation coverage: 100% of excluded crops include an explicit reason (BR-8).
- Rotation linkage: every rescue-crop recommendation includes a next-season crop suggestion (BR-9).
- Farmer priority re-ranking: changing the weight slider produces a visibly different crop order (BR-10).
- Dollar savings: at least one demo recommendation includes a market-price-based estimate (BR-11).
- Multi-season output: the agent produces a 3-crop rotation sequence with soil-health score (BR-12).
- API uptime: FastAPI endpoints respond with p95 < 500ms on cached data.
- Mobile PWA: loads and functions on a 3G connection with offline cache.

## 11. Post-MVP Roadmap

| Version | Focus | Key additions |
|---|---|---|
| **v1.1** | Data fidelity & agent intelligence | Real ingestion pipeline (imergpy ETL + retry), per-region TBASE, heat-stress penalty, SoilGrids/ISRIC soil lookup, OpenET ETa, SMAP moisture, conformal confidence calibration |
| **v1.2** | Decision depth | Farmer priority weighting slider, dollar savings estimate, rescue → next-season rotation, market price lookup, historical analog search |
| **v1.3** | Operational resilience | FastAPI API layer, Redis cache with invalidation, drift detection & staleness alerts, request tracing, audit log |
| **v2.0** | Field readiness & scale | Mobile PWA + SMS fallback, multi-region support (Southern Hemisphere seasons), heat-wave rescue events, offline mode, multi-language UI |

