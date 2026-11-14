# PIER API (`feat/api-backend`)

Owner: Danny · Plan tasks D1–D7 in `PLAN_SEIS_PERSONAS.md`.

```bash
pip install fastapi uvicorn
python piper_agent/data/generate_cache.py      # until Erik's cache-first loader lands
uvicorn piper_agent.api.main:app --reload       # run from the repo root (see "Known issues")
# interactive docs: http://localhost:8000/docs
```

## Layout

| File | Role |
|---|---|
| `main.py` | App, CORS, `X-Request-ID` middleware, error handlers (422/501/503/500 without tracebacks) |
| `routes.py` | Endpoints |
| `schemas.py` | Pydantic request models + validation (lat/lon ranges, ISO dates, weight keys) |
| `services.py` | **Only** module that imports A-team code; reads contract keys with `.get()` |
| `security.py` | API key (`PIER_API_KEY`), sliding-window rate limit, bounded audit log |
| `sms.py` | SMS parsing + ≤160-char replies for `/simulate_sms` |

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Public, not rate-limited |
| GET | `/demos` | Demo scenarios (name, label, lat/lon, date) — for the PWA selector |
| POST | `/detect_event` | `demo_name` optional (auto-detect); dates default to the demo packet |
| POST | `/recommend_crops` | Accepts `pesos_agricultor` (or legacy `farmer_weights`) |
| POST | `/generate_plan` | Full plan + contract keys + `alertas` + `monitoreo` |
| POST | `/simulate_sms` | `{"message": "41.8,-93.6,2025-05-15"}` → `{"reply": "PIER: FLOOD. Plant …"}` |
| GET | `/audit/log?limit=100` | Last N audit entries (memory, max `PIER_AUDIT_MAX`) |

### `POST /generate_plan`

Request:

```json
{
  "lat": 41.8, "lon": -93.6, "current_date": "2025-05-15",
  "demo_name": null,
  "demo_mode": true,
  "pesos_agricultor": {"soil_protection": 1, "salvage_revenue": 0.5, "water_conservation": 0},
  "rendimiento_t_ha": 1.5
}
```

Response (main keys): `plan_text, event_type, event_severity, event_confidence,
rescue_confidence, confianza_calibrada, gdd_accumulated, gdd_remaining, frost_date,
fallback, no_action_needed, crops[], exclusiones[], rotacion, ahorro, suelo, ola_calor,
fuente_datos, ultima_actualizacion, demo_mode, demo_name, auto_detected, alertas[],
monitoreo, event_details` and the legacy `dollar_savings` / `rotation` (same values as
`ahorro` / `rotacion`).

`alertas[]` items are `{"nivel": "info|warning|critical", "codigo": "...", "mensaje": "..."}`.
Codes: `SIN_CULTIVO_EN_VENTANA`, `SIN_EVENTO`, `DATOS_SINTETICOS`, `MODO_DEMO`,
`DEMO_AUTODETECTADO`, `FECHA_FUERA_DE_DATOS`, `PARAMETRO_PARCIAL`, `CALCULO_EN_API`,
`MONITOREO_*` (from `monitoring/drift.py`; staleness is only checked in live mode).

### Errors

All errors are JSON `{"error", "detail", "request_id"}`:
`401` bad API key · `422` validation / unknown demo / location without cached data ·
`429` rate limit (with `Retry-After`) · `501` live path not implemented ·
`503` data file missing (`missing_file`) · `500` unexpected (no internal details leaked).

## Integration with the other branches

- **Alina (A4/A5/A8/A9):** when `run_pier` accepts `pesos_agricultor` / `rendimiento_t_ha`,
  the API passes them automatically (signature inspection). When it returns `exclusiones`,
  `rotacion`, `ahorro`, `fuente_datos`, `confianza_calibrada`, `suelo`, `ola_calor`, the API
  uses them as-is. Until then it fills `exclusiones/rotacion/ahorro` from the existing tools
  with `"origen": "api_fallback"` and an info alert `CALCULO_EN_API`.
  `ahorro` accepts both the old shape (`estimated_savings_usd_per_ha`) and A5's (`usd_por_ha`,
  `net_savings_usd`); `usd_por_ha` is always present.
- **Erik (E2):** crop CSV path comes from `cache_loader.get_ruta_cultivos()` or `RUTA_CULTIVOS`
  if exported; `fuente_datos` from `cache_loader.get_fuente_datos(name)` if exported.
- **Matias (M11):** to serve the PWA from the API, add in `main.py` (Danny will merge it):
  `app.mount("/pwa", StaticFiles(directory=PWA_DIR, html=True))`. The PWA can now send
  `demo_name: null` and read `demo_mode`, `fuente_datos` and `alertas`; `/demos` lists scenarios.

## Known issues (outside `api/`)

- `tools/filter_rescue_crops.py` defaults `crops_csv` to a path relative to the cwd and
  `run_pier` does not pass it, so `/generate_plan` returns 503 unless the server runs from the
  repo root. Tracked by the `xfail` test `test_generate_plan_works_from_other_cwd`.
- `plan_rotation` can repeat the rescue crop as the final cover (Cereal rye → Cowpea → Cereal rye);
  A8 covers it.
- For `event_type == "none"` the agent still sets `fallback=True`; the API does not raise the
  lost-crop alert for it and sets `no_action_needed=true` (A3 fixes the root cause).
