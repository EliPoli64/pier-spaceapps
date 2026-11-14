# PIER — POWER + IMERG Extreme-weather Recovery Planner

**NASA Space Apps Challenge — Field Shift Challenge (Spec 3: Extreme Weather)**  
**Deadline:** Nov 15, 2026, 23:59

## What PIER does

When an extreme weather event (flood or drought) destroys a farmer's planned crop, PIER answers: *what can be planted now that will stabilize the soil and fit the remaining growing-season window?*

PIER:
1. **Detects** the event from IMERG rainfall anomaly (BR-1 — anomaly threshold, not absolute)
2. **Computes** the remaining GDD (thermal-time) window from POWER temperatures to climatological frost (BR-3)
3. **Filters** rescue crops matched to the event type and remaining window (BR-2, BR-3, BR-4)
4. **Generates** a recovery plan with plant-by dates, separate confidences, and a cover-crop fallback (BR-5, BR-6)

## How to run

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
- `--demo` (default on) — use cached data only (no live NASA calls)
- `--no-demo` — attempt live NASA path (production; not implemented in demo)

### Streamlit UI
```bash
streamlit run piper_agent/ui/streamlit_app.py
```
Then open the local URL shown by Streamlit. Enter lat/lon/date, pick a scenario, and click **Generate recovery plan**.

## Demo data (cache-only)

All IMERG/POWER responses are served from `piper_agent/data/cache/` during the demo. The live NASA Earthdata/POWER connection is labeled as a **production path only** (Spec §8). Synthetic cache data is used when Earthdata credentials are unavailable (see `piper_agent/data/generate_cache.py`).

## Business rules traceability

| BR | Rule | Implemented in |
|---|---|---|
| BR-1 | Event detection: anomaly threshold (3-day cum vs min(p95,100mm); 30-day cum vs p10) | `piper_agent/tools/detect_event.py` |
| BR-2 | Event type drives crop filter — never both at once | `piper_agent/tools/filter_rescue_crops.py` |
| BR-3 | GDD-based window: gdd_req ≤ gdd_remaining × 0.8 | `piper_agent/tools/filter_rescue_crops.py` |
| BR-4 | Explicit plant-by date; rank latest-first | `piper_agent/tools/filter_rescue_crops.py` |
| BR-5 | Cover-crop fallback; "cash crop is lost" statement | `piper_agent/tools/generate_recovery_plan.py` |
| BR-6 | Separate event-detection vs rescue-recommendation confidence | `piper_agent/tools/generate_recovery_plan.py` |

## Success metrics (Spec §10)

Verified by 37 passing tests (`pytest tests/`):

- [x] Flood demo → `event_type = flood`
- [x] Drought demo → `event_type = drought`
- [x] Normal demo → `event_type = none`
- [x] ≥2 eligible rescue crops for flood demo
- [x] ≥2 eligible rescue crops for drought demo
- [x] Fallback (cover crop) triggers when window too short; plan states "cash crop is lost"
- [x] All demo IMERG/POWER served from cache (no live calls)

## AI usage

Per notes.md, AI usage is declared in [`docs/AI_USAGE_DECLARATION.md`](docs/AI_USAGE_DECLARATION.md) with every agent prompt logged in [`docs/PROMPT_REGISTRY.md`](docs/PROMPT_REGISTRY.md).

## Project structure

```
piper_agent/
  contracts.py        # Shared data contracts (EventResult, GddResult, CropRecommendation, RecoveryPlan)
  config.py           # Constants (TBASE, safety margin 0.8, tolerance ordinals)
  agent.py            # Tool-calling loop (run_pier)
  __main__.py         # CLI entry point
  tools/
    detect_event.py           # BR-1
    fetch_power_gdd.py        # BR-3
    filter_rescue_crops.py    # BR-2,3,4
    generate_recovery_plan.py # BR-5,6
  data/
    cache_loader.py           # Cache-only data loader
    rescue_crops.csv          # Spec §3 crop database
    cache/                    # Synthetic IMERG + POWER caches
    baselines/                # 10-yr percentile baselines + frost dates
  ui/
    streamlit_app.py          # Streamlit frontend
    components.py             # Folium map, plan card, cache badge
tests/
  test_*.py                   # 37 unit/integration tests
demo/
  flood_demo.json, drought_demo.json, normal_demo.json
docs/
  AI_USAGE_DECLARATION.md
  PROMPT_REGISTRY.md
```

## License

NASA Space Apps Challenge submission.
