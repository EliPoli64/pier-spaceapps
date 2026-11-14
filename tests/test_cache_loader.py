"""Tests for Stage 1 cache layer."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from piper_agent.data.cache_loader import load_imerg, load_power, load_baselines, load_demo_packet, PIER_DEMO_MODE


def test_pier_demo_mode_defaults_true():
    assert PIER_DEMO_MODE is True, "PIER_DEMO_MODE should default to '1' (cache-only)"


def test_load_imerg_all_demos():
    for demo in ["flood", "drought", "normal"]:
        df = load_imerg(demo)
        assert not df.empty, f"{demo} IMERG empty"
        assert "date" in df.columns, f"{demo} IMERG missing date"
        assert "precipitation_mm" in df.columns, f"{demo} IMERG missing precipitation_mm"
        assert len(df) >= 30, f"{demo} IMERG has {len(df)} rows, need >=30"


def test_load_power_all_demos():
    for demo in ["flood", "drought", "normal"]:
        df = load_power(demo)
        assert not df.empty, f"{demo} POWER empty"
        for col in ["date", "T2M_MAX", "T2M_MIN", "PRECTOTCORR"]:
            assert col in df.columns, f"{demo} POWER missing {col}"
        assert len(df) >= 30, f"{demo} POWER has {len(df)} rows, need >=30"


def test_load_baselines_all_demos():
    for demo in ["flood", "drought", "normal"]:
        b = load_baselines(demo)
        assert "p95_3day_cum_rainfall" in b
        assert "p10_30day_cum_rainfall" in b
        assert "climatological_frost_date" in b
        assert b["p95_3day_cum_rainfall"] > 0
        assert b["p10_30day_cum_rainfall"] > 0


def test_load_demo_packets():
    for demo in ["flood_demo", "drought_demo", "normal_demo"]:
        pkt = load_demo_packet(demo)
        assert "name" in pkt
        assert "lat" in pkt and "lon" in pkt
        assert "current_date" in pkt


def test_flood_has_storm():
    df = load_imerg("flood")
    # Recent window 2025-05-10 to 2025-05-15 should have a 72h storm >100mm
    recent = df[(df["date"] >= "2025-05-10") & (df["date"] <= "2025-05-15")]
    cum3 = recent["precipitation_mm"].rolling(3).sum().max()
    assert cum3 > 100.0, f"Flood demo 72h cum={cum3:.1f}mm, expected >100mm"


def test_drought_has_deficit():
    df = load_imerg("drought")
    recent = df[(df["date"] >= "2025-01-01") & (df["date"] <= "2025-01-30")]
    cum30 = recent["precipitation_mm"].sum()
    b = load_baselines("drought")
    assert cum30 < b["p10_30day_cum_rainfall"], (
        f"Drought demo 30-day cum={cum30:.1f}mm, expected < p10_30day={b['p10_30day_cum_rainfall']:.1f}mm"
    )
