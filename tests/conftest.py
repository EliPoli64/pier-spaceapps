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
