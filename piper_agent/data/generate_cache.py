"""Genera el caché sintético de IMERG + POWER para los escenarios demo.

No requiere credenciales de Earthdata. Crea, por cada escenario de `demo/*.json`:
- data/cache/imerg/{demo}_imerg.csv     (date, precipitation_mm)
- data/cache/power/{demo}_power.csv     (date, T2M_MAX, T2M_MIN, PRECTOTCORR)
- data/baselines/{demo}_baselines.json  (p95, p10, fin de ventana, fuente_datos)
- data/baselines/southern_hemisphere.json (bandas de helada por latitud)

Cada archivo sintético lleva al lado un marcador SYNTHETIC_CACHE.

Uso:
    python -m piper_agent.data.generate_cache            # los tres escenarios
    python -m piper_agent.data.generate_cache flood      # solo uno
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_IMERG = os.path.join(RAIZ, "data", "cache", "imerg")
DIR_POWER = os.path.join(RAIZ, "data", "cache", "power")
DIR_BASELINES = os.path.join(RAIZ, "data", "baselines")
DIR_DEMOS = os.path.join(RAIZ, "..", "demo")

ESCENARIOS = ("flood", "drought", "normal")
LATITUD_TROPICAL = 23.5  # |lat| menor que esto: sin helada climatológica
FUENTE_SINTETICA = "sintetico"

# Mes-día típico de la primera helada de otoño por banda de latitud.
# Valores orientativos; requieren calibración local.
BANDAS_HELADA = {
    "nota": "valores típicos, requieren calibración local",
    "latitud_tropical": LATITUD_TROPICAL,
    "norte": [
        {"lat_min": 23.5, "lat_max": 30.0, "primera_helada": "12-15"},
        {"lat_min": 30.0, "lat_max": 40.0, "primera_helada": "11-05"},
        {"lat_min": 40.0, "lat_max": 50.0, "primera_helada": "10-10"},
        {"lat_min": 50.0, "lat_max": 90.0, "primera_helada": "09-15"},
    ],
    "sur": [
        {"lat_min": 23.5, "lat_max": 30.0, "primera_helada": "06-15"},
        {"lat_min": 30.0, "lat_max": 40.0, "primera_helada": "05-05"},
        {"lat_min": 40.0, "lat_max": 50.0, "primera_helada": "04-10"},
        {"lat_min": 50.0, "lat_max": 90.0, "primera_helada": "03-15"},
    ],
}


def es_tropical(lat: float) -> bool:
    return abs(lat) < LATITUD_TROPICAL


def leer_paquete(nombre: str) -> dict:
    """Lee demo/{nombre}_demo.json (fuente única de fechas y coordenadas)."""
    with open(os.path.join(DIR_DEMOS, f"{nombre}_demo.json"), encoding="utf-8") as f:
        return json.load(f)


def rango_fechas(inicio: str, fin: str):
    actual = date.fromisoformat(inicio)
    ultimo = date.fromisoformat(fin)
    while actual <= ultimo:
        yield actual
        actual += timedelta(days=1)


def generar_imerg(recent_start, recent_end, baseline_start, event_type) -> pd.DataFrame:
    """Lluvia diaria. Inundación: tormenta de 72 h > 100 mm. Sequía: déficit de 30 días."""
    rng = np.random.default_rng(42)
    inicio_reciente = date.fromisoformat(recent_start)
    registros = []
    for d in rango_fechas(baseline_start, recent_end):
        en_ventana = recent_start <= d.isoformat() <= recent_end
        if event_type == "flood" and en_ventana:
            idx = (d - inicio_reciente).days
            mm = {1: 40.0, 2: 35.0, 3: 30.0}.get(idx)
            if mm is None:
                mm = float(rng.gamma(2.0, 3.0))
        elif event_type == "drought" and en_ventana:
            mm = float(rng.gamma(0.5, 1.0))  # muy seco
        else:
            mm = float(rng.gamma(2.0, 3.0))
        registros.append({"date": d.isoformat(), "precipitation_mm": round(mm, 2)})
    return pd.DataFrame(registros)


def _fin_serie(lat: float, current_date: str, season_end: str | None) -> str:
    """Último día de la serie POWER: cubre la temporada actual completa."""
    if es_tropical(lat):
        fin = season_end or f"{current_date[:4]}-12-31"
        return max(fin, current_date)
    if lat > 0:
        return f"{current_date[:4]}-10-15"
    return f"{current_date[:4]}-12-31"


def generar_power(current_date, baseline_start, lat, season_end=None) -> pd.DataFrame:
    """T2M_MAX, T2M_MIN y PRECTOTCORR diarios: 10 años + temporada actual."""
    rng = np.random.default_rng(123)
    registros = []
    for d in rango_fechas(baseline_start, _fin_serie(lat, current_date, season_end)):
        doy = d.timetuple().tm_yday
        if es_tropical(lat):
            # Trópico: cálido todo el año, ciclo anual pequeño, sin heladas.
            tmean = 22.0 + 2.0 * np.sin(2 * np.pi * (doy - 80) / 365.0)
            semi_rango = 6.0
            lluvia_media = 1.0 + 3.0 * max(0, np.sin(2 * np.pi * (doy - 60) / 365.0))
        elif lat > 0:
            tmean = 12.0 + 15.0 * np.sin(2 * np.pi * (doy - 80) / 365.0)
            semi_rango = 7.0
            lluvia_media = 3.0 + 2.0 * max(0, np.sin(2 * np.pi * (doy - 100) / 365.0))
        else:
            # Hemisferio sur templado: ciclo invertido seis meses.
            tmean = 12.0 + 15.0 * np.sin(2 * np.pi * (doy - 262) / 365.0)
            semi_rango = 7.0
            lluvia_media = 3.0 + 2.0 * max(0, np.sin(2 * np.pi * (doy - 282) / 365.0))
        tmax = tmean + semi_rango + rng.normal(0, 2.0)
        tmin = tmean - semi_rango + rng.normal(0, 2.0)
        lluvia = max(0.0, float(rng.gamma(lluvia_media, 1.5)))
        registros.append({
            "date": d.isoformat(),
            "T2M_MAX": round(tmax, 1),
            "T2M_MIN": round(tmin, 1),
            "PRECTOTCORR": round(lluvia, 2),
        })
    return pd.DataFrame(registros)


def _primera_helada_otono(power_df: pd.DataFrame, lat: float) -> str | None:
    """Primera fecha de otoño con T2M_MIN <= 0 °C en el archivo histórico."""
    fechas = pd.to_datetime(power_df["date"])
    doy = fechas.dt.dayofyear
    # Otoño: después del día 200 en el norte; entre los días 60 y 200 en el sur.
    en_otono = (doy > 200) if lat > 0 else ((doy > 60) & (doy <= 200))
    heladas = power_df.loc[(power_df["T2M_MIN"] <= 0.0) & en_otono, "date"]
    if heladas.empty:
        return None
    return str(pd.to_datetime(heladas).min().date())


def calcular_baselines(power_df, lat, season_end=None, fuente_datos=FUENTE_SINTETICA) -> dict:
    """Umbrales de BR-1 (p95 de 3 días, p10 de 30 días) y fin de la ventana de cultivo.

    `climatological_frost_date` se conserva siempre por compatibilidad: en el
    trópico no hay helada y contiene el fin de la temporada de lluvias; el campo
    `frost_method` dice cuál de los dos casos aplica.
    """
    power_df = power_df.sort_values("date").reset_index(drop=True)
    lluvia = pd.Series(power_df["PRECTOTCORR"].values)
    p95_cum3 = float(np.percentile(lluvia.rolling(3, min_periods=1).sum().values, 95))
    p10_cum30 = float(np.percentile(lluvia.rolling(30, min_periods=1).sum().values, 10))

    if es_tropical(lat):
        fin_ventana = season_end or str(power_df["date"].iloc[-1])[:10]
        metodo = "fin_temporada_lluvias"
    else:
        fin_ventana = _primera_helada_otono(power_df, lat)
        metodo = "first_T2M_MIN_<=0_after_day200" if lat > 0 else "helada_climatologica_sur"
        if fin_ventana is None:
            fin_ventana = "2024-10-15" if lat > 0 else "2024-04-15"
            metodo = "fallback_fixed_date"

    return {
        "p95_3day_cum_rainfall": round(p95_cum3, 2),
        "p10_30day_cum_rainfall": round(p10_cum30, 2),
        "climatological_frost_date": fin_ventana,
        "frost_method": metodo,
        "season_end": season_end,
        "tropical": es_tropical(lat),
        "fuente_datos": fuente_datos,
        "note": "typical values, local calibration required",
    }


def escribir_bandas_helada() -> str:
    """Escribe data/baselines/southern_hemisphere.json (bandas de ambos hemisferios)."""
    os.makedirs(DIR_BASELINES, exist_ok=True)
    ruta = os.path.join(DIR_BASELINES, "southern_hemisphere.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(BANDAS_HELADA, f, indent=2, ensure_ascii=False)
    return ruta


def _marcar_sintetico(ruta_csv: str, mensaje: str) -> None:
    with open(ruta_csv.replace(".csv", ".SYNTHETIC_CACHE.txt"), "w", encoding="utf-8") as f:
        f.write(f"SYNTHETIC_CACHE: {mensaje}\n")


def generar_escenario(nombre: str, verbose: bool = False) -> dict:
    """Genera el caché sintético completo de un escenario. Devuelve sus baselines."""
    cfg = leer_paquete(nombre)
    for carpeta in (DIR_IMERG, DIR_POWER, DIR_BASELINES):
        os.makedirs(carpeta, exist_ok=True)

    imerg_df = generar_imerg(cfg["recent_start"], cfg["recent_end"],
                             cfg["baseline_start"], cfg["event_type"])
    ruta_imerg = os.path.join(DIR_IMERG, f"{nombre}_imerg.csv")
    imerg_df.to_csv(ruta_imerg, index=False)
    _marcar_sintetico(ruta_imerg, "sin credenciales de Earthdata; IMERG sintético para la demo.")

    power_df = generar_power(cfg["current_date"], cfg["baseline_start"],
                             cfg["lat"], cfg.get("season_end"))
    ruta_power = os.path.join(DIR_POWER, f"{nombre}_power.csv")
    power_df.to_csv(ruta_power, index=False)
    _marcar_sintetico(ruta_power, "API de NASA POWER no consultada; temperatura y lluvia sintéticas.")

    baselines = calcular_baselines(power_df, cfg["lat"], cfg.get("season_end"))
    ruta_baselines = os.path.join(DIR_BASELINES, f"{nombre}_baselines.json")
    with open(ruta_baselines, "w", encoding="utf-8") as f:
        json.dump(baselines, f, indent=2)

    if verbose:
        print(f"=== {nombre} ===")
        print(f"  IMERG: {ruta_imerg} ({len(imerg_df)} filas)")
        print(f"  POWER: {ruta_power} ({len(power_df)} filas)")
        print(f"  Baselines: {ruta_baselines} -> {baselines}\n")
    return baselines


def generar_cache(nombres=None, verbose: bool = False) -> None:
    """Genera el caché sintético de los escenarios indicados (por defecto, todos)."""
    for nombre in (nombres or ESCENARIOS):
        generar_escenario(nombre, verbose=verbose)
    escribir_bandas_helada()


if __name__ == "__main__":
    generar_cache(sys.argv[1:] or None, verbose=True)
    print("Listo. Todo el caché es SYNTHETIC_CACHE (sin llamadas a Earthdata/POWER).")
