# AI Usage Declaration — PIER (Spec 3: Extreme Weather Recovery)

**Project:** PIER — POWER + IMERG Extreme-weather Recovery Planner  
**Challenge:** NASA Space Apps — Field Shift Challenge (Spec 3: Extreme Weather)  
**Deadline:** Nov 15, 2026, 23:59

## 1. What AI was used for

AI agents (OpenCode) were used to implement the entire PIER codebase, following a stage-by-stage implementation plan (`plan.md`). Specifically:

| Area | AI contribution |
|---|---|
| Repository scaffolding | Folder tree, `__init__.py` files, `.gitignore`, `Dockerfile`, `requirements.txt` |
| Data layer | `cache_loader.py`, `rescue_crops.csv`, synthetic IMERG/POWER cache generator (`generate_cache.py`), 3 demo packets |
| Tool 1 — detect_event | BR-1 anomaly-threshold event detection (flood/drought/none) + unit tests |
| Tool 2 — fetch_power_gdd | BR-3 GDD accumulation + remaining-to-frost model + unit tests |
| Tool 3 — filter_rescue_crops | BR-2/3/4 crop filtering by event type + GDD window + plant-by dates + ranking + unit tests |
| Tool 4 — generate_recovery_plan | BR-5 cover-crop fallback + BR-6 separate confidences + plan text generation + smoke tests |
| Agent orchestration | `agent.py` tool-calling loop, `__main__.py` CLI, end-to-end tests |
| UI | `streamlit_app.py`, `components.py` (Folium map, recovery-plan card, cache badge) |
| Documentation | This declaration, `PROMPT_REGISTRY.md`, `README.md` |
| Demo data | Synthetic IMERG/POWER caches (no live Earthdata credentials available) |

## 2. Human decisions (not AI)

- Demo locations and dates (US Midwest flood, Horn of Africa drought, Iowa normal)
- Crop database values (from Spec §3, with "local calibration required" caveat)
- Go/no-go scope-cutting decisions (cache-only demo, synthetic data fallback)
- Presentation language and demo scenario selection
- Decision to use synthetic cache data when Earthdata credentials were unavailable

## 3. Models and tools used

- **OpenCode** (Nemotron model) — code implementation, test writing, plan execution
- **Streamlit 1.67.0**, **Folium 0.20.0**, **pandas 3.1.1**, **numpy 2.4.6** — UI and data stack
- **pytest 9.2.0** — test framework
- **Python 3.14.10** — runtime

No Hyperframes AI was used for video generation (time constraint).

## 4. AI usage statement

Every prompt given to the AI agent during implementation is logged in [`PROMPT_REGISTRY.md`](PROMPT_REGISTRY.md), organized by stage/task ID (T0.0 through T9.2 per `plan.md`).

## 5. Evaluation criteria alignment

- **Influence:** PIER addresses the "extreme weather" and "declining soil health" pressures from the Field Shift Challenge by recommending rescue crops that stabilize soil after flood/drought.
- **Creativity:** Uses GDD-based thermal-time windows (not calendar-based) for rescue-crop eligibility, with separate event-detection and rescue-confidence reporting.
- **Validity:** All business rules (BR-1 through BR-6) from Spec §5 are implemented and verified by 37 passing unit/integration tests.
- **Relevance:** Uses NASA IMERG and POWER Earth observations as specified; demo runs entirely on cached data so it works without live API credentials.
- **Presentation:** Streamlit UI with Folium map overlay, recovery-plan card, and cache-mode badge; CLI for headless demo.

## 6. Real API usage policy (production path, opt-in only)

Live NASA Earthdata / partner data calls are **opt-in only** and must be explicitly triggered by setting `PIER_DEMO_MODE=0` in the environment. This policy is independent of the AI implementation process and applies to all users of the PIER codebase.

**Key rules:**

- **Default mode is demo (`PIER_DEMO_MODE=1`):** All demo-mode operations use cached/synthetic data (`piper_agent/data/cache/`, `piper_agent/data/baselines/`). No live API calls are made.
- **Production path requires credentials:** To enable live NASA calls, set `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD` in the environment (never commit real credentials).
- **All existing tests run with `demo_mode=True`:** No test file changes are required or permitted for the production path. Production functionality is tested behind the `demo_mode` flag.
- **Graceful fallback:** If Earthdata credentials are missing, malformed, or any live API fails, the pipeline automatically falls back to synthetic cache and logs the event with a `fuente_datos="sintetico"` label.
- **Source transparency:** The `fuente_datos` field in every agent output reflects the actual data source used: `"sintetico"`, `"nasa_power"`, or `"nasa_power+imerg"`. This is always visible in the UI and API response.

**Live-data services this codebase can contact (when `PIER_DEMO_MODE=0` and the relevant key is set):**

| Service | What it provides | Required credential | Fallback when absent |
|---|---|---|---|
| NASA Earthdata POWER (daily point) | T2M_MAX, T2M_MIN, PRECTOTCORR, GWETROOT | None (public endpoint) | Synthetic cache fallback |
| NASA GPM IMERG (via imergpy / GES DISC OTF) | Daily precipitation | `EARTHDATA_USERNAME` + `EARTHDATA_PASSWORD` | POWER `PRECTOTCORR` as declared rainfall substitute, labeled `"nasa_power"` |
| OpenET | Actual evapotranspiration (ETa) | `PIER_OPENET_API_KEY` | Hargreaves ET0 from POWER temperatures, labeled `"nasa_power_hargreaves"` |
| NASA SMAP | Root-zone soil moisture | `PIER_SMAP_API_KEY` | POWER `GWETROOT`, labeled `"nasa_power_gwetroot"` |
| SoilGrids / ISRIC | Soil texture + water-holding properties | None (public endpoint) | Climate-zone texture estimate |

**What is never sent anywhere:**

- Real credentials are never committed to the repository and are never logged.
- Farmer calibration observations (`piper_agent/data/cache/calibracion/`) are stored locally per coordinate and are never transmitted.
- The demo path never contacts any external service; it uses only the synthetic cache.

**Why this policy exists:**

1. **Hackathon compliance:** The NASA Space Apps demo must run with cached data so it works without live credentials. Spec §8 labels the live path as "production" only.
2. **Reliability:** Live NASA / partner services depend on external endpoints (GES DISC, Earthdata OTF, OpenET, SMAP, SoilGrids) that may be unavailable during a hackathon or demo.
3. **Safety:** Production-path behavior must never break demo-mode functionality or existing tests.

**How to enable production path:**

```bash
# 1. Set Earthdata credentials (never commit to repo)
export EARTHDATA_USERNAME=your_username
export EARTHDATA_PASSWORD=your_password

# 2. Set PIER_DEMO_MODE=0 to enable live calls
export PIER_DEMO_MODE=0

# 3. Run (live NASA path will be attempted)
python -m piper_agent --lat 41.8 --lon -93.6 --date 2025-06-20 --no-demo
```

**What happens in production mode:**

- The ingestion pipeline (`piper_agent/data/ingestion/pipeline.py`) becomes the single real-data entry point.
- `detect_event()` and `fetch_power_gdd()` consume live POWER / IMERG data through that pipeline instead of `cache_loader`.
- Output `fuente_datos` becomes `"nasa_power"` or `"nasa_power+imerg"` instead of `"sintetico"`.
- If any live API fails, the circuit breaker (`piper_agent/data/resiliencia.py`) opens and the result falls back to synthetic cache with a logged warning.

**What stays the same in both modes:**

| Aspect | Demo mode | Production path |
|---|---|---|
| `run_pier` signature | Unchanged | Unchanged |
| All contract keys | Available via `.get()` | Available via `.get()` |
| Existing tests | ✅ Pass unchanged | ✅ Pass unchanged |
| UI rendering | Uses `.get()` | Uses `.get()` |
| Output structure | Same dict | Same dict + `fuente_datos` label |

This policy ensures that real API usage is a transparent, optional enhancement that does not affect the hackathon demo or the existing test suite.

## 7. Data use and privacy

- PIER stores synthetic cache under `piper_agent/data/cache/` and `piper_agent/data/baselines/`. These are regenerated by `python -m piper_agent.data.generate_cache` and are gitignored.
- PIER stores production real-data cache under `piper_agent/data/cache/real/`, `piper_agent/data/cache/openet/`, and `piper_agent/data/cache/smap/`. These are optional and gitignored.
- PIER stores farmer calibration observations under `piper_agent/data/cache/calibracion/`. These are personal per-coordinate observations, gitignored, and never transmitted.
- PIER does not collect, store, or transmit any personal data about farmers beyond what is explicitly supplied in a calibration observation.

## 8. Reproducibility

- A deterministic demo result is obtained by cloning the repo, setting `PIER_DEMO_MODE=1`, and running the CLI or API with one of the cached demo scenarios (`flood`, `drought`, `normal`, `late_flood`).
- The synthetic cache is regenerated by `python -m piper_agent.data.generate_cache`. The same generator and seed produce the same cache on every clean run.
- The contract version is the code version in this repo at the time of the run. Contract keys are read with `.get()` so the output stays stable as new keys are added.
- The real-data path is reproducible only when the same credentials, same endpoints, and same circuit-breaker state are used; otherwise the fallback path is taken and labeled accordingly.
