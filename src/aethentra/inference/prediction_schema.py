"""Input / output schemas for the weekly SIC forecast (pydantic v2)."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

GRID_SHAPE = (332, 316)
GRID_CRS = "EPSG:3412"


class ForecastRequest(BaseModel):
    issue_date: dt.date | None = Field(None, description="Forecast issue date t (UTC). Observations through day t are used. "
                                                         "Default: latest day available in the preprocessed record.")


class InputQuality(BaseModel):
    latest_observation_date: dt.date
    persistence_coverage_fraction: float = Field(..., ge=0, le=1, description="Ocean cells with a valid obs <= 3 days old")
    history_days_available_of_56: int
    atmosphere_days_available_of_7: int | None
    atmosphere_used: bool
    warnings: list[str] = []


class SectorSummary(BaseModel):
    sector: str
    extent_km2: float
    area_km2: float
    persistence_extent_km2: float


class Uncertainty(BaseModel):
    validated: bool
    method: str
    nominal_coverage: float | None = None
    empirical_test_coverage: float | None = None
    note: str


class ForecastSummary(BaseModel):
    forecast_id: str
    product: Literal["weekly_mean_sea_ice_concentration_forecast"] = "weekly_mean_sea_ice_concentration_forecast"
    data_type: Literal["model_prediction"] = "model_prediction"
    issue_date: dt.date
    issue_time_utc: dt.datetime
    target_start: dt.date
    target_end: dt.date
    quantity: str = "Mean sea-ice concentration over target_start..target_end (7-day mean, not daily, not anomaly)"
    units: str = "percent (0-100)"
    grid: str = "NSIDC Polar Stereographic South 25 km (EPSG:3412), 332 x 316"
    sic_threshold_percent: float = 15.0
    extent_km2: float
    area_km2: float
    persistence_extent_km2: float
    climatology_extent_km2: float
    sectors: list[SectorSummary]
    model_version: str
    model_name: str
    input_quality: InputQuality
    uncertainty: Uncertainty
    provenance: dict
    files: dict[str, str] = Field(default_factory=dict, description="logical file name -> download name (no filesystem paths)")
    limitations: list[str]
    generated_utc: dt.datetime
