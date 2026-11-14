"""Tests for Stage 10: data fidelity & ingestion pipeline."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from piper_agent.data.soil_lookup import lookup_soil, _texture_from_grids, _field_capacity_wilting, _climate_zone_from_lat
from piper_agent.data.redis_cache import get, set, invalidate_prefix, get_json, set_json


def test_soil_lookup_user_override():
    res = lookup_soil(lat=41.8, lon=-93.6, user_texture="Loam")
    assert res["texture_class"] == "Loam"
    assert res["source"] == "user"
    assert res["field_capacity_mm"] == 180
    assert res["wilting_point_mm"] == 90


def test_soil_lookup_unknown_texture_defaults_to_loam():
    res = lookup_soil(lat=41.8, lon=-93.6, user_texture="UnknownTexture")
    assert res["field_capacity_mm"] == 180
    assert res["wilting_point_mm"] == 90


def test_climate_zone_from_lat():
    assert _climate_zone_from_lat(65) == "montane"
    assert _climate_zone_from_lat(40) == "temperate"
    assert _climate_zone_from_lat(20) == "semi_arid"
    assert _climate_zone_from_lat(10) == "tropical"
    assert _climate_zone_from_lat(0) == "arid"


def test_texture_from_grids():
    # High sand → sandy loam
    props = {"sand": 600, "silt": 250, "clay": 150}
    assert _texture_from_grids(props) in ("Sandy loam", "Loam", "Sandy clay loam")
    # High clay → clay
    props = {"sand": 200, "silt": 200, "clay": 600}
    assert _texture_from_grids(props) in ("Clay", "Sandy clay", "Silty clay")


def test_field_capacity_wilting():
    fc, wp = _field_capacity_wilting("Sand")
    assert fc > wp
    fc, wp = _field_capacity_wilting("Clay")
    assert fc > wp


def test_redis_cache_set_get():
    set("test_key_123", {"hello": "world"}, ttl=60)
    val = get("test_key_123")
    assert val == {"hello": "world"}


def test_redis_cache_json():
    set_json("test_json_key", {"a": 1, "b": 2}, ttl=60)
    val = get_json("test_json_key")
    assert val == {"a": 1, "b": 2}


def test_redis_cache_missing():
    assert get("nonexistent_key_xyz") is None


def test_redis_cache_invalidate_prefix():
    set("prefix_foo", "val1", ttl=60)
    set("prefix_bar", "val2", ttl=60)
    set("other_baz", "val3", ttl=60)
    count = invalidate_prefix("prefix_")
    assert count >= 2
    assert get("prefix_foo") is None
    assert get("prefix_bar") is None
    assert get("other_baz") == "val3"
