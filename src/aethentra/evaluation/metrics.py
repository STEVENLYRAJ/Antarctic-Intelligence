"""Grid-forecast metrics accumulated as per-date sums so that any aggregation (all / season / sector / year) is exact.

Conventions
* Only ocean cells with a valid observed target enter the metrics (land / missing are never treated as 0 %).
* SIC errors in percentage points (pp). Area weights = exact cell areas (km^2).
* Extent = total area of cells with SIC >= 15 % ; sea-ice area = sum(cell area x SIC/100) over those cells.
* IIEE (Goessling et al. 2016) = area where forecast and observed 15 % classes disagree (km^2).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import ndimage

SUM_COLS = ["n", "w", "abs", "sq", "err", "wabs", "wsq", "werr", "obs", "obs2"]
EXT_COLS = ["ext_obs", "ext_pred", "area_obs", "area_pred", "tp", "fp", "fn"]


def edge_band(obs: np.ndarray, ocean: np.ndarray, cells: int, thr: float = 15) -> np.ndarray:
    ice = ocean & np.isfinite(obs) & (obs >= thr)
    opn = ocean & np.isfinite(obs) & (obs < thr)
    if not ice.any() or not opn.any():
        return np.zeros_like(ocean)
    near_ice = ndimage.distance_transform_edt(~ice) <= cells
    near_open = ndimage.distance_transform_edt(~opn) <= cells
    return ocean & near_ice & near_open


def grid_sums(pred: np.ndarray, obs: np.ndarray, area: np.ndarray, mask: np.ndarray, thr: float = 15) -> dict:
    m = mask & np.isfinite(obs) & np.isfinite(pred)
    p, o, a = pred[m].astype(np.float64), obs[m].astype(np.float64), area[m].astype(np.float64)
    e = p - o
    pi, oi = p >= thr, o >= thr
    return {"n": m.sum(), "w": a.sum(), "abs": np.abs(e).sum(), "sq": (e ** 2).sum(), "err": e.sum(),
            "wabs": (a * np.abs(e)).sum(), "wsq": (a * e ** 2).sum(), "werr": (a * e).sum(),
            "obs": o.sum(), "obs2": (o ** 2).sum(),
            "ext_obs": a[oi].sum(), "ext_pred": a[pi].sum(),
            "area_obs": (a[oi] * o[oi] / 100).sum(), "area_pred": (a[pi] * p[pi] / 100).sum(),
            "tp": a[pi & oi].sum(), "fp": a[pi & ~oi].sum(), "fn": a[~pi & oi].sum()}


def summarize(df: pd.DataFrame) -> dict:
    """Metrics from a frame of per-date sums (one row per issue date for a single group)."""
    if df.empty or df["n"].sum() == 0:
        return {}
    S = df[SUM_COLS + EXT_COLS].sum()
    n, w = S["n"], S["w"]
    out = {
        "n_cells": int(n), "n_dates": int(len(df)),
        "mae_pp": S["abs"] / n, "rmse_pp": np.sqrt(S["sq"] / n), "bias_pp": S["err"] / n,
        "area_weighted_mae_pp": S["wabs"] / w, "area_weighted_rmse_pp": np.sqrt(S["wsq"] / w), "area_weighted_bias_pp": S["werr"] / w,
        "r2": 1 - S["sq"] / (S["obs2"] - S["obs"] ** 2 / n) if S["obs2"] - S["obs"] ** 2 / n > 0 else np.nan,
    }
    ee = (df["ext_pred"] - df["ext_obs"])
    ae = (df["area_pred"] - df["area_obs"])
    with np.errstate(invalid="ignore", divide="ignore"):
        rel = (ee.abs() / df["ext_obs"]).replace([np.inf], np.nan)
    iiee = df["fp"] + df["fn"]
    tp, fp, fn = S["tp"], S["fp"], S["fn"]
    out.update({
        "extent_mae_km2": ee.abs().mean(), "extent_rmse_km2": np.sqrt((ee ** 2).mean()), "extent_bias_km2": ee.mean(),
        "extent_relative_error_mean": rel.mean(),
        "area_mae_km2": ae.abs().mean(), "area_rmse_km2": np.sqrt((ae ** 2).mean()), "area_bias_km2": ae.mean(),
        "iiee_mean_km2": iiee.mean(),
        "edge_iou": tp / (tp + fp + fn) if tp + fp + fn else np.nan,
        "edge_precision": tp / (tp + fp) if tp + fp else np.nan,
        "edge_recall": tp / (tp + fn) if tp + fn else np.nan,
    })
    p, r = out["edge_precision"], out["edge_recall"]
    out["edge_f1"] = 2 * p * r / (p + r) if p + r else np.nan
    return {k: (float(v) if isinstance(v, (np.floating, float, np.integer)) else v) for k, v in out.items()}


class Accumulator:
    """Collects per-(date, method, group) sums plus per-cell absolute-error maps."""

    def __init__(self, shape):
        self.rows = []
        self.err_maps: dict[str, np.ndarray] = {}
        self.bias_maps: dict[str, np.ndarray] = {}
        self.count_map = np.zeros(shape, np.int32)
        self._counted = set()

    def add(self, date, method: str, pred, obs, area, groups: dict[str, np.ndarray], thr=15):
        for g, mask in groups.items():
            s = grid_sums(pred, obs, area, mask, thr)
            s.update({"issue_date": pd.Timestamp(date), "method": method, "group": g})
            self.rows.append(s)
        m = groups["all"] & np.isfinite(obs) & np.isfinite(pred)
        if method not in self.err_maps:
            self.err_maps[method] = np.zeros(obs.shape, np.float64)
            self.bias_maps[method] = np.zeros(obs.shape, np.float64)
        self.err_maps[method][m] += np.abs(pred - obs)[m]
        self.bias_maps[method][m] += (pred - obs)[m]
        if date not in self._counted:
            self.count_map += m
            self._counted.add(date)

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


def add_calendar(df: pd.DataFrame, horizon: int, seasons: dict) -> pd.DataFrame:
    mid = df["issue_date"] + pd.Timedelta(days=(horizon + 1) / 2)
    df = df.copy()
    df["target_mid"] = mid
    df["year"] = mid.dt.year
    month_to_season = {m: s for s, ms in seasons.items() for m in ms}
    df["season"] = mid.dt.month.map(month_to_season)
    return df


def summarize_all(df: pd.DataFrame, seasons: dict, horizon: int) -> dict:
    df = add_calendar(df, horizon, seasons)
    out = {}
    for (method, group), g in df.groupby(["method", "group"]):
        out.setdefault(method, {})[group] = summarize(g)
        if group in ("all", "seasonal_ice_zone"):
            for s, gs in g.groupby("season"):
                out[method][f"{group}|season:{s}"] = summarize(gs)
    return out
