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
| **Elias** | `feat/docs-entrega` | `docs/**` (excluding `AI_USAGE_DECLARATION.md` and `PROMPT_REGISTRY.md` which belong to A/B), `requirements.txt`, `.gitattributes`, `.env.example`, monitoring setup | All of `piper_agent/`, `data/`, `ui//, `api/` |

Each person works in isolation. Integration happens only through:
- `run_pier(lat, lon, date, demo_mode, demo_name, pesos_agricultor, rendimiento_t_ha) -> dict` (stable contract)
- `load_demo_packet(demo_name) -> dict` (stable contract)
- New keys added by A‑team are read with `.get()` by B‑team

---

## Real API Usage — Production Path (Opt-In, Labeled)

The default demo mode uses cached/synthetic data (`PIER_DEMO_MODE=1`). A production path exists for live NASA Earthdata/POWER calls, but it is **opt-in only** and must be explicitly triggered by setting `PIER_DEMO_MODE=0`.

**Production path requirements (spec §8, Risk register):**
- `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD` must be set in `.env` (placeholder keys only in `.env.example`; never commit real credentials)
- All 95 existing tests continue to run with `demo_mode=True` — no changes to test files
- The live NASA connection is **labeled** in the output: `fuente_datos` becomes `"nasa_power"` or `"nasa_power+imerg"` instead of `"sintetico"`
- If Earthdata credentials are missing or the API fails, the agent **gracefully falls back** to synthetic cache and logs the event (circuit breaker pattern)
- Endpoints in `piper_agent/api/main.py` must respect the `demo_mode` flag and return `fuente_datos` transparently

**New task tags for production-path work** (optional, only if the team chooses to enable it):
- `PP1`: Add `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD` to `.env.example` with clear placeholder text and "never commit real credentials" warning
- `PP2`: Implement circuit breaker in `cache_loader.py` — after 3 consecutive live-call failures, fall back to synthetic cache and set `fuente_datos="sintetico"` with a logged warning
- `PP3`: Add `detect_event()` and `fetch_power_gdd()` code paths for `demo_mode=False` that call `imergpy`/`powerspec` directly (wrapped in retry/backoff)
- `PP4`: Ensure all new contract keys (`exclusiones`, `rotacion`, `ahorro`, `confianza_calibrada`, `suelo`, `ola_calor`, `fuente_datos`) are serialized in API response and read with `.get()` by B‑team
- `PP5`: Add monitoring alert when `fuente_datos` switches from live to fallback (for audit trail)

**Important:** No production-path task may be merged into master unless `demo_mode=True` tests still pass (95/95). Production paths are entirely opt-in and must not affect the hackathon demo.

---

## New Isolated Tasks for Each Branch (Code-Only, No Cross-Over)

### Erik — `feat/datos-cache` (Cache, Ingestion, Baselines, Soil, OpenET, SMAP)

**New P2 Tasks:**

| # | Task | Why/Notes |
|---|---|---|
| E8 | Add `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD` to `.env.example` with placeholder text: `"your_earthdata_username"` and `"your_earthdata_password"`; add warning comment: `"never commit real credentials"` | PP1: Production-path env vars; demo mode ignores these |
| E9 | Implement circuit breaker in `cache_loader.py`: track consecutive live‑call failures (default 3); after threshold, fall back to synthetic cache and set `fuente_datos="sintetico"` with a logged warning | PP2: Graceful fallback for production path |
| E10 | Wrap `imergpy.get_precipitation()` and `powerspec.daily()` calls in `fetch_openet_eta()` and `fetch_smap_moisture()` with retry‑backoff (3 attempts, exponential delay) and circuit breaker integration | PP3: Production‑path API calls with error handling |

**Existing tasks remain unchanged:** E1‑E7, E8‑E9 fixes. New tasks E8‑E10 are opt‑in production-path extensions that do not affect demo mode.

---

### Alina — `feat/logica-herramientas` (Tools, Contracts, Agent Orchestration)

**New P2 Tasks:**

| # | Task | Why/Notes |
|---|---|---|
| A10 | Add `PP4` contract‑key serialization test: verify that `run_pier()` returns all new contract keys (`exclusiones`, `rotacion`, `ahorro`, `confianza_calibrada`, `suelo`, `ola_calor`, `fuente_datos`) and that each is read with `.get()` in `tools/` and `api/` | Ensures production‑path keys don't break B‑team consumption |
| A11 | Implement `PP5` monitoring alert: when `fuente_datos` changes from `"nasa_power"` to `"sintetico"`, emit a structured log entry with timestamp, previous source, and reason | Operational resilience for production‑path fallback |

**Existing tasks remain unchanged:** A1‑A9. New tasks A10‑A11 are opt‑in and tested behind `demo_mode=True`.

---

### Neithan — `feat/gdd-climate` (GDD, Frost Logic, Climate Baselines)

**New P2 Tasks:**

| # | Task | Why/Notes |
|---|---|---|
| N5 | Add `--api-mode` CLI flag (default `demo`); when `live`, attempt `imergpy`/`powerspec` calls and flag result with `fuente_datos`; when `demo`, use cached data as before | Production‑path CLI option, separated from demo mode |
| N6 | Validate hemisphere‑frost logic against 10‑yr historical data: ensure `climatological_frost_date` computed from baselines matches expected pattern for given lat/lon | Confidence check for both demo and production paths |

**Existing tasks remain unchanged:** N1‑N4. New tasks N5‑N6 are opt‑in and do not alter demo‑mode behavior.

---

### Danny — `feat/api-backend` (FastAPI, Routes, Contract Consumption)

> **Status: 🚧 IN PROGRESS** — Danny (with Claude), branch `feat/api-backend`. D1–D10 implemented and tested (see `piper_agent/api/README.md`, PR #1). Waiting for review/merge.

**New P2 Tasks:**

| # | Task | Why/Notes |
|---|---|---|
| D8 | Add `demo_mode` query parameter to `/generate_plan` (default `true`); when `false`, pass through to `run_pier(demo_mode=False)` and surface `fuente_datos` in response JSON | Production‑path API toggle |
| D9 | Ensure `/health` endpoint returns `demo_mode_status: "active"` or `"production_path_available"` based on whether `EARTHDATA_USERNAME` is set (without revealing the actual username) | Operational awareness |
| D10 | Validate that all new contract keys are serialized using `.get()` pattern in response model; if any key is `None`, omit it from JSON rather than crashing | Prevents production‑path serialization failures |

**Existing tasks remain unchanged:** D1‑D7. New tasks D8‑D10 are opt‑in and behind `demo_mode` flag.

---

### Matias — `feat/ui-pwa` (Streamlit, Components, PWA, SMS Gateway)

**New P2 Tasks:**

| # | Task | Why/Notes |
|---|---|---|
| M12 | Add `demo_mode` toggle in Streamlit sidebar (default `True`); when `True`, show badge "Synthetic cache (no live Earthdata call)"; when `False`, show badge "Live NASA data (production path)" and display `fuente_datos` from agent output | Transparent UI for production path |
| M13 | When `demo_mode=False`, render `fuente_datos` badge in plan card and add small footer note: "Data from NASA POWER (live); may require Earthdata credentials" | User transparency |
| M14 | Add `POST /simulate_sms` endpoint (already D6) that respects `demo_mode` and returns appropriate badge text in SMS‑length reply | SMS gateway production-path awareness |

**Existing tasks remain unchanged:** M1‑M11. New tasks M12‑M14 are opt‑in and behind sidebar toggle.

---

### Elias — `feat/docs-entrega` (Documentation, Environment, Git Ops)

**New P2 Tasks:**

| # | Task | Why/Notes |
|---|---|---|
| E9 | Add section to `docs/AI_USAGE_DECLARATION.md`: "Production-path live NASA Earthdata/POWER calls are opt‑in only, triggered by `PIER_DEMO_MODE=0`. All demo-mode tests (95/95) use cached data only." | Documentation of API usage policy |
| E10 | Update `Dockerfile` healthcheck: `curl -f http://127.0.0.1:8000/health?demo_mode=true`; add note that `demo_mode=false` requires Earthdata credentials not available in this container | Production‑path Docker awareness |
| E11 | Add `PIER_DEMO_MODE` to `.env.example` with value `1` and explicit comment: `"1 = demo mode (cached/synthetic, recommended for hackathon); 0 = production path (live NASA, opt‑in only)"` | Clear default for all collaborators |

**Existing tasks remain unchanged:** E1‑E8. New tasks E9‑E11 are documentation/orchestration, no code in `piper_agent/`.

---

### QA / Integration (gap not covered by the 6 sections) — `feat/qa-integracion`

> **Status: ✅ Q1–Q5 done (PR pending review)** — Danny (with Claude). Owns only NEW paths: `.github/workflows/**`, `tests/acceptance/**`, `scripts/qa/**`. Touches no file owned by anyone else.

| # | Task | Why/Notes |
|---|---|---|
| Q1 | GitHub Actions QA gate (`.github/workflows/qa.yml`): full suite + acceptance + Spec §10 report on every `feat/**` push and PR | Elias's `ci.yml` only covers master/dev-elias and was failing (no fastapi, no demo cache) |
| Q2 | `tests/acceptance/`: Spec §10 success metrics + BR invariants per demo scenario; known gaps marked `xfail` with owner + task id so they flip to green as each branch lands | Shared definition of "done" across the 6 branches |
| Q3 | `scripts/qa/check_success_metrics.py`: PASS/FAIL report of Spec §10, with a network guard proving the demo is cache-only | Spec §10 "verified by network log"; useful before recording the demo |
| Q4 | `scripts/qa/branch_overlap.py`: lists files changed by more than one `feat/*` branch and changes outside each owner's paths | Ownership table has overlaps (e.g. `fetch_power_gdd.py`: Alina tools/**, Neithan, Erik E4; `config.py`: Alina + Neithan; `data/baselines/`: Erik + Neithan) |
| Q5 | Report uncovered science gaps to owners (detection ignores `current_date`, GDD remaining uses future observations, tropical drought demo uses temperate temperatures, no late-season fallback demo packet) | Not assigned in any section |

---

## Summary of Code-Only Deliverables per Person (Updated)

| Person | Branch | Key Code Deliverables (incl. new PP tasks) |
|---|---|---|
| **Erik** | `feat/datos-cache` | `cache_loader.py` with circuit breaker, `imerg_etl.py` retry‑backoff, `lookup_soil()`, `fetch_openet_eta()`, `fetch_smap_moisture()`, single `CROP_TBASE`; `.env.example` with Earthdata placeholders |
| **Alina** | `feat/logica-herramientas` | Fixed `detect_event` confidence, `filter_rescue_crops` `none` return, `generate_recovery_plan` normal‑scenario text, `compute_dollar_savings()`, `plan_rotation()`, `explain_exclusion()`, contract‑key serialization (`PP4`), monitoring alert (`PP5`) |
| **Neithan** | `feat/gdd-climate` | Hemisphere‑aware `fetch_power_gdd.py`, `--hemisphere` CLI, `season_end` in demo packets, `--api-mode` CLI flag for live data |
| **Danny** | `feat/api-backend` | `/generate_plan` with full contract serialization, `datetime.now(timezone.utc)`, `alertas` field, `/simulate_sms`, `demo_mode` query param, health endpoint awareness |
| **Matias** | `feat/ui-pwa` | Streamlit with 3 visual states, weights sliders, exclusion/rotation/savings sections, data‑source badge, `sms_gateway.py`, PWA fix (icons, paths), `demo_mode` sidebar toggle, source badges |
| **Elias** | `feat/docs-entrega` | Rewritten `README.md`, `.gitattributes`, `.env.example` with `PIER_DEMO_MODE`, `docs/contratos.md`, `docs/AI_USAGE_DECLARATION.md` update, `Dockerfile` healthcheck |

**No one works on:** video creation, slide decks, on‑screen branding, or any UI/UX polish beyond the code‑driven interface described above. The focus is entirely on making the engine reliable, multi‑hemisphere, transparent, and production‑path ready so that any presentation layer can consume it.

---

*Fused from `PLAN_PERSON_A.md`, `PLAN_PERSON_B.md`, and `quehacer.md`. All non-code elements (video, slides, presentation text) removed. 6 isolated branches. Integration only through `run_pier` and `load_demo_packet` contracts. Production‑path API usage is opt‑in only; default demo mode uses cached data and all 95 existing tests continue to pass.*