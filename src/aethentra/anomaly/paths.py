"""Paths and configuration for ML-04 (kept separate from ML-01/02/03)."""
from __future__ import annotations

from ..config import ROOT, load as _load

RAW = ROOT / "data" / "raw" / "ml04"
INTERIM = ROOT / "data" / "interim" / "ml04"
PROCESSED = ROOT / "data" / "processed" / "ml04"
CLIM = PROCESSED / "climatology"
FEATURES = PROCESSED / "features"
MODELS = ROOT / "models" / "ml04"
EXPERIMENTS = ROOT / "experiments" / "ml04"
METRICS = EXPERIMENTS / "metrics"
OUTPUTS = ROOT / "outputs" / "ml04"
FIGURES = OUTPUTS / "figures"
DOCS = ROOT / "docs" / "ml_task_04"


def load(name: str) -> dict:
    return _load(f"ml04/{name}")
