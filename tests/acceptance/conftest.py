"""Shared fixtures for the acceptance suite (Q2, feat/qa-integracion).

* ``gap(owner, task, why)`` marks a test that documents a known gap owned by
  another branch. It is a non-strict xfail: CI stays green while the gap is
  open and the test shows up as XPASS (✅ fixed) once the owner's branch lands.
  The terminal summary groups gaps by owner.
* ``no_network`` blocks every outbound socket connection, so a test using it
  proves the demo runs from cache only (Spec §10, "verified by network log").
"""
from __future__ import annotations

import os
import socket
import sys
from collections import defaultdict

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

_GAP_PREFIX = "GAP"


def gap(owner: str, task: str, why: str):
    """xfail marker for a known gap owned by ``owner`` (plan task ``task``)."""
    return pytest.mark.xfail(strict=False, reason=f"{_GAP_PREFIX}[{owner} {task}] {why}")


class NetworkBlocked(RuntimeError):
    pass


@pytest.fixture
def no_network(monkeypatch):
    """Fail loudly on any non-local network connection."""
    attempts: list = []
    real_connect = socket.socket.connect

    def guarded_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host in ("127.0.0.1", "::1", "localhost") or self.family == getattr(socket, "AF_UNIX", -1):
            return real_connect(self, address, *args, **kwargs)
        attempts.append(address)
        raise NetworkBlocked(f"Network access attempted during demo: {address}")

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host not in ("127.0.0.1", "::1", "localhost", None):
            attempts.append(host)
            raise NetworkBlocked(f"DNS lookup attempted during demo: {host}")
        return real_getaddrinfo(host, *args, **kwargs)

    real_getaddrinfo = socket.getaddrinfo
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    yield attempts


def pytest_terminal_summary(terminalreporter, exitstatus, config):  # pragma: no cover
    by_owner: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for kind in ("xfailed", "xpassed"):
        for rep in terminalreporter.stats.get(kind, []):
            reason = getattr(rep, "wasxfail", "") or ""
            if not reason.startswith(_GAP_PREFIX):
                continue
            owner_task = reason[len(_GAP_PREFIX) + 1: reason.index("]")]
            status = "✅ FIXED (remove the gap marker)" if kind == "xpassed" else "⏳ open"
            by_owner[owner_task.split()[0]].append((status, f"{owner_task}: {rep.nodeid.split('::')[-1]}"))
    if not by_owner:
        return
    terminalreporter.section("Known gaps by owner (feat/qa-integracion)")
    for owner in sorted(by_owner):
        terminalreporter.write_line(f"{owner}:")
        for status, line in sorted(by_owner[owner]):
            terminalreporter.write_line(f"   {status:34s} {line}")
