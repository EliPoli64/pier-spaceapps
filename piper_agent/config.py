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

# Hemisphere and API execution mode defaults
HEMISPHERE_DEFAULT = "auto"
VALID_HEMISPHERES = ("auto", "north", "south")
API_MODE_DEFAULT = "demo"
VALID_API_MODES = ("demo", "live")

# Climate regime & frost-window thresholds (aligned with generate_cache.py)
TROPICAL_LATITUDE = 23.5  # degrees |lat| below which frost is absent
FROST_THRESHOLD_C = 0.0  # degC; daily T2M_MIN <= 0.0 marks frost
FROST_NORTH_START_DOY = 200  # DOY > 200 autumn frost search (north)
FROST_SOUTH_DOY_RANGE = (60, 200)  # DOY 60..200 autumn search (Mar-Jul, south)

# Heat-wave detection thresholds (aligned with tools/detect_event.py)
HEAT_WAVE_TMAX_C = 35.0  # degC; T2M_MAX > 35.0 threshold
HEAT_WAVE_MIN_DAYS = 3  # consecutive days above HEAT_WAVE_TMAX_C

# Latitude frost bands matching generate_cache.FROST_BANDS plus tropical window
CLIMATE_FROST_BANDS = {
    "note": "typical values, local calibration required",
    "tropical_latitude": TROPICAL_LATITUDE,
    "north": [
        {
            "lat_min": TROPICAL_LATITUDE,
            "lat_max": 30.0,
            "first_frost": "12-15",
        },
        {"lat_min": 30.0, "lat_max": 40.0, "first_frost": "11-05"},
        {"lat_min": 40.0, "lat_max": 50.0, "first_frost": "10-10"},
        {"lat_min": 50.0, "lat_max": 90.0, "first_frost": "09-15"},
    ],
    "south": [
        {
            "lat_min": TROPICAL_LATITUDE,
            "lat_max": 30.0,
            "first_frost": "06-15",
        },
        {"lat_min": 30.0, "lat_max": 40.0, "first_frost": "05-05"},
        {"lat_min": 40.0, "lat_max": 50.0, "first_frost": "04-10"},
        {"lat_min": 50.0, "lat_max": 90.0, "first_frost": "03-15"},
    ],
    "tropical": {
        "lat_min": -TROPICAL_LATITUDE,
        "lat_max": TROPICAL_LATITUDE,
        "method": "rainy_season_end",
        "north_default": "11-15",
        "south_default": "05-15",
        "baseline_driven": True,
    },
}


def _build_frost_month_mappings() -> dict:
    """Derive paired north/south/tropical MM-DD and month mappings."""
    tropical = CLIMATE_FROST_BANDS["tropical"]
    paired_bands = [
        {
            "regime": "temperate",
            "lat_min": north_band["lat_min"],
            "lat_max": north_band["lat_max"],
            "north_mmdd": north_band["first_frost"],
            "south_mmdd": south_band["first_frost"],
            "north_month": int(north_band["first_frost"].split("-")[0]),
            "south_month": int(south_band["first_frost"].split("-")[0]),
            "method": "first_autumn_frost",
        }
        for north_band, south_band in zip(
            CLIMATE_FROST_BANDS["north"],
            CLIMATE_FROST_BANDS["south"],
        )
    ]
    paired_bands.append({
        "regime": "tropical",
        "lat_min": tropical["lat_min"],
        "lat_max": tropical["lat_max"],
        "north_mmdd": tropical["north_default"],
        "south_mmdd": tropical["south_default"],
        "north_month": int(tropical["north_default"].split("-")[0]),
        "south_month": int(tropical["south_default"].split("-")[0]),
        "method": tropical["method"],
    })
    return {
        "north_to_south": {
            band["north_mmdd"]: band["south_mmdd"] for band in paired_bands
        },
        "south_to_north": {
            band["south_mmdd"]: band["north_mmdd"] for band in paired_bands
        },
        "north_to_south_month": {
            band["north_month"]: band["south_month"] for band in paired_bands
        },
        "south_to_north_month": {
            band["south_month"]: band["north_month"] for band in paired_bands
        },
        "bands": paired_bands,
    }


FROST_MONTH_MAPPINGS = _build_frost_month_mappings()

# Ordered phenological season stages and GDD-progress threshold definitions.
# Progress ratio = gdd_accumulated / total_season_gdd (0.0 .. 1.0+).
SEASON_STAGES = (
    "planting",
    "vegetative",
    "flowering",
    "harvest",
    "post-harvest",
)

SEASON_STAGE_THRESHOLDS = {
    "planting": {
        "order": 1,
        "gdd_progress_min": 0.0,
        "gdd_progress_max": 0.15,
        "inclusive_max": False,
        "pre_season": True,
        "post_frost": False,
        "condition": "pre_season or 0.0 <= gdd_progress < 0.15",
        "hazard_sensitivity": {
            "flood": "high",
            "drought": "high",
            "heat_wave": "medium",
            "frost": "high",
        },
        "primary_hazards": ("flood", "drought", "frost"),
        "description": (
            "Pre-emergence to seedling establishment; sensitive to "
            "waterlogging, dry seedbeds, and early frost."
        ),
    },
    "vegetative": {
        "order": 2,
        "gdd_progress_min": 0.15,
        "gdd_progress_max": 0.50,
        "inclusive_max": False,
        "pre_season": False,
        "post_frost": False,
        "condition": "0.15 <= gdd_progress < 0.50",
        "hazard_sensitivity": {
            "flood": "medium",
            "drought": "medium",
            "heat_wave": "low",
            "frost": "medium",
        },
        "primary_hazards": ("flood", "drought"),
        "description": (
            "Active leaf and root growth; moderate resilience if stress "
            "duration is brief."
        ),
    },
    "flowering": {
        "order": 3,
        "gdd_progress_min": 0.50,
        "gdd_progress_max": 0.80,
        "inclusive_max": False,
        "pre_season": False,
        "post_frost": False,
        "condition": "0.50 <= gdd_progress < 0.80",
        "hazard_sensitivity": {
            "flood": "high",
            "drought": "high",
            "heat_wave": "high",
            "frost": "high",
        },
        "primary_hazards": ("heat_wave", "drought", "frost", "flood"),
        "description": (
            "Anthesis and early grain fill; peak sensitivity to heat waves, "
            "drought, waterlogging, and frost."
        ),
    },
    "harvest": {
        "order": 4,
        "gdd_progress_min": 0.80,
        "gdd_progress_max": 1.00,
        "inclusive_max": False,
        "pre_season": False,
        "post_frost": False,
        "condition": "0.80 <= gdd_progress < 1.00",
        "hazard_sensitivity": {
            "flood": "high",
            "drought": "low",
            "heat_wave": "low",
            "frost": "medium",
        },
        "primary_hazards": ("flood",),
        "description": (
            "Physiological maturity and grain dry-down; heavy rain threatens "
            "crop quality and field trafficability."
        ),
    },
    "post-harvest": {
        "order": 5,
        "gdd_progress_min": 1.00,
        "gdd_progress_max": None,
        "inclusive_max": True,
        "pre_season": False,
        "post_frost": True,
        "condition": "post_frost or gdd_progress >= 1.00",
        "hazard_sensitivity": {
            "flood": "low",
            "drought": "low",
            "heat_wave": "low",
            "frost": "low",
        },
        "primary_hazards": (),
        "description": (
            "Season completed or frost-terminated; focus shifts to soil "
            "protection and cover-crop windows."
        ),
    },
}

# Canonical physical units across climate, moisture, and coordinate series
CLIMATE_UNITS = {
    "gdd": {
        "unit": "degC-days",
        "symbol": "°C·d",
        "rate_unit": "degC-days/day",
        "base_temp_unit": "degC",
        "description": "Growing degree days above crop base temperature Tbase",
    },
    "temperature": {
        "unit": "degC",
        "symbol": "°C",
        "variables": ("T2M_MAX", "T2M_MIN", "TBASE"),
        "description": "Air temperature at 2 m in degrees Celsius",
    },
    "precipitation": {
        "unit": "mm",
        "symbol": "mm",
        "rate_unit": "mm/day",
        "variables": ("PRECTOTCORR", "precipitation_mm"),
        "description": "Liquid precipitation depth in millimeters",
    },
    "root_zone_soil_wetness": {
        "unit": "fraction",
        "symbol": "0-1",
        "volumetric_unit": "vol_pct",
        "variables": ("GWETROOT", "soil_moisture_vol_pct"),
        "description": (
            "NASA POWER GWETROOT saturation fraction (0-1); SMAP "
            "soil_moisture_vol_pct in volumetric percent (%)"
        ),
    },
    "doy": {
        "unit": "day_of_year",
        "range": (1, 366),
        "description": "Calendar day of year (1 = Jan 1, 365/366 = Dec 31)",
    },
    "coordinates": {
        "unit": "decimal_degrees",
        "symbol": "°",
        "lat_range": (-90.0, 90.0),
        "lon_range": (-180.0, 180.0),
        "crs": "WGS84",
        "description": "Geographic latitude and longitude in decimal degrees",
    },
}

# Representative multi-regime sites for validation & climate-regime tests
REPRESENTATIVE_REGIME_COORDINATES = {
    "temperate_north": {
        "regime": "temperate_north",
        "label": "US Midwest (Iowa)",
        "lat": 41.8,
        "lon": -93.6,
        "hemisphere": "north",
        "demo_scenario": "flood",
        "sites": (
            {
                "name": "iowa_midwest",
                "label": "US Midwest (Iowa)",
                "lat": 41.8,
                "lon": -93.6,
                "hemisphere": "north",
                "demo_scenario": "flood",
                "notes": "Flood, late_flood, and normal demo packets",
            },
        ),
    },
    "temperate_south": {
        "regime": "temperate_south",
        "label": "Western Cape (Cape Town)",
        "lat": -33.9,
        "lon": 18.4,
        "hemisphere": "south",
        "demo_scenario": None,
        "sites": (
            {
                "name": "cape_town",
                "label": "Western Cape (Cape Town)",
                "lat": -33.9,
                "lon": 18.4,
                "hemisphere": "south",
                "demo_scenario": None,
                "notes": "Southern Hemisphere test site (Stage 14)",
            },
            {
                "name": "buenos_aires_pampas",
                "label": "Argentine Pampas (Buenos Aires)",
                "lat": -34.6,
                "lon": -58.4,
                "hemisphere": "south",
                "demo_scenario": None,
                "notes": "Temperate Southern Hemisphere grain belt",
            },
        ),
    },
    "tropical": {
        "regime": "tropical",
        "label": "Horn of Africa (East Africa)",
        "lat": 9.0,
        "lon": 41.0,
        "hemisphere": "north",
        "demo_scenario": "drought",
        "sites": (
            {
                "name": "east_africa_drought",
                "label": "Horn of Africa (East Africa)",
                "lat": 9.0,
                "lon": 41.0,
                "hemisphere": "north",
                "demo_scenario": "drought",
                "notes": "Drought demo packet; rainy-season-end window",
            },
            {
                "name": "tropical_south_andes",
                "label": "Tropical South America (Central Andes)",
                "lat": -12.0,
                "lon": -75.0,
                "hemisphere": "south",
                "demo_scenario": None,
                "notes": "Tropical Southern Hemisphere validation site",
            },
        ),
    },
}
