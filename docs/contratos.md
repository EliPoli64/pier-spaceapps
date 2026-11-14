# Contrato entre A‑team y B‑team (PIER)

**Propósito:** Definir la firma estable de `run_pier` y las claves del paquete demo que B‑team consume, para que cada rama trabaje aislada sin romper la compatibilidad.

**Autoría:** Solo `Branch A` (Erik) modifica `piper_agent/contracts.py` y `piper_agent/data/cache_loader.py`. Todas las demás ramas importan y leen con `.get()`.

---

## 1. Firma de `run_pier`

```python
def run_pier(
    lat: float,
    lon: float,
    current_date: str,        # ISO "YYYY-MM-DD"
    demo_mode: bool = True,   # True = cache-only (demo); False = production path
    demo_name: str | None = None,   # "flood" | "drought" | "normal" | None
    pesos_agricultor: dict | None = None,   # {"soil_protection": w, "salvage_revenue": w, "water_conservation": w}
    rendimiento_t_ha: float | None = None,  # t/ha expected yield (for BR-11 dollar savings)
) -> dict:
```

**Llave devueltas (todas opcionales, usar `.get()` en B‑team):**

| Key | Tipo | Descripción |
|---|---|---|
| `event_result` | `dict` | Salida de `detect_event` (event_type, severity, confidence, details) |
| `gdd_result` | `dict` | Salida de `fetch_power_gdd` (gdd_accumulated, gdd_remaining, frost_date, avg_daily_gdd) |
| `crops` | `list[dict]` | Salida de `filter_rescue_crops` (lista de recomendaciones de rescate) |
| `recovery_plan` | `dict` | Salida de `generate_recovery_plan` (plan_text, structured) |
| `plan_text` | `str` | Texto legible para UI (BR-6 confianza separada, BR-5 fallback) |
| `demo_mode` | `bool` | Devuelto tal cual Entró; lo usa la UI para el badge de fuente de datos |
| `demo_name` | `str | None` | Devuelto tal cual Entró |
| `exclusiones` | `list[str]` | Una frase por cultivo excluido (BR‑8). `None` si none o todos incluidos. |
| `rotacion` | `dict | None` | Salida de `plan_rotation` (BR‑9, BR‑12). Ejemplo: `{"sequence": ["rye","cowpea","clover"], "soil_health_score": 85}`. |
| `ahorro` | `dict | None` | Salida de `compute_dollar_savings` (BR‑11). Ejemplo: `{"usd_por_ha": 287, "revenue_lost_usd": 420, "net_savings_usd": -133}`. |
| `confianza_calibrada` | `dict | None` | `{"evento": float, "rescate": float, "n_analogos": int}` (BR‑7). `None` si no hay históricos. |
| `suelo` | `dict | None` | Salida de `lookup_soil` (BR‑10). Ejemplo: `{"textura": "arcilla", "campo_capacidad_mm": 250, "punto_marchitez_mm": 120}`. |
| `ola_calor` | `dict | None` | Salida de `detect_heat_wave` (extensión opcional). |
| `fuente_datos` | `str` | `"sintetico"` | `"nasa_power"` | `"nasa_power+imerg"`. La UI muestra un badge con este valor. |

**Reglas del contrato:**

- **Llave existentes no cambian de nombre ni de tipo** (`run_pier`, `event_result`, `gdd_result`, `crops`, `recovery_plan`, `plan_text`, `demo_mode`, `demo_name`). 95 tests y el código de B los usan.
- **Nuevas claves pueden ser `None`**; B‑team siempre usa `.get(key)` para leerlas.
- **Cuando no hay evento** (`event_type == "none"`): `recovery_plan.fallback` es `False`, `crops` es `[]`, y `plan_text` dice que no hay evento extremo y el plan de siembra normal sigue.
- **`pesos_agricultor` y `rendimiento_t_ha`** se pasan desde la UI/API y se usan en `filter_rescue_crops` y `generate_recovery_plan` para re‑ordenar y añadir ahorro. Si no se proveen, se usan pesos por defecto (1/3 cada uno) y rendimiento `1.5 t/ha`.

---

## 2. Cargar paquete demo (`load_demo_packet`)

**Ubicación:** `piper_agent/data/cache_loader.py` (definida por Branch A).

```python
def load_demo_packet(demo_name: str) -> dict:
    """
    Retorna un dict con las llaves:
    - name: str
    - lat: float
    - lon: float
    - date: str (ISO)
    - description: str
    - fuente_datos: str  # "sintetico" siempre (cache-only)
    """
```

**Lectura en B‑team:** `packet = load_demo_packet(scenario)` y luego `packet.get("lat")`, `packet.get("lon")`, etc.

---

## 3. Flujo de integración (resumen)

1. **Branch A** hace `Phase 0` en `master`: renormaliza line endings, agrega `requirements.txt`, genera cache, comitea.
2. **Branch A** notifica a **Branch B** que la fase 0 lista; B crea su rama `feat/...` sobre el `master` actual.
3. **Small commits**, un tópico por commit, mensaje en español (`fix: confianza calibrada ahora incluye n_analogos`).
4. **Antes de cada integración:** `git fetch origin && git rebase origin/master`, luego `pytest tests/ -q`, luego merge `master` (fast‑forward) y `git push`.
5. **Notificar al otro equipo** después de cada push a `master`.
6. **Integración al final de cada bloque P0/P1**, no todo al final.

---

## 4. Convenios de lenguaje

- **Nuevo código en español:** comentarios, docstrings, nombres de nuevas funciones, variables y texto al usuario.
- **No renombrar** identificadores ingleses existentes (`run_pier`, `detect_event`, `EventResult`, etc.): 95 tests y B‑team los usan.
- **El video** puede ser en español con subtítulos en inglés (requisito de `notes.md`).
- **La UI muestra solo secciones si su clave no es `None`** (ej. `if resultado.get("rotacion")`).

---

## 5. Flujo de trabajo en paralelo (6 ramas)

| Fase | Quien | Qué hace |
|---|---|---|
| **0** | **Elias** (`feat/docs-entrega`) | `Phase 0` en `master` (renormalizar, `requirements.txt`, `.env.example`, `.gitattributes`, mover planes históricos, crear `docs/contratos.md`). Notificar a todos cuando listo. |
| **1** | **Erik** (`feat/datos-cache`) | Implementar `cache_loader.py`, `rescue_crops.csv`, datos cached, `baselines/`. Cuando listo, notificar a Alina y Neithan. |
| **2** | **Alina** (`feat/logica-herramientas`) | Implementar herramientas (`detect_event`, `filter_rescue_crops`, `generate_recovery_plan`, `compute_dollar_savings`). Importar de `cache_loader` y `contracts`. Cuando listo, notificar a Danny. |
| **3** | **Neithan** (`feat/gdd-climate`) | Implementar `fetch_power_gdd.py` con lógica hemisferio. Importar baselines de Erik. Cuando listo, notificar a Alina. |
| **4** | **Danny** (`feat/api-backend`) | Implementar FastAPI `/generate_plan`, `/detect_event`, `/recommend_crops`. Leer contrato con `.get()`. Cuando listo, notificar a Matias. |
| **5** | **Matias** (`feat/ui-pwa`) | Implementar Streamlit, PWA, SMS gateway. Leer agente con `.get()`. Cuando listo, notificar a Elias para cierre. |
| **6** | **Elias** (`feat/docs-entrega`) | Cierre final: verificar que todo esté documentado, README actualizado, tests verdes, video/script listos. Buffer hasta 23:59. |

**Regla de oro:** Si una rama necesita un nuevo campo en el contrato, pide al dueño del contrato (Elias/Branch A) y este lo aggiade en un commit aislado; luego todas las demás ramas re‑basean sobre el nuevo `master`.

---
*Fuse de PLAN_PERSON_A.md, PLAN_PERSON_B.md y quehacer.md. Solo contenido relacionado con contratos y flujo de trabajo entre ramas. Sin elementos de video o presentación.*