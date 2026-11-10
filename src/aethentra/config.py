"""Central paths and YAML configuration loading for AETHENTRA ML Task 01."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "configs"

RAW_DIR = ROOT / "data" / "raw" / "aethentra"
INTERIM_DIR = ROOT / "data" / "interim" / "aethentra"
PROCESSED_DIR = ROOT / "data" / "processed" / "aethentra"
MODELS_DIR = ROOT / "models"
EXPERIMENTS_DIR = ROOT / "experiments"
OUTPUTS_DIR = ROOT / "outputs"
DOCS_DIR = ROOT / "docs" / "ml_task_01"


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    with open(CONFIG_DIR / f"{name}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def rel(p) -> str:
    p = Path(p).resolve()
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()
