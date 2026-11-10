"""Load the frozen final model bundle (model + climatologies + metadata)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..config import EXPERIMENTS_DIR, MODELS_DIR
from ..features.atmosphere import Atmosphere
from ..features.build import ATM_FEATURES, FeatureContext
from ..features.climatology import Climatology
from ..models.tree_models import TreeModel
from ..preprocessing.cube import Cube

FINAL = MODELS_DIR / "final"


@dataclass
class Bundle:
    model: TreeModel
    fallback: TreeModel | None
    q_lo: TreeModel | None
    q_hi: TreeModel | None
    meta: dict
    ctx: FeatureContext
    test_metrics: dict | None


def load_bundle(directory: Path = FINAL, cube: Cube | None = None) -> Bundle:
    meta_p = directory / "final_model.meta.json"
    if not meta_p.exists():
        raise FileNotFoundError("No final model bundle; run scripts/train.py final")
    meta = json.loads(meta_p.read_text())
    model = TreeModel.load(directory, "final_model")
    q = sorted(directory.glob("final_q*.meta.json"))
    q_lo = TreeModel.load(directory, q[0].name.replace(".meta.json", "")) if len(q) == 2 else None
    q_hi = TreeModel.load(directory, q[1].name.replace(".meta.json", "")) if len(q) == 2 else None
    cube = cube or Cube()
    clim = Climatology.load(directory / "sic_climatology.npz")
    atm = None
    if set(ATM_FEATURES) & set(model.features + (q_lo.features if q_lo else [])):
        atm = Atmosphere.load(cube.grid["lat"], cube.grid["lon"])
        ap = directory / "atmos_climatology.npz"
        if atm is not None and ap.exists():
            z = np.load(ap)
            atm.clim = {k: z[k] for k in z.files if k != "period"}
            atm.clim_period = tuple(z["period"])
    test_p = EXPERIMENTS_DIR / "metrics" / "test_final" / "summary.json"
    tm = json.loads(test_p.read_text()) if test_p.exists() else None
    fb = TreeModel.load(directory, "final_model_sic_only") if (directory / "final_model_sic_only.meta.json").exists() else None
    return Bundle(model, fb, q_lo, q_hi, meta, FeatureContext(cube, clim, atm), tm)


@lru_cache(maxsize=1)
def cached_bundle() -> Bundle:
    return load_bundle()
