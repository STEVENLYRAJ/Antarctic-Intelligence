"""Weekly labels for ML-02.

Label A  T_week(t)   = mean of daily-mean T2m over days t+1 .. t+7  (degC; all 7 days required)
Label B  A_week(t)   = T_week(t) - mean of the 7 daily climatological values of the same target days
Categories           = A_week / sigma(cell, season) binned at the training-derived edges (default -2, -1, +1, +2 sigma),
                       sigma = std of weekly anomalies over the reference period issue dates (per cell, per target season).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..paths import load


def target_season(t) -> str:
    seasons = load("features")["seasons"]
    m = (pd.Timestamp(t) + pd.Timedelta(days=4)).month          # month of the middle target day
    return next(s for s, ms in seasons.items() if m in ms)


def weekly_labels(cube, clim, t) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (T_week, A_week, clim_week) for issue date t; NaN where fewer than min_valid target days exist."""
    cfg = load("features")["labels"]
    h = cfg["horizon_days"]
    t = pd.Timestamp(t)
    w = cube.window("t2m", t + pd.Timedelta(days=h), h)               # days t+1 .. t+h
    n = np.isfinite(w).sum(axis=0)
    with np.errstate(invalid="ignore"):
        tw = np.nanmean(w, axis=0) if n.any() else np.full(cube.n, np.nan, np.float32)
    tw = np.where(n >= cfg["min_valid_days"], tw, np.nan).astype(np.float32)
    cw = clim.window_mean("t2m", t + pd.Timedelta(days=1), h).astype(np.float32)
    return tw, (tw - cw).astype(np.float32), cw


def categorize(anom: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """0..4 (strong_cold .. strong_warm); -1 where anomaly or sigma is undefined."""
    edges = np.array(load("features")["categories"]["edges_sigma"], float)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = anom / sigma
    c = np.digitize(z, edges).astype(np.int8)                         # z < -2 -> 0 ; -2<=z<-1 -> 1 ; ... ; z >= 2 -> 4
    c[~np.isfinite(z)] = -1
    return c


class Sigma:
    """Per-cell, per-season std of weekly T2m anomalies over the training reference period."""

    def __init__(self, sig: dict):
        self.sig = sig

    @classmethod
    def fit(cls, cube, clim, issue_dates) -> "Sigma":
        seasons = load("features")["seasons"]
        s1 = {s: np.zeros(cube.n) for s in seasons}
        s2 = {s: np.zeros(cube.n) for s in seasons}
        n = {s: np.zeros(cube.n) for s in seasons}
        for t in issue_dates:
            _, a, _ = weekly_labels(cube, clim, t)
            s = target_season(t)
            ok = np.isfinite(a)
            s1[s] += np.where(ok, a, 0); s2[s] += np.where(ok, a * a, 0); n[s] += ok
        sig = {}
        for s in seasons:
            with np.errstate(invalid="ignore", divide="ignore"):
                m = s1[s] / n[s]
                sig[s] = np.sqrt(np.maximum(s2[s] / n[s] - m * m, 0) * n[s] / np.maximum(n[s] - 1, 1)).astype(np.float32)
        return cls(sig)

    def for_date(self, t) -> np.ndarray:
        return self.sig[target_season(t)]

    def save(self, path):
        np.savez_compressed(path, **self.sig)

    @classmethod
    def load(cls, path) -> "Sigma":
        z = np.load(path)
        return cls({k: z[k] for k in z.files})
