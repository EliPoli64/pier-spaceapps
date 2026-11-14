"""Tests for the QA scripts themselves (scripts/qa/)."""
from __future__ import annotations

import importlib.util
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT

QA_DIR = Path(REPO_ROOT) / "scripts" / "qa"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"qa_{name}", QA_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"qa_{name}"] = mod          # dataclasses need the module registered
    spec.loader.exec_module(mod)
    return mod


# ── check_success_metrics ────────────────────────────────────────────────────

def test_success_metrics_all_required_pass(capsys):
    mod = _load("check_success_metrics")
    rc = mod.main(["--markdown"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "required metrics pass" in out
    assert "❌" not in out
    assert socket.socket.connect is mod._real_connect      # network guard restored


def test_success_metrics_json_shape(capsys):
    import json

    mod = _load("check_success_metrics")
    mod.main(["--json"])
    data = json.loads(capsys.readouterr().out)
    ids = {m["id"] for m in data}
    assert {"S10.1-flood", "S10.1-drought", "S10.1-normal", "S10.2-flood", "S10.2-drought",
            "S10.3", "S10.4"} <= ids


# ── branch_overlap (on a throw-away git repo) ────────────────────────────────

def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


@pytest.fixture
def fake_remote_repo(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "master")
    (repo / "piper_agent" / "tools").mkdir(parents=True)
    (repo / "piper_agent" / "api").mkdir(parents=True)
    (repo / "piper_agent" / "tools" / "fetch_power_gdd.py").write_text("x = 1\n")
    (repo / "piper_agent" / "api" / "main.py").write_text("app = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")

    def branch(name, path, content):
        _git(repo, "checkout", "-q", "-b", name, "master")
        (repo / path).write_text(content)
        _git(repo, "commit", "-qam", name)

    branch("feat/logica-herramientas", "piper_agent/tools/fetch_power_gdd.py", "x = 2\n")
    branch("feat/gdd-climate", "piper_agent/tools/fetch_power_gdd.py", "x = 3\n")
    branch("feat/ui-pwa", "piper_agent/api/main.py", "app = 2\n")        # outside Matias's paths
    _git(repo, "checkout", "-q", "master")
    for ref in ("master", "feat/logica-herramientas", "feat/gdd-climate", "feat/ui-pwa"):
        _git(repo, "update-ref", f"refs/remotes/origin/{ref}", ref)
    return repo


def test_branch_overlap_finds_conflicts_and_scope(fake_remote_repo, monkeypatch):
    mod = _load("branch_overlap")
    monkeypatch.chdir(fake_remote_repo)
    r = mod.build_report("origin", "origin/master")

    assert set(r["branches"]) == {"origin/feat/logica-herramientas", "origin/feat/gdd-climate",
                                  "origin/feat/ui-pwa"}
    assert r["overlaps"]["piper_agent/tools/fetch_power_gdd.py"] == [
        "origin/feat/gdd-climate", "origin/feat/logica-herramientas"]
    conflict = r["pairs"][("origin/feat/gdd-climate", "origin/feat/logica-herramientas")]
    assert conflict == ["piper_agent/tools/fetch_power_gdd.py"]
    assert r["out_of_scope"] == {"origin/feat/ui-pwa": ["piper_agent/api/main.py"]}
    assert all(c == [] for c in r["vs_base"].values())
    md = mod.as_markdown(r, "origin")
    assert "Predicted merge conflicts" in md and "fetch_power_gdd.py" in md


def test_source_label_must_match_network_evidence(monkeypatch):
    """A run labeled live (nasa_power) with zero network calls must fail the SRC metric."""
    mod = _load("check_success_metrics")
    real_run = mod.run

    def lying_run(*a, **k):
        res = real_run(*a, **k)
        res["fuente_datos"] = "nasa_power"
        return res

    monkeypatch.setattr(mod, "run", lying_run)
    src = next(m for m in mod.evaluate() if m.id == "SRC")
    assert src.passed is False and "0 network calls" in src.evidence


def test_source_label_honest_in_demo():
    mod = _load("check_success_metrics")
    src = next(m for m in mod.evaluate() if m.id == "SRC")
    assert src.passed and src.required
