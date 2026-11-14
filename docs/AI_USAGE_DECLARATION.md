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
