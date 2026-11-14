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

> **Status: ✅ Q1–Q5 merged · ✅ Q6–Q7 done on `feat/qa-brechas-sin-dueno` (PR pending review)** — Danny (with Claude). Owns only NEW paths: `.github/workflows/**`, `tests/acceptance/**`, `scripts/qa/**`. Touches no file owned by anyone else.

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

## Next Wave: Real Data, Real Results — Work Needed Beyond the Demo

The six branches above get PIER working in demo mode on the hackathon floor. To turn it into a usable tool that can run on real coordinates with real data and produce defensible results (not just a hackathon showcase), the following work remains. Each course of action is still assigned to one person and stays isolated from the others.

### Erik — Real ingestion, multi‑source cache, and calibration data
- Replace synthetic cache generator with a real ingestion pipeline (`data/ingestion/`) that can pull from NASA Earthdata (IMERG final/early run) and NOAA/OpenLand/SMAP where available, with the demo cache remaining a silent fallback when credentials or network are absent.
- Add a small, versioned baseline store (`data/baselines/`) with per-region climatologies so every run can explain whether a rainfall/temperature/frost value is normal, extreme, or missing — the basis for any later trust/scoring layer.
- Implement the soil moisture and evapotranspiration lookups (`lookup_soil`, `fetch_openet_eta`, `fetch_smap_moisture`) against real datasets behind the same `demo_mode` gate used everywhere else, so Alina's tools can consume them without knowing whether they came from a live call or the cache.
- Ship calibration stubs: the agent should be able to accept farmer‑supplied observed yield or damage notes and store them in a personal calibration file per lat/lon so future runs can drift‑correct against local reality instead of global climatology.

### Alina — Confidence, calibration layer, and explanation depth
- Turn the current confidence heuristics into a calibration layer that can ingest observed outcomes (yield, damage, rescue decisions) and adjust `confianza_calibrada` over time, with clear bounds and a fallback to uncalibrated confidence when no local observations exist yet.
- Extend the orchestration (`agent.py`) so every recommendation is backed by one or more evidence tags from the data layer (e.g. "IMERG 72h spike", "POWER GDD behind normal", "Baltimore frost window") and can render both a concise version for SMS and a detailed version for the dashboard.
- Add a failure taxonomy so the agent can distinguish "no data" from "conflicting data" from "data suggests normal conditions" and route each to a different recommendation posture rather than treating all uncertainty the same.
- Finish `filter_rescue_crops`, `generate_recovery_plan`, and `plan_rotation` so they produce real, defensible text for each scenario type (flood, drought, frost, heatwave, normal) and so the same logic works in both demo and production paths.

### Neithan — Multi‑hemisphere climate correctness and grower‑facing agronomy
- Stabilize the GDD and frost logic across hemispheres and tropical/temperate boundaries, with the demo packets covering at least one representative coordinate per regime (e.g. temperate north, temperate south, tropical) so the branch can be validated without relying on a single test case.
- Add season detection and windowing so a recommendation respects whether the crop is in planting, vegetative, flowering, harvest window, or post‑harvest, which changes the meaning of a frost warning or a heatwave alert.
- Hook the climate outputs into the contract keys (`ola_calor`, `suelo`, `confianza_calibrada`) with real units and thresholds, and add the agronomic rationale as machine-readable metadata so Matias can render it and Danny can expose it without re‑deriving it.
- Validate against public historical reanalysis or cited climatologies so the branch can defend its numbers (e.g. "for this coordinate and date range, POWER GDD is X% below the 10‑yr baseline") when asked during judging.

### Danny — Production‑ready API, auth, records, and audit
- Harden the FastAPI layer for real use: proper request validation, per‑coordinate result storage (so a grower or operator can revisit a past plan), export formats (CSV/JSON), and a small auth or API-key gate so the public endpoint is not open.
- Add an audit trail for every run: inputs, `fuente_datos`, which cache/live path was taken, which circuit-breaker state existed, and which contract keys were present, so the system can later answer "why did it give this recommendation on this date."
- Make the health and readiness endpoints actually useful in production: data recency, last successful live call, current fallback state, and any outages or degraded sources, rather than a single boolean.
- Separate the demo-mode contract from any production-only contract extensions so the API can serve a stripped demo payload to the hackathon and a richer production payload to real users without two code paths forking the whole app.

### Matias — Real operator interface, multi‑language, and channel reach
- Build the dashboard around real workflow, not static demo cards: a way to paste or pick a coordinate, choose a date range, see which data source was used, inspect the evidence behind each recommendation, and export or share a plan.
- Make the UI correctly reflect the production path when it is enabled — live-data badge, credential-status awareness, explicit "this run used synthetic cache" indicators — so nobody mistakes a demo for a live operational tool.
- Add SMS/WhatsApp/email channel hooks beyond the simulator so an operator in the field can actually receive a plan in the right language and length, with a short code and a link to the full dashboard when needed.
- Support Spanish (and any other language the team can justify) for the operator-facing text so the tool can be handed to local grower organizations without requiring English literacy.

### Elias — Data-use, privacy, reproducibility, and delivery packaging
- Finish the AI usage and data declaration so it accurately covers both demo and production paths, including which external services are contacted, what is cached, what is persisted, and what is never sent anywhere.
- Package the repo so a stranger can clone, set `.env`, run a single command, and get a deterministic demo result, and so the same repo can be pointed at real credentials later without re-plumbing.
- Add a reproducibility checklist: which cache version produced which result, which contract version was used, and how to regenerate the demo exactly, so any claim made during judging can be traced back to a concrete run.
- Keep the delivery surface code-only: README, contracts, env examples, Dockerfile/healthcheck, CI, and any export or packaging scripts — nothing that depends on video, slides, or presentation polish.

---

### QA / Integration — Shared gating and truth for the next wave
- Keep the QA gate on every `feat/*` branch so new real-data work cannot land without passing lint, the full test suite, and the acceptance criteria that match the current demo scenarios.
- Maintain the overlap detector and ownership table so the real-data work stays isolated the same way the demo work did — especially around shared files like `config.py`, `contracts.py`, and `data/baselines/`.
- Keep the success-metric script up to date with whatever "real results" means at delivery time, with a network guard proving whether a given run used live data or cache, so claims about live data are verifiable rather than asserted.
- Carry forward the known science gaps report and make each gap either fixed, explicitly accepted with a documented rationale, or marked as a post-hackathon follow-up owned by a named person.

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
