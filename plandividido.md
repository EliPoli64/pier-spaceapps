# PIER — 6-Branch Implementation Plan

**Project:** PIER (POWER + IMERG Extreme-weather Recovery) — Spec 3  
**Deadline:** Sun Nov 15, 2026, 23:59  
**Strategy:** Contract-first, branch-per-layer. Each branch is a self-contained pull request with its own tests. Branches merge into `main` in a strict sequence so merges are seamless (no two branches touch the same files except the shared contract, which only Branch A modifies).

---

## 0. Branch strategy & merge order

| Order | Branch | Purpose | Depends on |
|---|---|---|---|
| 1 | `feat/a-data-cache-layer` | Folder tree, env, Docker, `contracts.py`, `cache_loader.py`, `rescue_crops.csv`, cached demo data | `main` |
| 2 | `feat/b-event-detection` | `detect_event` tool (BR-1) + tests | A |
| 3 | `feat/c-gdd-crop-filter` | `fetch_power_gdd` (BR-3) + `filter_rescue_crops` (BR-2/3/4) + tests | A |
| 4 | `feat/d-recovery-plan` | `generate_recovery_plan` tool (BR-5/6) + tests | A |
| 5 | `feat/e-agent-cli` | Agent tool-calling loop + CLI entry point + integration tests | A + B + C + D |
| 6 | `feat/f-ui-demo-declaration` | Streamlit UI + Folium map + plan card + cache badge + video/slides + AI declaration + README | A + B + C + D + E |

**Merge rule:** Always merge into `main` in the order above. Before merging branch N+1, rebase it onto latest `main` (which now contains branches 1…N). Branch A is the only branch allowed to create/modify `piper_agent/contracts.py` and `piper_agent/data/cache_loader.py`; every other branch imports from them but never edits them.

**Conflict avoidance:** Each branch owns a disjoint set of files (see "Files owned" per branch). If a branch needs a new field in a contract, it requests it via Branch A first, then rebases.

---

## Shared contract layer (defined in Branch A, consumed by all)

File: `piper_agent/contracts.py` — created only in Branch A. All branches import from it; none modify it.

```python
from dataclasses import dataclass
from typing import Literal, Optional
from datetime import date

EventType = Literal["flood", "drought", "none"]
Tolerance = Literal["Low", "Medium", "High"]

@dataclass
class EventResult:
    event_type: EventType
    severity: str            # "low" | "medium" | "high"
    confidence: float        # 0..1, anomaly-magnitude based (BR-6)
    details: dict            # cum3, cum30, flood_threshold, p10, p95

@dataclass
class GddResult:
    gdd_accumulated: float
    gdd_remaining: float
    frost_date: str          # ISO date
    avg_daily_gdd: float
    details: dict

@dataclass
class CropRecommendation:
    crop: str
    event_match: bool
    gdd_requirement: float   # conservative max GDD to maturity
    gdd_remaining: float
    margin_pct: float
    plant_by_date: str       # ISO date (BR-4)
    days_until_deadline: int
    rescue_confidence: float # 0..1, GDD-margin based (BR-6)

@dataclass
class RecoveryPlan:
    event_type: EventType
    event_confidence: float
    rescue_confidence: float
    gdd_accumulated: float
    gdd_remaining: float
    frost_date: str
    fallback: bool           # True when BR-5 cover-crop path triggers
    crops: list[CropRecommendation]
    plan_text: str
```

Demo packet schema (JSON): `{name, lat, lon, event_type, recent_start, recent_end, baseline_start, baseline_end, season_start, current_date, description}`.

---

## Branch A — feat/a-data-cache-layer (Data & Cache Foundation)

**Goal:** Repo skeleton, Python env, shared contract, cache loader, rescue-crop CSV, and pre-cached IMERG/POWER demo data so NO later branch needs live NASA access.

**Traceability:** Spec §4 (Python, pandas, Streamlit, Folium); Spec §3 (crop DB, data layers); Spec §8 (pre-fetch IMERG, label live as production path); Spec §9 (containerize, cache IMERG).

**Parent:** `main`  
**Files owned (only this branch touches these):**
- `piper_agent/__init__.py`, `piper_agent/contracts.py`, `piper_agent/data/cache_loader.py`
- `piper_agent/data/rescue_crops.csv`
- `piper_agent/data/cache/imerg/*`, `piper_agent/data/cache/power/*`, `piper_agent/data/baselines/*`
- `demo/flood_demo.json`, `demo/drought_demo.json`, `demo/normal_demo.json`
- `requirements.txt`, `.env.example`, `Dockerfile`, `.gitignore`, `tests/test_cache_loader.py`

**Tasks:**

**TA.0 — Scaffold folder tree + configs**  
Prompt:  
> In /home/elipoli/projs/pier-spaceapps, create the folder tree:
> piper_agent/__init__.py
> piper_agent/data/__init__.py
> piper_agent/data/cache/imerg/.gitkeep
> piper_agent/data/cache/power/.gitkeep
> piper_agent/data/baselines/.gitkeep
> demo/
> tests/
> Write .env.example with placeholder keys EARTHDATA_USERNAME and EARTHDATA_PASSWORD plus a comment that real credentials are never committed and demo mode does not use Earthdata. Write .gitignore for Python (__pycache__, *.pyc, .env, *.csv in cache, .vscode). Write README.md placeholder (one line). Do NOT create contracts.py or cache_loader.py yet (those are TA.2/TA.4).

**Acceptance:** `find piper_agent demo tests -type f` lists the files; `git status` shows only new untracked files.

**TA.1 — requirements.txt + Dockerfile**  
Prompt:  
> Write requirements.txt with pinned: streamlit, folium, pandas, numpy, requests, openpyxl, python-dotenv, imergpy. Add comment: imergpy needs wget + NASA Earthdata (live path only; demo uses cache). Write Dockerfile from python:3.11-slim installing wget, pip-installing requirements, copying repo, WORKDIR /app, and a RUN test `python -c "import streamlit,pandas,folium,numpy,requests,openpyxl"`. Document that Docker mitigates the imergpy/wget install risk (Spec §9).

**Acceptance:** `pip install -r requirements.txt` exits 0; Dockerfile present.

**TA.2 — contracts.py (shared data model)**  
Prompt:  
> Write /home/elipoli/projs/pier-spaceapps/piper_agent/contracts.py containing the EventResult, GddResult, CropRecommendation, RecoveryPlan dataclasses and EventType/Tolerance type aliases exactly as specified in the shared contract layer of this plan. Include TOLERANCE_ORDINAL = {"Low":1,"Medium":2,"High":3} and DEFAULT_TBASE_C = 10.0 and SAFETY_MARGIN = 0.8 constants used across branches. Add module docstring: "Shared contract between PIER branches; only Branch A modifies this file."

**Acceptance:** `from piper_agent.contracts import EventResult, GddResult, CropRecommendation, RecoveryPlan` imports cleanly.

**TA.3 — rescue_crops.csv**  
Prompt:  
> Create piper_agent/data/rescue_crops.csv with columns: crop,waterlogging_tolerance,drought_tolerance,days_to_maturity_min,days_to_maturity_max,gdd_base_c,gdd_to_maturity_min,gdd_to_maturity_max,planting_window_start,planting_window_end,notes. One row per crop from Spec §3: Sorghum (Medium/High, 90-120, base 10, 1400-1800), Millet (Low/High, 60-90, base 10, 1000-1400), Buckwheat (Low/Medium, 70-90, base 5, 800-1100), Cowpea (Medium/High, 60-90, base 10, 900-1300), Cereal rye (cover) (High/Medium, 60-90 biomass, base 0, 600-900). Add realistic MM-DD planting windows and notes "typical values, local calibration required".

**Acceptance:** `pandas.read_csv` loads 5 header + 5 data rows; tolerance values only Low/Medium/High.

**TA.4 — cache_loader.py**  
Prompt:  
> Write piper_agent/data/cache_loader.py with:
> - PIER_DEMO_MODE env flag (default "1" = true). When true, ALL reads come from cache; live imergpy/POWER calls are disabled.
> - load_imerg(demo_name) -> pandas.DataFrame(columns=[date, precipitation_mm]) from data/cache/imerg/{demo_name}.csv
> - load_power(demo_name) -> pandas.DataFrame(columns=[date,T2M_MAX,T2M_MIN,PRECTOTCORR]) from data/cache/power/{demo_name}.csv
> - load_baselines(demo_name) -> dict with p95_daily_rainfall, p10_daily_rainfall, climatological_frost_date
> - load_demo_packet(name) -> dict from demo/{name}.json
> - tolerate SYNTHETIC_CACHE marker files (Branch A may create synthetic caches if NASA unreachable).
> Docstring: "Demo serves only cached data; live Earthdata/POWER is production path (Spec §8)."

**Acceptance:** All three loader functions return non-empty objects for flood/drought/normal.

**TA.5 — Choose demo locations & dates (3 JSON packets)**  
Prompt:  
> Create demo/flood_demo.json, demo/drought_demo.json, demo/normal_demo.json per schema {name,lat,lon,event_type,recent_start,recent_end,baseline_start,baseline_end,season_start,current_date,description}. Flood: US Midwest (~41.8,-93.6), known heavy-rain 2025 date, current_date inside growing season. Drought: Horn of Africa or South Asia (~6.9,79.9 or 9.0,41.0), 30 dry days. Normal: same location as flood, a normal period (must return event_type=none). All dates ISO YYYY-MM-DD; current_date < climatological frost.

**Acceptance:** 3 JSON files load; current_date < baseline_end for each.

**TA.6 — Cache IMERG data (demo path)**  
Prompt:  
> For each demo packet, call imergpy.get_precipitation(lat,lon,start_date,end_date,freq="daily") for baseline+recent ranges. Save to data/cache/imerg/{demo}_imerg.csv with columns date,precipitation_mm. If Earthdata credentials unavailable, create SYNTHETIC_CACHE daily rainfall (0-30 mm/day; flood packet includes a 72h storm >100mm; drought packet includes a 30-day deficit) and write a SYNTHETIC_CACHE.txt marker beside each synthetic CSV. Print paths and first/last 5 rows.

**Acceptance:** Each demo has a cache/imerg CSV with date+precipitation_mm and ≥30 rows; flood shows a >100mm 72h storm; drought shows a 30-day deficit.

**TA.7 — Cache POWER data + 10-year baselines**  
Prompt:  
> Query NASA POWER Daily Point (T2M_MAX,T2M_MIN,PRECTOTCORR) for 10+ years per demo location. Save data/cache/power/{demo}_power.csv (date,T2M_MAX,T2M_MIN,PRECTOTCORR). Compute data/baselines/{demo}_baselines.json: p95_daily_rainfall, p10_daily_rainfall (10-yr daily PRECTOTCORR percentiles), climatological_frost_date (first fall date T2M_MIN<=0C, or best approximation; record method). If POWER unreachable, generate synthetic 10-yr seasonal temperature series and mark SYNTHETIC_CACHE.

**Acceptance:** Each demo has power CSV + baselines JSON with p95 > p10 and a frost_date string.

**TA.8 — Cache loader tests**  
Prompt:  
> Write tests/test_cache_loader.py: assert load_imerg/load_power/load_baselines return non-empty for flood/drought/normal; assert baselines p95 > p10; assert PIER_DEMO_MODE defaults to "1". Run pytest.

**Acceptance:** `pytest tests/test_cache_loader.py` passes.

**Definition of Done (Branch A):** Contract imports work; rescue_crops.csv (5 rows); 3 demo packets; caches validate; tests pass. Merge into `main` first.

---

## Branch B — feat/b-event-detection (Tool 1: detect_event)

**Goal:** Rule-based IMERG anomaly event detection implementing BR-1. Depends ONLY on Branch A's cache_loader + contracts.

**Traceability:** BR-1 (anomaly threshold not absolute; 3-day cum vs min(p95,100mm); 30-day cum vs p10; confidence by magnitude); Spec §6 tool `detect_event`; Spec §2.1 imergpy schema (date, precipitation_mm).

**Parent:** rebase onto `main` after Branch A merged  
**Files owned:**
- `piper_agent/tools/__init__.py`
- `piper_agent/tools/detect_event.py`
- `tests/test_detect_event.py`

**Input contract (from Branch A):** `cache_loader.load_imerg(demo_name)`, `cache_loader.load_baselines(demo_name)`, `contracts.EventResult`, `contracts.Tolerance`.

**Tasks:**

**TB.1 — Implement detect_event**  
Prompt:  
> Implement piper_agent/tools/detect_event.py:
> 
> Function: detect_event(lat, lon, recent_start, recent_end, baseline_dir) -> EventResult
> 
> BR-1 logic:
> 1. Load cached IMERG daily rainfall via cache_loader (date, precipitation_mm).
> 2. Compute 3-day cumulative (cum3) over recent window and 30-day cumulative (cum30).
> 3. Load baseline p95 and p10 from load_baselines.
> 4. flood_threshold = min(p95, 100.0). If cum3 > flood_threshold → event_type="flood".
> 5. Elif cum30 < p10 → event_type="drought".
> 6. Else event_type="none".
> 7. Confidence 0-1 (anomaly magnitude):
>    - flood: min(1.0, cum3/flood_threshold) scaled so threshold≈0.6, 2x threshold≈1.0.
>    - drought: min(1.0, (p10-cum30)/p10) scaled similarly.
>    - none: 1.0 - max(anomaly ratios), floor 0.1.
> 8. severity: high/medium/low from confidence bands.
> 9. Return EventResult(event_type, severity, confidence, details={cum3,cum30,flood_threshold,p10,p95}).
> Ensure 0<=confidence<=1. Do NOT call live imergpy; use cache_loader only.

**Acceptance:** Function imports; runs on cached flood/drought/normal; returns EventResult with event_type in {flood,drought,none}, confidence in [0,1], severity string.

**TB.2 — Unit tests**  
Prompt:  
> Write tests/test_detect_event.py using cached demo data:
> - flood_demo → assert event_type == "flood", 0<confidence<=1
> - drought_demo → assert event_type == "drought", 0<confidence<=1
> - normal_demo → assert event_type == "none"
> Run pytest; report 3/3.

**Acceptance:** `pytest tests/test_detect_event.py` passes.

**Definition of Done (Branch B):** detect_event classifies all 3 demos correctly; tests pass. Merge into `main` (rebase onto A first).

---

## Branch C — feat/c-gdd-crop-filter (Tools 2 & 3: fetch_power_gdd + filter_rescue_crops)

**Goal:** GDD computation (BR-3) and rescue-crop filtering (BR-2, BR-3, BR-4). Depends ONLY on Branch A.

**Traceability:** BR-2 (event-driven tolerance filter, never both); BR-3 (remaining_GDD = to_frost − accumulated; eligibility = gdd_req ≤ remaining × 0.8); BR-4 (plant-by date explicit; rank latest-first); Spec §2.2 POWER T2M_MAX/T2M_MIN; Spec §6 tools `fetch_power_gdd`, `filter_rescue_crops`.

**Parent:** rebase onto `main` after Branch A merged  
**Files owned:**
- `piper_agent/tools/fetch_power_gdd.py`
- `piper_agent/tools/filter_rescue_crops.py`
- `tests/test_fetch_power_gdd.py`
- `tests/test_filter_rescue_crops.py`

**Input contract (from Branch A):** `cache_loader.load_power`, `cache_loader.load_baselines`, `contracts.GddResult`, `contracts.CropRecommendation`, `contracts.DEFAULT_TBASE_C`, `contracts.SAFETY_MARGIN`, `contracts.TOLERANCE_ORDINAL`, `rescue_crops.csv`.

**Tasks:**

**TC.1 — Implement fetch_power_gdd**  
Prompt:  
> Implement piper_agent/tools/fetch_power_gdd.py:
> 
> Function: fetch_power_gdd(lat, lon, season_start, current_date, baseline_dir) -> GddResult
> 
> Logic:
> 1. Load cached POWER daily (date,T2M_MAX,T2M_MIN) from season_start to current_date via cache_loader.
> 2. Daily GDD = max(0, (T2M_MAX+T2M_MIN)/2 − DEFAULT_TBASE_C).
> 3. gdd_accumulated = sum season_start→current_date.
> 4. Load climatological_frost_date from baselines. gdd_to_frost = sum season_start→frost_date.
> 5. gdd_remaining = max(0, gdd_to_frost − gdd_accumulated); if current_date >= frost_date → 0.
> 6. avg_daily_gdd = mean daily GDD over last 14 days (or full window if shorter).
> 7. Return GddResult(gdd_accumulated, gdd_remaining, frost_date ISO, avg_daily_gdd, details={...}).
> Use cache_loader only; no live POWER calls.

**Acceptance:** gdd_accumulated≥0; gdd_remaining≥0; frost_date valid ISO; avg_daily_gdd≥0.

**TC.2 — Implement filter_rescue_crops**  
Prompt:  
> Implement piper_agent/tools/filter_rescue_crops.py:
> 
> Function: filter_rescue_crops(event_type, gdd_remaining, current_date, avg_daily_gdd, crops_csv) -> list[CropRecommendation]
> 
> Logic:
> 1. Load rescue_crops.csv. Map tolerance via TOLERANCE_ORDINAL.
> 2. BR-2: flood → keep waterlogging_tolerance ordinal ≥2 (exclude Low). drought → keep drought_tolerance ordinal ≥2. NEVER both filters at once.
> 3. BR-3: eligible only if gdd_to_maturity_max ≤ gdd_remaining × SAFETY_MARGIN (0.8).
> 4. BR-4: plant_by_date = current_date + ceil((gdd_remaining − gdd_requirement)/avg_daily_gdd) days; days_until_deadline = (plant_by_date − current_date).days.
> 5. rescue_confidence = min(1.0, (gdd_remaining − gdd_requirement)/(gdd_remaining × 0.2)) — headroom beyond the 20% margin.
> 6. Output fields per CropRecommendation: crop, event_match, gdd_requirement, gdd_remaining, margin_pct, plant_by_date ISO, days_until_deadline, rescue_confidence.
> 7. Rank by plant_by_date descending (latest feasible first). Return [] if none eligible (BR-5 fallback handled in Branch D).

**Acceptance:** Returns list sorted by plant_by_date desc; each field present; rescue_confidence in [0,1]; flood excludes Low waterlogging; drought excludes Low drought tolerance.

**TC.3 — Unit tests (GDD)**  
Prompt:  
> Write tests/test_fetch_power_gdd.py:
> - in-season date → gdd_remaining > 0
> - frost_date matches baselines climatological_frost_date
> - current_date >= frost_date → gdd_remaining == 0
> Run pytest.

**Acceptance:** `pytest tests/test_fetch_power_gdd.py` passes.

**TC.4 — Unit tests (crop filter)**  
Prompt:  
> Write tests/test_filter_rescue_crops.py:
> - flood demo + realistic gdd_remaining → assert len ≥ 2 (Spec §10 metric)
> - drought demo → assert len ≥ 2
> - late-season (tiny gdd_remaining) → assert result == []
> - assert no Low-waterlogging crop in flood results; no Low-drought-tolerance crop in drought results (BR-2)
> - assert sorted by plant_by_date descending
> Run pytest.

**Acceptance:** `pytest tests/test_filter_rescue_crops.py` passes; ≥2 crops for flood & drought; empty for late-season; sort order correct.

**Definition of Done (Branch C):** ≥2 eligible crops per demo event; fallback empty list on late season; tests pass. Merge into `main` (rebase onto A first; B and C can be merged in either order after A).

---

## Branch D — feat/d-recovery-plan (Tool 4: generate_recovery_plan)

**Goal:** Natural-language recovery plan with separate confidences and BR-5 fallback. Depends ONLY on Branch A (contracts) + consumes outputs of B and C via the agent in Branch E. This branch implements the pure plan generator function.

**Traceability:** BR-5 (cover crop / fallow fallback; explicit "cash crop is lost"); BR-6 (separate event-detection confidence vs rescue-recommendation confidence); Spec §6 tool `generate_recovery_plan`.

**Parent:** rebase onto `main` after Branch A merged  
**Files owned:**
- `piper_agent/tools/generate_recovery_plan.py`
- `tests/test_generate_recovery_plan.py` (optional smoke)

**Input contract (from Branch A):** `contracts.EventResult`, `contracts.GddResult`, `contracts.CropRecommendation`, `contracts.RecoveryPlan`.

**Tasks:**

**TD.1 — Implement generate_recovery_plan**  
Prompt:  
> Implement piper_agent/tools/generate_recovery_plan.py:
> 
> Function: generate_recovery_plan(event_result: EventResult, gdd_result: GddResult, crops: list[CropRecommendation], current_date: date) -> tuple[str, RecoveryPlan]
> 
> Logic:
> 1. BR-6: plan_text states detection confidence SEPARATELY from rescue confidence:
>    - "Event detection: {event_type}, confidence {event_confidence:.0%}"
>    - "Rescue recommendation confidence: {rescue_confidence:.0%} (based on GDD margin)"
> 2. Include GDD window: accumulated, remaining, climatological frost date, 20% safety margin note.
> 3. If crops non-empty: list each crop (ranked latest plant-by date first): name, plant-by date, days until deadline, one-line rationale (event match + GDD fit). Add caveat: "Typical GDD values — local calibration required."
> 4. BR-5: if crops empty → recommend fast-establishing cover (cereal rye or buckwheat) to protect soil; explicitly state: "The season's cash crop is lost; this recommendation is soil protection only, not a cash crop." Set RecoveryPlan.fallback=True.
> 5. Return (plan_text, RecoveryPlan(...)).

**Acceptance:** Output contains both confidence lines; non-empty case lists crops with plant-by dates; empty case includes cover-crop + "cash crop is lost" statement; fallback flag correct.

**TD.2 — Cross-tool smoke test**  
Prompt:  
> Call generate_recovery_plan with synthetic EventResult/GddResult/crops for: (a) flood with crops, (b) drought with crops, (c) none event, (d) late-season empty crops. Print plan_text for each. Verify (a)/(b) list crops, (c) reports no event, (d) shows cover crop + cash-crop-lost.

**Acceptance:** Four plan_texts printed; each satisfies its rule.

**Definition of Done (Branch D):** Plan generator produces separate confidences and BR-5 fallback. Merge into `main` (rebase onto A first).

---

## Branch E — feat/e-agent-cli (Agent orchestration + CLI)

**Goal:** Wire the four tools into the Spec §6 Python tool-calling loop with a CLI entry point and demo/live toggle. Depends on A + B + C + D.

**Traceability:** Spec §6 (Python tool-calling loop, four tools); Spec §8 (cached demo vs labeled live production path).

**Parent:** rebase onto `main` after Branches B, C, D merged  
**Files owned:**
- `piper_agent/agent.py`
- `piper_agent/__main__.py` (CLI entry: `python -m piper_agent`)
- `tests/test_agent_e2e.py`

**Input contract (from A/B/C/D):** `detect_event`, `fetch_power_gdd`, `filter_rescue_crops`, `generate_recovery_plan`, `cache_loader`, all contracts.

**Tasks:**

**TE.1 — Implement agent.py**  
Prompt:  
> Implement piper_agent/agent.py with synchronous tool-calling loop:
> 
> def run_pier(lat: float, lon: float, current_date: str, demo_mode: bool = True) -> dict:
>     # Step 1: detect_event -> event_result (BR-1)
>     # Step 2: fetch_power_gdd -> gdd_result (BR-3)
>     # Step 3: filter_rescue_crops -> crops (BR-2,3,4)
>     # Step 4: generate_recovery_plan -> plan_text, recovery_plan (BR-5,6)
>     # Return structured dict with all intermediate results + plan_text.
> 
> Pass outputs of each tool as inputs to the next; do not skip steps. DEMO_MODE=True uses cache_loader only (no live NASA). demo_mode=False attempts live imergpy/POWER and is labeled production path (Spec §8).

**Acceptance:** `run_pier` runs end-to-end for flood/drought/normal/late-season using only cache; returns dict with plan_text non-empty.

**TE.2 — CLI entry point**  
Prompt:  
> Add `python -m piper_agent --lat FLOAT --lon FLOAT --date YYYY-MM-DD [--demo]` that prints plan_text to stdout. --demo defaults true. Include --no-demo flag to attempt live path (labeled production).

**Acceptance:** `python -m piper_agent --lat 41.8 --lon -93.6 --date 2025-06-20 --demo` prints a plan.

**TE.3 — End-to-end smoke test**  
Prompt:  
> Write tests/test_agent_e2e.py: run run_pier for flood, drought, normal, late-season with demo_mode=True. Assert no exceptions; assert plan_text non-empty; assert cache_loader used (mock network or inspect calls). Print summary.

**Acceptance:** All four scenarios complete without error; no live network calls in demo mode.

**Definition of Done (Branch E):** Agent loop works end-to-end on cached data; CLI functional; e2e tests pass. Merge into `main` (rebase onto A+B+C+D first).

---

## Branch F — feat/f-ui-demo-declaration (Streamlit UI + demo assets + AI declaration)

**Goal:** Spec §4 frontend + notes.md deliverables (30s video or ≤7 slides, AI usage declaration). Depends on A + B + C + D + E.

**Traceability:** Spec §4 (Streamlit + Folium map overlay + recovery-plan card); notes.md (30s video, English, ≤7 slides fallback, AI usage declaration with every prompt, deadline Nov 15 23:59); Spec §10 (success metrics).

**Parent:** rebase onto `main` after Branch E merged  
**Files owned:**
- `piper_agent/ui/streamlit_app.py`
- `piper_agent/ui/components.py`
- `docs/AI_USAGE_DECLARATION.md`
- `docs/PROMPT_REGISTRY.md`
- `README.md` (full)
- `demo/` video or slides assets

**Input contract (from E):** `piper_agent.agent.run_pier`, CLI.

**Tasks:**

**TF.1 — Streamlit app skeleton**  
Prompt:  
> Write piper_agent/ui/streamlit_app.py: page title "PIER — Extreme-weather Recovery Planner"; sidebar inputs lat, lon, current date, demo mode toggle (default True), scenario selector (Flood/Drought/Normal/Auto-detect); main button "Generate recovery plan"; on click call piper_agent.agent.run_pier and render outputs.

**Acceptance:** `streamlit run piper_agent/ui/streamlit_app.py --server.headless true` starts (or module parses/imports cleanly if server unavailable).

**TF.2 — Folium map overlay**  
Prompt:  
> Add a Folium map centered on (lat,lon) with a color-coded marker: flood=blue, drought=orange, none=green; popup shows event type + confidence. If streamlit-folium unavailable, render map HTML via st.components.v1.html.

**Acceptance:** Map renders at field location with event-colored marker.

**TF.3 — Recovery-plan card**  
Prompt:  
> Render a bordered card containing: event type + detection confidence (separate line); GDD window (accumulated, remaining, frost date); rescue recommendation confidence (separate line); ranked crops table (crop, plant-by date, days until deadline, GDD margin); caveat "Typical GDD values — local calibration required." If fallback: cover-crop recommendation + "The season's cash crop is lost; soil protection only." (BR-5)

**Acceptance:** Card displays all fields for flood/drought/normal/late-season.

**TF.4 — Cache indicator badge**  
Prompt:  
> Show badge: "Demo mode — data cached (no live Earthdata call)" when demo_mode=True; "Live NASA data (production path)" when false.

**Acceptance:** Badge visible and correct per toggle.

**TF.5 — Success-metrics validation (Spec §10)**  
Prompt:  
> Run final validation: (1) flood→flood, drought→drought, normal→none; (2) ≥2 eligible crops for flood & drought; (3) fallback triggers on late season + plan states cash crop lost; (4) all IMERG from cache (cache_loader used, no live calls). Print metrics report; all 4 must PASS before recording.

**Acceptance:** Metrics report 4/4 PASS.

**TF.6 — 30-second demo video (English) OR ≤7 slides**  
Prompt:  
> Produce ≤30s English demo video showing: map location → event detection + confidence → GDD window → 2–3 rescue crops with plant-by dates ranked latest-first → fallback cover crop + cash-crop-lost. Use screen capture of Streamlit or CLI. If using Hyperframes AI, note it. Add English captions. If video impossible, build ≤7-slide English deck (problem, Spec 3, 4 tools, demo result, fallback, AI usage) as PDF/Markdown.

**Acceptance:** Video ≤30s (or ≤7 slides), English, covers all five beats.

**TF.7 — AI usage declaration + prompt registry**  
Prompt:  
> Write docs/AI_USAGE_DECLARATION.md: which parts were AI-produced (code, prompts, plan, video script, slides), which were human decisions (demo dates, crop choices, go/no-go, presentation language), models/tools used, statement that every agent prompt is logged in PROMPT_REGISTRY.md. Write docs/PROMPT_REGISTRY.md listing every prompt given to an AI agent, organized by branch/task ID (TA.0 … TF.7), with full prompt text.

**Acceptance:** Both files exist; all stage prompts included keyed by task ID.

**TF.8 — README + final commit**  
Prompt:  
> Write README.md: PIER one-paragraph description (Spec 3), how to run (pip install, streamlit run, CLI), demo instructions, spec traceability table (BR-1..BR-6 → files), success-metrics results. Then `git add -A && git commit -m "Stage 9/F: UI, demo, AI declaration, README; ready for demo"`.

**Acceptance:** Working tree clean; all deliverables committed before Nov 15 23:59.

**Definition of Done (Branch F):** UI runs; map + plan card render; cache badge shows; metrics 4/4 PASS; video/slides ready; declaration + registry complete. Merge last into `main`.

---

## Integration & merge checklist

Run before each merge into `main`:

- [ ] Rebase feature branch onto latest `main`.
- [ ] Run full test suite: `pytest tests/` (all branches' tests must pass together).
- [ ] Confirm no file overlap: `git diff main...feature --name-status` shows only that branch's owned files.
- [ ] Confirm `piper_agent/contracts.py` and `cache_loader.py` are unchanged (only Branch A touches them).
- [ ] Run `python -m piper_agent --demo` end-to-end (Branch E) and `streamlit run` smoke (Branch F) after final merge.

**If a branch is blocked:** fall back to its documented mitigation (synthetic cache in A, hardcoded event date in B/C, cover-crop fallback in C/D, CLI-only demo in F) and keep merging — the demo must run on cached data.

**Hard deadline:** All 6 branches merged into `main` by Sun Nov 15, 2026, 23:59.
