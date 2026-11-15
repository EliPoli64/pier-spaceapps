# QA & integration (`feat/qa-integracion`)

Section "QA / Integration" of `PLAN_SEIS_PERSONAS.md` (Q1–Q5). Owner: Danny.
Only new paths: `.github/workflows/qa.yml`, `tests/acceptance/**`, `scripts/qa/**`.

## Tools

| Command | What it tells you |
|---|---|
| `python -m pytest tests/acceptance -q -rxX` | Spec §10 + business rules. Ends with **"Known gaps by owner"**: ⏳ open or ✅ FIXED per person/task |
| `python scripts/qa/check_success_metrics.py` | PASS/FAIL of every Spec §10 metric with the network **blocked** (proof the demo is cache-only), plus `SRC`: each run's `fuente_datos` must match its real network use (a run labeled `nasa_power` with 0 calls fails). Run it before recording the demo |
| `python scripts/qa/check_success_metrics.py --live` | Production path (`demo_mode=False`): network allowed but **recorded per run**, so a claim of live data is verifiable |
| `python scripts/qa/branch_overlap.py --fetch` | Per branch with pending changes: files outside the owner's paths, files touched by several branches, and **predicted merge conflicts** (vs master and between every pair), without checking anything out. Ownership table includes the next-wave branches |
| GitHub Actions **PIER QA** | On every `feat/**` push and PR: blocking lint for hard errors (syntax, undefined names), style report, full suite, acceptance, Spec §10 table and (on PRs) the branch report in the job summary |

Before merging any branch into master: `python scripts/qa/branch_overlap.py --fetch --markdown`
and paste the output in the PR.

## How the gap markers work

A test decorated with `@gap("Owner", "Task", "why")` documents something that is not done yet.
It is a non-strict `xfail`: CI stays green while it fails. When the owner's branch fixes it, the
test **XPASSes** and the summary shows `✅ FIXED (remove the gap marker)` — the owner then deletes
the decorator so the requirement is locked in.

## Known gaps: every one is fixed, accepted or followed up

The registry is `tests/acceptance/gaps.py`. Each `xfail` / `@gap` test **must** have an entry with:
`disposition` (`fixed` | `accepted` | `follow_up`), a named `owner` + plan `task`, `when`
(deadline or condition), `demo_impact` (`visible` | `hidden` | `none`) and a written `rationale`.
`tests/acceptance/test_gap_registry.py` fails CI if an xfail is unregistered, an entry points to a
test that no longer exists, a `fixed` gap still has its marker, or a demo-visible follow-up has no
deadline.

```bash
python scripts/qa/gaps_report.py            # disposition + owner + deadline + live test status
python scripts/qa/gaps_report.py --markdown # same table as the CI job summary
```

When a gap's test starts passing, the report says `NOW PASSES`: set the entry to `fixed`
(or delete it) and remove the `@gap` marker so the requirement is locked in.

History: Q5 found four unowned gaps; Q6–Q7 fixed two (detection follows `current_date`,
`late_flood` demo), Erik fixed the tropical drought demo, and the look-ahead GDD is now an
accepted limitation for the demo owned by Neithan for the production path (measured +1.6% / +8%,
inside the 10-year p10–p90 band, same crops recommended).

Also noticed:

- Ownership overlaps in the plan that will produce merge conflicts if two people edit them:
  `tools/fetch_power_gdd.py` (Alina `tools/**`, Neithan, Erik E4), `config.py` (Alina, Neithan),
  `data/baselines/` (Erik, Neithan), `demo/*.json` (Erik E1, Neithan N4). Agree who edits each
  before starting; `branch_overlap.py` will show it as soon as both branches are pushed.
- Plan task Elias E8 puts an SMS simulator in `piper_agent/ui/`, which is Matias's folder.
