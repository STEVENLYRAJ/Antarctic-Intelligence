"""Reference forecasts. Every method gets the same fallback chain and the same evaluation mask."""
from __future__ import annotations

import numpy as np


def fallback(pred: np.ndarray, F: dict) -> np.ndarray:
    """Fill cells where a method is undefined: latest valid obs -> past-week mean -> climatology -> 0. Clip to [0, 100]."""
    out = pred.copy()
    for k in ("sic_d0", "sic_w1", "clim_target"):
        bad = ~np.isfinite(out)
        if not bad.any():
            break
        out[bad] = F[k][bad]
    out[~np.isfinite(out)] = 0.0
    return np.clip(out, 0, 100).astype(np.float32)


BASELINES = {
    # B1: latest valid daily field (<= 3 days old) persists over t+1..t+7
    "persistence": lambda F: F["sic_d0"],
    # B1b: past-7-day mean persists
    "persistence_week": lambda F: F["sic_w1"],
    # B2: training-period day-of-year climatology averaged over the target window
    "climatology": lambda F: F["clim_target"],
    # B3: recent linear trend (7-day least-squares slope) extrapolated to the target-window midpoint (t+4)
    "linear_trend": lambda F: F["sic_d0"] + 4.0 * np.nan_to_num(F["sic_trend7"]),
    # B4: anomaly persistence = target-window climatology + past-week anomaly
    "anomaly_persistence": lambda F: F["anom_persist"],
}


def predict_baseline(name: str, F: dict) -> np.ndarray:
    return fallback(BASELINES[name](F).astype(np.float32), F)
