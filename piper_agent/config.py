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
