# PIER — AI-Agent Implementation Plan (historical)

**Project:** PIER (POWER + IMERG Extreme-weather Recovery) — Spec 3 (Extreme Weather) + Cross-Cutting Context  
**Deadline:** Sun Nov 15, 2026, 23:59 (local) — ≈36 hours from plan start (Sat Nov 14)  
**Demo format:** 30-second video (recommended) OR ≤7 slides; English spoken; English CC if Spanish  
**Evaluation criteria:** Influence, Creativity, Validity, Relevance, Presentation  
**Execution mode:** Every task below is an atomic unit for an AI agent. Each task lists inputs, outputs, spec traceability (BR = Business Rule from spec.md §5), an exact prompt to paste into the agent, and acceptance criteria. Do not start a task until its inputs exist.

> **Demo data rule (spec §8, Risk register):** During the demo ALL IMERG/POWER responses are served from `data/cache/`. The live NASA Earthdata / POWER connection is labeled as a *production path only*. Agents must verify cache-only operation via network log before the demo.

## 0. How agents should use this plan

1. Pick the next stage whose **Inputs** are all satisfied.
2. Read **Traceability** so you know which spec sections and BRs the code must satisfy.
3. For each task: paste the **Agent prompt** into your coding agent, review the produced code, run the **Acceptance criteria**, then check the task off.
4. Commit after every stage (`git add -A && git commit -m "Stage N: ..."`).
5. If a task cannot be completed (missing credential, install failure), fall back to its documented mitigation and keep moving — the demo must run on cached data.

## Repository & timeline assumptions

| Item | Value |
|---|---|
| Repo root | `/home/elipoli/projs/pier-spaceapps` |
| Python package | `piper_agent/` (tools, data, ui, config, prompts) |
| Crop DB | `piper_agent/data/rescue_crops.csv` |
| Cache | `piper_agent/data/cache/{imerg,power}/` + `piper_agent/data/baselines/` |
| Demo packets | `demo/{flood,drought,normal}.json` |
| AI declaration | `docs/AI_USAGE_DECLARATION.md` + `docs/PROMPT_REGISTRY.md` |
| Total budget | ~38 agent-hours, compressed into Sat Nov 14 → Sun Nov 15 23:59 |

### Suggested schedule (hard deadline Nov 15 23:59)

| Day | Block | Stages | Cumulative |
|---|---|---|---|
| Sat Nov 14 AM | 0–2 | Stage 0, Stage 1 | 6h |
| Sat Nov 14 PM | 2–10 | Stage 2 | 10h |
| Sat Nov 14 evening | 10–14 | Stage 3 | 14h |
| Sun Nov 15 AM | 14–18 | Stage 4 | 18h |
| Sun Nov 15 midday | 18–22 | Stage 5 | 22h |
| Sun Nov 15 early PM | 22–26 | Stage 6 (agent loop) | 26h |
| Sun Nov 15 mid PM | 26–32 | Stage 7 (Streamlit UI) | 32h |
| Sun Nov 15 evening | 32–38 | Stage 8 (video/demos), Stage 9 (declaration) | 38h |

**Scope-cutting triage (in order, if behind schedule):**  
1. Drop Folium map polish → keep a simple st.markdown location display.  
2. Drop video → submit ≤7 slides (English).  
3. Reduce to one demo location → keep flood + drought hardcoded and disclosed (spec §9 risk).  
4. Ship CLI-only + screen-captured demo instead of interactive UI.

## Stage 0 — Repo scaffolding & environment

**Goal:** Create the PIER repo skeleton, Python environment, dependency manifest, and Dockerfile so every later stage runs offline/cached.

**Traceability:** Spec §4 Tech Stack (Python tool-calling loop, pandas, Streamlit, Folium); Spec §9 Risk (`imergpy` install / wget dependency → containerize).

**Inputs:** none (repo root exists).  
**Outputs:** folder tree, `requirements.txt`, `.env.example`, `Dockerfile`, working `pip install`, import smoke test.

### Tasks

**T0.0 — Create folder structure**  
Agent prompt:  
> In /home/elipoli/projs/pier-spaceapps, create the following folder tree and empty __init__.py files where indicated:  
> piper_agent/__init__.py  
> piper_agent/tools/__init__.py  
> piper_agent/tools/detect_event.py   # BR-1 event detection  
> piper_agent/tools/fetch_power_gdd.py   # BR-3 GDD model  
> piper_agent/tools/filter_rescue_crops.py   # BR-2, BR-3, BR-4 crop filter  
> piper_agent/tools/generate_recovery_plan.py   # BR-5, BR-6 plan generator  
> piper_agent/agent.py   # tool-calling loop (Spec §6)  
> piper_agent/config.py   # constants (TBASE per crop, 0.8 safety margin, tolerance ordinals)  
> piper_agent/data/rescue_crops.csv   # Spec §3 crop database  
> piper_agent/data/cache/imerg/   # cached IMERG Excel/CSV per demo  
> piper_agent/data/cache/power/   # cached POWER daily T2M_MAX/T2M_MIN/PRECTOTCORR  
> piper_agent/data/baselines/   # 10-yr 95th/10th percentile baselines + climatological frost dates  
> piper_agent/ui/streamlit_app.py   # Spec §4 frontend  
> piper_agent/ui/components.py  
> piper_agent/prompts/   # prompt registry fragments (notes.md AI declaration)  
> tests/test_detect_event.py  
> tests/test_fetch_power_gdd.py  
> tests/test_filter_rescue_crops.py  
> demo/flood_demo.json  
> demo/drought_demo.json  
> demo/normal_demo.json  
> docs/AI_USAGE_DECLARATION.md  
> docs/PROMPT_REGISTRY.md  
> requirements.txt  
> .env.example  
> Dockerfile  
> .gitignore  
> README.md  

**Acceptance:** `find piper_agent tests demo docs -type f` lists all files above; `git status` clean except new files.

**T0.1 — requirements.txt**  
Agent prompt:  
> Write /home/elipoli/projs/pier-spaceapps/requirements.txt with pinned versions: streamlit, folium, pandas, numpy, requests, openpyxl, python-dotenv, imergpy. Add a comment that imergpy requires wget and NASA Earthdata credentials (live path only: demo uses cache).  

**Acceptance:** `pip install -r requirements.txt` completes with exit code 0.

**T0.2 — .env.example**  
Agent prompt:  
> Write .env.example with placeholder-only keys: EARTHDATA_USERNAME=your_username, EARTHDATA_PASSWORD=your_password. Add a comment: never commit real credentials; demo mode does not use Earthdata.  

**Acceptance:** File exists; contains no real secrets.

**T0.3 — Dockerfile**  
Agent prompt:  
> Write a Dockerfile (python:3.11-slim) that installs wget, copies requirements.txt, runs pip install, copies the repo, sets WORKDIR /app. Include a RUN to test `python -c "import streamlit, pandas, folium, numpy"`. Document: this mitigates the imergpy/wget install risk (spec §9).  

**Acceptance:** `docker build -t pier-agent .` succeeds (or at least Dockerfile syntax is valid if Docker unavailable).

**T0.4 — Import smoke test**  
Agent prompt:  
> Run `python -c "import streamlit, pandas, folium, numpy, requests, openpyxl; print('imports ok')"`. Report the output. If imergpy is installed, also test `import imergpy` and report.  

**Acceptance:** All imports print OK.

**Definition of Done (Stage 0):** `pip install` succeeds; folder tree matches T0.0; smoke test passes; first commit made.

## Stage 1 — Rescue-crop database + cached IMERG/POWER demo data

**Goal:** Build the Spec §3 rescue-crop CSV and pre-fetch/cache IMERG + POWER responses for three demo packets (flood, drought, normal) so the demo never depends on live Earthdata.

**Traceability:** Spec §3 Data Needed (crop DB table); Spec §8 Demo Scope (pre-fetch IMERG; label live as production path); Spec §9 Risk (cache IMERG Excel).

**Inputs:** Stage 0 outputs (repo, env).  
**Outputs:** `data/rescue_crops.csv`, `data/cache/imerg/*`, `data/cache/power/*`, `data/baselines/*`, `demo/*.json` packets.

### Tasks

**T1.1 — Write rescue_crops.csv**  
Agent prompt:  
> Create /home/elipoli/projs/pier-spaceapps/piper_agent/data/rescue_crops.csv with these exact columns:  
> crop,waterlogging_tolerance,drought_tolerance,days_to_maturity_min,days_to_maturity_max,gdd_base_c,gdd_to_maturity_min,gdd_to_maturity_max,planting_window_start,planting_window_end,notes  
> Fill one row per crop using Spec §3 table values (Sorghum, Millet, Buckwheat, Cowpea, Cereal rye (cover)). Tolerance values: Low/Medium/High text. days_to_maturity and GDD ranges from the table. GDD base: Sorghum 10, Millet 10, Buckwheat 5, Cowpea 10, Cereal rye 0. Add realistic planting_window_start/end (e.g., MM-DD) and notes ("typical values, local calibration required").  

**Acceptance:** CSV has header + 5 data rows; `pandas.read_csv` loads it; tolerance column contains only Low/Medium/High.

**T1.2 — Choose demo locations & dates**  
Agent prompt:  
> Define three demo packets in /home/elipoli/projs/pier-spaceapps/demo/ as JSON files: flood_demo.json, drought_demo.json, normal_demo.json. Each packet: {name, lat, lon, event_type, recent_start, recent_end, baseline_start, baseline_end, season_start, current_date, description}. Choose:  
> - Flood: US Midwest (e.g., near lat 41.8, lon -93.6 Iowa), a known heavy-rain date in 2025; recent window = event date minus 7 days; baseline = 10 years preceding.  
> - Drought: Horn of Africa or South Asia (e.g., lat 6.9, lon 79.9 per imergpy example, or lat 9.0, lon 41.0 Horn of Africa); recent window = 30 dry days; baseline = 10 years.  
> - Normal: same location as flood, a normal rainfall period; must return event_type = none.  
> All dates ISO format (YYYY-MM-DD). Keep current_date inside the growing season (before climatological frost) so GDD math works.  

**Acceptance:** 3 JSON files load; dates are valid ISO; current_date < baseline_end.

**T1.3 — Cache IMERG data (demo path)**  
Agent prompt:  
> Write a Python script (or notebook steps) that calls `imergpy.get_precipitation(lat=..., lon=..., start_date=..., end_date=..., freq="daily")` for each demo packet location and date range (baseline + recent). Save the Excel output and records to /home/elipoli/projs/pier-spaceapps/piper_agent/data/cache/imerg/ named {demo}_{location}.csv with columns date,precipitation_mm. Also save a copy of the original Excel. Print the file paths and the first/last 5 rows of each CSV. If Earthdata credentials are unavailable, create realistic synthetic daily rainfall CSVs matching IMERG scale (0–30 mm/day, with one 3-day storm >100 mm for flood and 30-day deficit for drought) and mark them SYNTHETIC_CACHE in a metadata column/file.  

**Acceptance:** For each demo packet, a CSV exists under data/cache/imerg/ with columns date,precipitation_mm and ≥30 rows; flood packet contains a 72-hour storm; drought packet contains a 30-day deficit.

**T1.4 — Cache POWER data + baselines**  
Agent prompt:  
> Query NASA POWER Daily Point (agricultural) parameters T2M_MAX, T2M_MIN, PRECTOTCORR for each demo location for 10+ years ending near the demo date. Save daily CSVs to /home/elipoli/projs/pier-spaceapps/piper_agent/data/cache/power/{demo}_power.csv with columns date,T2M_MAX,T2M_MIN,PRECTOTCORR. Then compute and save to /home/elipoli/projs/pier-spaceapps/piper_agent/data/baselines/{demo}_baselines.json:  
> - p95_daily_rainfall (95th percentile of 10-yr daily PRECTOTCORR)  
> - p10_daily_rainfall (10th percentile)  
> - climatological_frost_date (first fall date with T2M_MIN <= 0 C, or best available approximation; record method used)  
> If POWER API is unreachable, generate synthetic 10-yr temperature series with realistic seasonal cycle and mark SYNTHETIC_CACHE.  

**Acceptance:** Each demo has power CSV (date,T2M_MAX,T2M_MIN,PRECTOTCORR) and baselines JSON with p95, p10, climatological_frost_date.

**T1.5 — Cache loader helper**  
Agent prompt:  
> Write piper_agent/data/cache_loader.py with functions:  
> - load_imerg(demo_name) -> pandas.DataFrame (date, precipitation_mm) from cache  
> - load_power(demo_name) -> pandas.DataFrame (date, T2M_MAX, T2M_MIN, PRECTOTCORR) from cache  
> - load_baselines(demo_name) -> dict  
> - DEMO_MODE flag (read env PIER_DEMO_MODE=1 default true); when true, always read cache; when false, allow live imergpy/POWER calls.  
> Include a docstring: "Demo serves only cached data; live Earthdata is production path (spec §8)."  

**Acceptance:** `from piper_agent.data.cache_loader import load_imerg, load_power, load_baselines` works; each returns non-empty DataFrame/dict for flood/drought/normal.

**T1.6 — Validate caches**  
Agent prompt:  
> Run a validation script that loads all three demo packets through cache_loader and asserts: IMERG non-empty with date column parsed; POWER non-empty with T2M_MAX/T2M_MIN; baselines contain p95 > p10; print PASS/FAIL per demo.  

**Acceptance:** Validation prints PASS for all three demos.

**Definition of Done (Stage 1):** rescue_crops.csv (5 rows), 3 demo packets, cached IMERG + POWER + baselines, loader validates. Commit.

## Stage 2 — Tool 1: detect_event (BR-1)

**Goal:** Implement rule-based anomaly event detection from IMERG daily rainfall.

**Traceability:** BR-1 (anomaly threshold, not absolute; 3-day cum vs min(p95,100mm); 30-day cum vs p10; confidence by anomaly magnitude); Spec §6 tool `detect_event`; Spec §2.1 imergpy output schema (date, precipitation_mm).

**Inputs:** Stage 1 cache_loader, demo packets.  
**Outputs:** `piper_agent/tools/detect_event.py`, `tests/test_detect_event.py`.

### Tasks

**T2.1 — Implement detect_event**  
Agent prompt:  
> Implement /home/elipoli/projs/pier-spaceapps/piper_agent/tools/detect_event.py:  
>  
> Function signature: detect_event(lat, lon, recent_start, recent_end, baseline_dir) -> dict  
>  
> Logic (BR-1):  
> 1. Load cached IMERG daily rainfall for the location (date, precipitation_mm).  
> 2. Compute 3-day cumulative rainfall over the recent window (cum3) and 30-day cumulative rainfall (cum30).  
> 3. Load baseline 10-year daily distribution p95 and p10 from baseline_dir.  
> 4. Flood threshold = min(p95, 100.0). If cum3 > flood_threshold → event_type = "flood".  
> 5. Else if cum30 < p10 → event_type = "drought".  
> 6. Else event_type = "none".  
> 7. Confidence (0–1, anomaly-magnitude based):  
>    - flood: min(1.0, cum3 / flood_threshold) scaled so just-over-threshold ≈ 0.6, double threshold ≈ 1.0.  
>    - drought: min(1.0, (p10 - cum30) / p10) scaled similarly.  
>    - none: 1.0 - max(anomaly ratios) or a low baseline confidence.  
> 8. Return {"event_type": str, "severity": str, "confidence": float, "details": {cum3, cum30, flood_threshold, p10, p95}}.  
>  
> Ensure 0 <= confidence <= 1. severity: "high"/"medium"/"low" derived from confidence.  

**Acceptance:** Function imports and runs on cached flood/drought/normal data; returns dict with event_type ∈ {flood,drought,none}, confidence float in [0,1], severity string.

**T2.2 — Unit tests**  
Agent prompt:  
> Write tests/test_detect_event.py using the cached demo data:  
> - flood_demo → assert result["event_type"] == "flood"  
> - drought_demo → assert result["event_type"] == "drought"  
> - normal_demo → assert result["event_type"] == "none"  
> - assert 0 <= confidence <= 1 for all three  
> Run pytest and report results.  

**Acceptance:** `pytest tests/test_detect_event.py` passes (3/3).

**Definition of Done (Stage 2):** detect_event correctly classifies all 3 demos; tests pass. Commit.

## Stage 3 — Tool 2: fetch_power_gdd (BR-3)

**Goal:** Compute GDD accumulated to date and GDD remaining to climatological frost from POWER temperature data.

**Traceability:** BR-3 (remaining_GDD = GDD_to_frost − GDD_accumulated; eligibility uses remaining window); Spec §2.2 POWER T2M_MAX/T2M_MIN; Spec §3 POWER climatological frost date.

**Inputs:** Stage 1 cache_loader + baselines.  
**Outputs:** `piper_agent/tools/fetch_power_gdd.py`, `tests/test_fetch_power_gdd.py`.

### Tasks

**T3.1 — Implement fetch_power_gdd**  
Agent prompt:  
> Implement /home/elipoli/projs/pier-spaceapps/piper_agent/tools/fetch_power_gdd.py:  
>  
> Function signature: fetch_power_gdd(lat, lon, season_start, current_date, baseline_dir) -> dict  
>  
> Logic:  
> 1. Load cached POWER daily data (date, T2M_MAX, T2M_MIN) for the location from season_start to current_date.  
> 2. GDD per day = max(0, (T2M_MAX + T2M_MIN)/2 − TBASE). Use TBASE = 10.0 C as default reference (store in piper_agent/config.py); note per-crop TBASE adjustment happens in Stage 4.  
> 3. gdd_accumulated = sum of daily GDD from season_start to current_date.  
> 4. Load climatological_frost_date from baseline_dir (Stage 1). GDD_to_frost = sum of daily GDD from season_start to climatological_frost_date.  
> 5. gdd_remaining = GDD_to_frost − gdd_accumulated (floor at 0; if current_date >= frost_date, gdd_remaining = 0).  
> 6. avg_daily_gdd = mean daily GDD over the last 14 days (or full window if shorter).  
> 7. Return {"gdd_accumulated": float, "gdd_remaining": float, "frost_date": ISO str, "avg_daily_gdd": float, "details": {...}}.  

**Acceptance:** Function imports; gdd_accumulated ≥ 0; gdd_remaining ≥ 0; frost_date is a valid ISO date; avg_daily_gdd ≥ 0.

**T3.2 — Unit tests**  
Agent prompt:  
> Write tests/test_fetch_power_gdd.py using cached demo data:  
> - in-season date → assert gdd_remaining > 0  
> - assert frost_date matches baselines climatological_frost_date  
> - current_date >= frost_date → assert gdd_remaining == 0  
> Run pytest.  

**Acceptance:** `pytest tests/test_fetch_power_gdd.py` passes.

**Definition of Done (Stage 3):** GDD math correct on cached data; fallback to zero remaining after frost. Commit.

## Stage 4 — Tool 3: filter_rescue_crops (BR-2, BR-3, BR-4)

**Goal:** Filter rescue crops by event type and GDD window, compute plant-by dates, rank latest-first.

**Traceability:** BR-2 (event-driven tolerance filter, never both); BR-3 (GDD-based window, 0.8 safety margin); BR-4 (plant-by date explicit, rank by latest plant-by date); Spec §3 crop DB; Spec §6 tool `filter_rescue_crops`.

**Inputs:** Stage 1 rescue_crops.csv; Stage 2 detect_event output; Stage 3 fetch_power_gdd output.  
**Outputs:** `piper_agent/tools/filter_rescue_crops.py`, `tests/test_filter_rescue_crops.py`.

### Tasks

**T4.1 — Implement filter_rescue_crops**  
Agent prompt:  
> Implement /home/elipoli/projs/pier-spaceapps/piper_agent/tools/filter_rescue_crops.py:  
>  
> Function signature: filter_rescue_crops(event_type, gdd_remaining, current_date, avg_daily_gdd, crops_csv) -> list[dict]  
>  
> Logic:  
> 1. Load rescue_crops.csv. Map tolerance to ordinal: Low=1, Medium=2, High=3.  
> 2. BR-2: if event_type == "flood": keep rows where waterlogging_tolerance ordinal >= 2 (exclude Low). if event_type == "drought": keep rows where drought_tolerance ordinal >= 2. Never apply both filters simultaneously.  
> 3. BR-3: crop eligible only if gdd_to_maturity_max <= gdd_remaining * 0.8 (20% safety margin for late planting/slower emergence). Use the conservative (max) GDD-to-maturity.  
> 4. BR-4: plant_by_date = current_date + (gdd_remaining − gdd_to_maturity_max) / avg_daily_gdd days (ceil to whole days). days_until_deadline = (plant_by_date − current_date).days.  
> 5. Rescue confidence (0–1, GDD-margin based): min(1.0, (gdd_remaining − gdd_to_maturity_max) / (gdd_remaining * 0.2)) — i.e., how much headroom beyond the required crop GDD relative to the 20% margin.  
> 6. Output fields per crop: crop, event_match (tolerance satisfied), gdd_requirement, gdd_remaining, margin_pct, plant_by_date (ISO), days_until_deadline, rescue_confidence.  
> 7. Rank list by plant_by_date descending (latest feasible plant-by date first).  
>  
> Return empty list [] if no crop is eligible (BR-5 fallback handled in Stage 5).  

**Acceptance:** Function returns list of dicts sorted by plant_by_date desc; each dict has the listed fields; rescue_confidence in [0,1].

**T4.2 — Unit tests**  
Agent prompt:  
> Write tests/test_filter_rescue_crops.py using cached demo data:  
> - flood demo + realistic gdd_remaining → assert len(result) >= 2 (spec §10 success metric)  
> - drought demo → assert len(result) >= 2  
> - late-season date (gdd_remaining tiny) → assert result == []  
> - assert no crop with Low waterlogging appears in flood results; no crop with Low drought tolerance appears in drought results (BR-2)  
> - assert list sorted by plant_by_date descending  
> Run pytest.  

**Acceptance:** `pytest tests/test_filter_rescue_crops.py` passes; ≥2 crops for flood & drought; empty for late-season; sort order correct.

**Definition of Done (Stage 4):** ≥2 eligible crops per demo event; fallback empty list triggers on late season. Commit.

## Stage 5 — Tool 4: generate_recovery_plan (BR-5, BR-6)

**Goal:** Generate the natural-language recovery plan with separate confidences and the cover-crop fallback.

**Traceability:** BR-5 (fallback cover crop / cash crop lost); BR-6 (separate event-detection vs rescue-recommendation confidence); Spec §6 tool `generate_recovery_plan`.

**Inputs:** Stage 2 detect_event output; Stage 3 fetch_power_gdd output; Stage 4 filter output.  
**Outputs:** `piper_agent/tools/generate_recovery_plan.py`.

### Tasks

**T5.1 — Implement generate_recovery_plan**  
Agent prompt:  
> Implement /home/elipoli/projs/pier-spaceapps/piper_agent/tools/generate_recovery_plan.py:  
>  
> Function signature: generate_recovery_plan(event_result, gdd_result, crops_list, current_date) -> (str plan_text, dict structured)  
>  
> Logic:  
> 1. BR-6: plan_text must state detection confidence separately from rescue confidence:  
>    - "Event detection: {event_type}, confidence {event_confidence:.0%}"  
>    - "Rescue recommendation confidence: {rescue_confidence:.0%} (based on GDD margin)"  
> 2. Include GDD window: accumulated, remaining, climatological frost date, safety margin note (20%).  
> 3. If crops_list non-empty: for each crop (ranked latest plant-by date first): name, plant-by date, days until deadline, one-line rationale (event match + GDD fit). Add caveat: "Typical GDD values — local calibration required."  
> 4. BR-5: if crops_list empty: recommend a fast-establishing cover (cereal rye or buckwheat) to protect soil and explicitly state: "The season's cash crop is lost; this recommendation is soil protection only, not a cash crop."  
> 5. Return structured dict with keys: event_type, event_confidence, rescue_confidence, gdd_accumulated, gdd_remaining, frost_date, fallback (bool), crops (list), plan_text.  

**Acceptance:** Output contains both confidence lines; non-empty case lists crops with plant-by dates; empty case includes "cash crop is lost" statement and cover-crop recommendation.

**T5.2 — Manual smoke test**  
Agent prompt:  
> Call generate_recovery_plan with outputs from T2.1/T3.1/T4.1 for flood demo, drought demo, normal demo, and a late-season date. Print plan_text for each. Verify: flood/drought → crops listed; normal → no event message; late-season → cover crop + cash-crop-lost statement.  

**Acceptance:** Four plan_texts printed; each satisfies the corresponding rule above.

**Definition of Done (Stage 5):** Plan generator produces separate confidences and BR-5 fallback. Commit.

## Stage 6 — Agent orchestration loop (tool-calling loop)

**Goal:** Wire the four tools into the Spec §6 Python tool-calling loop with a CLI entry point and demo/live mode toggle.

**Traceability:** Spec §6 Agent orchestration; Spec §8 (cached demo vs labeled live production path).

**Inputs:** Stages 2–5 tools + cache_loader.  
**Outputs:** `piper_agent/agent.py`, CLI smoke test.

### Tasks

**T6.1 — Implement agent.py**  
Agent prompt:  
> Implement /home/elipoli/projs/pier-spaceapps/piper_agent/agent.py with a synchronous tool-calling loop:  
>  
> def run_pier(lat, lon, current_date, demo_mode=True):  
>     # Step 1: detect_event (BR-1) -> event_result  
>     # Step 2: fetch_power_gdd (BR-3) -> gdd_result  
>     # Step 3: filter_rescue_crops (BR-2,3,4) -> crops_list  
>     # Step 4: generate_recovery_plan (BR-5,6) -> plan_text, structured  
>     # Return structured dict including all intermediate results.  
>  
> Pass outputs of each tool as inputs to the next (detect_event -> filter; fetch_power_gdd -> filter + plan). Do not skip steps. Include DEMO_MODE toggle: true uses piper_agent.data.cache_loader only; false attempts live imergpy/POWER (labeled production path).  

**Acceptance:** `run_pier` runs end-to-end for flood/drought/normal/late-season using only cache (demo_mode=True); returns structured dict.

**T6.2 — CLI entry point**  
Agent prompt:  
> Add `python -m piper_agent.agent --lat FLOAT --lon FLOAT --date YYYY-MM-DD [--demo]` that prints the plan_text to stdout. Include --demo flag default true.  

**Acceptance:** `python -m piper_agent.agent --lat 41.8 --lon -93.6 --date 2025-06-20 --demo` prints a plan.

**T6.3 — End-to-end smoke test**  
Agent prompt:  
> Run run_pier for all four demo scenarios (flood, drought, normal, late-season) with demo_mode=True. Assert no exceptions; assert plan_text non-empty; assert no live network calls are attempted (mock or confirm cache_loader used). Print summary.  

**Acceptance:** All four scenarios complete without error; plans printed.

**Definition of Done (Stage 6):** Agent loop works end-to-end on cached data; CLI functional. Commit.

## Stage 7 — Streamlit UI + Folium map

**Goal:** Build the Spec §4 frontend: Streamlit app with Folium map overlay and recovery-plan card.

**Traceability:** Spec §4 Tech Stack (Streamlit + Folium map overlay + recovery-plan card); Spec §8 (cache badge: "Demo data (cached)" vs "Live NASA data").

**Inputs:** Stage 6 agent.py.  
**Outputs:** `piper_agent/ui/streamlit_app.py`, `piper_agent/ui/components.py`.

### Tasks

**T7.1 — Streamlit app skeleton**  
Agent prompt:  
> Write /home/elipoli/projs/pier-spaceapps/piper_agent/ui/streamlit_app.py:  
> - Page title "PIER — Extreme-weather Recovery Planner".  
> - Sidebar: lat input, lon input, current date input, demo mode toggle (default True), scenario selector (Flood demo / Drought demo / Normal demo / Auto-detect).  
> - Main button "Generate recovery plan".  
> - On click: call piper_agent.agent.run_pier with selected inputs; render outputs.  

**Acceptance:** `streamlit run piper_agent/ui/streamlit_app.py` starts without error (can verify with `python -c "import ast; ast.parse(open(...).read())"` if streamlit server can't launch).

**T7.2 — Folium map overlay**  
Agent prompt:  
> Add a Folium map (streamlit-folium or st.components.v1.html) centered on (lat, lon) with a color-coded marker: flood=blue, drought=orange, none=green. Add a popup showing event type and confidence. If streamlit-folium is not installed, render the map as an HTML string via st.components.v1.html.  

**Acceptance:** Map renders at the field location with event-colored marker.

**T7.3 — Recovery-plan card**  
Agent prompt:  
> Render a card (st.container or st.markdown with border) containing:  
> - Event type + detection confidence (BR-6 separate line)  
> - GDD window: accumulated, remaining, climatological frost date  
> - Rescue recommendation confidence (BR-6 separate line)  
> - Ranked crops table: crop, plant-by date, days until deadline, GDD margin  
> - Caveat: "Typical GDD values — local calibration required."  
> - If fallback: cover-crop recommendation + "The season's cash crop is lost; soil protection only." (BR-5)  

**Acceptance:** Card displays all fields for flood/drought/normal/late-season.

**T7.4 — Cache indicator badge**  
Agent prompt:  
> Show a badge: "Demo mode — data cached (no live Earthdata call)" when demo_mode=True; "Live NASA data (production path)" when false. Verify the badge appears.  

**Acceptance:** Badge visible and correct per toggle.

**T7.5 — Local run check**  
Agent prompt:  
> Launch `streamlit run piper_agent/ui/streamlit_app.py --server.headless true` briefly, capture that it binds to a port, then kill it. Or if server cannot launch, verify by parsing and importing the module and calling its render functions with mocked st.  

**Acceptance:** App loads; no crashes on any demo scenario.

**Definition of Done (Stage 7):** Streamlit app runs; map + plan card render for all demos; cache badge present. Commit.

## Stage 8 — Demo preparation & 30-second video

**Goal:** Produce the deadline deliverables per notes.md: validate success metrics, record the demo video (or slides).

**Traceability:** Spec §10 Success Metrics; Spec §8 Demo Scope; notes.md (30s video, English, Hyperframes AI optional, deadline Nov 15 23:59).

**Inputs:** Stage 6 + Stage 7 outputs; cached demo packets.  
**Outputs:** demo video (≤30s) OR ≤7 slides; validated success metrics.

### Tasks

**T8.1 — Validate success metrics (spec §10)**  
Agent prompt:  
> Run a final validation script that checks every Spec §10 success metric:  
> 1. Event detection classifies flood demo = flood, drought demo = drought, normal demo = none. (PASS/FAIL)  
> 2. At least 2 eligible rescue crops for flood demo and drought demo. (PASS/FAIL)  
> 3. Fallback path triggers when window too short; plan states cash crop is lost. (PASS/FAIL)  
> 4. All IMERG responses served from cache during demo (verify cache_loader used, no live calls). (PASS/FAIL)  
> Print a metrics report. All must PASS before recording.  

**Acceptance:** Metrics report shows 4/4 PASS.

**T8.2 — Record 30-second demo video (English)**  
Agent prompt:  
> Produce a ≤30-second demo video in English showing: (1) field location on map, (2) agent detects event (flood or drought) with confidence, (3) GDD window computed, (4) 2–3 rescue crops with plant-by dates ranked latest-first, (5) fallback cover crop when window too short + cash-crop-lost statement. Use screen capture of the Streamlit app or CLI run. If using Hyperframes AI, note it in the AI usage declaration. Keep under 30 seconds; add English captions.  

**Acceptance:** Video file exists; duration ≤30s; spoken English; covers all five demo beats.

**T8.3 — Backup: ≤7 slides deck**  
Agent prompt:  
> If video cannot be completed, build a ≤7-slide deck (English): problem, Spec 3 context, how PIER works (4 tools), demo result (flood + drought), fallback/BR-5, AI usage. Save as PDF or Markdown.  

**Acceptance:** Deck exists; ≤7 slides; English.

**T8.4 — Rehearse timing**  
Agent prompt:  
> Time the video playback; if over 30s, trim and re-export.  

**Acceptance:** Final video ≤30s.

**Definition of Done (Stage 8):** Success metrics 4/4 PASS; video ≤30s (or ≤7 slides) ready before Nov 15 23:59.

## Stage 9 — AI usage declaration & evaluation package

**Goal:** Satisfy the notes.md AI Usage declaration ("an MD with what the AI agents do, with every prompt the agent adds") and position for Influence/Creativity/Validity/Relevance/Presentation.

**Traceability:** notes.md AI Usage declaration requirement; evaluation criteria.

**Inputs:** Prompts used across all stages (collect them as you go).  
**Outputs:** `docs/AI_USAGE_DECLARATION.md`, `docs/PROMPT_REGISTRY.md`, updated README, final commit.

### Tasks

**T9.1 — Write AI_USAGE_DECLARATION.md**  
Agent prompt:  
> Write /home/elipoli/projs/pier-spaceapps/docs/AI_USAGE_DECLARATION.md describing:  
> - Which parts were produced by AI agents (code, prompts, plan, video script, slides).  
> - Which parts were human decisions (demo dates, crop choices, go/no-go, presentation language).  
> - Models/tools used (e.g., OpenCode Nemotron, Hyperframes AI if used).  
> - A statement that every agent prompt is logged in PROMPT_REGISTRY.md.  

**Acceptance:** File exists; honest and complete.

**T9.2 — Consolidate PROMPT_REGISTRY.md**  
Agent prompt:  
> Write /home/elipoli/projs/pier-spaceapps/docs/PROMPT_REGISTRY.md listing every prompt given to an AI agent in this project, organized by stage/task ID (T0.0 … T9.2), with the full prompt text. This is the "every prompt the agent adds" record required by notes.md.  

**Acceptance:** All stage prompts above are included, keyed by task ID.

**T9.3 — README**  
Agent prompt:  
> Write README.md: one-paragraph PIER description (Spec 3 extreme-weather recovery), how to run (pip install, streamlit run, CLI), demo instructions, spec traceability table (BR-1..BR-6 → files), and success-metrics results.  

**Acceptance:** README renders; run instructions work.

**T9.4 — Final commit**  
Agent prompt:  
> `git add -A && git commit -m "Stage 9: AI usage declaration, prompt registry, README; ready for demo"`.  

**Acceptance:** Working tree clean; all deliverables committed before Nov 15 23:59.

## Stage 10 — Data fidelity & ingestion pipeline (v1.1)

**Goal:** Replace synthetic cache with a real production ingestion pipeline; add soil, ET, and moisture data layers.

**Traceability:** Spec §3 Data Needed (soil texture, OpenET ETa, SMAP moisture); Spec §4 Tech Stack (production ETL, Redis cache); Spec §11 Post-MVP Roadmap v1.1.

**Inputs:** Stage 9 outputs (MVP complete).  
**Outputs:** `piper_agent/data/ingestion/`, `piper_agent/data/soil_lookup.py`, `piper_agent/data/fetch_openet.py`, `piper_agent/data/fetch_smap.py`, `piper_agent/data/redis_cache.py`, updated tests.

### Tasks

**T10.1 — Real imergpy ingestion pipeline**  
Agent prompt:  
> Write piper_agent/data/ingestion/imerg_etl.py: wrap imergpy.get_precipitation with retry/backoff (3 attempts, exponential backoff), Earthdata cookie refresh, and fallback to nearest GES DISC grid cell when point query fails. Save to Redis cache (not just local CSV). Include circuit breaker: if Earthdata is down 3x in a row, fall back to synthetic cache and log the event.  

**Acceptance:** Module imports; ETL function exists with retry logic; fallback path tested.

**T10.2 — Soil texture lookup (SoilGrids/ISRIC)**  
Agent prompt:  
> Write piper_agent/data/soil_lookup.py: lookup_soil(lat, lon) -> {texture_class, field_capacity_mm, wilting_point_mm}. Accept user-provided soil texture as override. If SoilGrids API unavailable, return a reasonable default based on lat/lon climate zone and mark as estimated. Output feeds BR-10 water-shortage screening.  

**Acceptance:** Function returns dict with all four fields; user override works.

**T10.3 — OpenET ETa + SMAP moisture fetchers**  
Agent prompt:  
> Write piper_agent/data/fetch_openet.py (fetch_openet_eta(lat, lon, date_range) -> DataFrame[date, eta_mm]) and piper_agent/data/fetch_smap.py (fetch_smap_moisture(lat, lon, date_range) -> DataFrame[date, soil_moisture_vol_pct]). Both use cache-first, API-second pattern with SYNTHETIC_CACHE fallback.  

**Acceptance:** Both modules import; return non-empty DataFrames with correct columns.

**T10.4 — Redis cache layer**  
Agent prompt:  
> Write piper_agent/data/redis_cache.py: Redis-backed cache with TTL invalidation on new IMERG/POWER overpasses. Functions: get(key), set(key, value, ttl), invalidate_prefix(prefix). Fall back to local filesystem cache if Redis unavailable.  

**Acceptance:** Module imports; get/set work; filesystem fallback tested.

**Definition of Done (Stage 10):** Real ingestion pipeline works with fallback; soil/ET/moisture fetchers return data; Redis cache with filesystem fallback. Commit.

## Stage 11 — Agent intelligence: conformal confidence + analog search (v1.1)

**Goal:** Replace heuristic confidence with calibrated confidence; add historical analog search.

**Traceability:** BR-7 (calibrated confidence), BR-8 (explanations); Spec §4 Tech Stack (conformal prediction); Spec §11 Roadmap v1.1.

**Inputs:** Stage 10 outputs.  
**Outputs:** `piper_agent/tools/confidence_calibration.py`, `piper_agent/tools/search_analogs.py`, `piper_agent/tools/explain_exclusion.py`, tests.

### Tasks

**T11.1 — Conformal confidence calibration**  
Agent prompt:  
> Write piper_agent/tools/confidence_calibration.py: given historical validation cases (event_type, predicted_confidence, actual_outcome), compute conformal prediction intervals so that "80% confidence" means the outcome occurs ~80% of the time. Output calibrated_confidence and a reliability plot data series.  

**Acceptance:** Module imports; calibration function returns calibrated confidence in [0,1]; reliability data series computable.

**T11.2 — Historical analog search**  
Agent prompt:  
> Write piper_agent/tools/search_analogs.py: search_analogs(event_type, location, gdd_remaining) -> list of historical matches from IMERG/POWER archive with matched crops and outcomes. Used to calibrate confidence and provide precedent for recommendations.  

**Acceptance:** Function returns list of analog dicts; empty list when no history available (graceful degradation).

**T11.3 — Explanation generator for exclusions**  
Agent prompt:  
> Write piper_agent/tools/explain_exclusion.py: explain_exclusion(crop, event_type, gdd_remaining, filter_reason) -> human-readable string. Examples: "Buckwheat excluded: Low waterlogging tolerance for this flood event." "Sorghum excluded: needs 1800 GDD, only 1200 remain." (BR-8)  

**Acceptance:** Function returns non-empty string for each exclusion reason type.

**Definition of Done (Stage 11):** Conformal calibration, analog search, and explanation generation all work. Commit.

## Stage 12 — Decision depth: farmer priorities, dollar savings, rotation (v1.2)

**Goal:** Multi-criteria crop ranking, dollar estimates, and rescue → rotation linkage.

**Traceability:** BR-9 (rotation linkage), BR-10 (farmer priorities), BR-11 (dollar savings), BR-12 (multi-season); Spec §4 Tech Stack (market price API); Spec §11 Roadmap v1.2.

**Inputs:** Stage 11 outputs.  
**Outputs:** `piper_agent/tools/filter_rescue_crops.py` (extended), `piper_agent/tools/plan_rotation.py`, `piper_agent/tools/fetch_market_price.py`, tests.

### Tasks

**T12.1 — Farmer priority weighting slider**  
Agent prompt:  
> Extend filter_rescue_crops to accept farmer_weights (soil_protection, salvage_revenue, water_conservation, each 0-1). Compute composite score = weighted sum of normalized criteria. Re-rank crops by composite score, not just latest plant-by date (BR-10).  

**Acceptance:** Changing weights changes crop order; scores documented.

**T12.2 — Dollar savings estimate**  
Agent prompt:  
> Write piper_agent/tools/fetch_market_price.py: fetch_market_price(crop, region, date) -> price_per_unit. Compute dollar savings = rescued_crop_revenue − total_loss (0 if crop lost). Include in plan output (BR-11).  

**Acceptance:** Function returns price; savings calculation included in plan text.

**T12.3 — Rescue → rotation planner**  
Agent prompt:  
> Write piper_agent/tools/plan_rotation.py: plan_rotation(rescue_crop, next_season_constraints) -> rotation_sequence, soil_health_score. Suggest next season's crop based on what the rescue crop leaves behind (N fixation from cowpea, residue cover from rye). Output 3-crop sequence (rescue → main → cover) with cumulative soil-health score (BR-9, BR-12).  

**Acceptance:** Function returns rotation sequence and score; links rescue crop to next-season choice.

**Definition of Done (Stage 12):** Weighted ranking, dollar savings, and rotation planner all work. Commit.

## Stage 13 — Operational resilience: FastAPI + Redis + monitoring (v1.3)

**Goal:** Production API layer with caching, monitoring, and drift detection.

**Traceability:** Spec §4 Tech Stack (FastAPI, Redis, monitoring); Spec §11 Roadmap v1.3.

**Inputs:** Stage 12 outputs.  
**Outputs:** `piper_agent/api/`, `piper_agent/monitoring/`, tests.

### Tasks

**T13.1 — FastAPI API layer**  
Agent prompt:  
> Write piper_agent/api/main.py: FastAPI app with endpoints POST /detect_event, POST /recommend_crops, POST /generate_plan, GET /health. Each accepts lat/lon/date and returns JSON. Add API key auth and rate limiting.  

**Acceptance:** Server starts; endpoints return correct JSON; auth middleware present.

**T13.2 — Monitoring & drift detection**  
Agent prompt:  
> Write piper_agent/monitoring/drift.py: detect when IMERG/POWER data is stale (>3 days), when confidence drops below threshold, or when recommendations fall outside historical norms. Emit structured log entries for audit.  

**Acceptance:** Drift detection function runs; log output includes timestamp, metric, severity.

**T13.3 — Request tracing & audit log**  
Agent prompt:  
> Add request ID propagation through all tools; log every recommendation with full inputs (lat, lon, date, event_type, confidences, crops) for post-season validation.  

**Acceptance:** Every agent run produces an audit log entry with complete inputs.

**Definition of Done (Stage 13):** API server runs; monitoring detects drift; audit log complete. Commit.

## Stage 14 — Field readiness: mobile PWA + SMS + multi-region (v2.0)

**Goal:** Deployable product for farmers in the field.

**Traceability:** Spec §4 Tech Stack (mobile PWA, SMS fallback); Spec §11 Roadmap v2.0.

**Inputs:** Stage 13 outputs.  
**Outputs:** `piper_agent/ui/pwa/`, `piper_agent/ui/sms_gateway.py`, hemisphere-aware GDD, tests.

### Tasks

**T14.1 — Mobile PWA frontend**  
Agent prompt:  
> Build a mobile-first PWA (React or vanilla JS + service worker) that mirrors the Streamlit UI: field location input, event detection, GDD window, rescue crops with plant-by dates, fallback cover crop. Works offline using cached baselines and crop DB.  

**Acceptance:** PWA loads on mobile; offline mode functions with cached data.

**T14.2 — SMS/USSD fallback gateway**  
Agent prompt:  
> Write piper_agent/ui/sms_gateway.py: accept inbound SMS with lat/lon, run PIER agent, reply with concise rescue-crop recommendation (crop name + plant-by date). For low-connectivity, low-literacy farmers.  

**Acceptance:** Gateway parses SMS; returns valid recommendation text.

**T14.3 — Hemisphere-aware seasons**  
Agent prompt:  
> Make GDD and frost-date logic hemisphere-aware: Southern Hemisphere growing seasons run opposite to Northern. Detect hemisphere from lat sign and adjust season_start/frost_date accordingly.  

**Acceptance:** Southern Hemisphere demo (e.g., lat -30) produces correct season logic.

**T14.4 — Heat-wave rescue events**  
Agent prompt:  
> Extend detect_event to flag heat-wave events (T2M_MAX above crop-specific threshold for N consecutive days). Recommend heat-tolerant rescue crops (sorghum, millet) with adjusted GDD penalty.  

**Acceptance:** Heat-wave detection works; heat-tolerant crops recommended.

**Definition of Done (Stage 14):** PWA + SMS gateway work; hemisphere-aware logic verified; heat-wave events detected. Commit.

## Prompt Registry (consolidated)

| Task | Prompt summary | Full prompt location |
|---|---|---|
| T0.0 | Repo folder tree | Stage 0, T0.0 |
| T0.1 | requirements.txt | Stage 0, T0.1 |
| T0.2 | .env.example | Stage 0, T0.2 |
| T0.3 | Dockerfile | Stage 0, T0.3 |
| T0.4 | Import smoke test | Stage 0, T0.4 |
| T1.1 | rescue_crops.csv | Stage 1, T1.1 |
| T1.2 | Demo packets JSON | Stage 1, T1.2 |
| T1.3 | Cache IMERG data | Stage 1, T1.3 |
| T1.4 | Cache POWER + baselines | Stage 1, T1.4 |
| T1.5 | Cache loader helper | Stage 1, T1.5 |
| T1.6 | Validate caches | Stage 1, T1.6 |
| T2.1 | detect_event implementation | Stage 2, T2.1 |
| T2.2 | detect_event tests | Stage 2, T2.2 |
| T3.1 | fetch_power_gdd implementation | Stage 3, T3.1 |
| T3.2 | fetch_power_gdd tests | Stage 3, T3.2 |
| T4.1 | filter_rescue_crops implementation | Stage 4, T4.1 |
| T4.2 | filter_rescue_crops tests | Stage 4, T4.2 |
| T5.1 | generate_recovery_plan implementation | Stage 5, T5.1 |
| T5.2 | Plan smoke test | Stage 5, T5.2 |
| T6.1 | Agent orchestration loop | Stage 6, T6.1 |
| T6.2 | CLI entry point | Stage 6, T6.2 |
| T6.3 | End-to-end smoke test | Stage 6, T6.3 |
| T7.1 | Streamlit skeleton | Stage 7, T7.1 |
| T7.2 | Folium map | Stage 7, T7.2 |
| T7.3 | Recovery-plan card | Stage 7, T7.3 |
| T7.4 | Cache badge | Stage 7, T7.4 |
| T7.5 | Local run check | Stage 7, T7.5 |
| T8.1 | Success-metrics validation | Stage 8, T8.1 |
| T8.2 | 30s video | Stage 8, T8.2 |
| T8.3 | Slides deck (backup) | Stage 8, T8.3 |
| T8.4 | Timing rehearsal | Stage 8, T8.4 |
| T9.1 | AI usage declaration | Stage 9, T9.1 |
| T9.2 | Prompt registry | Stage 9, T9.2 |
| T9.3 | README | Stage 9, T9.3 |
| T9.4 | Final commit | Stage 9, T9.4 |
| T10.1 | Real imergpy ingestion pipeline | Stage 10, T10.1 |
| T10.2 | Soil texture lookup (SoilGrids/ISRIC) | Stage 10, T10.2 |
| T10.3 | OpenET ETa + SMAP moisture fetchers | Stage 10, T10.3 |
| T10.4 | Redis cache layer | Stage 10, T10.4 |
| T11.1 | Conformal confidence calibration | Stage 11, T11.1 |
| T11.2 | Historical analog search | Stage 11, T11.2 |
| T11.3 | Explanation generator for exclusions | Stage 11, T11.3 |
| T12.1 | Farmer priority weighting slider | Stage 12, T12.1 |
| T12.2 | Dollar savings estimate | Stage 12, T12.2 |
| T12.3 | Rescue → rotation planner | Stage 12, T12.3 |
| T13.1 | FastAPI API layer | Stage 13, T13.1 |
| T13.2 | Monitoring & drift detection | Stage 13, T13.2 |
| T13.3 | Request tracing & audit log | Stage 13, T13.3 |
| T14.1 | Mobile PWA frontend | Stage 14, T14.1 |
| T14.2 | SMS/USSD fallback gateway | Stage 14, T14.2 |
| T14.3 | Hemisphere-aware seasons | Stage 14, T14.3 |
| T14.4 | Heat-wave rescue events | Stage 14, T14.4 |

*When an agent executes a task, it should append the exact prompt it used (and any refinements) to this registry in Stage 9.*

## Risk register (condensed for the deadline)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Earthdata/GES DISC auth not ready | Medium | High | Demo uses cache only; live path labeled production (spec §8) |
| imergpy/wget install fails | Low | Medium | Dockerfile + synthetic cache fallback (T1.3/T1.4) |
| Anomaly threshold misfires on demo date | Medium | High | Pre-validate both demo events in T2.2; hardcode event date and disclose (spec §9) |
| No crop fits window | Medium | Low | Feature by design — BR-5 cover crop + cash-crop-lost |
| Crop GDD values off for demo region | Medium | Medium | Label "typical values, local calibration required" (T1.1 caveat) |
| Video >30s | Medium | Medium | Trim in T8.4; fallback to ≤7 slides (T8.3) |
| Streamlit won't launch headless | Low | Medium | CLI + screenshots suffice; video can be CLI capture |
| Earthdata GES DISC OTF throttling | Medium | High | Redis cache + synthetic fallback; circuit breaker |
| Conformal calibration needs ≥100 validation cases | Medium | Medium | Start with heuristic confidence, calibrate as data accumulates |
| SoilGrids/ISRIC API rate limits | Low | Medium | Cache soil lookups; default to climate-zone estimates |
| FastAPI deployment complexity | Low | Medium | Start with local uvicorn; containerize with Docker |
| Mobile PWA service-worker caching bugs | Medium | Medium | Test offline mode thoroughly; fallback to server-rendered UI |
| SMS gateway provider costs/limits | Low | Medium | Twilio-like provider; rate-limit inbound messages |

## Success-metrics verification checklist (Spec §10)

Before committing Stage 9, confirm:

- [ ] Flood demo → `event_type = flood`
- [ ] Drought demo → `event_type = drought`
- [ ] Normal demo → `event_type = none`
- [ ] Flood demo returns ≥2 eligible rescue crops
- [ ] Drought demo returns ≥2 eligible rescue crops
- [ ] Late-season date → empty crop list + cover crop + "cash crop is lost" statement
- [ ] Demo run uses only `data/cache/` (no live IMERG call) — verified via cache_loader
- [ ] Video ≤30s (or ≤7 slides), English
- [ ] `docs/AI_USAGE_DECLARATION.md` and `docs/PROMPT_REGISTRY.md` exist

**Post-MVP (v1.1+):**

- [ ] Conformal reliability plot: predicted confidence within ±5% of observed frequency across ≥100 validation cases
- [ ] 100% of excluded crops include an explicit reason (BR-8)
- [ ] Every rescue-crop recommendation includes next-season crop suggestion (BR-9)
- [ ] Weight slider visibly re-ranks crops (BR-10)
- [ ] At least one recommendation includes dollar-savings estimate (BR-11)
- [ ] Agent produces 3-crop rotation sequence with soil-health score (BR-12)
- [ ] FastAPI p95 < 500ms on cached data
- [ ] PWA loads and functions on 3G with offline cache

## End of plan.

Execute stages in order; commit after each stage; MVP (Stages 0–9) must be complete by Sun Nov 15, 2026 23:59. Post-MVP stages (10–14) extend beyond the hackathon deadline.