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

## Gaps found (Q5)

Things that are wrong today and that **no section of the plan assigns**:

| Gap | Evidence (test) | Suggested owner |
|---|---|---|
| `detect_event` ignores `current_date`: it always uses the demo packet's fixed window, so any Iowa date returns the packet's event (auto-detect = always flood) | `test_gap_detection_follows_current_date` | Alina (tools) |
| GDD remaining is summed from **future observations** in the cache (look-ahead); without them it becomes 0. On the real decision date only climatology is known | `test_gap_gdd_remaining_has_no_lookahead` | Neithan (GDD) |
| Drought demo (Ethiopia, 9°N) uses Iowa's temperate temperature cycle: 0 GDD accumulated and every crop "plant today (0 days)" | `test_gap_tropical_drought_demo_is_plausible` | Erik (synthetic data) |
| No demo packet for the BR-5 fallback: showing it requires typing a late date by hand | `test_gap_fallback_has_its_own_demo_packet` | Erik (demo packets) |

Gaps already in someone's task list (tracked so you can see when they land):
Alina A2/A3/A4/A7/A8, Neithan N1, Neithan/Erik N4/E1, Erik E2, Elias (requirements).

Also noticed:

- `ci.yml` on `dev-elias` was failing (`ModuleNotFoundError: fastapi`); once fixed it will fail
  again on a fresh runner because the demo cache is not committed. Fix: add
  `fastapi uvicorn httpx` to `requirements.txt` and run `python piper_agent/data/generate_cache.py`
  before `pytest` (as `qa.yml` does) until Erik's cache-first loader lands.
- Ownership overlaps in the plan that will produce merge conflicts if two people edit them:
  `tools/fetch_power_gdd.py` (Alina `tools/**`, Neithan, Erik E4), `config.py` (Alina, Neithan),
  `data/baselines/` (Erik, Neithan), `demo/*.json` (Erik E1, Neithan N4). Agree who edits each
  before starting; `branch_overlap.py` will show it as soon as both branches are pushed.
- Plan task Elias E8 puts an SMS simulator in `piper_agent/ui/`, which is Matias's folder.
