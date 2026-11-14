"""Pruebas de la rama feat/datos-cache: caché, ingesta, suelo, OpenET y SMAP."""
import json
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from piper_agent.data import cache_loader, generate_cache
from piper_agent.data.fetch_openet import fetch_openet_eta
from piper_agent.data.fetch_smap import fetch_smap_moisture
from piper_agent.data.ingestion import imerg_etl
from piper_agent.data.resiliencia import CortaCircuito, llamar_con_reintentos
from piper_agent.data.soil_lookup import lookup_soil


# ── Paquetes demo y contrato ────────────────────────────────────────────

def test_paquetes_demo_tienen_season_end():
    for nombre in ("flood", "drought", "normal"):
        with open(os.path.join("demo", f"{nombre}_demo.json")) as f:
            assert "season_end" in json.load(f)


def test_load_demo_packet_acepta_nombre_corto_y_largo():
    corto = cache_loader.load_demo_packet("flood")
    largo = cache_loader.load_demo_packet("flood_demo")
    assert corto == largo
    assert corto["date"] == corto["current_date"]
    assert corto["fuente_datos"] == "sintetico"


def test_ruta_cultivos_no_depende_del_directorio(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ruta = cache_loader.get_ruta_cultivos()
    assert ruta.is_absolute() and ruta.exists()
    assert "crop" in pd.read_csv(ruta).columns


# ── Caché primero ───────────────────────────────────────────────────────

def test_cache_ausente_se_regenera(tmp_path, monkeypatch):
    for attr, sub in (("DIR_IMERG", "imerg"), ("DIR_POWER", "power"), ("DIR_BASELINES", "base")):
        monkeypatch.setattr(generate_cache, attr, str(tmp_path / sub))
    monkeypatch.setattr(cache_loader, "IMERS", str(tmp_path / "imerg"))
    monkeypatch.setattr(cache_loader, "POWERS", str(tmp_path / "power"))
    monkeypatch.setattr(cache_loader, "BASELINES", str(tmp_path / "base"))

    assert not cache_loader.load_imerg("flood").empty
    assert not cache_loader.load_power("flood").empty
    assert cache_loader.load_baselines("flood")["fuente_datos"] == "sintetico"
    assert (tmp_path / "imerg" / "flood_imerg.SYNTHETIC_CACHE.txt").exists()


def test_escenario_desconocido_falla_claro():
    with pytest.raises(FileNotFoundError):
        cache_loader.load_imerg("no_existe")


# ── Clima por latitud ───────────────────────────────────────────────────

def test_tropico_sin_helada_y_con_gdd():
    b = cache_loader.load_baselines("drought")
    assert b["tropical"] is True
    assert b["frost_method"] == "fin_temporada_lluvias"
    assert b["climatological_frost_date"] == b["season_end"]
    power = cache_loader.load_power("drought")
    assert power["T2M_MIN"].min() > 0, "no debe helar en el trópico"
    enero = power[(power["date"] >= "2025-01-01") & (power["date"] <= "2025-01-30")]
    assert ((enero["T2M_MAX"] + enero["T2M_MIN"]) / 2 - 10).clip(lower=0).sum() > 0


def test_latitud_templada_conserva_helada():
    b = cache_loader.load_baselines("flood")
    assert b["tropical"] is False
    assert b["frost_method"] == "first_T2M_MIN_<=0_after_day200"


def test_power_hemisferio_sur_invierte_estaciones():
    df = generate_cache.generar_power("2025-03-01", "2024-01-01", lat=-35.0)
    df["mes"] = pd.to_datetime(df["date"]).dt.month
    medias = df.groupby("mes")["T2M_MAX"].mean()
    assert medias[1] > medias[7], "enero debe ser más cálido que julio en el sur"


def test_bandas_helada_ambos_hemisferios():
    bandas = cache_loader.load_bandas_helada()
    assert bandas["norte"] and bandas["sur"]
    for banda in bandas["sur"]:
        assert {"lat_min", "lat_max", "primera_helada"} <= set(banda)


# ── Fuente de datos y cortacircuito ─────────────────────────────────────

def test_cortacircuito_abre_tras_umbral():
    cc = CortaCircuito(umbral=3)
    for _ in range(2):
        cc.registrar_fallo()
    assert not cc.esta_abierto()
    cc.registrar_fallo()
    assert cc.esta_abierto()
    cc.registrar_exito()
    assert not cc.esta_abierto()


def test_reintentos_con_espera_exponencial():
    esperas, llamadas = [], []

    def inestable():
        llamadas.append(1)
        if len(llamadas) < 3:
            raise ConnectionError("caída")
        return "ok"

    cc = CortaCircuito()
    assert llamar_con_reintentos(inestable, cortacircuito=cc, dormir=esperas.append) == "ok"
    assert esperas == [2.0, 4.0]
    assert cc.fallos == 0


def test_reintentos_agotados_cuentan_un_fallo():
    def siempre_falla():
        raise ConnectionError("caída")

    cc = CortaCircuito(umbral=1)
    with pytest.raises(RuntimeError):
        llamar_con_reintentos(siempre_falla, cortacircuito=cc, dormir=lambda s: None)
    assert cc.esta_abierto()
    with pytest.raises(RuntimeError, match="abierto"):
        llamar_con_reintentos(lambda: "ok", cortacircuito=cc)


def test_fuente_cae_a_sintetico_con_cortacircuito_abierto(monkeypatch):
    monkeypatch.setattr(cache_loader, "load_baselines", lambda n: {"fuente_datos": "nasa_power"})
    assert cache_loader.get_fuente_datos("flood") == "nasa_power"
    cc = CortaCircuito(umbral=1)
    cc.registrar_fallo()
    monkeypatch.setattr(cache_loader, "cortacircuito_en_vivo", cc)
    assert cache_loader.get_fuente_datos("flood") == "sintetico"


# ── POWER real (red simulada) ───────────────────────────────────────────

class _RespuestaFalsa:
    def __init__(self, cuerpo):
        self._cuerpo = cuerpo

    def raise_for_status(self):
        pass

    def json(self):
        return self._cuerpo


def test_descargar_power_interpreta_respuesta(monkeypatch):
    import requests

    cuerpo = {"properties": {"parameter": {
        "T2M_MAX": {"20240618": 30.1, "20240619": -999.0, "20240620": 28.0},
        "T2M_MIN": {"20240618": 18.2, "20240619": 17.0, "20240620": 16.5},
        "PRECTOTCORR": {"20240618": 0.0, "20240619": 55.3, "20240620": 80.4},
    }}}
    monkeypatch.setattr(requests, "get", lambda *a, **k: _RespuestaFalsa(cuerpo))
    df = imerg_etl.descargar_power(43.2, -96.3, "2024-06-18", "2024-06-20")
    assert list(df.columns) == ["date", "T2M_MAX", "T2M_MIN", "PRECTOTCORR"]
    assert list(df["date"]) == ["2024-06-18", "2024-06-20"], "el día con -999 se descarta"


def test_actualizar_cache_real_no_toca_cache_si_falla(monkeypatch):
    def falla(*a, **k):
        raise RuntimeError("sin red")

    monkeypatch.setattr(imerg_etl, "descargar_power", falla)
    antes = cache_loader.load_baselines("flood")
    assert imerg_etl.actualizar_cache_real("flood") == "sintetico"
    assert cache_loader.load_baselines("flood") == antes


# ── Suelo, OpenET y SMAP sin red en modo demo ───────────────────────────

@pytest.fixture
def sin_red(monkeypatch):
    import requests

    def prohibido(*a, **k):
        raise AssertionError("no debe haber llamadas de red en modo demo")

    monkeypatch.setattr(requests, "get", prohibido)


def test_suelo_sin_red_y_con_claves_nuevas(sin_red):
    suelo = lookup_soil(9.0, 41.0)
    assert suelo["source"] == "climate_zone_estimate"
    assert suelo["capacidad_retencion_mm"] == suelo["field_capacity_mm"] - suelo["wilting_point_mm"]
    assert suelo["materia_organica_pct"] > 0
    assert suelo["textura"] == suelo["texture_class"]


def test_openet_estimado_y_luego_cache(sin_red, tmp_path):
    args = (41.8, -93.6, "2025-05-01", "2025-05-10")
    df = fetch_openet_eta(*args, cache_dir=str(tmp_path))
    assert list(df.columns) == ["date", "eta_mm"] and len(df) == 10
    assert df.attrs["fuente"] == "estimado"
    otra = fetch_openet_eta(*args, cache_dir=str(tmp_path))
    assert otra.attrs["fuente"] == "estimado", "el marcador sintético se respeta al releer"
    assert otra["eta_mm"].tolist() == df["eta_mm"].tolist()


def test_smap_estimado_dentro_de_rango(sin_red, tmp_path):
    df = fetch_smap_moisture(9.0, 41.0, "2025-01-01", "2025-01-30", cache_dir=str(tmp_path))
    assert list(df.columns) == ["date", "soil_moisture_vol_pct"] and len(df) == 30
    assert df["soil_moisture_vol_pct"].between(5.0, 45.0).all()
    assert df.attrs["fuente"] == "estimado"
