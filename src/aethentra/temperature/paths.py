"""Paths and configuration for ML-02 (kept separate from the ML-01 sea-ice module)."""
from __future__ import annotations

from ..config import ROOT, load as _load

RAW_ERA5 = ROOT / "data" / "raw" / "era5"
RAW_STATIONS = ROOT / "data" / "raw" / "station_observations"
INTERIM = ROOT / "data" / "interim" / "ml02"
PROCESSED = ROOT / "data" / "processed" / "ml02"
MODELS = ROOT / "models" / "ml02"
EXPERIMENTS = ROOT / "experiments" / "ml02"
METRICS = EXPERIMENTS / "metrics"
OUTPUTS = ROOT / "outputs" / "ml02"
FIGURES = OUTPUTS / "figures"
DOCS = ROOT / "docs" / "ml_task_02"


def load(name: str) -> dict:
    return _load(f"ml02/{name}")
