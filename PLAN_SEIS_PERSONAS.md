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

> **Status: ✅ DONE** — D1–D10 merged (PR #1).

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

> **Status: ✅ Q1–Q5 merged · ✅ Q6–Q7 merged (PR #8)** — Danny (with Claude). Owns only NEW paths: `.github/workflows/**`, `tests/acceptance/**`, `scripts/qa/**`. Touches no file owned by anyone else.

| # | Task | Why/Notes |
|---|---|---|
| Q1 | GitHub Actions QA gate (`.github/workflows/qa.yml`): full suite + acceptance + Spec §10 report on every `feat/**` push and PR | Elias's `ci.yml` only covers master/dev-elias and was failing (no fastapi, no demo cache) |
| Q2 | `tests/acceptance/`: Spec §10 success metrics + BR invariants per demo scenario; known gaps marked `xfail` with owner + task id so they flip to green as each branch lands | Shared definition of "done" across the 6 branches |
| Q3 | `scripts/qa/check_success_metrics.py`: PASS/FAIL report of Spec §10, with a network guard proving the demo is cache-only | Spec §10 "verified by network log"; useful before recording the demo |
| Q4 | `scripts/qa/branch_overlap.py`: lists files changed by more than one `feat/*` branch and changes outside each owner's paths | Ownership table has overlaps (e.g. `fetch_power_gdd.py`: Alina tools/**, Neithan, Erik E4; `config.py`: Alina + Neithan; `data/baselines/`: Erik + Neithan) |
| Q5 | Report uncovered science gaps to owners (detection ignores `current_date`, GDD remaining uses future observations, tropical drought demo uses temperate temperatures, no late-season fallback demo packet) | Not assigned in any section |
| Q6 | Unowned gap: event detection must use the requested `current_date` (window = last 7 days ending today) instead of the demo packet's fixed window; auto-detect picks the dataset by location, not by event | `agent.py` + `detect_event.py` minimal change, coordinated with Alina |
| Q7 | Unowned gap: add a `late_flood` demo packet that shows the BR-5 fallback without typing a date by hand | `demo/late_flood_demo.json`, coordinated with Erik |

---

## Next Wave: Real Data, Real Results — One Branch Per Person

The six branches above get PIER working in demo mode on the hackathon floor. To turn it into a usable tool that can run on real coordinates with real data and produce defensible results (not just a hackathon showcase), the following work remains. Each person gets one extra real-data branch. The file ownership is split so no two people touch the same file, even across the existing branches and these new ones.

Prerequisite: the real-data modules listed below already exist in this repo and already have tests. This wave is mostly about coordination, wiring, and guardrails — choosing exactly who owns the live-data path, the tool branches, the climate interpretation, the API hardening, the operator UI, and the delivery packaging — not about rewriting those modules from scratch.

Existing real-data modules that the branches below coordinate around:
- `piper_agent/data/ingestion/pipeline.py` — `ingerir_punto()`, the real-data entry point for temperature + rainfall + source label.
- `piper_agent/data/ingestion/imerg_etl.py` — `descargar_power()`, `actualizar_cache_real()`, IMERG fetch with retry and circuit breaker.
- `piper_agent/data/climatologia.py` — versioned per-region climatologies and `clasificar_valor()`.
- `piper_agent/data/fetch_openet.py` — OpenET ETa / Hargreaves fallback.
- `piper_agent/data/fetch_smap.py` — SMAP soil moisture / GWETROOT fallback.
- `piper_agent/data/soil_lookup.py` — SoilGrids lookup / climate-zone fallback.
- `piper_agent/data/calibracion.py` — farmer observations and local correction factor.
- `piper_agent/data/resiliencia.py` — retry, backoff, and shared circuit breaker.
- `piper_agent/tools/confidence_calibration.py` — conformal confidence calibration.

The file split below keeps those existing modules assigned to one owner each in the real-data wave. The only shared files remain the integration contracts: `run_pier(...)` and `load_demo_packet(...)`, plus the new contract keys that downstream code already reads with `.get()`.

### Danny — Production‑ready API, auth, records, and audit

> **Status: ✅ DONE (merged, PR #11; rename fix PR #14)** — Danny (with Claude), branch `feat/api-produccion`: run store + per-coordinate history, CSV/JSON exports, persistent audit trail with evidence, `/ready`, demo/full views, multi-key auth required in production. Also the QA / Integration next-wave items (lint gate, ownership table, live-vs-cache verification).
- Harden the FastAPI layer for real use: proper request validation, per‑coordinate result storage (so a grower or operator can revisit a past plan), export formats (CSV/JSON), and a small auth or API-key gate so the public endpoint is not open.
- Add an audit trail for every run: inputs, `fuente_datos`, which cache/live path was taken, which circuit-breaker state existed, and which contract keys were present, so the system can later answer "why did it give this recommendation on this date."
- Make the health and readiness endpoints actually useful in production: data recency, last successful live call, current fallback state, and any outages or degraded sources, rather than a single boolean.
- Separate the demo-mode contract from any production-only contract extensions so the API can serve a stripped demo payload to the hackathon and a richer production payload to real users without two code paths forking the whole app.
### Erik — `feat/datos-cache` (existing) + `feat/ingesta-real`

**Owns on the new branch:** `piper_agent/data/ingestion/imerg_etl.py` production polish, `piper_agent/data/ingestion/pipeline.py` production polish, `piper_agent/data/climatologia.py` production polish, `piper_agent/data/fetch_openet.py` production polish, `piper_agent/data/fetch_smap.py` production polish, `piper_agent/data/soil_lookup.py` production polish, `piper_agent/data/calibracion.py` production polish, `piper_agent/data/resiliencia.py` production polish, plus any new files under `piper_agent/data/**` that Erik creates.

**What Erik does on this branch, in priority order:**
1. Verify that each existing real-data module already has a clean `demo_mode`-aware contract: cache-first, live only when `PIER_DEMO_MODE=0`, graceful fallback to synthetic with `fuente_datos` labeling, and no hard network dependency in demo mode. Fix any module that currently hard-fails or accidentally makes live calls in demo mode.
2. Make `ingerir_punto()` the single real-data entry point that `agent.py` and the tools call in production, so there is one place that decides POWER vs IMERG vs fallback and one place that writes cached real results under `data/cache/real/`.
3. Add the Earthdata credential checks and circuit-breaker wiring so that a missing or invalid credential never crashes the pipeline; it just yields `fuente_datos="nasa_power"` or `"sintetico"` with a recorded `motivo_respaldo`.
4. Confirm `actualizar_cache_real()` can refresh a demo scenario's cache from real NASA POWER/IMERG when run explicitly, and that it leaves demo mode untouched otherwise.

**Does NOT touch:** `piper_agent/agent.py`, `piper_agent/tools/**`, `piper_agent/api/**`, `piper_agent/ui/**`, `piper_agent/monitoring/**`, `docs/**`, `Dockerfile`, `.env.example`, `.gitignore`, `requirements.txt`.

### Alina — `feat/logica-herramientas` (existing) + `feat/herramientas-vivos`

**Owns on the new branch:** `piper_agent/tools/detect_event.py` production branch, `piper_agent/tools/fetch_power_gdd.py` production branch, `piper_agent/tools/filter_rescue_crops.py` production branch, `piper_agent/tools/generate_recovery_plan.py` production branch, `piper_agent/tools/confidence_calibration.py` production branch, `piper_agent/agent.py` orchestration shape for the production path, and any new files under `piper_agent/tools/**` that Alina creates.

**What Alina does on this branch, in priority order:**
1. Give each tool a clean `demo_mode` / data-source parameter so it can run against live data from `ingerir_punto()`, `obtener_climatologia()`, `lookup_soil()`, OpenET, and SMAP instead of only `cache_loader`. Keep the existing cache-based signatures working unchanged.
2. Make the production path produce the already-contracted keys through the tools when live data is available: `exclusiones`, `rotacion`, `ahorro`, `confianza_calibrada`, `suelo`, `ola_calor`, `fuente_datos`. Prefer adding these as tool outputs first; only touch `contracts.py` if a new key truly needs to be part of a dataclass the tools already return.
3. Ensure every new or changed key is readable downstream with `.get()` so the API and UI do not break when a live run has not filled a key yet.
4. Add the failure taxonomy semantics the plan calls for: distinguish "no data" from "conflicting data" from "data suggests normal conditions" at the tool level, so the orchestration can route them differently instead of treating all missing live data as one case.

**Does NOT touch:** `piper_agent/data/**` implementation (Erik owns that), `piper_agent/api/**`, `piper_agent/ui/**`, `piper_agent/monitoring/**`, `docs/**`, `Dockerfile`, `.env.example`, `.gitignore`, `requirements.txt`. Alina may read cache/ingestion outputs, but should not own or rewrite ingestion logic.

### Neithan — `feat/gdd-climate` (existing) + `feat/clima-multihemisferio`

**Owns on the new branch:** `piper_agent/tools/fetch_power_gdd.py` climate correctness work (the hemisphere/frost/season pieces that live in the GDD tool itself), `piper_agent/data/baselines/**` climate baseline work that Neithan owns, and any new files under `piper_agent/data/baselines/**` that Neithan creates. If Neithan already owns a climate slice of `piper_agent/config.py` in the existing plan, Neithan may also own that slice here; otherwise `config.py` changes belong to the branch that already owns them.

**What Neithan does on this branch, in priority order:**
1. Stabilize the GDD and frost logic so it behaves correctly in both hemispheres and across temperate/tropical boundaries when fed real POWER data from the ingestion pipeline, not just the synthetic cache.
2. Add season detection / windowing semantics that the real-data path can use: planting, vegetative, flowering, harvest, post-harvest, so a frost warning or heat alert means the right thing at the right time of season.
3. Validate the real-data GDD/frost behavior against the existing demo packets and against at least one representative coordinate per regime (temperate north, temperate south, tropical) so the branch can be checked without depending on a single test site.
4. Hook climate outputs into the contract keys that come from climate (`ola_calor`, `suelo` where soil is climate-informed, inputs to `confianza_calibrada`) with real units and thresholds, and expose the agronomic rationale as machine-readable metadata.

**Does NOT touch:** `piper_agent/data/ingestion/**`, `piper_agent/data/fetch_openet.py`, `piper_agent/data/fetch_smap.py`, `piper_agent/data/soil_lookup.py`, `piper_agent/data/calibracion.py`, `piper_agent/data/resiliencia.py`, `piper_agent/api/**`, `piper_agent/ui/**`, `piper_agent/monitoring/**`, `docs/**`, `Dockerfile`, `.env.example`, `.gitignore`, `requirements.txt`. In particular, Neithan does not own the ingestion pipeline or the OpenET/SMAP/soil/calibration modules — those belong to Erik's real-data layer.

### Danny — `feat/api-backend` (existing) + `feat/api-produccion`

**Owns on the new branch:** `piper_agent/api/**` production hardening, including `piper_agent/api/main.py`, `piper_agent/api/routes.py`, `piper_agent/api/services.py`, `piper_agent/api/schemas.py`, `piper_agent/api/sms.py`, and any new files under `piper_agent/api/**` that Danny creates.

**What Danny does on this branch, in priority order:**
1. Harden the API for real use: explicit request validation, per-coordinate result storage so a grower or operator can revisit a past plan, export paths (CSV/JSON), and an API-key or auth gate so the public endpoint is not open by default.
2. Add an audit trail for every run: inputs, `fuente_datos`, which cache/live path was taken, which circuit-breaker state existed, and which contract keys were present, so the system can later answer "why this recommendation on this date."
3. Make the health/readiness endpoints actually useful in production: data recency, last successful live call, current fallback state, and any degraded sources, rather than a single status word.
4. Keep the demo-mode contract separable from any production-only contract extensions so the API can serve a stripped demo payload to the hackathon and a richer production payload to real users without forking the whole app.

**Does NOT touch:** `piper_agent/data/**`, `piper_agent/tools/**`, `piper_agent/ui/**`, `piper_agent/monitoring/**`, `docs/**` (except anything Danny already owns in the existing plan), `Dockerfile`, `.env.example`, `.gitignore`, `requirements.txt`.

### Matias — `feat/ui-pwa` (existing) + `feat/interfaz-operador`

**Owns on the new branch:** `piper_agent/ui/**` production UI work, including `piper_agent/ui/streamlit_app.py`, `piper_agent/ui/components.py`, `piper_agent/ui/sms_gateway.py`, `piper_agent/ui/sms_simulator.py`, PWA files, and any new files under `piper_agent/ui/**` that Matias creates.

**What Matias does on this branch, in priority order:**
1. Build the operator-facing UI around a real workflow rather than static demo cards: paste or pick a coordinate, choose a date range, see which data source was used, inspect the evidence behind each recommendation, and export or share a plan.
2. Make the UI correctly reflect the production path when it is enabled — live-data badge, credential-status awareness, explicit "this run used synthetic cache" indicators, and `fuente_datos` surfaced from the agent response rather than inferred.
3. Add SMS / WhatsApp / email channel hooks beyond the simulator so an operator in the field can actually receive a plan in the right language and length, with a short code and a link to the full dashboard when needed.
4. Support Spanish (and any other language the team can justify) for operator-facing text, and keep the demo and production UI paths visually distinct so nobody mistakes a demo for a live operational tool.

**Does NOT touch:** `piper_agent/data/**`, `piper_agent/tools/**`, `piper_agent/api/**`, `piper_agent/monitoring/**`, `docs/**` (except anything Matias already owns), `Dockerfile`, `.env.example`, `.gitignore`, `requirements.txt`.

### Elias — `feat/docs-entrega` (existing) + `feat/entrega-produccion`

**Owns on the new branch:** production-path documentation and packaging outside `piper_agent/`: `docs/**` production-path docs, `.env.example`, `.gitignore`, `requirements.txt`, `Dockerfile`, and any new documentation or packaging files Elias creates outside `piper_agent/`.

**What Elias does on this branch, in priority order:**
1. Finish the AI usage / data declaration so it accurately covers both demo and production paths: which external services are contacted, what is cached, what is persisted, what is never sent anywhere, and what happens when credentials are missing or the live path fails.
2. Update `.env.example` so it documents the real-data credentials and toggles clearly: Earthdata username/password, OpenET key, SMAP key, SoilGrids usage, `PIER_DEMO_MODE`, the demo/production distinction, and an explicit "never commit real credentials" warning.
3. Update `Dockerfile` and the container story so the default image is demo-safe, the production path is opt-in, the healthcheck is correct for the mode it targets, and runtime credential mounting is documented rather than assumed.
4. Add a reproducibility checklist and packaging story: which cache version produced which result, which contract version was used, how to regenerate the demo exactly, and how the same repo can later be pointed at real credentials without re-plumbing.
5. Keep the delivery surface code-only: README, contracts, env examples, Dockerfile/healthcheck, CI, and any export or packaging scripts — nothing that depends on video, slides, or presentation polish.

**Does NOT touch:** `piper_agent/**` code files beyond what Elias already owns in the existing plan. If a docs-only or packaging-only change requires a tiny coordination point with another branch, Elias coordinates through the existing contract points rather than editing that branch's files.

---

### QA / Integration — Shared gating and truth for the next wave

> **Status: 🚧 IN PROGRESS** — Danny (with Claude), branch `feat/qa-brechas-cierre`: gap registry (each gap fixed / accepted with rationale / follow-up with named owner), enforced by the acceptance suite and shown in CI.
- Keep the QA gate on every `feat/*` branch so new real-data work cannot land without passing lint, the full test suite, and the acceptance criteria that match the current demo scenarios.
- Maintain the overlap detector and ownership table so the real-data work stays isolated the same way the demo work did — especially around shared files like `config.py`, `contracts.py`, and `data/baselines/`.
- Keep the success-metric script up to date with whatever "real results" means at delivery time, with a network guard proving whether a given run used live data or cache, so claims about live data are verifiable rather than asserted.
- Carry forward the known science gaps report and make each gap either fixed, explicitly accepted with a documented rationale, or marked as a post-hackathon follow-up owned by a named person.

---

### Real-data wave — ownership summary

| Person | Existing branch | New real-data branch | Owns (real-data wave) | Does NOT touch |
|---|---|---|---|---|
| Erik | `feat/datos-cache` | `feat/ingesta-real` | `piper_agent/data/ingestion/**`, `piper_agent/data/climatologia.py`, `piper_agent/data/fetch_openet.py`, `piper_agent/data/fetch_smap.py`, `piper_agent/data/soil_lookup.py`, `piper_agent/data/calibracion.py`, `piper_agent/data/resiliencia.py`, new `piper_agent/data/**` |
| Alina | `feat/logica-herramientas` | `feat/herramientas-vivos` | `piper_agent/tools/**`, `piper_agent/agent.py` production orchestration shape, new `piper_agent/tools/**` |
| Neithan | `feat/gdd-climate` | `feat/clima-multihemisferio` | `piper_agent/tools/fetch_power_gdd.py` climate pieces, `piper_agent/data/baselines/**`, Neithan's climate slice of `piper_agent/config.py` if any |
| Danny | `feat/api-backend` | `feat/api-produccion` | `piper_agent/api/**`, new `piper_agent/api/**` |
| Matias | `feat/ui-pwa` | `feat/interfaz-operador` | `piper_agent/ui/**`, new `piper_agent/ui/**` |
| Elias | `feat/docs-entrega` | `feat/entrega-produccion` | `docs/**` production docs, `.env.example`, `.gitignore`, `requirements.txt`, `Dockerfile`, new delivery/packaging files outside `piper_agent/` |

---

## Summary of Code-Only Deliverables per Person (Updated)

| Person | Branch | Key Code Deliverables (incl. new PP tasks) |
|---|---|---|
| **Erik** | `feat/datos-cache` | `cache_loader.py` with circuit breaker, `imerg_etl.py` retry‑backoff, `lookup_soil()`, `fetch_openet_eta()`, `fetch_smap_moisture()`, single `CROP_TBASE`; `.env.example` with Earthdata placeholders; real ingestion pipeline + versioned baselines + calibration stubs |
| **Alina** | `feat/logica-herramientas` | Fixed `detect_event` confidence, `filter_rescue_crops` `none` return, `generate_recovery_plan` normal‑scenario text, `compute_dollar_savings()`, `plan_rotation()`, `explain_exclusion()`, contract‑key serialization (`PP4`), monitoring alert (`PP5`); calibration layer + evidence tags + failure taxonomy |
| **Neithan** | `feat/gdd-climate` | Hemisphere‑aware `fetch_power_gdd.py`, `--hemisphere` CLI, `season_end` in demo packets, `--api-mode` CLI flag for live data; multi‑regime validation, season windowing, agronomic metadata + threshold/unit contract keys |
| **Danny** | `feat/api-backend` | `/generate_plan` with full contract serialization, `datetime.now(timezone.utc)`, `alertas` field, `/simulate_sms`, `demo_mode` query param, health endpoint awareness; auth/records/export/audit trail, real health/readiness, demo vs production payload separation |
| **Matias** | `feat/ui-pwa` | Streamlit with 3 visual states, weights sliders, exclusion/rotation/savings sections, data‑source badge, `sms_gateway.py`, PWA fix (icons, paths), `demo_mode` sidebar toggle, source badges; real operator workflow, multi‑language, live channel hooks, production-path transparency |
| **Elias** | `feat/docs-entrega` | Rewritten `README.md`, `.gitattributes`, `.env.example` with `PIER_DEMO_MODE`, `docs/contratos.md`, `docs/AI_USAGE_DECLARATION.md` update, `Dockerfile` healthcheck; AI/data declaration, reproducibility packaging, one-command demo, delivery scripts |

**No one works on:** video creation, slide decks, on‑screen branding, or any UI/UX polish beyond the code‑driven interface described above. The focus is entirely on making the engine reliable, multi‑hemisphere, transparent, and production‑path ready so that any presentation layer can consume it.

---

## Streamlined QA / Integration (covers the rest of the team)

The integration layer is not "Elias only" — it is a shared concern now that there is real-data work ahead. It still owns only new paths (`.github/workflows/**`, `tests/acceptance/**`, `scripts/qa/**`) and never touches anyone else's files.

| Concern | What changed for the real-data wave |
|---|---|
| Per-branch gate | Every `feat/*` push/PR runs lint + the full 95-test suite + the acceptance scenarios for the current demo, so no branch can regress the demo while adding real-data code. |
| Shared truth | `scripts/qa/check_success_metrics.py` reports Spec success metrics with a network guard that says whether each run used live data or cache, so the team can verify claims instead of trusting them. |
| Ownership hygiene | `scripts/qa/branch_overlap.py` lists any file touched by more than one branch and any change outside each owner's paths, so the isolation guarantees stay intact as the real-data work expands. |
| Science gaps | `scripts/qa/` keeps the known gaps report current, with each gap either fixed, explicitly accepted with a rationale, or handed to a named owner as a post-hackathon follow-up. |

---

## Integration Contract (unchanged)

- `run_pier(lat, lon, date, demo_mode, demo_name, pesos_agricultor, rendimiento_t_ha) -> dict`
- `load_demo_packet(demo_name) -> dict`
- New keys added upstream are read downstream with `.get()`; no existing English identifier is renamed by the A‑team.
- Demo mode is the default (`PIER_DEMO_MODE=1`); production path is opt-in only (`PIER_DEMO_MODE=0`) and must never break the 95 demo-mode tests.

---

## Shipping rule

- Each person merges only within their own branch and their own file paths.
- Demo-mode tests (95/95) must stay green before any merge, including any production-path change.
- Real-data or production-path work is always labeled in the output via `fuente_datos` and is never the default.
- Video, slides, presentation text, and branding are out of scope for everyone; PIER ships as code that a presentation layer can consume.

---

*Plan updated for the real-data / real-results wave. Same 6 isolated branches, same contract points, same demo-first default. The next wave adds real ingestion, calibration, multi-hemisphere climate correctness, a production-ready API, a real operator interface, and delivery/reproducibility packaging — one course of action per person.*
