# Prompt Registry — PIER (Spec 3: Extreme Weather Recovery)

Every instruction given to the AI agent during implementation, organized by stage/task ID from `plan.md`. This satisfies the notes.md requirement: "an MD with what the AI agents do, with every prompt the agent adds."

---

## Stage 0 — Repo scaffolding & environment

### T0.0 — Create folder structure
> In /home/elipoli/projs/pier-spaceapps, create the following folder tree and empty __init__.py files where indicated: piper_agent/__init__.py, piper_agent/tools/__init__.py, piper_agent/tools/detect_event.py, piper_agent/tools/fetch_power_gdd.py, piper_agent/tools/filter_rescue_crops.py, piper_agent/tools/generate_recovery_plan.py, piper_agent/agent.py, piper_agent/config.py, piper_agent/data/rescue_crops.csv, piper_agent/data/cache/imerg/, piper_agent/data/cache/power/, piper_agent/data/baselines/, piper_agent/ui/streamlit_app.py, piper_agent/ui/components.py, piper_agent/prompts/, tests/test_detect_event.py, tests/test_fetch_power_gdd.py, tests/test_filter_rescue_crops.py, demo/flood_demo.json, demo/drought_demo.json, demo/normal_demo.json, docs/AI_USAGE_DECLARATION.md, docs/PROMPT_REGISTRY.md, requirements.txt, .env.example, Dockerfile, .gitignore, README.md

### T0.1 — requirements.txt
> Write requirements.txt with pinned versions: streamlit, folium, pandas, numpy, requests, openpyxl, python-dotenv, imergpy. Add a comment that imergpy requires wget and NASA Earthdata credentials (live path only; demo uses cache).

### T0.2 — .env.example
> Write .env.example with placeholder-only keys: EARTHDATA_USERNAME=your_username, EARTHDATA_PASSWORD=your_password. Add a comment: never commit real credentials; demo mode does not use Earthdata.

### T0.3 — Dockerfile
> Write a Dockerfile (python:3.11-slim) that installs wget, copies requirements.txt, runs pip install, copies the repo, sets WORKDIR /app. Include a RUN to test python imports. Document: this mitigates the imergpy/wget install risk (spec §9).

### T0.4 — Import smoke test
> Run python -c "import streamlit, pandas, folium, numpy, requests, openpyxl; print('imports ok')". Report the output.

---

## Stage 1 — Rescue-crop database + cached IMERG/POWER demo data

### T1.1 — rescue_crops.csv
> Create piper_agent/data/rescue_crops.csv with columns: crop,waterlogging_tolerance,drought_tolerance,days_to_maturity_min,days_to_maturity_max,gdd_base_c,gdd_to_maturity_min,gdd_to_maturity_max,planting_window_start,planting_window_end,notes. One row per crop from Spec §3 table (Sorghum, Millet, Buckwheat, Cowpea, Cereal rye cover).

### T1.2 — Demo packets JSON
> Create demo/flood_demo.json, demo/drought_demo.json, demo/normal_demo.json per schema {name,lat,lon,event_type,recent_start,recent_end,baseline_start,baseline_end,season_start,current_date,description}. Flood: US Midwest (~41.8,-93.6). Drought: Horn of Africa (~9.0,41.0). Normal: same location as flood.

### T1.3 — Cache IMERG data
> For each demo packet, call imergpy.get_precipitation for baseline+recent ranges. Save to data/cache/imerg/{demo}_imerg.csv. If Earthdata credentials unavailable, create SYNTHETIC_CACHE daily rainfall (flood packet includes 72h storm >100mm; drought packet includes 30-day deficit).

### T1.4 — Cache POWER data + baselines
> Query NASA POWER Daily Point (T2M_MAX,T2M_MIN,PRECTOTCORR) for 10+ years per demo location. Save data/cache/power/{demo}_power.csv. Compute data/baselines/{demo}_baselines.json: p95_3day_cum_rainfall, p10_30day_cum_rainfall, climatological_frost_date. If POWER unreachable, generate synthetic 10-yr series.

### T1.5 — Cache loader helper
> Write piper_agent/data/cache_loader.py with load_imerg, load_power, load_baselines, load_demo_packet functions. PIER_DEMO_MODE env flag (default true = cache-only). Docstring: demo serves only cached data; live Earthdata/POWER is production path.

### T1.6 — Validate caches
> Run validation script asserting all three demo packets load correctly through cache_loader.

---

## Stage 2 — Tool 1: detect_event (BR-1)

### T2.1 — detect_event implementation
> Implement piper_agent/tools/detect_event.py: detect_event(lat, lon, recent_start, recent_end, baseline_dir, demo_name) -> EventResult. BR-1: flood = 3-day cum > min(p95_3day_cum, 100mm); drought = 30-day cum < p10_30day_cum; none otherwise. Confidence 0-1 by anomaly magnitude. Uses cache_loader only.

### T2.2 — detect_event tests
> Write tests/test_detect_event.py: flood→flood, drought→drought, normal→none, confidence in [0,1], flood 72h storm exceeds threshold.

---

## Stage 3 — Tools 2 & 3: fetch_power_gdd + filter_rescue_crops

### T3.1 — fetch_power_gdd implementation
> Implement piper_agent/tools/fetch_power_gdd.py: fetch_power_gdd(lat, lon, season_start, current_date, demo_name) -> GddResult. Daily GDD = max(0, (Tmax+Tmin)/2 - TBASE). gdd_remaining = gdd_to_frost - gdd_accumulated. Frost date month-day applied to current season year.

### T3.2 — fetch_power_gdd tests
> Write tests/test_fetch_power_gdd.py: in-season gdd_remaining>0, frost_date matches baseline, post-frost gdd_remaining=0, values in range.

### T4.1 — filter_rescue_crops implementation
> Implement piper_agent/tools/filter_rescue_crops.py: filter_rescue_crops(event_type, gdd_remaining, current_date, avg_daily_gdd, crops_csv) -> list[CropRecommendation]. BR-2: event-type tolerance filter (never both). BR-3: gdd_req <= gdd_remaining * 0.8. BR-4: plant_by_date explicit, rank latest-first.

### T4.2 — filter_rescue_crops tests
> Write tests/test_filter_rescue_crops.py: >=2 crops flood/drought, empty late-season, BR-2 tolerance exclusion, BR-3 0.8 margin, BR-4 ranking and plant-by date.

---

## Stage 4 — Tool 4: generate_recovery_plan (BR-5, BR-6)

### T5.1 — generate_recovery_plan implementation
> Implement piper_agent/tools/generate_recovery_plan.py: generate_recovery_plan(event_result, gdd_result, crops, current_date) -> (plan_text, RecoveryPlan). BR-6: separate event detection confidence vs rescue confidence. BR-5: cover-crop fallback + "cash crop is lost" statement.

### T5.2 — Plan smoke test
> Write tests/test_generate_recovery_plan.py: flood/drought/none/fallback scenarios with separate confidences.

---

## Stage 5 — Agent orchestration + CLI

### T6.1 — agent.py
> Implement piper_agent/agent.py: run_pier(lat, lon, current_date, demo_mode, demo_name) orchestrating detect_event → fetch_power_gdd → filter_rescue_crops → generate_recovery_plan in sequence. demo_mode=True uses cache only; demo_mode=False raises NotImplementedError (production path).

### T6.2 — CLI entry point
> Create piper_agent/__main__.py: python -m piper_agent --lat FLOAT --lon FLOAT --date YYYY-MM-DD [--demo] [--demo-name X].

### T6.3 — E2E tests
> Write tests/test_agent_e2e.py: flood/drought/normal/late-season e2e, demo_mode_only_cache, auto_select_demo, at_least_2_crops per Spec §10.

---

## Stage 6 — Streamlit UI + demo assets + declaration

### T7.1 — Streamlit app skeleton
> Write piper_agent/ui/streamlit_app.py: page title, sidebar lat/lon/date/demo mode/scenario, main button, call run_pier on click.

### T7.2 — Folium map overlay
> Add Folium map centered on (lat,lon) with event-colored marker (flood=blue, drought=orange, none=green), popup with event type + confidence.

### T7.3 — Recovery-plan card
> Render bordered card: event type + detection confidence, GDD window, rescue confidence, ranked crops table, caveat, BR-5 fallback with "cash crop is lost".

### T7.4 — Cache badge
> Show badge: "Demo mode — data cached" vs "Live NASA data (production path)".

### T7.5 — Local run check
> Verify streamlit app imports/parses cleanly.

### T8.1 — Success-metrics validation
> Validate all Spec §10 metrics: flood→flood, drought→drought, normal→none, ≥2 crops each, fallback triggers, cache-only demo.

### T8.2 — 30-second demo video
> Produce ≤30s English demo video: map → event detection → GDD window → rescue crops with plant-by dates → fallback cover crop + cash-crop-lost.

### T8.3 — Slides deck (backup)
> If video unavailable: ≤7-slide English deck (problem, Spec 3, 4 tools, demo result, fallback, AI usage).

### T8.4 — Timing rehearsal
> Verify video ≤30 seconds.

### T9.1 — AI usage declaration
> Write docs/AI_USAGE_DECLARATION.md: AI-produced vs human-decision parts, models/tools, statement that all prompts logged here.

### T9.2 — Prompt registry
> Write docs/PROMPT_REGISTRY.md (this file): every prompt keyed by stage/task ID.

### T9.3 — README
> Write README.md: PIER description, how to run, demo instructions, BR traceability table, success-metrics results.

### T9.4 — Final commit
> git add -A && git commit -m "Stage 6: UI, demo assets, AI declaration, README; ready for demo"

---

## Stage 7 (not implemented — scope-cutting fallback)

If behind schedule per plan.md triage: drop Folium polish → drop video → submit ≤7 slides → CLI-only demo.
