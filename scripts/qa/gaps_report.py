#!/usr/bin/env python3
"""Known-gaps report: each gap with its disposition, owner, deadline and live test status.

    python scripts/qa/gaps_report.py            # text
    python scripts/qa/gaps_report.py --markdown # for CI summary / PR comments
    python scripts/qa/gaps_report.py --no-run   # registry only, without running the tests

Runs the registered xfail tests once to show which ones already pass (fixed
upstream but still marked) — those need their marker removed and the entry
set to ``fixed``.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = REPO_ROOT / "tests" / "acceptance" / "gaps.py"
ICON = {"fixed": "✅", "accepted": "🟡", "follow_up": "🔴"}
IMPACT = {"visible": "👀 visible", "hidden": "hidden", "none": "none"}


def load_registry() -> dict:
    spec = importlib.util.spec_from_file_location("pier_gaps", REGISTRY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.GAPS


def test_status(names: list[str]) -> dict[str, str]:
    """{test name: 'still failing' | 'NOW PASSES' | 'error'} by running the suite once."""
    with TemporaryDirectory() as tmp:
        xml = Path(tmp) / "r.xml"
        subprocess.run([sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:warnings",
                        "-p", "no:cacheprovider", f"--junitxml={xml}", "-k", " or ".join(names)],
                       cwd=REPO_ROOT, capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(REPO_ROOT)})
        if not xml.exists():
            return {}
        out: dict[str, str] = {}
        for case in ET.parse(xml).iter("testcase"):
            name = case.get("name", "").split("[")[0]
            if name not in names:
                continue
            skipped = case.find("skipped")
            if skipped is not None and "xfail" in (skipped.get("type", "") + skipped.get("message", "")):
                out.setdefault(name, "still failing")
            elif case.find("failure") is not None or case.find("error") is not None:
                out[name] = "error"
            else:
                out[name] = "NOW PASSES"
        return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--no-run", action="store_true")
    args = ap.parse_args(argv)

    gaps = load_registry()
    status = {} if args.no_run else test_status(sorted(gaps))
    order = {"follow_up": 0, "accepted": 1, "fixed": 2}
    rows = sorted(gaps.items(), key=lambda kv: (order[kv[1]["disposition"]], kv[1]["owner"], kv[0]))

    counts = {d: sum(g["disposition"] == d for g in gaps.values()) for d in order}
    if args.markdown:
        print("## PIER — known gaps\n")
        print(f"🔴 follow-up: **{counts['follow_up']}** · 🟡 accepted: **{counts['accepted']}** · "
              f"✅ fixed: **{counts['fixed']}**\n")
        print("| | Gap | Owner | Until | Demo | Test |")
        print("|---|---|---|---|---|---|")
        for name, g in rows:
            st = status.get(name, "—")
            st = "⚠️ NOW PASSES — remove marker" if st == "NOW PASSES" else st
            print(f"| {ICON[g['disposition']]} | {g['title']} | {g['owner']} ({g['task']}) | "
                  f"{g.get('when', '')} | {IMPACT[g['demo_impact']]} | {st} |")
    else:
        print(f"PIER known gaps — follow-up {counts['follow_up']}, accepted {counts['accepted']}, "
              f"fixed {counts['fixed']}\n")
        for name, g in rows:
            print(f"[{g['disposition'].upper():9s}] {g['title']}")
            print(f"    owner {g['owner']} ({g['task']}) · until: {g.get('when', '-')} · "
                  f"demo: {g['demo_impact']} · test: {status.get(name, '-')}")
            print(f"    {g['rationale']}\n")
    stale = [n for n, s in status.items() if s == "NOW PASSES" and gaps[n]["disposition"] != "fixed"]
    if stale:
        print(f"\nThese now pass — mark them fixed and remove the marker: {', '.join(stale)}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
