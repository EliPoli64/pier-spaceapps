# PIER — POWER + IMERG Extreme-weather Recovery Planner

**NASA Space Apps Challenge — Field Shift Challenge (Spec 3: Extreme Weather)**  
**Deadline:** Nov 15, 2026, 23:59  
**Branches:** 6 isolated development branches (Erik/Alina/Neithan/Danny/Matias/Elias) — see `PLAN_SEIS_PERSONAS.md`

---

## What PIER does

When an extreme weather event (flood or drought) destroys a farmer's planned crop, PIER answers: *what can be planted now that will stabilize the soil and fit the remaining growing-season window?*

PIER pipeline (4 tools, all cached/demo-mode by design):

1. **Detect** the event from IMERG rainfall anomaly (BR-1 — anomaly threshold, not absolute)
2. **Compute** the remaining GDD (thermal-time) window from POWER temperatures to climatological frost (BR-3)
3. **Filter** rescue crops matched to the event type and remaining window (BR-2, BR-3, BR-4)
4. **Generate** a recovery plan with plant-by dates, separate confidences, and a cover-crop fallback (BR-5, BR-6)

All demo data is served from `piper_agent/data/cache/`. Live NASA Earthdata/POWER calls are labeled as a **production path only** (Spec §8, Risk register). The project runs entirely offline with synthetic cache for the hackathon demo.

---

## Quick start

### Prerequisites

```bash
pip install -r requirements.txt
```

### CLI (demo mode — cached data, no Earthdata needed)

```bash
python -m piper_agent --lat 41.8 --lon -93.6 --date 2025-05-15 --demo-name flood
```

Options:

- `--demo-name flood | drought | normal` — choose a pre-cached demo scenario
- `--demo` (default **on**) — use cached data only (no live NASA calls)
- `--no-demo` — attempt live NASA path (production; not implemented in demo UI)

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
| **Erik** | `feat/datos-cache` | `piper_agent/data/**`, cache loader, ingestion, baselines, soil, OpenET, SMAP |
| **Alina** | `feat/logica-herramientas` | `piper_agent/tools/**`, contracts, config, agent orchestration |
| **Neithan** | `feat/gdd-climate` | `fetch_power_gdd.py`, climate baselines, hemisphere support |
| **Danny** | `feat/api-backend` | `piper_agent/api/**`, FastAPI routes, contract consumption |
| **Matias** | `feat/ui-pwa` | `piper_agent/ui/**`, Streamlit, PWA, SMS gateway |
| **Elias** | `feat/docs-entrega` | `docs/**`, `.gitattributes`, `.env.example`, `requirements.txt`, `Dockerfile` |

See `PLAN_SEIS_PERSONAS.md` for complete isolation guarantees and integration protocol.

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
| BR-7 | Calibrated confidence via historical analogs | `piper_agent/tools/confidence_calibration.py` (v1.1) |
| BR-8 | Explicit exclusion reasons per crop | `piper_agent/tools/explain_exclusion.py` (v1.1) |
| BR-9 | Rescue → rotation linkage with soil‑health score | `piper_agent/tools/plan_rotation.py` (v1.2) |
| BR-10 | Farmer priority weighting (soil, revenue, water) | `piper_agent/tools/filter_rescue_crops.py` (v1.2) |
| BR-11 | Dollar‑savings estimate per recommendation | `piper_agent/tools/fetch_market_price.py` (v1.2) |
| BR-12 | Multi‑season rotation planner | `piper_agent/tools/plan_rotation.py` (v1.2) |

---

## Success metrics (Spec §10)

Verified by passing tests (`pytest tests/`: 95 tests total):

- [x] Flood demo → `event_type = flood`
- [x] Drought demo → `event_type = drought`
- [x] Normal demo → `event_type = none`
- [x] ≥2 eligible rescue crops for flood demo
- [x] ≥2 eligible rescue crops for drought demo
- [x] Fallback (cover crop) triggers when window too short; plan states "cash crop is lost"
- [x] All demo IMERG/POWER served from cache (no live calls)

---

## AI usage

Per notes.md, AI usage is declared in [`docs/AI_USAGE_DECLARATION.md`](docs/AI_USAGE_DECLARATION.md) with every agent prompt logged in [`docs/PROMPT_REGISTRY.md`](docs/PROMPT_REGISTRY.md).

Project‑level AI declaration: code, prompts, plan, and video script were generated by AI agents; demo dates, crop choices, go/no‑go, and presentation language are human decisions.

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
    cache_loader.py           # Cache‑only data loader
    rescue_crops.csv          # Spec §3 crop database
    cache/                    # Synthetic IMERG + POWER caches
    baselines/                # 10‑yr percentile baselines + frost dates
    ingestion/                # Production ETL (v1.1+)
    soil_lookup.py            # Soil texture (v1.1+)
    fetch_openet.py           # OpenET ETa (v1.1+)
    fetch_smap.py             # SMAP moisture (v1.1+)
    redis_cache.py            # Redis‑backed cache (v1.1+)
  ui/
    streamlit_app.py          # Streamlit frontend
    components.py             # Folium map, plan card, cache badge
    sms_gateway.py            # SMS/USSD fallback (P1)
    sms_simulator.py          # Demo SMS simulation (Elias)
tests/
  test_*.py                   # 95 unit/integration tests
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

# 2. Run CLI for flood demo
python -m piper_agent --lat 41.8 --lon -93.6 --date 2025-06-20 --demo-name flood

# 3. Run Streamlit
streamlit run piper_agent/ui/streamlit_app.py

# 4. Test API
uvicorn piper_agent.api.main:app
# Then: curl -X POST http://127.0.0.1:8000/generate_plan \
#   -H "Content-Type: application/json" \
#   -d '{"lat":41.8,"lon:-93.6,"date":"2025-06-20","demo_name":"flood"}'
```

---

## Data source transparency

The badge shown in the UI reflects `fuente_datos` from the agent output:

- `"sintetico"` — demo mode, data from `piper_agent/data/cache/` (default, no Earthdata needed)
- `"nasa_power"` — live POWER API call (production path)
- `"nasa_power+imerg"` — live POWER + IMERG (production path)

In demo mode (`PIER_DEMO_MODE=1`, the default), `fuente_datos` is always `"sintetico"`. No real Earthdata credentials are required.

---

## License

NASA Space Apps Challenge submission.