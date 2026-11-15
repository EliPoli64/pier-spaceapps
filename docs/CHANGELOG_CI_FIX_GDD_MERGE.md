# CI fix — GDD merge wiring (`feat/herramientas-vivos` × `feat/gdd-climate`)

**Date:** 2026-11-15  
**Branch base:** `master` @ `4dd884c` (Merge PR #17)  
**Author context:** local repair before push — Matias / agent session  
**Status:** verified end-to-end (pytest + demos + API + Streamlit + live NASA POWER)

---

## 1. Problem

After merging `feat/herramientas-vivos` into `master` (on top of the large `feat/gdd-climate` rewrite), **PIER CI went red**: **14 failed / ~359 passed**.

Root cause was a **merge wiring gap**, not a bad product idea:

| Layer | What broke |
|---|---|
| `fetch_power_gdd` | Signature still accepted live kwargs `power=` / `baselines=` (from herramientas-vivos), but the climate rewrite body only read `power_df=` and ignored those kwargs. |
| `run_pier` (live) | Passed `power` + `baselines` into GDD **without** `demo_mode=False`, so GDD defaulted to `demo_mode=True` and raised: `Either demo_name, baseline_dir, or power_df must be provided when demo_mode=True.` |
| Details contract | Tests expected `remaining_method` + `data_status`; climate rewrite only emitted `projection_method`. |
| CLI live | `main()` always called `run_pier` first; live no longer raised `NotImplementedError`, so `_run_live_or_fallback` (and its monkeypatched `ingest_point`) never ran. |
| Demo `--season-start` | Agent accepted `season_start` but only applied it on the live path. |

### Failing tests (CI summary)

- `tests/test_agent_e2e.py::test_demo_mode_only_cache`
- `tests/test_api_backend.py` — live / demo_mode query / env default
- `tests/test_herramientas_vivos.py` — GDD live projection, no-frost `no_data`, demo `remaining_method`, live offline labels, A11 source change
- `tests/test_gdd_climate.py` — CLI season-start JSON, live mocked NASA, offline fallback, `--no-demo`

---

## 2. What we changed

### Files touched

1. `piper_agent/tools/fetch_power_gdd.py`
2. `piper_agent/agent.py`
3. `piper_agent/__main__.py`

### Also added (verification / docs)

4. `scripts/qa/e2e_pre_push_check.py` — repeatable E2E smoke (demos, CLI, API, live)
5. `docs/E2E_PRE_PUSH_REPORT.json` — last machine-readable E2E report
6. This document

### Behavioral fixes

**`fetch_power_gdd`**
- Alias `power` → `power_df` when only `power` is provided.
- Honor caller `baselines` (override / merge) via `baselines_override` in `_load_climate_inputs`.
- If `monthly_gdd_normal` + frost/season-end bound → remaining GDD via **climatological projection** (`remaining_method=climatological_projection`).
- Otherwise keep climate zero-lookahead projector and label **`remaining_method=observed_cache`**.
- Emit **`data_status`** (`ok` / `no_data`) for the failure taxonomy (explicit unbounded frost → `no_data`).

**`run_pier`**
- Always forward `demo_mode=` into `fetch_power_gdd` (after `**gdd_kwargs` so it wins).
- In demo mode, honor optional `season_start` override (CLI `--season-start`).

**CLI `main`**
- Live (`demo_mode=False`) → `_run_live_or_fallback` first (climate JSON contract + test monkeypatches).
- Demo → `_call_run_pier` first, with previous `NotImplementedError` fallback kept.

---

## 3. What is *not* in this change

- No `.env` / credentials committed (`.env` remains gitignored).
- No intentional change to business rules BR-1…BR-12 beyond restoring the post-merge contracts.
- No UI redesign; Streamlit already worked once the agent/GDD wiring was fixed.
- `imergpy` still optional: live rainfall can come from POWER `PRECTOTCORR` with a labeled fallback reason.

---

## 4. How to reproduce verification locally

Use **Python 3.11** (project pin). Pandas on 3.15 breaks.

```powershell
cd pier-spaceapps
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe piper_agent\data\generate_cache.py

# Full suite (CI equivalent)
.\.venv\Scripts\python.exe -m pytest tests/ -q --tb=short

# E2E smoke including live NASA POWER (needs EARTHDATA_* in .env)
.\.venv\Scripts\python.exe scripts\qa\e2e_pre_push_check.py

# UI
.\.venv\Scripts\python.exe -m streamlit run piper_agent\ui\streamlit_app.py
```

---

## 5. E2E results (pre-push)

Report file: [`E2E_PRE_PUSH_REPORT.json`](./E2E_PRE_PUSH_REPORT.json)

| Check | Result | Notes |
|---|---|---|
| demo flood / drought / normal / late_flood | PASS | Correct event types + crops / fallback |
| season_start override | PASS | `2025-04-15` applied; lower accumulated GDD |
| CLI flood JSON | PASS | `remaining_method=observed_cache` |
| API `/generate_plan` flood | PASS | `event_type=flood`, 2 crops |
| **live NASA POWER** (Iowa) | PASS | `fuente_datos=nasa_power`, `remaining_method=climatological_projection`, plan + 1 crop |
| Streamlit UI | PASS (manual) | Flood demo → map + recovery plan + crop table |

Live note: IMERG via `imergpy` was not installed; rainfall used POWER with explicit `fallback_reason` — expected and labeled.

Pytest (pre-push re-run): **373 passed, 9 xpassed, 0 failed** (gap markers still xpass until owners remove them).

---

## 6. Suggested commit / PR message

```
fix(gdd): rewire power/baselines after climate×herramientas merge

Restore live GDD inputs (power/baselines aliases), remaining_method +
data_status, demo season_start override, and CLI live routing so CI and
live NASA POWER path work again.
```

---

## 7. Risk / follow-ups

- Gap registry still reports several Alina/Neithan markers as **PASSES NOW** — owners should remove xfail/gap markers in a follow-up PR.
- Pandas `dayofyear` deprecation warnings remain (non-blocking).
- For production API with `PIER_DEMO_MODE=0`, set `PIER_API_KEY` (or `PIER_REQUIRE_API_KEY=0` only for local smoke).
