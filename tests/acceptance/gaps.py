"""Known-gaps registry (QA / Integration — next wave).

Every test marked ``@gap(...)`` MUST have an entry here, with exactly one
disposition (enforced by ``test_gap_registry.py``):

* ``fixed``      — done; the ``@gap`` marker must be removed (the test XPASSes until then).
* ``accepted``   — known limitation accepted for the hackathon, with a documented
                   rationale (and measured impact when possible).
* ``follow_up``  — must be fixed by a named owner; ``when`` says before what.

``demo_impact`` says whether a judge could see the problem in the demo:
``visible`` (shows up on screen / in the plan text), ``hidden`` (only in edge
cases or internals) or ``none``.
"""
from __future__ import annotations

DISPOSITIONS = ("fixed", "accepted", "follow_up")
DEMO_IMPACT = ("visible", "hidden", "none")
TEAM = ("Erik", "Alina", "Neithan", "Danny", "Matias", "Elias")

GAPS: dict[str, dict] = {
    "test_gap_normal_scenario_is_not_a_fallback": {
        "title": "No-event scenario says 'The season's cash crop is lost' and triggers the BR-5 fallback",
        "owner": "Alina", "task": "A3",
        "disposition": "follow_up", "when": "before recording the demo video",
        "demo_impact": "visible",
        "rationale": (
            "The normal demo's plan text tells the farmer the crop is lost when nothing happened. "
            "The API already sets no_action_needed=true and does not raise the lost-crop alert, "
            "but the plan text comes from generate_recovery_plan. Until fixed, do not show the "
            "normal scenario's plan text in the video."
        ),
    },
    "test_gap_run_pier_returns_contract_keys": {
        "title": "run_pier does not return exclusiones / rotacion / ahorro / fuente_datos",
        "owner": "Alina", "task": "A4",
        "disposition": "accepted", "when": "post-hackathon (production path)",
        "demo_impact": "none",
        "rationale": (
            "The API fills exclusiones, rotacion and ahorro from the existing tools and labels "
            "them origen='api_fallback'; fuente_datos comes from the data layer. Demo payloads are "
            "complete. Follow-up for the production path belongs to Alina (feat/herramientas-vivos)."
        ),
    },
    "test_gap_run_pier_accepts_weights_and_yield": {
        "title": "run_pier ignores pesos_agricultor and rendimiento_t_ha",
        "owner": "Alina", "task": "A4",
        "disposition": "accepted", "when": "post-hackathon",
        "demo_impact": "hidden",
        "rationale": (
            "BR-10 re-ranking works in filter_rescue_crops and in /recommend_crops; only the "
            "end-to-end run_pier path ignores the weights, and the API says so with the "
            "PARAMETRO_PARCIAL alert. Savings use the yield in the API fallback."
        ),
    },
    "test_gap_confidence_not_saturated": {
        "title": "Rescue confidence is 100% for every eligible crop in typical cases",
        "owner": "Alina", "task": "A7",
        "disposition": "accepted", "when": "post-hackathon (BR-7 calibration)",
        "demo_impact": "visible",
        "rationale": (
            "Rescue confidence is the GDD-margin heuristic of BR-6; calibrated confidence (BR-7) "
            "needs ≥100 validation cases that do not exist yet. Measured: flood demo gives "
            "[1.0, 1.0]. Present it as 'GDD margin is comfortable', not as a probability."
        ),
    },
    "test_gap_rotation_does_not_repeat_rescue_crop": {
        "title": "Rotation can end with the rescue crop again (Cereal rye → Cowpea → Cereal rye)",
        "owner": "Alina", "task": "A8",
        "disposition": "follow_up", "when": "before delivery (Nov 15 23:59)",
        "demo_impact": "visible",
        "rationale": (
            "Visible in the rotation section of the flood demo. Small fix in plan_rotation: "
            "choose a different cover when the main crop or the rescue crop is the default cover."
        ),
    },
    "test_gap_gdd_remaining_has_no_lookahead": {
        "title": "GDD remaining is summed from future observations (look-ahead)",
        "owner": "Neithan", "task": "Q5 → feat/clima-multihemisferio",
        "disposition": "accepted", "when": "must be fixed before any real-data (PIER_DEMO_MODE=0) use",
        "demo_impact": "hidden",
        "rationale": (
            "In the synthetic demo the future values are drawn from the same climatology, so the "
            "bias is small. Measured on the cached data: flood 1659 GDD vs 10-yr climatology 1633 "
            "(p10–p90 1623–1641, +1.6%); late_flood 114 vs 106 (p10–p90 97–117, +8%). Same crops "
            "recommended either way. With real data the future is unknown: the remaining window "
            "must come from climatology, so this blocks the production path."
        ),
    },
    "test_gap_tropics_have_no_frost": {
        "title": "Tropical sites: GDD tool does not record that the season ends with the rains",
        "owner": "Neithan", "task": "N1",
        "disposition": "follow_up", "when": "post-hackathon (feat/clima-multihemisferio)",
        "demo_impact": "hidden",
        "rationale": (
            "Erik's baselines already mark tropical sites with frost_method='fin_temporada_lluvias' "
            "and the drought demo uses its season_end, so the numbers are right; only the GDD "
            "tool's details do not expose the method."
        ),
    },
    "test_gap_run_pier_works_from_any_cwd": {
        "title": "filter_rescue_crops defaults to a cwd-relative crops CSV",
        "owner": "Alina", "task": "A2/D2",
        "disposition": "follow_up", "when": "post-hackathon",
        "demo_impact": "hidden",
        "rationale": (
            "Only bites when the server or CLI is started outside the repo root. The API's own "
            "endpoints pass an absolute path, the QA scripts chdir to the repo root and the API "
            "answers 503 with missing_file=rescue_crops.csv. One-line fix: default to "
            "cache_loader.get_crops_path()."
        ),
    },
    "test_generate_plan_works_from_other_cwd": {
        "title": "Same as test_gap_run_pier_works_from_any_cwd, seen through the API",
        "owner": "Alina", "task": "A2/D2",
        "disposition": "follow_up", "when": "post-hackathon",
        "demo_impact": "hidden",
        "rationale": "Duplicate view of the cwd-relative crops path, kept in the API suite.",
    },
}

__all__ = ["GAPS", "DISPOSITIONS", "DEMO_IMPACT", "TEAM"]
