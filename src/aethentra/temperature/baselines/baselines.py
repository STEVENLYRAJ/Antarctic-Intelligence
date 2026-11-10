"""ML-02 baselines (anomaly forecasts; absolute T = clim_target + anomaly).

climatology        A = 0 (the week follows the 1981-2010 seasonal cycle)
persistence        A = anomaly of the last observed day (day t)
persistence_week   A = mean anomaly of the last 7 days (t-6 .. t)
recent_trend       A = anom_w1 + 0.5 * (anom_w1 - anom_w2), clipped to +-4 sigma (cell, season) of training anomalies
damped_persistence A = alpha(season, land/ocean) * anom_w1, alpha fitted by least squares on TRAINING issue dates
"""
from __future__ import annotations

import numpy as np

BASELINES = ["climatology", "persistence", "persistence_week", "recent_trend", "damped_persistence"]


def predict_baseline(name: str, F: dict, sigma: np.ndarray | None = None, alpha: dict | None = None, season: str | None = None) -> np.ndarray:
    a1 = F["anom_w1"]
    if name == "climatology":
        out = np.where(np.isfinite(a1), 0.0, np.nan)
    elif name == "persistence":
        out = np.where(np.isfinite(F["anom_d0"]), F["anom_d0"], a1)
    elif name == "persistence_week":
        out = a1
    elif name == "recent_trend":
        tr = np.where(np.isfinite(F["anom_w2"]), a1 - F["anom_w2"], 0.0)
        out = a1 + 0.5 * tr
        if sigma is not None:
            lim = 4 * np.where(np.isfinite(sigma), sigma, np.nanmax(sigma))
            out = np.clip(out, -lim, lim)
    elif name == "damped_persistence":
        if alpha is None or season is None:
            raise ValueError("damped_persistence needs fitted alpha and the target season")
        land = F["land"] > 0.5
        out = np.where(land, alpha[f"{season}_land"], alpha[f"{season}_ocean"]) * a1
    else:
        raise ValueError(name)
    return np.asarray(out, np.float32)


def fit_damped_alpha(rows) -> dict:
    """rows: DataFrame with anom_w1, target_anom, land, season (training issue dates only)."""
    alpha = {}
    for (s, l), g in rows.groupby(["season", rows["land"] > 0.5]):
        x, y = g["anom_w1"].to_numpy(float), g["target_anom"].to_numpy(float)
        ok = np.isfinite(x) & np.isfinite(y)
        alpha[f"{s}_{'land' if l else 'ocean'}"] = float((x[ok] * y[ok]).sum() / (x[ok] ** 2).sum())
    return alpha
