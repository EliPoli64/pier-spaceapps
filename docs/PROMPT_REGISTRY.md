# Prompt Registry — PIER (Spec 3: Extreme Weather Recovery)

Every instruction given to the AI agent during implementation, organized by stage/task ID and, where relevant, by branch. This satisfies the notes.md requirement: "an MD with what the AI agents do, with every prompt the agent adds."

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

### T9.4 — Prompt registry update
> Update docs/PROMPT_REGISTRY.md to reflect the current stage and any branch-level plan prompts added since the last commit.

---

## Stage 7 (not implemented — scope-cutting fallback)

If behind schedule per plan.md triage: drop Folium polish → drop video → submit ≤7 slides → CLI-only demo.

---

## Stage 10 — Data fidelity & ingestion pipeline (v1.1)

### T10.1 — Optional real NASA POWER download
> Implement a production-path helper in the data layer that can download real NASA POWER daily time series when valid Earthdata credentials are available, wrapped in retry/backoff and a circuit-breaker fallback to synthetic cache. Demo mode must still use cache only.

### T10.2 — OpenET ETa ingestion
> Add an optional OpenET evapotranspiration data loader behind the same demo-mode gate as everything else, so the agent can later consume real ETa when credentials exist.

### T10.3 — SMAP soil moisture ingestion
> Add an optional NASA SMAP soil moisture data loader behind the same demo-mode gate, for later soil-moisture-aware recommendations.

### T10.4 — Ingestion tests
> Add tests that prove the optional ingestion layer imports cleanly, fails closed when credentials are absent, and never changes the demo-mode contract or the 95-test suite.

---

## Stage 11 — Agent intelligence: conformal confidence + analog search (v1.1)

### T11.1 — Conformal confidence
> Add a confidence-calibration layer that can incorporate observed outcomes and produce calibrated confidence bands instead of raw heuristic scores, with a fallback to uncalibrated confidence when no local observations exist.

### T11.2 — Analog search
> Add a historical-analog search helper that finds past periods similar to the current event window and surfaces them as evidence behind the agent's recommendation.

### T11.3 — Explanation hooks
> Add machine-readable explanation metadata per crop and per recommendation, so the UI and API can render both short and detailed reasons without re-deriving them.

### T11.4 — Intelligence tests
> Add tests for calibrated confidence bounds, analog search stability, and the explanation metadata contract.

---

## Stage 12 — Decision depth: farmer priorities, dollar savings, rotation (v1.2)

### T12.1 — Farmer priority weights
> Add farmer-priority weighting (soil protection, salvage revenue, water conservation) to the crop-filter and ranking logic, with sensible defaults when weights are not supplied.

### T12.2 — Dollar savings estimate
> Add a market-price/savings helper that can estimate dollar impact of a rescue recommendation versus the lost cash crop, using cached or placeholder prices when no live market feed exists.

### T12.3 — Multi-season rotation planner
> Add a rotation planner that links rescue crops to subsequent-season suggestions and a simple soil-health score, so the plan can express sequence rather than a single crop.

### T12.4 — Decision-depth tests
> Add tests for weighting reorder behavior, savings estimate shape, and rotation sequence correctness.

---

## Stage 13 — Operational resilience: FastAPI + Redis + monitoring (v1.3)

### T13.1 — FastAPI backend
> Add a FastAPI backend with a `/generate_plan` endpoint that consumes the `run_pier` contract, plus `/detect_event`, `/recommend_crops`, and a readiness-aware `/health` endpoint.

### T13.2 — Demo/production toggle in the API
> Add API-level support for the demo/production toggle so `/generate_plan` can surface `fuente_datos` transparently without forking the whole app into two code paths.

### T13.3 — Redis-backed cache (optional)
> Add an optional Redis-backed cache layer behind the same demo-mode gate, with filesystem fallback when Redis is absent.

### T13.4 — Monitoring and stale-data drift alerts
> Add monitoring hooks and stale-data / drift-detection alerts for production use, wired so they do not affect the demo-mode contract.

### T13.5 — Operational-resilience tests
> Add tests for the API endpoints, the demo/production toggle behavior, and the monitoring/drift hooks in demo mode.

---

## Stage 14 — Field readiness: mobile PWA + SMS + multi-region (v2.0)

### T14.1 — Mobile PWA
> Add a mobile-first PWA with offline support, app manifest, service worker, and event/plan rendering that reads from the agent contract.

### T14.2 — SMS / USSD gateway
> Add an SMS/USSD gateway helper and a simulator for demos, with the same demo/production data-source awareness.

### T14.3 — Multi-region climate correctness
> Add hemisphere-aware and tropical/temperate-aware climate logic so GDD, frost, and season detection behave correctly across representative regions.

### T14.4 — Field-readiness tests
> Add tests for the PWA assets/parsing, SMS gateway behavior, and hemisphere/season logic.

---

## Branch-level plan prompts

### PLAN_PERSON_A.md
> Person A (core: data + agent logic): implement in isolation per the shared contract, no video/presentation work, demo-first, production path opt-in only.

### PLAN_PERSON_B.md
> Person B (interface + delivery: API, UI, PWA, documentation, video): implement in isolation per the shared contract, no overlap with Person A files, demo-first, production path opt-in only.

### PLAN_SEIS_PERSONAS.md
> Fused 6-person plan: Erik, Alina, Neithan, Danny, Matias, Elias. Isolated branches, integration only through run_pier and load_demo_packet, production path opt-in labeled via fuente_datos, demo-mode tests stay green.

---

## Real-data / real-results next wave prompts

### Erik — real ingestion, multi-source cache, calibration data
> Replace the synthetic-only cache story with a real ingestion pipeline that can pull from NASA Earthdata (IMERG) and optional NOAA/OpenLand/SMAP sources behind the same demo-mode gate, keep a versioned per-region baseline store, wire soil/OpenET/SMAP lookups for Alina's tools, and add per-coordinate calibration stubs for farmer-observed outcomes.

### Alina — confidence, calibration layer, explanation depth
> Turn heuristic confidence into a calibration layer that ingests observed outcomes, add evidence tags to every recommendation, add a failure taxonomy (no data / conflicting data / normal), and finish the scenario text and tool behaviors for flood/drought/frost/heatwave/normal.

### Neithan — multi-hemisphere climate correctness and agronomy
> Stabilize GDD and frost logic across hemispheres and tropical/temperate boundaries, add season detection/windowing, hook climate outputs into the contract keys with real units/thresholds and agronomic metadata, and validate against cited climatologies.

### Danny — production-ready API, auth, records, audit
> Harden the FastAPI layer for real use: request validation, per-coordinate result storage, CSV/JSON export, API-key gate, audit trail including fuente_datos and circuit-breaker state, useful health/readiness, and demo vs production payload separation.

### Matias — real operator interface, multi-language, channel reach
> Build the dashboard around a real operator workflow, reflect production path correctly in the UI, add live SMS/WhatsApp/email channel hooks, and support Spanish and other justified operator-facing languages.

### Elias — data-use, privacy, reproducibility, delivery packaging
> Finish the AI usage and data declaration so it covers demo and production paths, package the repo for a one-command reproducible demo, add a reproducibility checklist, and keep the delivery surface code-only.

### Alina — `feat/herramientas-vivos` — live-data tools, failure taxonomy, contract keys
> Give each tool a `demo_mode` / data-source parameter so it can run on live data from the ingestion layer without changing the cache signatures; make `run_pier(demo_mode=False)` a labeled production path instead of `NotImplementedError`; have `run_pier` return `exclusiones`, `rotacion`, `ahorro`, `confianza_calibrada`, `suelo`, `ola_calor` and `fuente_datos`, read with `.get()` downstream; add a failure taxonomy that tells "no data", "conflicting data" and "normal conditions" apart and routes each differently; log a structured alert when `fuente_datos` falls from real data to `sintetico` (PP5); test the contract keys (PP4).

---

## QA / integration prompts

### feat/qa-integracion — QA gate, acceptance, success metrics, overlap detection
> Add a CI QA gate on every feat/* branch, an acceptance suite against Spec §10 plus BR invariants, a success-metrics script with a network guard that proves whether a run used live data or cache, and a branch-overlap detector to keep the isolation guarantees honest.

### Matias — pre-push CI repair + full E2E after GDD merge (2026-11-15)
> Pull master, diagnose red CI after PR #17 (`feat/herramientas-vivos` × climate rewrite), rewire `power`/`baselines` into `fetch_power_gdd`, restore `remaining_method`/`data_status`, forward `demo_mode` from `run_pier`, honor demo `--season-start`, route CLI live through `_run_live_or_fallback`. Verify end-to-end before upload: full pytest, Spec §10 metrics, all demo scenarios, API `/generate_plan`, Streamlit UI with data, live NASA POWER with teammate `.env`, and document in `docs/CHANGELOG_CI_FIX_GDD_MERGE.md` + `scripts/qa/e2e_pre_push_check.py`.

---

*Every prompt the agent added is recorded above, organized by stage/task ID and branch where relevant. Demo-first, production path opt-in only, code-only delivery, 95 demo-mode tests stay green. T9.4 is intentionally a prompt-registry update rather than the old final commit, because this file stays open-ended as stages 10–14 and the real-data next wave are added.*
