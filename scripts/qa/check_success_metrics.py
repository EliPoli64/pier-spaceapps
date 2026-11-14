#!/usr/bin/env python3
"""Q3 — Spec §10 success-metrics report (feat/qa-integracion).

    python scripts/qa/check_success_metrics.py            # human-readable table
    python scripts/qa/check_success_metrics.py --markdown # for CI / PR comments
    python scripts/qa/check_success_metrics.py --json
    python scripts/qa/check_success_metrics.py --live     # production path: network allowed
                                                          # but recorded per run

Runs every demo scenario through ``run_pier`` with ALL outbound network
connections blocked, so a PASS on the cache-only metric is real evidence
that the demo does not depend on NASA services (Spec §8/§10). Exit code is
1 if any Spec §10 metric fails. Post-MVP metrics are reported but never
fail the run.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from dataclasses import asdict, dataclass

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO_ROOT)
# Some tools still resolve data paths against the cwd (see the A2/D2 gap), so the
# report always runs from the repository root, wherever it is launched from.
os.chdir(REPO_ROOT)

LATE_SEASON = ("late_flood",)   # demo packet for the BR-5 fallback (Q7)


@dataclass
class Metric:
    id: str
    title: str
    passed: bool
    evidence: str
    required: bool = True


# ── Network guard ────────────────────────────────────────────────────────────

_attempts: list[str] = []
_mode = {"block": True}
_real_connect = socket.socket.connect
_real_getaddrinfo = socket.getaddrinfo
_LOCAL = {"127.0.0.1", "::1", "localhost"}


def _guard_connect(self, address, *a, **k):
    host = address[0] if isinstance(address, tuple) else str(address)
    if host in _LOCAL or self.family == getattr(socket, "AF_UNIX", -1):
        return _real_connect(self, address, *a, **k)
    _attempts.append(f"connect {address}")
    if not _mode["block"]:
        return _real_connect(self, address, *a, **k)
    raise OSError(f"[qa] network blocked: {address}")


def _guard_getaddrinfo(host, *a, **k):
    if host not in _LOCAL and host is not None:
        _attempts.append(f"dns {host}")
        if not _mode["block"]:
            return _real_getaddrinfo(host, *a, **k)
        raise OSError(f"[qa] DNS blocked: {host}")
    return _real_getaddrinfo(host, *a, **k)


def block_network() -> None:
    socket.socket.connect = _guard_connect
    socket.getaddrinfo = _guard_getaddrinfo


def restore_network() -> None:
    socket.socket.connect = _real_connect
    socket.getaddrinfo = _real_getaddrinfo


# ── Runs ─────────────────────────────────────────────────────────────────────

LIVE_SOURCES = ("nasa_power", "nasa_power+imerg")


def run(name: str, current_date: str | None = None, live: bool = False) -> dict:
    from piper_agent.agent import run_pier
    from piper_agent.data.cache_loader import load_demo_packet

    pkt = load_demo_packet(f"{name}_demo")
    t0 = time.perf_counter()
    before = len(_attempts)
    res = run_pier(lat=pkt["lat"], lon=pkt["lon"], current_date=current_date or pkt["current_date"],
                   demo_mode=not live, demo_name=name)
    res["_elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    res["_network_calls"] = len(_attempts) - before
    if not res.get("fuente_datos"):
        try:
            from piper_agent.data.cache_loader import get_fuente_datos
            res["fuente_datos"] = get_fuente_datos(name)
        except Exception:  # noqa: BLE001
            res["fuente_datos"] = None
    return res


def evaluate(live: bool = False) -> list[Metric]:
    _attempts.clear()
    _mode["block"] = not live
    results: dict[str, dict] = {}
    errors: dict[str, str] = {}
    block_network()
    try:
        for key, args in {"flood": ("flood",), "drought": ("drought",), "normal": ("normal",),
                          "late": LATE_SEASON}.items():
            try:
                results[key] = run(*args, live=live)
            except Exception as exc:  # noqa: BLE001
                errors[key] = f"{type(exc).__name__}: {exc}"
    finally:
        restore_network()

    def ev(key):
        return results[key]["event_result"].event_type if key in results else f"ERROR ({errors[key]})"

    def crops(key):
        return [c.crop for c in results[key]["crops"]] if key in results else []

    m: list[Metric] = []
    for key, expected in (("flood", "flood"), ("drought", "drought"), ("normal", "none")):
        got = ev(key)
        m.append(Metric(f"S10.1-{key}", f"{key} demo → event_type = {expected}",
                        got == expected, f"got {got}"))
    for key in ("flood", "drought"):
        c = crops(key)
        m.append(Metric(f"S10.2-{key}", f"≥2 eligible rescue crops ({key})",
                        len(c) >= 2, ", ".join(c) or errors.get(key, "none")))
    late = results.get("late")
    late_ok = bool(late) and late["recovery_plan"].fallback and "cash crop is lost" in late["plan_text"]
    m.append(Metric("S10.3", "Fallback cover crop + 'cash crop is lost' (late_flood demo)",
                    late_ok, "fallback triggered" if late_ok else errors.get("late", "no fallback")))
    if not live:
        m.append(Metric("S10.4", "All IMERG/POWER served from cache (network blocked)",
                        not _attempts and not errors,
                        "0 network attempts" if not _attempts else "; ".join(_attempts[:3])))

    # Data-source honesty: a run may only be labeled live if it actually used the network.
    lies = [f"{k}: labeled {r['fuente_datos']} with 0 network calls"
            for k, r in results.items() if r.get("fuente_datos") in LIVE_SOURCES and r["_network_calls"] == 0]
    hidden = [f"{k}: {r['_network_calls']} network calls but labeled {r.get('fuente_datos')}"
              for k, r in results.items()
              if r["_network_calls"] > 0 and r.get("fuente_datos") not in LIVE_SOURCES]
    labels = ", ".join(f"{k}={r.get('fuente_datos')} ({r['_network_calls']} calls)" for k, r in results.items())
    m.append(Metric("SRC", "fuente_datos matches the network evidence of each run",
                    not lies and not hidden, "; ".join(lies + hidden) or labels or "no runs",
                    required=not live))
    if live:
        live_ok = [k for k, r in results.items() if r.get("fuente_datos") in LIVE_SOURCES]
        m.append(Metric("LIVE", "Production path returns live NASA data",
                        bool(live_ok),
                        f"live: {live_ok or 'none'}; " + (
                            f"{len(errors)} scenario(s) failed, e.g. {next(iter(errors.values()))[:120]}"
                            if errors else "no errors"),
                        required=False))

    # Post-MVP (informational)
    if "flood" in results:
        r = results["flood"]
        m.append(Metric("PM-BR9", "Rescue recommendation includes next-season rotation (BR-9)",
                        bool(r.get("rotacion")), "run_pier key 'rotacion'", required=False))
        m.append(Metric("PM-BR11", "Recommendation includes dollar estimate (BR-11)",
                        bool(r.get("ahorro")), "run_pier key 'ahorro'", required=False))
        confs = [c.rescue_confidence for c in r["crops"]]
        m.append(Metric("PM-conf", "Rescue confidence not saturated at 100%",
                        bool(confs) and (max(confs) < 1 or len(set(confs)) > 1),
                        f"confidences {confs}", required=False))
    if "normal" in results:
        r = results["normal"]
        ok = not r["recovery_plan"].fallback and "cash crop is lost" not in r["plan_text"]
        m.append(Metric("PM-none", "No-event scenario does not declare the crop lost",
                        ok, "fallback=%s" % r["recovery_plan"].fallback, required=False))
    worst = max((r["_elapsed_ms"] for r in results.values()), default=0)
    m.append(Metric("PM-latency", "Agent run < 500 ms on cached data",
                    bool(results) and worst < 500,
                    f"slowest scenario {worst} ms", required=False))
    return m


# ── Output ───────────────────────────────────────────────────────────────────

def as_text(metrics: list[Metric]) -> str:
    lines = ["PIER — Spec §10 success metrics", "=" * 60]
    for section, req in (("Required (Spec §10)", True), ("Post-MVP (informational)", False)):
        lines.append(f"\n{section}")
        for x in (x for x in metrics if x.required is req):
            mark = "PASS" if x.passed else ("FAIL" if req else "TODO")
            lines.append(f"  [{mark}] {x.title}\n         {x.evidence}")
    req = [x for x in metrics if x.required]
    lines.append(f"\n{sum(x.passed for x in req)}/{len(req)} required metrics pass")
    return "\n".join(lines)


def as_markdown(metrics: list[Metric]) -> str:
    out = ["## PIER — Spec §10 success metrics", "", "| | Metric | Evidence |", "|---|---|---|"]
    for x in metrics:
        icon = "✅" if x.passed else ("❌" if x.required else "⏳")
        tag = "" if x.required else " _(post-MVP)_"
        out.append(f"| {icon} | {x.title}{tag} | {x.evidence.replace('|', '/')} |")
    req = [x for x in metrics if x.required]
    out += ["", f"**{sum(x.passed for x in req)}/{len(req)} required metrics pass.**"]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--markdown", action="store_true")
    g.add_argument("--json", action="store_true")
    ap.add_argument("--live", action="store_true",
                    help="run the production path (demo_mode=False) with network recorded, not blocked")
    args = ap.parse_args(argv)

    metrics = evaluate(live=args.live)
    if args.json:
        print(json.dumps([asdict(x) for x in metrics], indent=2, ensure_ascii=False))
    elif args.markdown:
        print(as_markdown(metrics))
    else:
        print(as_text(metrics))
    return 0 if all(x.passed for x in metrics if x.required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
