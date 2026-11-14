"""Request / response models for the PIER API.

Field names that already existed (English) are kept unchanged for
backwards compatibility; the A-team/B-team contract keys from
``PLAN_SEIS_PERSONAS.md`` (``pesos_agricultor``, ``rendimiento_t_ha``,
``exclusiones``, ``rotacion``, ``ahorro``, ``fuente_datos``, ``alertas``...)
are added alongside them.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

WEIGHT_KEYS = ("soil_protection", "salvage_revenue", "water_conservation")


def _validate_iso_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"'{value}' is not a valid ISO date (YYYY-MM-DD)") from exc


def _validate_weights(value: dict[str, float] | None) -> dict[str, float] | None:
    if value is None:
        return None
    unknown = set(value) - set(WEIGHT_KEYS)
    if unknown:
        raise ValueError(f"Unknown weight keys {sorted(unknown)}; allowed: {list(WEIGHT_KEYS)}")
    if any(v < 0 for v in value.values()):
        raise ValueError("Weights must be ≥ 0")
    if value and sum(value.values()) <= 0:
        raise ValueError("At least one weight must be > 0")
    return {k: float(v) for k, v in value.items()}


class _Location(BaseModel):
    model_config = ConfigDict(extra="ignore")

    lat: float = Field(..., ge=-90, le=90, description="Field latitude (°)")
    lon: float = Field(..., ge=-180, le=180, description="Field longitude (°)")


class DetectEventRequest(_Location):
    recent_start: str | None = Field(None, description="Recent window start (ISO). Optional.")
    recent_end: str | None = Field(None, description="Recent window end / 'today' (ISO). "
                                                     "Defaults to the demo packet's dates.")
    demo_name: str | None = Field(None, description="Demo scenario; null = auto-detect from lat/lon")

    _dates = field_validator("recent_start", "recent_end")(_validate_iso_date)

    @model_validator(mode="after")
    def _ordered(self) -> "DetectEventRequest":
        if self.recent_start and self.recent_end and self.recent_start > self.recent_end:
            raise ValueError("recent_start must be on or before recent_end")
        return self


class RecommendCropsRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_type: Literal["flood", "drought", "none"] = Field(..., description="flood | drought | none")
    gdd_remaining: float = Field(..., ge=0, description="GDD remaining to end of season")
    current_date: str = Field(..., description="Current date (ISO)")
    avg_daily_gdd: float = Field(..., ge=0, description="Average daily GDD")
    farmer_weights: dict[str, float] | None = Field(None, description="BR-10 weights (legacy name)")
    pesos_agricultor: dict[str, float] | None = Field(None, description="BR-10 weights (contract name)")

    _date = field_validator("current_date")(_validate_iso_date)
    _w1 = field_validator("farmer_weights")(_validate_weights)
    _w2 = field_validator("pesos_agricultor")(_validate_weights)

    @property
    def weights(self) -> dict[str, float] | None:
        return self.pesos_agricultor or self.farmer_weights


class GeneratePlanRequest(_Location):
    current_date: str = Field(..., description="Current date (ISO)")
    demo_name: str | None = Field(None, description="Demo scenario; null = auto-detect from lat/lon")
    demo_mode: bool | None = Field(None, description="True = cached data; False = live production "
                                                    "path. null = server default (PIER_DEMO_MODE). "
                                                    "The ?demo_mode= query parameter overrides it.")
    rendimiento_t_ha: float | None = Field(None, gt=0, le=50,
                                           description="Expected yield (t/ha) for the savings estimate")
    expected_yield_tons_per_ha: float | None = Field(None, gt=0, le=50,
                                                     description="Legacy alias of rendimiento_t_ha")
    pesos_agricultor: dict[str, float] | None = Field(None, description="BR-10 farmer priority weights")
    farmer_weights: dict[str, float] | None = Field(None, description="Legacy alias of pesos_agricultor")

    _date = field_validator("current_date")(_validate_iso_date)
    _w1 = field_validator("pesos_agricultor")(_validate_weights)
    _w2 = field_validator("farmer_weights")(_validate_weights)

    @property
    def weights(self) -> dict[str, float] | None:
        return self.pesos_agricultor or self.farmer_weights

    @property
    def yield_t_ha(self) -> float:
        return self.rendimiento_t_ha or self.expected_yield_tons_per_ha or 1.5


class SimulateSmsRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str = Field(..., min_length=1, max_length=320,
                         description="Farmer SMS, e.g. '41.8,-93.6,2025-05-15'")
    from_number: str | None = Field(None, max_length=32, description="Sender (logged masked)")
    current_date: str | None = Field(None, description="Used when the SMS has no date")
    demo_name: str | None = Field(None, description="Force a demo scenario")
    max_length: int = Field(160, ge=40, le=480)

    _date = field_validator("current_date")(_validate_iso_date)


class Alerta(BaseModel):
    nivel: Literal["info", "warning", "critical"]
    codigo: str
    mensaje: str


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str
    demo_mode_status: Literal["active", "production_path_available"]
    demo_mode_default: bool


class SmsResponse(BaseModel):
    reply: str
    length: int
    parsed: dict[str, Any] | None
    request_id: str


__all__ = [
    "WEIGHT_KEYS",
    "DetectEventRequest",
    "RecommendCropsRequest",
    "GeneratePlanRequest",
    "SimulateSmsRequest",
    "Alerta",
    "HealthResponse",
    "SmsResponse",
]
