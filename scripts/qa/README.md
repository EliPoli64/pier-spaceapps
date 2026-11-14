# QA & integration (`feat/qa-integracion`)

Section "QA / Integration" of `PLAN_SEIS_PERSONAS.md` (Q1–Q5). Owner: Danny.
Only new paths: `.github/workflows/qa.yml`, `tests/acceptance/**`, `scripts/qa/**`.

## Tools

| Command | What it tells you |
|---|---|
| `python -m pytest tests/acceptance -q -rxX` | Spec §10 + business rules. Ends with **"Known gaps by owner"**: ⏳ open or ✅ FIXED per person/task |
| `python scripts/qa/check_success_metrics.py` | PASS/FAIL of every Spec §10 metric with the network **blocked** (proof the demo is cache-only). Run it before recording the demo |
| `python scripts/qa/branch_overlap.py --fetch` | Per branch: files outside the owner's paths, files touched by several branches, and **predicted merge conflicts** (vs master and between every pair), without checking anything out |
| GitHub Actions **PIER QA** | Runs all of the above on every `feat/**` push and every PR; the Spec §10 table appears in the job summary |

Before merging any branch into master: `python scripts/qa/branch_overlap.py --fetch --markdown`
and paste the output in the PR.

## How the gap markers work

A test decorated with `@gap("Owner", "Task", "why")` documents something that is not done yet.
It is a non-strict `xfail`: CI stays green while it fails. When the owner's branch fixes it, the
test **XPASSes** and the summary shows `✅ FIXED (remove the gap marker)` — the owner then deletes
the decorator so the requirement is locked in.

## Gaps found (Q5) and their status

Unowned gaps found in Q5, now **fixed** by Danny in Q6–Q7 (`feat/qa-brechas-sin-dueno`):

| Gap | Fix | Locked by |
|---|---|---|
| `detect_event` ignored `current_date` (fixed packet window; Iowa auto-detect = always flood) | `agent.py`: detection window = last 7 days ending on the requested date (newest available week + a note in the plan when the date is after the cached data); auto-detect picks the Iowa scenario whose data covers the date. The API uses the same logic | `test_q6_*`, `test_auto_select_demo`, `test_autodetect_follows_the_date` |
| No demo packet for the BR-5 fallback | `demo/late_flood_demo.json` (Iowa, 2025-08-28 storm). Scenario list is now discovered from `demo/*_demo.json`, so the cache is generated for it automatically. Added to the Streamlit and PWA selectors | `test_q7_*`, Spec §10 report uses it |
| Drought demo with temperate temperatures | Fixed by Erik's `feat/datos-cache` (tropical profile) | `test_tropical_drought_demo_is_plausible` |

Still open, unassigned in the plan (suggested owner Neithan):

| Gap | Evidence (test) |
|---|---|
| GDD remaining is summed from **future observations** in the cache (look-ahead); without them it becomes 0. On the real decision date only climatology is known | `test_gap_gdd_remaining_has_no_lookahead` |

Gaps already in someone's task list (tracked so you can see when they land):
Alina A2/A3/A4/A7/A8, Neithan N1. Already landed: Erik E2 (cache-first), Elias (requirements),
Neithan/Erik N4/E1 (`season_end`).

Also noticed:

- Ownership overlaps in the plan that will produce merge conflicts if two people edit them:
  `tools/fetch_power_gdd.py` (Alina `tools/**`, Neithan, Erik E4), `config.py` (Alina, Neithan),
  `data/baselines/` (Erik, Neithan), `demo/*.json` (Erik E1, Neithan N4). Agree who edits each
  before starting; `branch_overlap.py` will show it as soon as both branches are pushed.
- Plan task Elias E8 puts an SMS simulator in `piper_agent/ui/`, which is Matias's folder.
