# PIER — POWER + IMERG Extreme-weather Recovery Planner

**NASA Space Apps Challenge — Field Shift Challenge (Spec 3: Extreme Weather)**  
**Deadline:** Nov 15, 2026, 23:59  
**Branches:** 6 isolated development branches (Erik/Alina/Neithan/Danny/Matias/Elias) — see `PLAN_SEIS_PERSONAS.md`

---

## What PIER does

When an extreme weather event (flood or drought) destroys a farmer's planned crop, PIER answers: *what can be planted now that will stabilize the soil and fit the remaining growing-season window?*

PIER's data path is moving to **real NASA Earthdata and partner datasets** — NASA Earthdata POWER daily weather, NASA GPM IMERG rainfall, and the plan's intended NOAA / OpenLand data layers — with real credentials and real endpoints. Synthetic cache remains as the offline fallback and for the hackathon demo, not as the project's default story.

PIER pipeline (4 tools + contracts):

1. **Detect** the event from rainfall anomaly (BR-1)
2. **Compute** the remaining GDD (thermal-time) window from POWER temperatures to climatological frost (BR-3)
3. **Filter** rescue crops matched to the event type and remaining window (BR-2, BR-3, BR-4)
4. **Generate** a recovery plan with plant-by dates, separate confidences, and a cover-crop fallback (BR-5, BR-6)

What is real today vs what is still being wired:

- **Implemented (code + tests):** tool contracts (`contracts.py`), agent orchestration (`agent.py`), `detect_event`, `fetch_power_gdd`, `filter_rescue_crops`, `generate_recovery_plan`, FastAPI API surface, Streamlit UI, PWA files, SMS gateway stub, monitoring/drift stubs, and the full demo-mode test suite.
- **Still needed for the real-data path:** real credential handling and the live Earthdata POWER / IMERG client path, the NOAA and OpenLand clients/endpoints referenced in the plan, and the live-data branches of the tools under a clear `PIER_DEMO_MODE=0` opt-in. Today, live data is a labeled production path that currently raises `NotImplementedError` in `agent.py`.

---

## Quick start

### Prerequisites

```bash
pip install -r requirements.txt
```

### CLI (demo mode — cached data, no Earthdata needed)

```bash
python -m piper_agent --lat 41.8 --lon -93.6 --date 2025-05-15 --demo
```

Options:

- `--demo` (default **on**) — use cached data only (no live NASA calls)
- `--no-demo` — attempt the live NASA path (production; not implemented yet)
- `--demo-name flood | drought | normal` — choose a specific cached demo scenario

### Streamlit UI

```bash
streamlit run piper_agent/ui/streamlit_app.py
```

Open the local URL shown by Streamlit. Enter lat/lon/date, pick a scenario, and click **Generate recovery plan**.

### API

```bash
uvicorn piper_agent.api.main:app
```

Default: `http://127.0.0.1:8000`.  
Endpoints: `POST /generate_plan`, `POST /detect_event`, `POST /recommend_crops`, `GET /health`.

### PWA

Open `http://localhost:8000/pwa/` for the mobile‑first progressive web app (served from the API's StaticFiles mount).

---

## Branches & ownership (6‑person isolated development)

| Person | Branch | Owns (file paths) |
|---|---|---|
| **Erik** | `feat/datos-cache` | `piper_agent/data/**`, cache loader, ingestion point, baselines, soil/ET/moisture fetchers |
| **Alina** | `feat/logica-herramientas` | `piper_agent/tools/**`, contracts, config, agent orchestration |
| **Neithan** | `feat/gdd-climate` | `fetch_power_gdd.py`, climate baselines, hemisphere support |
| **Danny** | `feat/api-backend` | `piper_agent/api/**`, FastAPI routes, contract consumption |
| **Matias** | `feat/ui-pwa` | `piper_agent/ui/**`, Streamlit, PWA, SMS gateway |
| **Elias** | `feat/docs-entrega` | `docs/**`, `.gitattributes`, `.env.example`, `requirements.txt`, `Dockerfile` |

See `PLAN_SEIS_PERSONAS.md` for the isolation guarantees, the integration contract (`run_pier(...)` and `load_demo_packet(...)`), and the real-data split per person.

---

## Data sources (current direction)

PIER is pivoting to real sources, in this order of what the team is targeting:

- **NASA Earthdata POWER** — daily point weather used for GDD, frost, and temperature baselines.
- **NASA GPM IMERG** — daily rainfall used for flood/drought anomaly detection.
- **NOAA** — referenced in the plan as an intended data layer; a client and endpoint still need to be chosen and implemented.
- **OpenLand / OpenET-style ETa and SMAP-style soil moisture** — referenced in the plan as intended layers; clients and endpoints still need to be chosen and implemented.

"Real" means real credentials and real endpoints, not just cache filenames. `.env.example` holds placeholder-only keys. Real credentials are **never** committed.

---

## Demo mode vs live data

- Default: `PIER_DEMO_MODE=1` (demo mode). Data is served from cache; `fuente_datos` is `"sintetico"`.
- Production path: `PIER_DEMO_MODE=0` (opt-in). This is the labeled live NASA path. Today it is not implemented in `agent.py` and raises `NotImplementedError`.

Cached demo data can be regenerated with `python piper_agent/data/generate_cache.py` after a fresh clone.

---

## Business rules traceability

| BR | Rule | Implemented in |
|---|---|---|
| BR-1 | Event detection: anomaly threshold (3‑day cum vs min(p95,100mm); 30‑day cum vs p10) | `piper_agent/tools/detect_event.py` |
| BR-2 | Event type drives crop filter — never both at once | `piper_agent/tools/filter_rescue_crops.py` |
| BR-3 | GDD‑based window: gdd_req ≤ gdd_remaining × 0.8 | `piper_agent/tools/filter_rescue_crops.py` |
| BR-4 | Explicit plant‑by date; rank latest‑first | `piper_agent/tools/filter_rescue_crops.py` |
| BR-5 | Cover‑crop fallback; "cash crop is lost" statement | `piper_agent/tools/generate_recovery_plan.py` |
| BR-6 | Separate event‑detection vs rescue‑recommendation confidence | `piper_agent/tools/generate_recovery_plan.py` |
| BR-7 | Calibrated confidence via historical analogs | roadmap / calibration layer to add |
| BR-8 | Explicit exclusion reasons per crop | `piper_agent/tools/explain_exclusion.py` (v1.1) |
| BR-9 | Rescue → rotation linkage with soil‑health score | `piper_agent/tools/plan_rotation.py` (v1.2) |
| BR-10 | Farmer priority weighting (soil, revenue, water) | `piper_agent/tools/filter_rescue_crops.py` (v1.2) |
| BR-11 | Dollar‑savings estimate per recommendation | `piper_agent/tools/fetch_market_price.py` (v1.2) |
| BR-12 | Multi‑season rotation planner | `piper_agent/tools/plan_rotation.py` (v1.2) |

---

## Success metrics (Spec §10)

Verified by passing tests (`python -m pytest tests/ -q --tb=short`):

- [x] Flood demo → `event_type = flood`
- [x] Drought demo → `event_type = drought`
- [x] Normal demo → `event_type = none`
- [x] ≥2 eligible rescue crops for flood demo
- [x] ≥2 eligible rescue crops for drought demo
- [x] Fallback (cover crop) triggers when window too short; plan states "cash crop is lost"
- [x] All cached demo IMERG/POWER served from cache (no live calls) in demo mode

Current local result: 202 passed, 9 xfailed, 0 failed (`python -m pytest tests/ -q --tb=short`).

---

## What still needs real endpoints / real clients

This repo already implements the engine and the demo path. The real-data pivot still needs decisions and code for:

- **NASA Earthdata POWER live client/path** — endpoint, auth, and the `demo_mode=False` branch in the tools.
- **NASA GPM IMERG live client/path** — endpoint, auth, and the `demo_mode=False` branch in `detect_event`.
- **NOAA client/endpoint** — which NOAA source and how it is consumed; not yet defined in this repo.
- **OpenLand / OpenET / SMAP client/endpoint** — which source and how it is consumed; not yet defined in this repo.
- **Real credential handling** — placeholder keys only in `.env.example`; real values are set locally and never committed.

Those items are owned per person in `PLAN_SEIS_PERSONAS.md`.

---

## AI usage

Per notes.md, AI usage is declared in [`docs/AI_USAGE_DECLARATION.md`](docs/AI_USAGE_DECLARATION.md) with every agent prompt logged in [`docs/PROMPT_REGISTRY.md`](docs/PROMPT_REGISTRY.md).

Project‑level AI declaration: code, prompts, plan, and video script were generated by AI agents; demo dates, crop choices, go/no‑go, and presentation language are human decisions.

---

## Reproducibility

- Cache is gitignored and regenerated by `python piper_agent/data/generate_cache.py`.
- Baselines are regenerated together with the cache so demo packets carry `tropical`, `season_end`, and `fuente_datos`.
- Demo-mode tests are deterministic in cache mode.

---

## Project structure

```text
piper_agent/
  contracts.py        # Shared data contracts (EventResult, GddResult, CropRecommendation, RecoveryPlan)
  config.py           # Constants (TBASE, safety margin 0.8, tolerance ordinals)
  agent.py            # Tool‑calling loop (run_pier)
  __main__.py         # CLI entry point
  tools/
    detect_event.py           # BR-1
    fetch_power_gdd.py        # BR-3
    filter_rescue_crops.py    # BR-2,3,4
    generate_recovery_plan.py # BR-5,6
  data/
    cache_loader.py           # Cache‑first data loader
    rescue_crops.csv          # Spec §3 crop database
    cache/                    # Synthetic IMERG + POWER caches
    baselines/                # Percentile baselines + frost dates
    generate_cache.py         # Regenerates synthetic cache + baselines
    ingestion/                # Production ETL point (real-data path)
    soil_lookup.py            # Soil texture (v1.1+)
    fetch_openet.py           # OpenET ETa (v1.1+)
    fetch_smap.py             # SMAP moisture (v1.1+)
    redis_cache.py            # Redis‑backed cache (v1.1+)
  ui/
    streamlit_app.py          # Streamlit frontend
    components.py             # Folium map, plan card, cache badge
    sms_gateway.py            # SMS/USSD fallback (P1)
    sms_simulator.py          # Demo SMS simulation (Elias)
    pwa/                      # Progressive web app files
  api/
    main.py                   # FastAPI app
  monitoring/
    __init__.py
    drift.py                  # Drift detection stub
tests/
  test_*.py                   # Unit/integration tests
demo/
  flood_demo.json, drought_demo.json, normal_demo.json
docs/
  AI_USAGE_DECLARATION.md
  PROMPT_REGISTRY.md
  contratos.md              # A‑team/B‑team contract (Elias)
  historico/                # Historical plans (plan.md, planidivido.md moved here)
requirements.txt
.env.example
Dockerfile
.gitignore
README.md
```

---

## Running the full pipeline (Elias's integration check)

From a clean clone, after all 6 branches have merged into `master`:

```bash
# 1. Install
pip install -r requirements.txt

# 2. Regenerate cache if you cloned without it
python piper_agent/data/generate_cache.py

# 3. Run CLI for flood demo
python -m piper_agent --lat 41.8 --lon -93.6 --date 2025-06-20 --demo --demo-name flood

# 4. Run Streamlit
streamlit run piper_agent/ui/streamlit_app.py

# 5. Test API
uvicorn piper_agent.api.main:app
# Then: curl -X POST http://127.0.0.1:8000/generate_plan \
#   -H "Content-Type: application/json" \
#   -d '{"lat":41.8,"lon":-93.6,"date":"2025-06-20","demo_name":"flood"}'
```

---

## Credential guidance

- `.env.example` contains **placeholder-only** keys.
- Real Earthdata / NOAA / OpenLand credentials are set in a local `.env` and are **never committed**.
- Demo mode needs no credentials. Live data needs the relevant credentials for the chosen endpoints.
- The live path is labeled in the output via `fuente_datos` and is opt-in through `PIER_DEMO_MODE=0`.

---

## License

NASA Space Apps Challenge submission.