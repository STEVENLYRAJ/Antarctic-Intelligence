"""ML-02 metrics from per-(issue date, region) sufficient statistics.

Note: absolute-T error and anomaly error are identical cell by cell (both use the same target-week climatology), so MAE /
RMSE / bias are the same for labels A and B; R^2 and correlation differ (different variance of the reference).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CAT_NAMES = ["strong_cold", "cold", "near_normal", "warm", "strong_warm"]


def region_masks(grid: dict) -> dict:
    land = grid["land"].astype(bool)
    reg = grid["region"]
    coastal = grid["coastal"].astype(bool)
    return {"all": np.ones(land.size, bool), "antarctica_land": land, "southern_ocean": ~land, "antarctic_peninsula": reg == 1,
            "west_antarctica": reg == 2, "east_antarctica": reg == 3, "coastal_land": land & coastal, "inland": land & ~coastal}


SUMS = ["n", "w", "e", "ae", "e2", "we", "wae", "we2", "o", "o2", "wo", "wo2", "ta", "ta2", "p", "p2", "po", "wp", "wp2", "wpo"]


def grid_sums(pred_a, obs_a, obs_t, area, m) -> dict:
    ok = m & np.isfinite(pred_a) & np.isfinite(obs_a)
    p, o, t, w = (x[ok].astype(np.float64) for x in (pred_a, obs_a, obs_t, area))
    e = p - o
    return {"n": ok.sum(), "w": w.sum(), "e": e.sum(), "ae": np.abs(e).sum(), "e2": (e * e).sum(), "we": (w * e).sum(),
            "wae": (w * np.abs(e)).sum(), "we2": (w * e * e).sum(), "o": o.sum(), "o2": (o * o).sum(), "wo": (w * o).sum(),
            "wo2": (w * o * o).sum(), "ta": t.sum(), "ta2": (t * t).sum(), "p": p.sum(), "p2": (p * p).sum(), "po": (p * o).sum(),
            "wp": (w * p).sum(), "wp2": (w * p * p).sum(), "wpo": (w * p * o).sum()}


def summarize(s: pd.DataFrame) -> dict:
    """s: rows of per-date sums for ONE model and ONE region (optionally a season subset)."""
    S = s[SUMS].sum()
    n, w = S["n"], S["w"]
    if n == 0:
        return {"n_cells": 0}
    mae, rmse, bias = S["ae"] / n, np.sqrt(S["e2"] / n), S["e"] / n
    ss_a = S["o2"] - S["o"] ** 2 / n
    ss_t = S["ta2"] - S["ta"] ** 2 / n
    cov = S["po"] / n - (S["p"] / n) * (S["o"] / n)
    vp, vo = S["p2"] / n - (S["p"] / n) ** 2, S["o2"] / n - (S["o"] / n) ** 2
    # per-date uncentred, area-weighted anomaly pattern correlation (ACC), averaged over issue dates
    with np.errstate(invalid="ignore", divide="ignore"):
        acc_d = s["wpo"] / np.sqrt(s["wp2"] * s["wo2"])
    return {"n_cells": int(n), "n_dates": int(s["date"].nunique()),
            "mae_degC": float(mae), "rmse_degC": float(rmse), "bias_degC": float(bias),
            "area_weighted_mae_degC": float(S["wae"] / w), "area_weighted_rmse_degC": float(np.sqrt(S["we2"] / w)),
            "area_weighted_bias_degC": float(S["we"] / w),
            "r2_absolute_t2m": float(1 - S["e2"] / ss_t) if ss_t > 0 else None,
            "r2_anomaly": float(1 - S["e2"] / ss_a) if ss_a > 0 else None,
            "anomaly_correlation_all": float(cov / np.sqrt(vp * vo)) if vp > 0 and vo > 0 else None,
            "acc_pattern_mean": float(np.nanmean(acc_d)) if np.isfinite(acc_d).any() else None,
            "msss_vs_climatology": float(1 - S["we2"] / S["wo2"]) if S["wo2"] > 0 else None,
            "mse_area_weighted": float(S["we2"] / w)}


def classification(cm: np.ndarray) -> dict:
    cm = np.asarray(cm, float)
    tot = cm.sum()
    if tot == 0:
        return {}
    recall = np.divide(np.diag(cm), cm.sum(1), out=np.full(5, np.nan), where=cm.sum(1) > 0)
    out = {"confusion_matrix_obs_rows_pred_cols": cm.astype(int).tolist(), "labels": CAT_NAMES, "accuracy": float(np.trace(cm) / tot),
           "balanced_accuracy": float(np.nanmean(recall)), "per_class_recall": dict(zip(CAT_NAMES, map(float, recall)))}

    def binary(obs_sel, pred_sel):
        tp = cm[np.ix_(obs_sel, pred_sel)].sum()
        fp = cm[np.ix_([i for i in range(5) if i not in obs_sel], pred_sel)].sum()
        fn = cm[np.ix_(obs_sel, [i for i in range(5) if i not in pred_sel])].sum()
        pr = tp / (tp + fp) if tp + fp else np.nan
        rc = tp / (tp + fn) if tp + fn else np.nan
        f1 = 2 * pr * rc / (pr + rc) if pr + rc else np.nan
        return {"precision": float(pr), "recall": float(rc), "f1": float(f1), "observed_events": int(cm[obs_sel].sum())}
    out["warm_ge_1sigma"] = binary([3, 4], [3, 4])
    out["cold_le_-1sigma"] = binary([0, 1], [0, 1])
    out["extreme_warm_ge_2sigma"] = binary([4], [4])
    out["extreme_cold_le_-2sigma"] = binary([0], [0])
    return out


class Accumulator:
    def __init__(self, grid: dict, area: np.ndarray):
        self.masks = region_masks(grid)
        self.area = area
        self.rows = []
        n = area.size
        self.cm = {r: np.zeros((5, 5), np.int64) for r in self.masks}
        self.map_e, self.map_ae, self.map_e2, self.map_n = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)

    def add(self, date, season, pred_a, obs_a, obs_t, cat_pred=None, cat_obs=None, maps: bool = True):
        for r, m in self.masks.items():
            self.rows.append({"date": date, "season": season, "region": r, **grid_sums(pred_a, obs_a, obs_t, self.area, m)})
            if cat_pred is not None:
                ok = m & (cat_pred >= 0) & (cat_obs >= 0)
                np.add.at(self.cm[r], (cat_obs[ok], cat_pred[ok]), 1)
        if maps:
            ok = np.isfinite(pred_a) & np.isfinite(obs_a)
            e = np.where(ok, pred_a - obs_a, 0.0)
            self.map_e += e; self.map_ae += np.abs(e); self.map_e2 += e * e; self.map_n += ok

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)

    def summary(self) -> dict:
        df = self.frame()
        out = {}
        for r, g in df.groupby("region"):
            out[r] = summarize(g)
            out[r]["by_season"] = {s: summarize(gs) for s, gs in g.groupby("season")}
            if self.cm[r].sum():
                out[r]["categories"] = classification(self.cm[r])
        return out

    def maps(self) -> dict:
        with np.errstate(invalid="ignore", divide="ignore"):
            return {"mae": self.map_ae / self.map_n, "bias": self.map_e / self.map_n, "rmse": np.sqrt(self.map_e2 / self.map_n)}
