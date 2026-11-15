"""Test-wide settings: never write the API run store into the user's home."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolated_api_store(tmp_path_factory):

    mp = pytest.MonkeyPatch()
    mp.setenv("PIER_API_DB", str(tmp_path_factory.mktemp("pier_store") / "pier_api.sqlite3"))
    try:
        from piper_agent.api.store import reset_store
        reset_store()
    except Exception:  # noqa: BLE001  (API package not importable → nothing to isolate)
        pass
    yield
    mp.undo()


@pytest.fixture
def offline_live(monkeypatch):
    """Production path (demo_mode=False) without network: ingestion falls back to synthetic data.

    `ingest_point` keeps its real signature but runs in demo mode and records why, exactly
    as it does when NASA POWER is unreachable; SoilGrids is skipped (climate-zone estimate).
    """
    from piper_agent.data import soil_lookup
    from piper_agent.data.ingestion import pipeline

    real = pipeline.ingest_point

    def offline(lat, lon, start, end, demo_mode=None, **kw):
        data = real(lat, lon, start, end, demo_mode=True, **kw)
        data["fallback_reason"] = "network disabled in tests"
        return data

    monkeypatch.setattr(pipeline, "ingest_point", offline)
    monkeypatch.setattr(soil_lookup, "_soilgrids_query", lambda lat, lon: None)
