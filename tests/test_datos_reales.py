"""Pruebas de la segunda etapa de feat/datos-cache: ingesta real, climatologías y calibración."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from piper_agent.data import calibracion, climatologia
from piper_agent.data._series_cache import radiacion_extraterrestre_mm
from piper_agent.data.fetch_openet import fetch_openet_eta
from piper_agent.data.fetch_smap import fetch_smap_moisture
from piper_agent.data.ingestion import imerg_etl, pipeline
from piper_agent.data.resiliencia import CortaCircuito


@pytest.fixture
def sin_red(monkeypatch):
    import requests

    def prohibido(*a, **k):
        raise AssertionError("no debe haber llamadas de red")

    monkeypatch.setattr(requests, "get", prohibido)


@pytest.fixture
def produccion(monkeypatch, tmp_path):
    """Ruta de producción con carpetas temporales y cortacircuito limpio."""
    from piper_agent.data import resiliencia

    monkeypatch.setenv("PIER_DEMO_MODE", "0")
    monkeypatch.delenv("EARTHDATA_USERNAME", raising=False)
    monkeypatch.delenv("EARTHDATA_PASSWORD", raising=False)
    monkeypatch.setattr(pipeline, "DIR_REAL", str(tmp_path / "real"))
    monkeypatch.setattr(climatologia, "DIR_REGIONES", str(tmp_path / "regiones"))
    monkeypatch.setattr(resiliencia, "cortacircuito_en_vivo", CortaCircuito())
    monkeypatch.setattr(resiliencia.time, "sleep", lambda s: None)
    return tmp_path


def _power_falso(lat, lon, inicio, fin, intentos=3, parametros=imerg_etl.POWER_PARAMETROS):
    dias = pd.date_range(inicio, fin, freq="D")
    columnas = {
        "T2M_MAX": np.full(len(dias), 30.0),
        "T2M_MIN": np.full(len(dias), 16.0),
        "PRECTOTCORR": np.full(len(dias), 2.0),
        "GWETROOT": np.full(len(dias), 0.5),
    }
    df = pd.DataFrame({p: columnas[p] for p in parametros})
    df.insert(0, "date", dias.strftime("%Y-%m-%d"))
    return df


# ── Ingesta ─────────────────────────────────────────────────────────────

def test_clave_region_celda_de_medio_grado():
    assert pipeline.clave_region(41.8, -93.6) == "lat+42.0_lon-093.5"
    assert pipeline.clave_region(41.76, -93.44) == pipeline.clave_region(41.8, -93.6)


def test_modo_demo_no_usa_red_y_usa_cache_demo(sin_red):
    datos = pipeline.ingerir_punto(41.8, -93.6, "2025-05-01", "2025-05-15", demo_mode=True)
    assert datos["fuente_datos"] == "sintetico"
    assert datos["escenario_demo"] == "normal"
    assert datos["motivo_respaldo"] is None
    assert len(datos["power"]) == 15 and len(datos["lluvia"]) == 15


def test_modo_demo_lejos_de_los_demos_genera_serie(sin_red):
    datos = pipeline.ingerir_punto(-33.4, -70.7, "2024-01-01", "2024-01-31", demo_mode=True)
    assert datos["escenario_demo"] is None
    assert len(datos["power"]) == 31
    assert list(datos["lluvia"].columns) == ["date", "precipitation_mm"]


def test_produccion_usa_power_real_y_lo_guarda(produccion, monkeypatch):
    llamadas = []

    def falso(*a, **k):
        llamadas.append(1)
        return _power_falso(*a, **k)

    monkeypatch.setattr(imerg_etl, "descargar_power", falso)
    datos = pipeline.ingerir_punto(10.0, -84.0, "2024-01-01", "2024-01-10")
    assert datos["fuente_datos"] == "nasa_power"
    assert "GWETROOT" in datos["power"].columns
    assert datos["lluvia"]["precipitation_mm"].tolist() == [2.0] * 10
    otra = pipeline.ingerir_punto(10.0, -84.0, "2024-01-01", "2024-01-10")
    assert otra["fuente_datos"] == "nasa_power" and len(llamadas) == 1, "la segunda sale del caché"


def test_produccion_con_imerg_marca_la_fuente(produccion, monkeypatch):
    monkeypatch.setattr(imerg_etl, "descargar_power", _power_falso)
    registros = [{"date": "2024-01-01", "precipitation_mm": 9.5},
                 {"date": "2024-01-02", "precipitation_mm": 0.0}]
    monkeypatch.setattr(imerg_etl, "fetch_with_retry", lambda *a, **k: ("x.xlsx", registros))
    datos = pipeline.ingerir_punto(10.0, -84.0, "2024-01-01", "2024-01-02", usar_imerg=True)
    assert datos["fuente_datos"] == "nasa_power+imerg"
    assert datos["lluvia"]["precipitation_mm"].tolist() == [9.5, 0.0]


def test_produccion_cae_a_respaldo_sin_lanzar_error(produccion, monkeypatch):
    def falla(*a, **k):
        raise RuntimeError("sin red")

    monkeypatch.setattr(imerg_etl, "descargar_power", falla)
    datos = pipeline.ingerir_punto(41.8, -93.6, "2025-05-01", "2025-05-15")
    assert datos["fuente_datos"] == "sintetico"
    assert "sin red" in datos["motivo_respaldo"]
    assert not datos["power"].empty


# ── Climatologías versionadas ───────────────────────────────────────────

def test_climatologia_se_guarda_con_version_y_fuente(sin_red, monkeypatch, tmp_path):
    monkeypatch.setattr(climatologia, "DIR_REGIONES", str(tmp_path))
    clima = climatologia.obtener_climatologia(41.8, -93.6, hasta="2025-05-15", demo_mode=True)
    assert clima["version"] == climatologia.VERSION_BASELINES
    assert clima["fuente_datos"] == "sintetico"
    assert len(clima["meses"]) == 12
    assert (tmp_path / "lat+42.0_lon-093.5_v1.json").exists()
    assert climatologia.cargar_climatologia(41.8, -93.6) == clima


def test_climatologia_sintetica_se_recalcula_en_produccion(produccion, monkeypatch):
    climatologia.obtener_climatologia(41.8, -93.6, hasta="2025-05-15", demo_mode=True)
    monkeypatch.setattr(imerg_etl, "descargar_power", _power_falso)
    real = climatologia.obtener_climatologia(41.8, -93.6, hasta="2025-05-15")
    assert real["fuente_datos"] == "nasa_power"


def test_clasificar_valor_normal_extremo_y_faltante(sin_red, monkeypatch, tmp_path):
    monkeypatch.setattr(climatologia, "DIR_REGIONES", str(tmp_path))
    clima = climatologia.obtener_climatologia(41.8, -93.6, hasta="2025-05-15", demo_mode=True)
    mediana = clima["meses"]["5"]["lluvia_3d"]["p50"]

    normal = climatologia.clasificar_valor(clima, "lluvia_3d", mediana, "2025-05-15")
    assert normal["estado"] == "normal" and normal["direccion"] is None

    alto = climatologia.clasificar_valor(clima, "lluvia_3d", 105.0, "2025-05-15")
    assert alto["estado"] == "extremo" and alto["direccion"] == "alto"
    assert "por encima" in alto["explicacion"]

    bajo = climatologia.clasificar_valor(clima, "lluvia_30d", 0.0, "2025-05-15")
    assert bajo["estado"] == "extremo" and bajo["direccion"] == "bajo"

    assert climatologia.clasificar_valor(clima, "tmin", None, "2025-05-15")["estado"] == "faltante"
    assert climatologia.clasificar_valor(None, "tmax", 30.0, "2025-05-15")["estado"] == "faltante"
    with pytest.raises(ValueError):
        climatologia.clasificar_valor(clima, "viento", 1.0, "2025-05-15")


# ── Humedad y evapotranspiración reales ─────────────────────────────────

def test_smap_usa_gwetroot_de_power_en_produccion(produccion, monkeypatch):
    monkeypatch.setattr(imerg_etl, "descargar_power", _power_falso)
    df = fetch_smap_moisture(10.0, -84.0, "2024-01-01", "2024-01-05", cache_dir=str(produccion / "smap"))
    assert df.attrs["fuente"] == "nasa_power_gwetroot"
    assert df["soil_moisture_vol_pct"].tolist() == [22.5] * 5  # 0.5 de saturación × 45 % de porosidad


def test_openet_usa_hargreaves_con_power_en_produccion(produccion, monkeypatch):
    monkeypatch.setattr(imerg_etl, "descargar_power", _power_falso)
    df = fetch_openet_eta(10.0, -84.0, "2024-01-01", "2024-01-05", cache_dir=str(produccion / "openet"))
    assert df.attrs["fuente"] == "nasa_power_hargreaves"
    assert df["eta_mm"].between(2.0, 8.0).all(), df["eta_mm"].tolist()


def test_series_caen_a_estimado_si_power_falla(produccion, monkeypatch):
    def falla(*a, **k):
        raise RuntimeError("sin red")

    monkeypatch.setattr(imerg_etl, "descargar_power", falla)
    df = fetch_smap_moisture(10.0, -84.0, "2024-01-01", "2024-01-05", cache_dir=str(produccion / "smap"))
    assert df.attrs["fuente"] == "estimado" and len(df) == 5


def test_radiacion_extraterrestre_valores_fao():
    # FAO-56, ejemplo 8: 20°S, 3 de septiembre (día 246) → Ra = 32.2 MJ/m²/día
    assert radiacion_extraterrestre_mm(-20.0, 246) / 0.408 == pytest.approx(32.2, abs=0.2)


# ── Calibración local ───────────────────────────────────────────────────

@pytest.fixture
def carpeta_calibracion(monkeypatch, tmp_path):
    monkeypatch.setenv("PIER_CALIBRACION_DIR", str(tmp_path))
    return tmp_path


def test_observaciones_se_guardan_por_region(carpeta_calibracion):
    calibracion.registrar_observacion(41.8, -93.6, "2025-09-30", "Cowpea",
                                      rendimiento_observado_t_ha=1.2, nota="granizo en agosto")
    calibracion.registrar_observacion(41.76, -93.44, "2025-10-02", "Cowpea", dano_pct=30)
    assert len(calibracion.cargar_observaciones(41.8, -93.6)) == 2
    assert calibracion.cargar_observaciones(9.0, 41.0) == []
    assert (carpeta_calibracion / "lat+42.0_lon-093.5.json").exists()


def test_observacion_invalida_se_rechaza(carpeta_calibracion):
    with pytest.raises(ValueError):
        calibracion.registrar_observacion(41.8, -93.6, "2025-09-30", "Cowpea", dano_pct=140)
    with pytest.raises(ValueError):
        calibracion.registrar_observacion(41.8, -93.6, "30/09/2025", "Cowpea")
    assert calibracion.cargar_observaciones(41.8, -93.6) == []


def test_factor_correccion_necesita_tres_observaciones(carpeta_calibracion):
    for observado in (1.2, 1.0):
        calibracion.registrar_observacion(41.8, -93.6, "2025-09-30", "Cowpea",
                                          rendimiento_observado_t_ha=observado,
                                          rendimiento_esperado_t_ha=1.5)
    sin_calibrar = calibracion.factor_correccion(41.8, -93.6, "Cowpea")
    assert sin_calibrar == {"factor": 1.0, "calibrado": False, "n_observaciones": 2}

    calibracion.registrar_observacion(41.8, -93.6, "2026-09-30", "Cowpea",
                                      rendimiento_observado_t_ha=1.35,
                                      rendimiento_esperado_t_ha=1.5)
    calibrado = calibracion.factor_correccion(41.8, -93.6, "Cowpea")
    assert calibrado["calibrado"] is True and calibrado["factor"] == pytest.approx(0.8)
    assert calibracion.factor_correccion(41.8, -93.6, "Millet")["calibrado"] is False


def test_factor_correccion_acotado(carpeta_calibracion):
    for _ in range(3):
        calibracion.registrar_observacion(41.8, -93.6, "2025-09-30", "Millet",
                                          rendimiento_observado_t_ha=0.1,
                                          rendimiento_esperado_t_ha=1.5)
    assert calibracion.factor_correccion(41.8, -93.6, "Millet")["factor"] == 0.5


def test_historial_alimenta_la_calibracion_de_confianza(carpeta_calibracion):
    from piper_agent.tools.confidence_calibration import calibrate_confidence

    for maduro in (True, True, False, True, True):
        calibracion.registrar_observacion(41.8, -93.6, "2025-09-30", "Cowpea", evento="flood",
                                          confianza_predicha=0.9, cultivo_maduro=maduro)
    calibracion.registrar_observacion(41.8, -93.6, "2025-09-30", "Cowpea", nota="sin resultado")
    historial = calibracion.historial_validacion(41.8, -93.6)
    assert len(historial) == 5
    assert set(historial[0]) == {"event_type", "predicted_confidence", "actual_outcome"}
    assert 0.0 <= calibrate_confidence(0.9, "flood", historial) < 0.9
