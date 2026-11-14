#!/usr/bin/env python3
"""Q4 — Branch ownership & merge-conflict report (feat/qa-integracion).

    git fetch origin '+refs/heads/*:refs/remotes/origin/*'
    python scripts/qa/branch_overlap.py              # text report
    python scripts/qa/branch_overlap.py --markdown   # for a PR comment
    python scripts/qa/branch_overlap.py --fetch      # fetch first

For every remote branch (except master) it shows:
  1. files changed outside the owner's paths from PLAN_SEIS_PERSONAS.md,
  2. files changed by more than one branch,
  3. real merge conflicts: branch vs master and every pair of branches,
     computed with `git merge-tree --write-tree` (no checkout, nothing changes).

Exit code is always 0: this is information for the integration step.
"""
from __future__ import annotations

import argparse
import fnmatch
import itertools
import subprocess
import sys
from collections import defaultdict

# Ownership from PLAN_SEIS_PERSONAS.md ("Owns (file paths)" + task tables).
OWNERS: dict[str, tuple[str, tuple[str, ...]]] = {
    "feat/datos-cache": ("Erik", (
        "piper_agent/data/*", "demo/*", ".env.example")),
    "feat/logica-herramientas": ("Alina", (
        "piper_agent/tools/*", "piper_agent/contracts.py", "piper_agent/config.py",
        "piper_agent/agent.py")),
    "feat/gdd-climate": ("Neithan", (
        "piper_agent/tools/fetch_power_gdd.py", "piper_agent/data/baselines/*",
        "piper_agent/config.py", "piper_agent/__main__.py", "demo/*")),
    "feat/api-backend": ("Danny", ("piper_agent/api/*",)),
    "feat/ui-pwa": ("Matias", ("piper_agent/ui/*",)),
    "feat/docs-entrega": ("Elias", (
        "docs/*", "README.md", "requirements.txt", ".gitattributes", ".env.example",
        "Dockerfile", ".github/workflows/ci.yml")),
    "dev-elias": ("Elias", (
        "docs/*", "README.md", "requirements.txt", ".gitattributes", ".env.example",
        "Dockerfile", ".github/workflows/ci.yml")),
    "feat/qa-integracion": ("Danny (QA)", (
        ".github/workflows/qa.yml", "tests/acceptance/*", "scripts/qa/*")),
}
# Anyone may add their own tests and update their status line in the plan.
SHARED_OK = ("tests/*", "PLAN_SEIS_PERSONAS.md")


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=check)


def remote_branches(remote: str, base: str) -> list[str]:
    out = git("for-each-ref", "--format=%(refname:short)", f"refs/remotes/{remote}").stdout.split()
    skip = {f"{remote}/HEAD", f"{remote}", base}
    return sorted(b for b in out if b not in skip)


def changed_files(base: str, ref: str) -> tuple[list[str], str]:
    r = git("diff", "--name-only", f"{base}...{ref}", check=False)
    if r.returncode == 0:
        return [f for f in r.stdout.splitlines() if f], ""
    r = git("diff", "--name-only", base, ref, check=False)        # shallow clone: no merge base
    return [f for f in r.stdout.splitlines() if f], "no merge-base (shallow clone?) — two-dot diff"


def merge_conflicts(a: str, b: str) -> list[str] | None:
    """Conflicting paths when merging a and b; None if git cannot compute it."""
    r = git("merge-tree", "--write-tree", "--name-only", "--no-messages", a, b, check=False)
    if r.returncode == 0:
        return []
    if r.returncode == 1:
        lines = r.stdout.splitlines()[1:]                         # first line: tree id
        return sorted({ln for ln in lines if ln.strip()})
    return None


def owned(path: str, globs: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in globs + SHARED_OK)


def build_report(remote: str, base: str) -> dict:
    branches = remote_branches(remote, base)
    files: dict[str, list[str]] = {}
    notes: dict[str, str] = {}
    for b in branches:
        files[b], notes[b] = changed_files(base, b)

    out_of_scope: dict[str, list[str]] = {}
    for b, fl in files.items():
        short = b.split("/", 1)[1] if b.startswith(remote + "/") else b
        owner = OWNERS.get(short)
        if owner is None:
            out_of_scope[b] = ["(branch not in PLAN_SEIS_PERSONAS.md)"]
            continue
        bad = [f for f in fl if not owned(f, owner[1])]
        if bad:
            out_of_scope[b] = bad

    touched_by: dict[str, list[str]] = defaultdict(list)
    for b, fl in files.items():
        for f in fl:
            if f != "PLAN_SEIS_PERSONAS.md":
                touched_by[f].append(b)
    overlaps = {f: bs for f, bs in sorted(touched_by.items()) if len(bs) > 1}

    vs_base = {b: merge_conflicts(base, b) for b in branches}
    pairs = {}
    for a, b in itertools.combinations(branches, 2):
        c = merge_conflicts(a, b)
        if c:
            pairs[(a, b)] = c
        elif c is None:
            pairs[(a, b)] = ["(could not compute)"]
    return {"base": base, "branches": branches, "files": files, "notes": notes,
            "out_of_scope": out_of_scope, "overlaps": overlaps, "vs_base": vs_base, "pairs": pairs}


def person(branch: str, remote: str) -> str:
    short = branch.split("/", 1)[1] if branch.startswith(remote + "/") else branch
    return OWNERS.get(short, ("?",))[0]


def as_text(r: dict, remote: str) -> str:
    L = [f"PIER branch report (base {r['base']})", "=" * 60, "", "Branches:"]
    for b in r["branches"]:
        c = r["vs_base"][b]
        state = "clean merge" if c == [] else ("?" if c is None else f"CONFLICTS with base: {', '.join(c)}")
        L.append(f"  {b:34s} {person(b, remote):12s} {len(r['files'][b]):3d} files  {state}")
        if r["notes"][b]:
            L.append(f"      note: {r['notes'][b]}")
    L += ["", "Changes outside the owner's paths:"]
    L += [f"  {b}: {', '.join(fl)}" for b, fl in r["out_of_scope"].items()] or ["  none"]
    L += ["", "Files changed by more than one branch:"]
    L += [f"  {f}: {', '.join(bs)}" for f, bs in r["overlaps"].items()] or ["  none"]
    L += ["", "Merge conflicts between branches:"]
    L += [f"  {a} × {b}: {', '.join(c)}" for (a, b), c in r["pairs"].items()] or ["  none"]
    return "\n".join(L)


def as_markdown(r: dict, remote: str) -> str:
    L = [f"## PIER branch report (base `{r['base']}`)", "",
         "| Branch | Owner | Files | Merge into base |", "|---|---|---|---|"]
    for b in r["branches"]:
        c = r["vs_base"][b]
        state = "✅ clean" if c == [] else ("❔" if c is None else "❌ " + ", ".join(f"`{x}`" for x in c))
        L.append(f"| `{b}` | {person(b, remote)} | {len(r['files'][b])} | {state} |")
    L += ["", "### Outside the owner's paths"]
    L += [f"- `{b}`: " + ", ".join(f"`{f}`" for f in fl) for b, fl in r["out_of_scope"].items()] or ["None ✅"]
    L += ["", "### Same file in several branches"]
    L += [f"- `{f}`: " + ", ".join(f"`{b}`" for b in bs) for f, bs in r["overlaps"].items()] or ["None ✅"]
    L += ["", "### Predicted merge conflicts between branches"]
    L += [f"- `{a}` × `{b}`: " + ", ".join(f"`{x}`" for x in c) for (a, b), c in r["pairs"].items()] or ["None ✅"]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--base", default=None, help="default: <remote>/master")
    ap.add_argument("--fetch", action="store_true", help="fetch all remote branches first")
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args(argv)
    base = args.base or f"{args.remote}/master"
    if args.fetch:
        git("fetch", "--quiet", "--depth=200", args.remote,
            f"+refs/heads/*:refs/remotes/{args.remote}/*", check=False)
    try:
        report = build_report(args.remote, base)
    except subprocess.CalledProcessError as exc:
        print(f"git failed: {exc.stderr}", file=sys.stderr)
        return 0
    print(as_markdown(report, args.remote) if args.markdown else as_text(report, args.remote))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
