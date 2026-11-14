# Plan for Person A — Core: data and agent logic

**Project:** PIER (POWER + IMERG Extreme-weather Recovery) — Spec 3
**Deadline:** Sunday, November 15, 2026, 23:59
**Branch:** `feat/nucleo-datos`
**Companion plan:** [`PLAN_PERSON_B.md`](PLAN_PERSON_B.md)

Person A owns everything that computes: data, tools (`tools/`), agent orchestration and the CLI. Person B owns everything that displays and ships: API, UI, PWA, monitoring, documentation, Docker and the video.

---

## 1. Rules to avoid conflicts

### 1.1 Files that ONLY Person A touches

| Path | Notes |
|---|---|
| `piper_agent/data/**` | cache loader, generators, ingestion, soil, OpenET, SMAP, Redis, crop CSV |
| `piper_agent/tools/**` | all agent tools |
| `piper_agent/agent.py`, `piper_agent/__main__.py` | orchestration and CLI |
| `piper_agent/contracts.py`, `piper_agent/config.py` | shared contracts |
| `demo/*.json` | demo packets |
| `requirements.txt`, `.gitignore`, `.gitattributes` | if B needs a dependency, B asks A |
| existing `tests/` except `test_stage13_operational_resilience.py` | plus the new `tests/test_nucleo_*.py` |

### 1.2 Files that A does NOT touch (they belong to B)

`piper_agent/api/**`, `piper_agent/ui/**`, `piper_agent/monitoring/**`, `docs/**`, `README.md`, `Dockerfile`, `.env.example`, `notes.md`, `tests/test_stage13_operational_resilience.py`, `tests/test_interfaz_*.py`.

If A needs a change in one of B's files (or the other way round), ask by message and let the owner do it. Never make a "quick edit" to someone else's file.

### 1.3 Git workflow

1. A does **Phase 0** directly on `master` and notifies B. B does not create a branch before that notice.
2. Then: `git checkout -b feat/nucleo-datos`.
3. Small commits, one topic per commit, message in Spanish (`fix: evento "none" ya no declara cosecha perdida`).
4. Before each integration: `git fetch origin && git rebase origin/master`, then `pytest tests/ -q`, then merge into `master` (fast-forward) and `git push`.
5. Integrate at the end of each P0/P1 block, not everything at the end. Notify B after every push to `master`.

### 1.4 Language convention

- New code in Spanish: comments, docstrings, names of new functions, variables and keys, user-facing text.
- **Do not rename** existing English identifiers (`run_pier`, `detect_event`, `EventResult`…): 95 tests and B's code use them.

---

## 2. Contract between A and B

B only consumes `run_pier` and `load_demo_packet`. A commits to this signature and these keys; B reads them with `.get()` so work can start before they exist.

```python
resultado = run_pier(
    lat, lon, current_date,
    demo_mode=True,
    demo_name=None,
    pesos_agricultor=None,          # new: {"soil_protection", "salvage_revenue", "water_conservation"}
    rendimiento_t_ha=1.5,           # new: for the estimated savings
)
```

| Key | Type | Status |
|---|---|---|
| `event_result`, `gdd_result`, `crops`, `recovery_plan`, `plan_text`, `demo_mode`, `demo_name` | as today | exists |
| `exclusiones` | `list[str]` — one sentence per excluded crop (BR-8) | new |
| `rotacion` | `dict \| None` — output of `plan_rotation` (BR-9, BR-12) | new |
| `ahorro` | `dict \| None` — output of `compute_dollar_savings` (BR-11) | new |
| `confianza_calibrada` | `dict \| None` — `{"evento": float, "rescate": float, "n_analogos": int}` (BR-7) | new |
| `suelo` | `dict \| None` — output of `lookup_soil` | new |
| `ola_calor` | `dict \| None` — output of `detect_heat_wave` | new |
| `fuente_datos` | `str` — `"sintetico"`, `"nasa_power"` or `"nasa_power+imerg"` | new |

Contract rules: existing keys do not change name or type; every new key may be `None`; when there is no event, `recovery_plan.fallback` is `False` and `crops` is `[]`.

---

## 3. Phase 0 — Prepare `master` (A only, ~30 min, before B creates a branch)

| # | Task | Why |
|---|---|---|
| 0.1 | Create `.gitattributes` with `* text=auto eol=lf` and run `git add --renormalize .` in a single commit | The 56 text files are LF in git and CRLF on disk; without this, every merge shows false differences |
| 0.2 | Add to `requirements.txt`: `fastapi`, `uvicorn`, `pydantic`, `httpx`, `pytest` | The API and the tests import them and they are not listed today: a clean install fails |
| 0.3 | Remove `piper_agent/data/cache/` and `piper_agent/data/baselines/` from `.gitignore`, run `python piper_agent/data/generate_cache.py` and commit the generated files | A fresh clone has no cache and everything fails with `FileNotFoundError`; the README does not mention the step |
| 0.4 | `pytest tests/ -q` (95 must pass), push to `master`, notify B | Common starting point |

---

## 4. Tasks

Priority: **P0** = the demo looks wrong without it; **P1** = raises the score; **P2** = only if time is left.

### A1 (P0) — The "normal" scenario declares the crop lost

**Verified problem:** `python -m piper_agent --lat 41.8 --lon -93.6 --date 2025-07-07 --demo-name normal` detects `none` but prints the rye recommendation and "The season's cash crop is lost". The "no event" confidence also always comes out at 10%.

**Files:** `tools/generate_recovery_plan.py`, `tools/filter_rescue_crops.py`, `tools/detect_event.py`.

- In `generate_recovery_plan`: if `event_type == "none"`, the text says there is no extreme event and the normal planting plan stands; `fallback=False`; no crop list.
- In `filter_rescue_crops`: with `event_type == "none"` return `[]` immediately.
- In `detect_event`: the `none` branch divides `cum30 / p10`, which in a normal period is greater than 1 and pushes confidence to the floor. Compute it as the distance to both thresholds (how far `cum3` is from the flood threshold and `cum30` from p10).
- Remove the duplicated `import pandas as pd`.

**Done when:** the normal scenario does not mention a lost crop, `fallback` is `False`, and the `none` confidence is above 0.5 in the demo.

### A2 (P0) — The drought scenario makes no agronomic sense

**Verified problem:** the drought demo (lat 9.0, lon 41.0) shows 0 accumulated GDD, frost on October 6 and every crop with "plant by today (0 days)". Cause: `generate_cache.py` uses Iowa's thermal cycle for any positive latitude, and the model assumes there is always a frost.

**Files:** `data/generate_cache.py`, `tools/fetch_power_gdd.py`, `demo/drought_demo.json`.

- In `fetch_power_gdd`: if `abs(lat) < 23.5` there is no frost; the end of the window is the new `season_end` field of the demo packet (end of the rainy season). Store the method used in `details` (`"helada_climatologica"` or `"fin_temporada_lluvias"`).
- Replace the trick of adding 182 days for the Southern Hemisphere with the same logic: find the first autumn frost according to hemisphere.
- In `generate_cache.py`: tropical temperatures for `abs(lat) < 23.5`; put the code under `if __name__ == "__main__":` and remove the `DEMOS_FROST_LAT` global.
- Add `season_end` to `drought_demo.json`.

**Done when:** the drought demo shows accumulated GDD above 0, different deadlines per crop and no frost date.

### A3 (P0) — Use real NASA data

**Problem:** 100% of the cache is synthetic, including the "IMERG" percentiles, which are computed on synthetic POWER rainfall. In a NASA challenge this weighs on the validity criterion.

**Files:** new `data/descargar_power.py`, `data/cache_loader.py`, `demo/*.json`, cache.

- `descargar_power.py`: queries the NASA POWER daily API (no credentials required) with `T2M_MAX`, `T2M_MIN`, `PRECTOTCORR`, community `AG`, 2015 to date, for each demo packet; writes the same CSV and JSON files as today. If the download fails, keep the synthetic data.
- Precipitation: if Earthdata credentials are available, use `data/ingestion/imerg_etl.py` (it already has retries); otherwise use POWER `PRECTOTCORR` and declare it in `fuente_datos`. Do not call "IMERG" something that is not.
- Choose real events and **verify them against the downloaded data** before fixing them. Candidates: the northwest Iowa floods of June 2024 and the Horn of Africa drought of 2022.
- `cache_loader`: expose `fuente_datos(demo_name)` by reading the `SYNTHETIC_CACHE` markers.

**Done when:** the three scenarios still classify correctly (`flood`, `drought`, `none`) with real data and `resultado["fuente_datos"]` reflects it. If a real event does not cross the threshold, change the date or place, not the threshold.

### A4 (P0) — Connect what is already written to the agent

**Verified problem:** stages 10–14 added tools that `run_pier` never calls. `explain_exclusion`, `plan_rotation`, `compute_dollar_savings` and the farmer weights are only used in the API; `lookup_soil`, `fetch_openet_eta`, `fetch_smap_moisture`, `detect_heat_wave`, `calibrate_confidence`, `redis_cache` and `imerg_etl` are not used in any flow. The CLI and Streamlit do not show BR-7 to BR-12.

**Files:** `agent.py`, `tools/generate_recovery_plan.py`, `__main__.py`.

- `run_pier` receives `pesos_agricultor` and `rendimiento_t_ha`, passes them to `filter_rescue_crops` and fills the new keys of section 2.
- `lookup_soil` must take a parameter so it does not hit the network in demo mode.
- `generate_recovery_plan` adds to the text: excluded crops and reason, three-cycle rotation with soil score, estimated savings.
- CLI: options `--peso-suelo`, `--peso-ingreso`, `--peso-agua`.

**Done when:** the flood demo CLI shows exclusions, rotation and savings, and changing the weights changes the crop order.

### A5 (P1) — Paths that depend on the working directory

**Verified problem:** running the agent outside the repo root fails with `No such file or directory: 'piper_agent/data/rescue_crops.csv'`. `search_analogs` looks in `<root>/data/analogs`, a folder that does not exist, so calibration is never applied.

**Files:** `tools/filter_rescue_crops.py`, `tools/search_analogs.py`, `data/redis_cache.py`.

- Resolve paths with `Path(__file__)`. Export `RUTA_CULTIVOS` from `cache_loader` so B can import it in the API.
- `redis_cache` creates a folder on import; do it only when writing.

### A6 (P1) — Missing agronomic rules

- `CROP_TBASE` is defined twice (`config.py` and `contracts.py`) and never used: every crop is computed with base 10 °C although rye is base 0 and buckwheat base 5. Compute remaining GDD per crop and keep a single definition.
- `planting_window_start/end` from the CSV is not used: rye is recommended in May when its window is August–October. Exclude crops outside their window with reason `planting_window`.
- `heat_stress_tmax_c` is not used: penalize rescue confidence if the recent maximum exceeds it.
- Confidence saturates at 100% in almost every case; revise the scale so it distinguishes between crops.

### A7 (P1) — Real analogs and calibration (BR-7)

New `data/generar_analogos.py`: walk the 10 years of the archive, run `detect_event` per year and record whether each crop would have reached its GDD before the end of the window. Save to `piper_agent/data/analogos/`. That gives `search_analogs` and `calibrate_confidence` a true history. Do not invent outcomes by hand.

### A8 (P2) — Extras

- Heat wave as an event type in `EventType` and in the filter.
- Use SMAP moisture and ETa to grade drought severity.
- `plan_rotation` produces "rye → cowpea → rye"; avoid repeating the rescue crop as the final cover.

---

## 5. Tests

- New tests in `tests/test_nucleo_*.py`, one per task.
- If an existing test pinned wrong behavior (for example, the `none` case), fix the test in the same commit as the code.
- `pytest tests/ -q` green before each integration.

## 6. Suggested schedule

| When | What |
|---|---|
| Saturday, noon | Phase 0 on `master` |
| Saturday, afternoon | A1, A2 → integrate |
| Saturday, evening | A4 → integrate (unblocks B's UI) |
| Sunday, morning | A3, A5 → integrate |
| Sunday, until 15:00 | A6, A7 if there is time |
| Sunday 16:00 | **Code freeze.** Only fixes B requests for the video |
| Sunday 21:00 | Final check with B; buffer until 23:59 |
