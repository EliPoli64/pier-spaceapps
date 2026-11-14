# Plan for Person B — Interface and delivery: API, UI, PWA, documentation and video

**Project:** PIER (POWER + IMERG Extreme-weather Recovery) — Spec 3
**Deadline:** Sunday, November 15, 2026, 23:59
**Branch:** `feat/interfaz-entrega`
**Companion plan:** [`PLAN_PERSON_A.md`](PLAN_PERSON_A.md)

Person B owns everything that displays and ships: API, Streamlit, PWA, SMS, monitoring, documentation, Docker and the video. Person A owns everything that computes: data, tools, agent and CLI.

---

## 1. Rules to avoid conflicts

### 1.1 Files that ONLY Person B touches

| Path | Notes |
|---|---|
| `piper_agent/api/**` | FastAPI |
| `piper_agent/ui/**` | Streamlit, components, PWA, SMS gateway |
| `piper_agent/monitoring/**` | drift and alerts |
| `docs/**`, `README.md`, `notes.md` | includes the AI declaration and prompt registry |
| `Dockerfile`, `.env.example` | |
| `tests/test_stage13_operational_resilience.py` and new `tests/test_interfaz_*.py` | |
| Video, script and slides | in `docs/entrega/` |

### 1.2 Files that B does NOT touch (they belong to A)

`piper_agent/data/**`, `piper_agent/tools/**`, `piper_agent/agent.py`, `piper_agent/__main__.py`, `piper_agent/contracts.py`, `piper_agent/config.py`, `demo/*.json`, `requirements.txt`, `.gitignore`, `.gitattributes` and the rest of `tests/`.

If B needs a new dependency or a change in the agent, ask A by message. Never edit someone else's file. Note: `tests/test_stage14_field_readiness.py` belongs to A but tests the SMS gateway; if B changes the SMS reply text, tell A so that test gets adjusted.

### 1.3 Git workflow

1. **Wait for A's notice** that Phase 0 is on `master` (it normalizes line endings in every file; branching earlier guarantees conflicts). Meanwhile, work on the video script (B6), which does not touch the repo.
2. `git pull origin master` and `git checkout -b feat/interfaz-entrega`.
3. Small commits, one topic per commit, message in Spanish.
4. Before each integration: `git fetch origin && git rebase origin/master`, then `pytest tests/ -q`, then merge into `master` (fast-forward) and `git push`.
5. Integrate at the end of each block, not everything at the end. Notify A after every push to `master`.

### 1.4 Language convention

- New code in Spanish: comments, docstrings, new names, interface text.
- **Do not rename** existing English identifiers or routes (`/generate_plan`, `render_map`…): the tests use them.
- The video may be in Spanish **with English subtitles** (requirement from `notes.md`).

---

## 2. Contract between A and B

B only consumes `run_pier` and `load_demo_packet`. Nothing is recomputed in the API or the UI: they show what the agent returns.

```python
resultado = run_pier(
    lat, lon, current_date,
    demo_mode=True,
    demo_name=None,
    pesos_agricultor=None,          # new: {"soil_protection", "salvage_revenue", "water_conservation"}
    rendimiento_t_ha=1.5,           # new
)
```

| Key | Type | Status |
|---|---|---|
| `event_result`, `gdd_result`, `crops`, `recovery_plan`, `plan_text`, `demo_mode`, `demo_name` | as today | exists |
| `exclusiones` | `list[str]` (BR-8) | added by A |
| `rotacion` | `dict \| None` (BR-9, BR-12) | added by A |
| `ahorro` | `dict \| None` (BR-11) | added by A |
| `confianza_calibrada` | `dict \| None` — `{"evento", "rescate", "n_analogos"}` (BR-7) | added by A |
| `suelo` | `dict \| None` | added by A |
| `ola_calor` | `dict \| None` | added by A |
| `fuente_datos` | `str` — `"sintetico"`, `"nasa_power"`, `"nasa_power+imerg"` | added by A |

**How to work in parallel:** always read with `resultado.get("rotacion")` and show the section only if it is not `None`. That way the UI works today and completes itself when A integrates. Until A accepts `pesos_agricultor`, call `run_pier` without that argument and leave the control disabled.

---

## 3. Tasks

Priority: **P0** = the demo looks wrong or a deliverable is missing without it; **P1** = raises the score; **P2** = only if time is left.

### B1 (P0) — Streamlit shows wrong results by default

**Verified problems in `ui/streamlit_app.py` and `ui/components.py`:**

- The date field starts at today's date (2026). The cache covers up to 2025, so every scenario falls into "no crop fits, cash crop lost". The demo fails unless the date is changed by hand.
- Choosing a scenario does not change latitude, longitude or date. "Auto-detect" uses the flood demo for any unknown coordinate.
- The mode badge uses `getattr(recovery_plan, "demo_mode", True)`; `RecoveryPlan` has no such field, so it always says "Demo".
- The plan text is shown as a block using three separate `st.markdown` calls and does not render as a block.
- With a `none` event the red fallback box is shown.

**What to do:**

- When a scenario is chosen, load `load_demo_packet` and fill lat, lon and date with the packet values (the user can edit them afterwards).
- Pass `demo_mode` as an explicit parameter to `render_recovery_plan_card`.
- Use `st.code(plan_text)`.
- Three distinct visual states: with crops, fallback (BR-5), and no event.
- Verify from a clean clone that `streamlit run piper_agent/ui/streamlit_app.py` finds the `piper_agent` package; if not, document `python -m streamlit run …` in the README.

**Done when:** opening the app, choosing each scenario and pressing the button gives the correct result without touching anything else.

### B2 (P0) — Show rules BR-7 to BR-12 in the UI

Today the UI only shows BR-1 to BR-6; the most distinctive part of the project is not visible.

**Files:** `ui/streamlit_app.py`, `ui/components.py`.

- Three sliders in the sidebar: soil protection, salvage revenue, water conservation (BR-10). Expected yield field (t/ha).
- Crop table with deadline, days left, GDD margin, confidence and composite score.
- "Excluded crops and why" section (BR-8).
- "Suggested rotation" section: rescue → main → cover, with soil-health score and fixed nitrogen (BR-9, BR-12).
- "Estimated savings" section in USD/ha, noting that it is an estimate (BR-11).
- Calibrated confidence next to the heuristic one when available, with the number of analogs (BR-7).
- Data-source badge based on `fuente_datos`: it must be clear whether the data is synthetic or real NASA data.

**Done when:** moving a slider changes the table order (after A integrates A4) and each section appears only if its key has data.

### B3 (P1) — API

**Verified problems in `api/main.py`:**

- `POST /generate_plan` receives `farmer_weights` but does not use them: the crop order does not change.
- The PWA sends `demo_name: null` in automatic mode and the API answers 422 because the field is `str`.
- The response does not include `demo_mode`, and the PWA reads it for the badge.
- `/recommend_crops` opens `piper_agent/data/rescue_crops.csv` with a relative path: it fails outside the repo root.
- The API recomputes rotation and savings on its own instead of using what the agent returns.
- `monitoring/drift.py` is not called from anywhere.
- `datetime.utcnow()` is deprecated.

**What to do:**

- `demo_name: str | None = None`.
- `/generate_plan` passes weights and yield to `run_pier` and serializes its keys (`exclusiones`, `rotacion`, `ahorro`, `fuente_datos`, `demo_mode`…). Remove the duplicated computation.
- Import the CSV path from `cache_loader` (A exports it as `RUTA_CULTIVOS`).
- Call `run_all_checks` on every plan and return `alertas` in the response.
- Mount the PWA with `StaticFiles` (see B4).
- `datetime.now(timezone.utc)`.

**Tests:** `tests/test_interfaz_api.py` — weights change the order, null `demo_name` answers 200, the PWA answers 200.

### B4 (P1) — PWA

**Verified problems in `ui/pwa/`:**

- The API does not serve the PWA: `/pwa/index.html` and `/manifest.json` answer 404.
- `index.html` requests `/manifest.json`, `/sw.js`, `/icon-192.png` and `/icon-512.png`; the first two live at another path and the icons do not exist.
- If the API fails, fixed made-up numbers (85%, 1100 GDD, "plant by 2025-07-15") are shown as if they were a result.

**What to do:**

- Mount the folder at `/pwa` and use relative paths in `index.html`, `manifest.json` and `sw.js`.
- Create the two icons.
- Replace the made-up result: store the last real response in `localStorage` and show it offline with the label "last saved result"; if there is none, show only the error.
- Add the priority sliders and the exclusions, rotation and savings sections.

### B5 (P0) — Outdated documentation

| File | What is wrong | What to do |
|---|---|---|
| `README.md` | Says 37 tests (there are 95), only BR-1 to BR-6, structure without API/PWA/SMS/monitoring, does not explain how to generate the cache | Rewrite: install, generate or download cache, CLI, Streamlit, API (`uvicorn piper_agent.api.main:app`), PWA, BR-1 to BR-12 table with file, which data is real and which synthetic |
| `docs/AI_USAGE_DECLARATION.md` | Covers up to stage 9, 37 tests, BR-1 to BR-6 | Add stages 10–14 and this phase; list every AI tool actually used and what for; separate human decisions |
| `docs/PROMPT_REGISTRY.md` | Ends at T9.4 | Add the prompts for stages 10–14 (they are in `plan.md`) and for this phase. `notes.md` requires logging every prompt given to an agent |
| `plan.md`, `plandividido.md` | Earlier plans with paths from another machine | Move to `docs/historico/` without editing, or leave them; decide with A |

Do not claim anything in the documentation that the code does not do: confirm the state of `fuente_datos` with A before writing "uses IMERG data".

### B6 (P0) — 30-second video (or up to 7 slides)

There is no presentation deliverable in the repo. Rules from `notes.md`: at most 30 s, or at most 7 slides; in English, or in Spanish with English subtitles. Criteria: influence, creativity, validity, relevance, presentation.

Suggested script (record the Streamlit screen):

| Seconds | Image | Message |
|---|---|---|
| 0–5 | Map with the event marker | A flood has just destroyed the crop. What gets planted now? |
| 5–11 | Detection and confidence | PIER detects the event from NASA's rainfall anomaly |
| 11–18 | GDD window and crop table | It computes the heat left in the season and gives a deadline per crop |
| 18–24 | Slider, exclusions and rotation | The farmer weighs soil, revenue and water; every exclusion is explained |
| 24–30 | No-window scenario → cover crop | If nothing fits, it protects the soil and says so clearly |

- Save the script and subtitles in `docs/entrega/`. If the video is large, host it outside the repo and link it in the README.
- **Record after A integrates A1–A4**; before that, the normal and drought scenarios show incorrect results.
- Fallback if time runs out: 7 slides (problem, NASA data, how it decides, flood demo, drought demo, fallback, AI usage).

### B7 (P1) — Docker and environment variables

- `Dockerfile`: the `CMD` only prints the CLI help. Expose the port and start the API (which serves the PWA) or Streamlit; verify that the image contains the cache.
- `.env.example`: missing `PIER_API_KEY`, `PIER_DEMO_MODE`, `PIER_OPENET_API_KEY`, `PIER_REDIS_HOST`, `PIER_STALE_DATA_HOURS`, `PIER_LOW_CONFIDENCE`, all read by the code.
- The image's Python version (3.11) does not match the one declared in `AI_USAGE_DECLARATION.md` (3.14); make them consistent.

### B8 (P2) — Extras

- A demo command to simulate an inbound SMS.
- Spanish/English language selector in Streamlit.
- A readable or exportable `/audit/log` page.

---

## 4. Tests

- New tests in `tests/test_interfaz_*.py`.
- `pytest tests/ -q` green before each integration.
- Before recording: walk through the three scenarios by hand in Streamlit and in the PWA.

## 5. Suggested schedule

| When | What |
|---|---|
| Saturday, noon | Video script (B6) while A finishes Phase 0 |
| Saturday, afternoon | B1 → integrate |
| Saturday, evening | B2 with `.get()`, B3 → integrate |
| Sunday, morning | B4, B7; adjust B2 to A's real keys |
| Sunday, until 16:00 | B5 with the final numbers (tests, data source) |
| Sunday 16:00 | **Code frozen.** Record the video (B6) |
| Sunday 20:00 | Subtitles, link in README, final integration |
| Sunday 21:00 | Final check with A from a clean clone; buffer until 23:59 |
