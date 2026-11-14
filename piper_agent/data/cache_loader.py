"""Demo cache loader for PIER.

Demo serves only cached data; live Earthdata/POWER is production path (Spec §8).
Set PIER_DEMO_MODE=0 to attempt live calls (not implemented in this stage).
"""
import json
import os
from datetime import date

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMERS = os.path.join(ROOT, "data", "cache", "imerg")
POWERS = os.path.join(ROOT, "data", "cache", "power")
BASELINES = os.path.join(ROOT, "data", "baselines")
DEMOS = os.path.join(ROOT, "..", "demo")

PIER_DEMO_MODE = os.environ.get("PIER_DEMO_MODE", "1") == "1"


def load_imerg(demo_name: str) -> pd.DataFrame:
    """Load cached IMERG daily rainfall (date, precipitation_mm)."""
    path = os.path.join(IMERS, f"{demo_name}_imerg.csv")
    df = pd.read_csv(path, parse_dates=["date"])
    return df


def load_power(demo_name: str) -> pd.DataFrame:
    """Load cached POWER daily data (date, T2M_MAX, T2M_MIN, PRECTOTCORR)."""
    path = os.path.join(POWERS, f"{demo_name}_power.csv")
    df = pd.read_csv(path, parse_dates=["date"])
    return df


def load_baselines(demo_name: str) -> dict:
    """Load cached baselines (p95, p10, climatological_frost_date)."""
    path = os.path.join(BASELINES, f"{demo_name}_baselines.json")
    with open(path) as f:
        return json.load(f)


def load_demo_packet(name: str) -> dict:
    """Load a demo packet JSON (demo/{name}.json)."""
    path = os.path.join(DEMOS, f"{name}.json")
    with open(path) as f:
        return json.load(f)


__all__ = ["load_imerg", "load_power", "load_baselines", "load_demo_packet", "PIER_DEMO_MODE"]
