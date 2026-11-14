# PIER configuration constants
# Tolerance ordinals, TBASE per crop, safety margin (0.8), etc.
# Implemented in Stage 4 (config used across tools)

TOLERANCE_ORDINAL = {"Low": 1, "Medium": 2, "High": 3}
DEFAULT_TBASE_C = 10.0
SAFETY_MARGIN = 0.8

# Per-crop GDD base temperatures (Spec §3)
CROP_TBASE = {
    "Sorghum": 10.0,
    "Millet": 10.0,
    "Buckwheat": 5.0,
    "Cowpea": 10.0,
    "Cereal rye (cover)": 0.0,
}

# --- Live-data tools (feat/herramientas-vivos) ---
DEFAULT_YIELD_T_HA = 1.5          # expected yield when the caller gives none (same default as the API)
MIN_WINDOW_COVERAGE = 0.8         # share of the last 30 days that must have rainfall data
CONFLICT_ABS_MM = 15.0            # two rainfall sources differ by more than this AND ...
CONFLICT_REL = 0.5                # ... by more than this fraction of the larger one -> conflicting data
CONFLICT_CONFIDENCE_FACTOR = 0.6  # event confidence multiplier when the data conflict
MIN_HISTORY_FOR_CALIBRATION = 5   # validation cases needed before the conformal calibration is used
