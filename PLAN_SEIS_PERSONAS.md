# Plan for 6 People — Isolated Branches, Code-Only Implementation

**Project:** PIER (POWER + IMERG Extreme-weather Recovery) — Spec 3  
**Deadline:** Sunday, November 15, 2026, 23:59  
**Strategy:** 6 developers work completely isolated, each on their own branch. No file overlaps. Integration happens only through explicit contract points (the `run_pier` signature and demo packet keys). This file fuses `PLAN_PERSON_A.md`, `PLAN_PERSON_B.md`, and `quehacer.md`, removing all UI/video/demo concerns and keeping only code implementation.

---

## Branch Assignments & Isolation Guarantees

| Person | Branch | Owns (file paths) | Does NOT touch |
|---|---|---|---|
| **Erik** | `feat/datos-cache` | `piper_agent/data/**`, `data/generate_cache.py`, `data/cache_loader.py`, `data/baselines/`, `data/ingestion/` | All of `piper_agent/api/`, `piper_agent/ui/`, `piper_agent/monitoring/`, `docs/`, `README.md` |
| **Alina** | `feat/logica-herramientas` | `piper_agent/tools/**`, `piper_agent/contracts.py`, `piper_agent/config.py`, `piper_agent/agent.py` (orchestration only) | All of `piper_agent/data/`, `piper_agent/ui/`, `piper_agent/api/` |
| **Neithan** | `feat/gdd-climate` | `piper_agent/tools/fetch_power_gdd.py`, `piper_agent/data/baselines/`, `piper_agent/config.py` (climate section) | All of `piper_agent/ui/`, `piper_agent/api/`, `piper_agent/data/ingestion/` (except what Erik provides) |
| **Danny** | `feat/api-backend` | `piper_agent/api/**`, `piper_agent/api/main.py`, `piper_agent/api/routes.py`, contracts consumption | All of `piper_agent/data/`, `piper_agent/tools/`, `piper_agent/ui/`, `piper_agent/monitoring/` |
| **Matias** | `feat/ui-pwa` | `piper_agent/ui/**`, `piper_agent/ui/streamlit_app.py`, `piper_agent/ui/components.py`, `piper_agent/ui/sms_gateway.py`, PWA files | All of `piper_agent/data/`, `piper_agent/tools/`, `piper_agent/api/` (except REST contracts) |
| **Elias** | `feat/docs-entrega` | `docs/**` (excluding AI_USAGE_DECLARATION.md and PROMPT_REGISTRY.md which belong to A/B), `requirements.txt`, `.gitattributes`, `.env.example`, monitoring setup | All of `piper_agent/`, `data/`, `ui/`, `api/`;

Each person works in isolation. Integration happens only through:
- `run_pier(lat, lon, date, demo_mode, demo_name, pesos_agricultor, rendimiento_t_ha) -> dict` (stable contract)
- `load_demo_packet(demo_name) -> dict` (stable contract)
- New keys added by A‑team are read with `.get()` by B‑team

---

## Person A Team (Data, Logic, Tools)

### Erik — `feat/datos-cache` (Cache, Ingestion, Baselines, Soil, OpenET, SMAP)

**P0 Code Implementation Tasks:**

| # | Task | Why/Notes |
|---|---|---|
| E1 | Refactor `data/generate_cache.py` under `if __name__ == "__main__":`; remove global `DEMOS_FROST_LAT`; add `season_end` field to all demo JSON packets (flood, drought, normal) | Guarantees frost logic per scenario; needed by GDD window |
| E2 | Implement `data/cache_loader.py`: `load_demo_packet(name) -> dict`, `get_ruta_cultivos() -> Path`, `get_fuente_datos(name) -> str`; cache-first pattern: read from `data/cache/` if present, otherwise compute synthetic | Common entry point for B‑team; makes baseline data accessible |
| E3 | Add `data/ingestion/imerg_etl.py`: retry‑wrapped IMERG fetch (or POWER `PRECTOTCORR` stand‑in); write CSV/JSON same format as today; declare `fuente_datos` as `"sintetico"` or `"nasa_power"` or `"nasa_power+imerg"` | Real NASA data path without Earthdata credentials in demo |
| E4 | Add `data/baselines/southern_hemisphere.json` with frost‑month mappings per latitude band; modify `fetch_power_gdd.py` to select Northern vs. Southern baseline based on `lat` sign | Multi‑hemisphere support (BR‑3 extension) |
| E5 | Implement `lookup_soil(lat, lon) -> dict` with soil texture, organic matter, water holding capacity; keep it offline‑first (no network in demo) | BR‑10 soil‑protection weight; needed by A4 and UI |
| E6 | Add `fetch_openet_eta(lat, lon, date_range) -> DataFrame[date, eta_mm]` (cache‑first: read `data/cache/openet/`; synthetic fallback with `"estimated"` badge) | BR‑11 water‑savings computation |
| E7 | Add `fetch_smap_moisture(lat, lon, date_range) -> DataFrame[date, soil_moisture_vol_pct]` (cache‑first) | Drought severity grading; BR‑7 analog calibration |

**P1 Code Fixes:**
- E8: Fix duplicate `CROP_TBASE` definition — single source in `config.py`; add crop‑specific bases (rye=0, buckwheat=5, sorghum=10, maize=8)
- E9: Use `planting_window_start/end` from rescue_crops.csv to exclude crops outside their window; add `planting_window` exclusion reason

**Branch isolation:** Erik never touches `piper_agent/api/`, `piper_agent/ui/`, or any template files. B‑team integrates via `cache_loader` exports.

---

### Alina — `feat/logica-herramientas` (Tools, Contracts, Agent Orchestration)

**P0 Code Implementation Tasks:**

| # | Task | Why/Notes |
|---|---|---|
| A1 | Refactor `tools/detect_event.py`: normal `none` branch confidence = distance to thresholds (`abs(cum30 - p10) / (p10 - p5)`); remove duplicated `import pandas as pd` | Fixes BR‑1 normal‑scenario confidence farce |
| A2 | In `tools/filter_rescue_crops.py`: early return `[]` when `event_type == "none"`; add `planting_window` exclusion check per crop | Ensures normal scenario shows no rescue crops; BR‑8 planting‑window |
| A3 | In `tools/generate_recovery_plan.py`: when `event_type == "none"`, set `fallback=False`, `crops=[]`, plan text = "No extreme event detected; normal planting plan stands"; add `exclusion_reasons` list to structured output | BR‑5 safety net; BR‑8 exclusions visible to UI |
| A4 | Wire `run_pier()` to receive `pesos_agricultor` and `rendimiento_t_ha` and pass them to `filter_rescue_crops` and `generate_recovery_plan`; fill new contract keys (`exclusiones`, `rotacion`, `ahorro`, `confianza_calibrada`, `suelo`, `ola_calor`, `fuente_datos`) | A‑team/B‑team contract interface |
| A5 | Add `compute_dollar_savings(crop, rendimiento_t_ha, precio_usd_ton) -> dict` with keys `usd_por_ha`, `revenue_lost_usd`, `net_savings_usd`; integrate into `generate_recovery_plan` output | BR‑11 concrete value |

**P1 Code Fixes:**
- A6: Add `heat_stress_tmax_c` usage — if recent `T2M_MAX` exceeds it, penalize rescue confidence by 10–20%
- A7: Revise confidence scale so it saturates below 100% in typical cases; add `n_analogos` to `confianza_calibrada`

**P2 Code Fixes:**
- A8: Implement `plan_rotation(rescue_crop, soil_dict) -> dict` with 3‑cycle (rescue → main → cover), soil‑health score, fixed‑nitrogen credit; avoid repeating rescue crop as final cover
- A9: Add `explain_exclusion(crop, reason) -> str` for UI tool‑tip text

**Branch isolation:** Alina never touches `piper_agent/ui/` or `piper_agent/api/`. Her tools are consumed by the API and CLI through the stable `run_pier` signature.

---

### Neithan — `feat/gdd-climate` (GDD, Frost Logic, Climate Baselines)

**P0 Code Implementation Tasks:**

| # | Task | Why/Notes |
|---|---|---|
| N1 | Modify `fetch_power_gdd.py`: if `abs(lat) < 23.5` no climatological frost; else compute first autumn frost date per hemisphere; store method used in `details` field (`"helada_climatologica"` or `"fin_temporada_lluvias"`) | BR‑3 frost logic; enables Southern‑hemisphere demos |
| N2 | Add `--hemisphere` CLI flag (default `auto` from lat sign) and `--season-start` / `--season-end` overrides; update Streamlit sidebar toggle | Usability for global farmers |
| N3 | Replace the "add 182 days" trick with proper hemisphere‑aware frost date lookup from `baselines/southern_hemisphere.json` | Correct GDD accumulation per season |

**P1 Code Fixes:**
- N4: Add `season_end` field to demo packets (flood, drought, normal); compute from baseline, not hard‑coded

**Branch isolation:** Neithan only touches `piper_agent/tools/fetch_power_gdd.py` and `piper_agent/data/baselines/`. Climate data stays within his branch.

---

## Person B Team (API, UI, PWA, Documentation)

### Danny — `feat/api-backend` (FastAPI, Routes, Contract Consumption)

**P0 Code Implementation Tasks:**

| # | Task | Why/Notes |
|---|---|---|
| D1 | Fix `POST /generate_plan`: accept `demo_name: str | None = None`; pass `pesos_agricultor` and `rendimiento_t_ha` to `run_pier`; serialize agent return keys (`exclusiones`, `rotacion`, `ahorro`, `fuente_datos`, `demo_mode`) into response JSON; remove duplicated computation | BR‑7 to BR‑12 visible in API; PWA badge needs `demo_mode` |
| D2 | Fix `/recommend_crops`: import `RUTA_CULTIVOS` from `cache_loader` (A‑team export); use absolute path via `Path(__file__).resolve().parent.parent / "data" / "rescue_crops.csv"` | Works outside repo root |
| D3 | Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` throughout | Python 3.11 compat |
| D4 | Add `alertas` field to `/generate_plan` response: list of validation warnings (e.g., "no crop fits GDD window", "live data fallback") | Monitoring/UX |
| D5 | Call `monitoring/drift.py.check()` on each plan and include `ultima_actualizacion` and `fuente_datos` in response | BR‑13 operational resilience |

**P1 Code Fixes:**
- D6: Add `pesos_agricultor` weighting to crop order in rotation computation (delegate to `plan_rotation` from A‑team)
- D7: Add `POST /simulate_sms` endpoint that calls `run_pier` with farmer‑type input and returns SMS‑length reply

**Branch isolation:** Danny only touches `piper_agent/api/`. He never touches `piper_agent/data/`, `piper_agent/tools/`, or `piper_agent/ui/`.

---

### Matias — `feat/ui-pwa` (Streamlit, Components, PWA, SMS Gateway)

**P0 Code Implementation Tasks:**

| # | Task | Why/Notes |
|---|---|---|
| M1 | Fix `ui/streamlit_app.py`: when scenario chosen, call `load_demo_packet` and fill lat/lon/date from packet (user can edit); pass `demo_mode` explicitly to `render_recovery_plan_card`; use `st.code(plan_text)` for single‑block rendering; three visual states: with crops, fallback (BR‑5), no event | BR‑1..BR‑6 visible; demo works out‑of‑the‑box |
| M2 | Add sidebar sliders: soil protection, salvage revenue, water conservation weights (BR‑10); expected yield (t/ha) field | A‑team pesos integration |
| M3 | Add crop table with columns: crop, deadline, days left, GDD margin, confidence, composite score | BR‑8, BR‑7 visualization |
| M4 | Add "Excluded crops and why" section (BR‑8); appear only if `excluciones` list has items | exclusions visible |
| M5 | Add "Suggested rotation" section: rescue → main → cover, with soil‑health score and fixed‑nitrogen (BR‑9, BR‑12); appear only if `rotacion` dict has data | rotation visible |
| M6 | Add "Estimated savings" section (BR‑11) in USD/ha, noting estimate | dollar savings visible |
| M7 | Add data‑source badge based on `fuente_datos` from agent output: "Synthetic cache", "NASA POWER", or "NASA POWER+IMERG" | transparency |
| M8 | Add `piper_agent/ui/sms_gateway.py` with `handle_sms(message: str) -> str`: validate `lat,lon,date` format; call `run_pier`; return ≤160 char reply; fallback "Please send: lat,lon,date" on bad format | BR‑14 SMS fallback (P1) |

**P1 Code Fixes:**
- M9: Replace made‑up numbers in PWA fallback: store last real agent response in `localStorage`; show offline with label "last saved result"
- M10: Add language selector (Spanish/English) for user-facing text; UI strings in both languages

**P2 Code Fixes:**
- M11: Create PWA icons (`icon-192.png`, `icon-512.png`) and fix `index.html`, `manifest.json`, `sw.js` relative paths; mount PWA folder at `/pwa` via FastAPI `StaticFiles`

**Branch isolation:** Matias only touches `piper_agent/ui/` and PWA static files. API contracts consumed via `.get()`.

---

### Elias — `feat/docs-entrega` (Documentation, Environment, Git Ops)

**P0 Code Implementation Tasks:**

| # | Task | Why/Notes |
|---|---|---|
| E1 | Rewrite `README.md`: install guide, generate/download cache, CLI (`python -m piper_agent`), Streamlit (`streamlit run piper_agent/ui/streamlit_app.py`), API (`uvicorn piper_agent.api.main:app`), PWA, BR‑1 to BR‑12 table with file ownership (A vs B), real vs synthetic data flag | Common starting point for all 6 branches |
| E2 | Update `.gitattributes` with `* text=auto eol=lf` and commit; run `git add --renormalize .` | Prevents false merge diffs (Phase 0 from both original plans) |
| E3 | Update `.env.example` with all required vars: `PIER_DEMO_MODE`, `PIER_OPENET_API_KEY`, `PIER_REDIS_HOST`, `PIER_STALE_DATA_HOURS`, `PIER_LOW_CONFIDENCE`, `PIER_API_KEY` (placeholder) | All code reads these; previously missing |
| E4 | Add `docs/contratos.md`: stable contract between A‑team and B‑team (`run_pier` signature, contract keys, `.get()` usage) | Coordination between isolated branches |
| E5 | Add `docs/historico/` move for `plan.md`, `plandividido.md` (leave untouched; decide with A‑team) | Historical record |

**P1 Code Fixes:**
- E6: Add `monitoring/drift.py` import and check in API; call on each plan response; include drift alert in response
- E7: Ensure Python version consistency: `3.11` in `Dockerfile` and `AI_USAGE_DECLARATION.md` (both already 3.11; verify)

**P2 Code Fixes:**
- E8: Add demo SMS simulation command‑line script (uses `run_pier`; output formatted for SMS) — for Matias's `sms_gateway.py` testing

**Branch isolation:** Elias only touches `docs/`, `.gitattributes`, `.env.example`, `requirements.txt`, `Dockerfile`. Never touches `piper_agent/`.

---

## Integration Protocol (Happens Only at Merge Points)

1. **Each person works in their branch:** `feat/datos-cache`, `feat/logica-herramientas`, `feat/gdd-climate`, `feat/api-backend`, `feat/ui-pwa`, `feat/docs-entrega`
2. **Before each integration:** `git fetch origin && git rebase origin/master`
3. **Run full test suite:** `pytest tests/ -q` (95 tests must pass)
4. **Merge into master** (fast‑forward if no conflicts; if conflicts, escalate to the two owners)
5. **Notify the other team** after every push to master
6. **Contract stability:** B‑team reads every new key with `.get()`; A‑team never renames existing English identifiers

---

## Summary of Code-Only Deliverables per Person

| Person | Branch | Key Code Deliverables |
|---|---|---|
| **Erik** | `feat/datos-cache` | `cache_loader.py`, `imerg_etl.py`, `southern_hemisphere.json`, `lookup_soil()`, `fetch_openet_eta()`, `fetch_smap_moisture()`, single `CROP_TBASE` |
| **Alina** | `feat/logica-herramientas` | Fixed `detect_event` confidence, `filter_rescue_crops` `none` return, `generate_recovery_plan` normal‑scenario text, `compute_dollar_savings()`, `plan_rotation()`, `explain_exclusion()` |
| **Neithan** | `feat/gdd-climate` | Hemisphere‑aware `fetch_power_gdd.py`, `--hemisphere` CLI, `season_end` in demo packets |
| **Danny** | `feat/api-backend` | `/generate_plan` with full contract serialization, `/recommend_crops` absolute path, `datetime.now(timezone.utc)`, `alertas` field, `/simulate_sms` |
| **Matias** | `feat/ui-pwa` | Streamlit with 3 visual states, weights sliders, exclusion/rotation/savings sections, data‑source badge, `sms_gateway.py`, PWA fix (icons, paths) |
| **Elias** | `feat/docs-entrega` | Rewritten `README.md`, `.gitattributes`, `.env.example`, `docs/contratos.md`, monitoring drift integration |

**No one works on:** video creation, slide decks, on‑screen branding, or any UI/UX polish beyond the code‑driven interface described above. The focus is entirely on making the engine reliable, multi‑hemisphere, and transparent so that any presentation layer can consume it.

---
*Fused from `PLAN_PERSON_A.md`, `PLAN_PERSON_B.md`, and `quehacer.md`. All non-code elements (video, slides, presentation text) removed. 6 isolated branches. Integration only through `run_pier` and `load_demo_packet` contracts.*