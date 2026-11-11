"""Paths and configuration for ML-03 (kept separate from ML-01 / ML-02)."""
from __future__ import annotations

from ..config import ROOT, load as _load

RAW_S1 = ROOT / "data" / "raw" / "sentinel1"
RAW_CHARTS = ROOT / "data" / "raw" / "ice_charts" / "usnic_antarctic"
RAW_AUX = ROOT / "data" / "raw" / "ml03_aux"
INTERIM = ROOT / "data" / "interim" / "ml03"
PROCESSED = ROOT / "data" / "processed" / "ml03"
MODELS = ROOT / "models" / "ml03"
EXPERIMENTS = ROOT / "experiments" / "ml03"
METRICS = EXPERIMENTS / "metrics"
OUTPUTS = ROOT / "outputs" / "ml03"
FIGURES = OUTPUTS / "figures"
DOCS = ROOT / "docs" / "ml_task_03"


def load(name: str) -> dict:
    return _load(f"ml03/{name}")
