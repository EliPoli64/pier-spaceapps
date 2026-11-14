# PIER API (`feat/api-backend`)

Owner: Danny · Plan tasks D1–D10 and the next-wave "Production‑ready API, auth, records, and audit" in `PLAN_SEIS_PERSONAS.md`.

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
| `store.py` | SQLite run store + persistent audit (per-coordinate history, retention) |
| `audit.py` | Audit record per run: inputs, data path, circuit breaker, contract keys, versions, evidence |
| `readiness.py` | `/ready` report: data recency, live path, circuit breaker, store |
| `views.py` | `completa` / `demo` payload projection; CSV exports |

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Public, not rate-limited. `demo_mode_status`: `active` or `production_path_available` (Earthdata username set; never revealed); `demo_mode_default` |
| GET | `/demos` | Demo scenarios (name, label, lat/lon, date) — for the PWA selector |
| POST | `/detect_event` | `demo_name` optional (auto-detect); dates default to the demo packet |
| POST | `/recommend_crops` | Accepts `pesos_agricultor` (or legacy `farmer_weights`) |
| POST | `/generate_plan` | Full plan + contract keys + `alertas` + `monitoreo`. `?demo_mode=false` (query) overrides the body; default = `PIER_DEMO_MODE` |
| POST | `/simulate_sms` | `{"message": "41.8,-93.6,2025-05-15"}` → `{"reply": "PIER: FLOOD. Plant …"}` |
| GET | `/audit/log?limit=100` | Last N audit entries (persistent; in-memory fallback) |
| GET | `/ready` | Public readiness: `ready` / `degraded` / `not_ready` (503) with per-dataset cache + newest date, credentials, circuit breaker, last live run, last fallback, store status |
| GET | `/plans?lat=&lon=&radius_deg=&since=&limit=` | Stored runs for a field (same ~1 km cell by default), newest first |
| GET | `/plans/export?lat=&lon=&format=csv\|json` | That history as a download |
| GET | `/plans/{run_id}?vista=` | A stored run: request + response |
| GET | `/plans/{run_id}/audit` | Why PIER recommended what it did (see below) |
| GET | `/plans/{run_id}/export?format=csv\|json` | One plan: CSV = one row per crop |

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

**D10:** optional contract keys (`exclusiones, rotacion, ahorro, confianza_calibrada, suelo,
ola_calor, ultima_actualizacion, dollar_savings, rotation, event_severity, event_details`) are
**omitted** when they have no value — read them with `.get()`. If building one of them fails, it is
dropped and a `CLAVE_NO_SERIALIZABLE` alert is added instead of returning 500.

**Demo vs production (D8):** `demo_mode` resolution order: query `?demo_mode=` → body `demo_mode`
→ env `PIER_DEMO_MODE` (default `1`). While the agent's live path is not implemented the API
returns `501`. If a live request comes back with `fuente_datos == "sintetico"` (circuit-breaker
fallback), the response carries the critical alert `FALLBACK_DATOS_SINTETICOS`.

`alertas[]` items are `{"nivel": "info|warning|critical", "codigo": "...", "mensaje": "..."}`.
Codes: `SIN_CULTIVO_EN_VENTANA`, `SIN_EVENTO`, `DATOS_SINTETICOS`, `MODO_DEMO`,
`DEMO_AUTODETECTADO`, `FECHA_FUERA_DE_DATOS`, `PARAMETRO_PARCIAL`, `CALCULO_EN_API`,
`FALLBACK_DATOS_SINTETICOS`, `CLAVE_NO_SERIALIZABLE`,
`MONITOREO_*` (from `monitoring/drift.py`; staleness is only checked in live mode).

### Views — one response, two payloads

`/generate_plan?vista=completa` (default, `PIER_API_VIEW`) returns everything plus `run_id`,
`guardado` and `enlaces` (plan, audit, CSV, history). `?vista=demo` returns a projection of the
same response for the hackathon screen / PWA: plan text, confidences, GDD window, crops
(name, plant-by, days, confidence, role), critical alerts + data-source badge, `contrato`.
The stored run always keeps the full payload.

### Audit record (`/plans/{run_id}/audit`)

`entradas` (request) · `resuelto` (scenario, auto-detected, demo mode, view) ·
`datos` (`fuente_datos`, `ruta` = `cache` | `live` | `live_fallback_to_cache`,
newest observation, circuit-breaker state at that moment, cached files with mtime + synthetic flag) ·
`contrato` (version, keys from the agent / filled by the API / absent) ·
`versiones` (API, git commit or `PIER_GIT_SHA`) · `decision` · `alertas` ·
`evidencia` (plain-language chain: rain vs thresholds, GDD window, eligible and excluded crops).

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `PIER_API_KEY` / `PIER_API_KEYS` | — | Accepted keys (`PIER_API_KEYS` comma-separated, for rotation) |
| `PIER_REQUIRE_API_KEY` | `auto` | `1`/`0`/`auto` (auto = required when `PIER_DEMO_MODE=0`; if required and no key is set, protected endpoints return 503) |
| `PIER_API_DB` | `~/.pier/pier_api.sqlite3` | Run store (`:memory:` allowed) |
| `PIER_STORE_RETENTION_DAYS` | `90` | Stored runs/audit older than this are purged (0 = keep) |
| `PIER_STORE_DISABLED` | — | `1` = do not persist (plans still served, alert `SIN_PERSISTENCIA`) |
| `PIER_API_VIEW` | `completa` | Default payload view |
| `PIER_GIT_SHA` | git HEAD | Code version written to audit records |
| `PIER_RATE_LIMIT_MAX` / `_WINDOW` | 60 / 60 s | Rate limit per key / IP |

Privacy: stored rows contain field coordinates and request parameters (needed to revisit a
field's plans); phone numbers only masked; nothing is sent to third parties; rows expire.

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
