"""Pydantic schemas of the ML-02 weekly T2m forecast (see docs/ml_task_02/MODEL_OUTPUT_SCHEMA.md)."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class T2mForecastRequest(BaseModel):
    issue_date: dt.date | None = Field(None, description="Forecast issue day (inputs <= this day). Default: latest day in the record.")
    write_layers: bool = Field(False, description="Also export frontend layers (GeoTIFF / PNG / JSON).")


class InputQuality(BaseModel):
    latest_input_date: dt.date
    t2m_cells_valid_fraction: float
    history_days_available_of_56: int
    predictors_missing: list[str]
    warnings: list[str]


class RegionSummary(BaseModel):
    region: str
    area_km2: float
    forecast_mean_t2m_degC: float
    climatology_mean_t2m_degC: float
    forecast_mean_anomaly_degC: float
    last_week_observed_anomaly_degC: float
    fraction_warm_ge_1sigma: float
    fraction_cold_le_minus1sigma: float
    fraction_extreme_abs_ge_2sigma: float


class Uncertainty(BaseModel):
    validated: bool
    method: str
    nominal_coverage: float | None = None
    empirical_test_coverage: float | None = None
    note: str


class T2mForecastSummary(BaseModel):
    forecast_id: str
    data_type: str = "model_prediction"
    product: str = "AETHENTRA ML-02 weekly-mean 2 m temperature and anomaly (statistical forecast from reanalysis; not an NWP weather forecast)"
    issue_date: dt.date
    issue_time_utc: dt.datetime
    target_start: dt.date
    target_end: dt.date
    units: dict
    climatology_reference_period: list[int]
    model_version: str
    model_name: str
    reanalysis_source: str
    regions: list[RegionSummary]
    input_quality: InputQuality
    uncertainty: Uncertainty
    test_metrics_reference: dict | None = None
    provenance: dict
    limitations: list[str]
    files: dict = {}
    generated_utc: dt.datetime
