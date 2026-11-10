"""Leakage-safe labels and features for weekly SIC forecasts.

Issue time t = end of day t (UTC). Inputs use observations on days <= t only.
Target = mean of daily SIC over days t+1 .. t+7 (valid when >= min_valid_days observed), in percent.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import ndimage

from ..config import load
from ..preprocessing.cube import Cube
from .atmosphere import Atmosphere
from .climatology import Climatology

SIC_FEATURES = ["sic_d0", "sic_age", "sic_w1", "sic_w2", "sic_w3", "sic_w4", "sic_w8", "d_w1_w2", "d_d0_w1",
                "sic_std28", "sic_trend7", "clim_target", "clim_target_std", "clim_now", "clim_change", "anom_w1",
                "anom_persist", "nbr3_w1", "nbr7_w1", "grad_w1", "dist_edge_km", "unc_w1",
                "sie_w1", "sie_sector_w1", "sie_change"]
STATIC_FEATURES = ["dist_coast_km", "lat", "lon_sin", "lon_cos", "sector"]
SEASON_FEATURES = ["doy_sin", "doy_cos", "month"]
ATM_FEATURES = ["air_w1", "air_anom_w1", "uwnd_w1", "vwnd_w1", "wspd_w1", "slp_w1", "slp_anom_w1"]


def feature_names(with_atmosphere: bool) -> list[str]:
    return SIC_FEATURES + STATIC_FEATURES + SEASON_FEATURES + (ATM_FEATURES if with_atmosphere else [])


def issue_dates(start: str, end: str, horizon: int | None = None) -> pd.DatetimeIndex:
    """7-day cadence anchored at configs/features.yaml issue_anchor; the full target window must lie inside [start, end]."""
    f = load("features")["labels"]
    horizon = horizon or f["horizon_days"]
    anchor = pd.Timestamp(f["issue_anchor"])
    all_d = pd.date_range(anchor, pd.Timestamp(end), freq=f"{f['issue_cadence_days']}D")
    return all_d[(all_d >= pd.Timestamp(start)) & (all_d + pd.Timedelta(days=horizon) <= pd.Timestamp(end))]


def _nanmean(a, axis=0, min_count=1):
    v = np.isfinite(a)
    n = v.sum(axis=axis)
    s = np.where(v, a, 0).sum(axis=axis)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = s / n
    m[n < min_count] = np.nan
    return m.astype(np.float32), n


def _masked_filter(a: np.ndarray, valid: np.ndarray, size: int) -> np.ndarray:
    num = ndimage.uniform_filter(np.where(valid, a, 0).astype(np.float64), size, mode="constant")
    den = ndimage.uniform_filter(valid.astype(np.float64), size, mode="constant")
    with np.errstate(invalid="ignore", divide="ignore"):
        out = num / den
    out[den < 1e-6] = np.nan          # no valid neighbour (float round-off can leave den ~ 0 -> inf)
    return out.astype(np.float32)


@dataclass
class FeatureContext:
    cube: Cube
    clim: Climatology
    atmos: Atmosphere | None = None

    def __post_init__(self):
        self.f = load("features")
        g = self.cube.grid
        self.lat = g["lat"].astype(np.float32)
        lon = np.deg2rad(g["lon"])
        self.lon_sin, self.lon_cos = np.sin(lon).astype(np.float32), np.cos(lon).astype(np.float32)
        self.sector = g["sector"].astype(np.float32)
        self.dist_coast = g["dist_coast_km"].astype(np.float32)
        self.area = self.cube.area
        self.ocean = self.cube.ocean
        self.n_sectors = len(self.f["sectors"])
        self.sector_names = list(self.f["sectors"])

    # ------------------------------------------------------------------ labels
    def target(self, t) -> tuple[np.ndarray, np.ndarray]:
        L = self.f["labels"]
        w = self.cube.window(pd.Timestamp(t) + pd.Timedelta(days=L["horizon_days"]), L["horizon_days"])
        return _nanmean(w, 0, L["min_valid_days"])

    def persistence(self, t) -> tuple[np.ndarray, np.ndarray]:
        """Latest valid daily SIC within persistence_max_age_days (per cell) and its age in days."""
        m = self.f["labels"]["persistence_max_age_days"]
        w = self.cube.window(t, m + 1)[::-1]          # day t first
        p = np.full(w.shape[1:], np.nan, np.float32)
        age = np.full(w.shape[1:], np.nan, np.float32)
        for k in range(m + 1):
            fill = np.isnan(p) & np.isfinite(w[k])
            p[fill] = w[k][fill]
            age[fill] = k
        return p, age

    # ------------------------------------------------------------------ features
    def extent(self, field: np.ndarray, mask: np.ndarray | None = None) -> float:
        m = self.ocean & np.isfinite(field) & (field >= 15)
        if mask is not None:
            m &= mask
        return float(self.area[m].sum() / 1e6)

    def features(self, t) -> dict[str, np.ndarray]:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)   # all-NaN slices (gaps) are expected and yield NaN
            return self._features(pd.Timestamp(t))

    def _features(self, t) -> dict[str, np.ndarray]:
        F: dict[str, np.ndarray] = {}
        hist = self.cube.window(t, 56)                 # days t-55 .. t
        p, age = self.persistence(t)
        F["sic_d0"], F["sic_age"] = p, age
        wk = {}
        for k in self.f["sic_lags_weeks"]:
            seg = hist[56 - 7 * k: 56 - 7 * (k - 1)]
            wk[k], _ = _nanmean(seg, 0, 3)
            F[f"sic_w{k}"] = wk[k]
        F["d_w1_w2"] = wk[1] - wk[2]
        F["d_d0_w1"] = p - wk[1]
        F["sic_std28"] = np.nanstd(hist[-28:], axis=0).astype(np.float32) if np.isfinite(hist[-28:]).any() else np.full(p.shape, np.nan, np.float32)
        last7 = hist[-7:]
        x = np.arange(7, dtype=np.float32) - 3
        v = np.isfinite(last7)
        n = v.sum(0)
        xm = np.where(v, x[:, None, None], 0).sum(0) / np.maximum(n, 1)
        ym = np.where(v, last7, 0).sum(0) / np.maximum(n, 1)
        cov = np.where(v, (x[:, None, None] - xm) * (np.nan_to_num(last7) - ym), 0).sum(0)
        var = np.where(v, (x[:, None, None] - xm) ** 2, 0).sum(0)
        with np.errstate(invalid="ignore", divide="ignore"):
            F["sic_trend7"] = np.where(n >= 4, cov / var, np.nan).astype(np.float32)   # % per day
        h = self.f["labels"]["horizon_days"]
        ct, cts = self.clim.window_mean(t + pd.Timedelta(days=1), h)
        cn, _ = self.clim.window_mean(t - pd.Timedelta(days=6), 7)
        F["clim_target"], F["clim_target_std"], F["clim_now"] = ct, cts, cn
        F["clim_change"] = ct - cn
        F["anom_w1"] = wk[1] - cn
        F["anom_persist"] = np.clip(ct + F["anom_w1"], 0, 100)
        valid = np.isfinite(wk[1]) & self.ocean
        F["nbr3_w1"] = _masked_filter(wk[1], valid, 3)
        F["nbr7_w1"] = _masked_filter(wk[1], valid, 7)
        filled = np.where(valid, wk[1], F["nbr7_w1"])
        filled = np.where(np.isfinite(filled), filled, 0)
        gy, gx = np.gradient(filled)
        F["grad_w1"] = np.hypot(gx, gy).astype(np.float32)     # % per 25 km
        ice = self.ocean & (filled >= 15)
        open_ = self.ocean & (filled < 15)
        d_open = ndimage.distance_transform_edt(~open_) * 25.0 if open_.any() else np.full(p.shape, 5000.0)
        d_ice = ndimage.distance_transform_edt(~ice) * 25.0 if ice.any() else np.full(p.shape, 5000.0)
        F["dist_edge_km"] = np.where(ice, d_open, -d_ice).astype(np.float32)
        sd = self.cube.stdev[max(self.cube.idx(t) - 6, 0): self.cube.idx(t) + 1].astype(np.float32)
        sd[sd > 100] = np.nan
        F["unc_w1"], _ = _nanmean(sd, 0, 1)
        sie1, sie2 = self.extent(wk[1]), self.extent(wk[2])
        F["sie_w1"] = np.full(p.shape, sie1, np.float32)
        F["sie_change"] = np.full(p.shape, sie1 - sie2, np.float32)
        ss = np.zeros(p.shape, np.float32)
        for s in range(self.n_sectors):
            m = self.sector == s
            ss[m] = self.extent(wk[1], m)
        F["sie_sector_w1"] = ss
        F["dist_coast_km"] = self.dist_coast
        F["lat"], F["lon_sin"], F["lon_cos"], F["sector"] = self.lat, self.lon_sin, self.lon_cos, self.sector
        mid = t + pd.Timedelta(days=(h + 1) / 2)
        ang = 2 * np.pi * (mid.dayofyear - 1) / 365.25
        F["doy_sin"] = np.full(p.shape, np.sin(ang), np.float32)
        F["doy_cos"] = np.full(p.shape, np.cos(ang), np.float32)
        F["month"] = np.full(p.shape, mid.month, np.float32)
        if self.atmos is not None:
            wd = self.f["atmosphere"]["window_days"]
            co = {}
            for v in ["air", "uwnd", "vwnd", "slp"]:
                c, n_ = self.atmos.window_mean_coarse(v, t, wd)
                co[v] = c
                F[f"{v}_w1"] = self.atmos.to_grid(c) if c is not None else np.full(p.shape, np.nan, np.float32)
            F["wspd_w1"] = np.hypot(F["uwnd_w1"], F["vwnd_w1"])
            for v in ["air", "slp"]:
                if co[v] is not None and v in self.atmos.clim:
                    F[f"{v}_anom_w1"] = self.atmos.to_grid(co[v] - self.atmos.window_clim_coarse(v, t, wd))
                else:
                    F[f"{v}_anom_w1"] = np.full(p.shape, np.nan, np.float32)
        return F

    def active_mask(self, F: dict) -> np.ndarray:
        """Cells handled by the ML model (selection uses INPUTS only, never the target)."""
        p = np.nan_to_num(F["sic_d0"])
        return self.ocean & ((p > 0) | (np.nan_to_num(F["clim_target"]) > 0) | (np.nan_to_num(F["nbr7_w1"]) > 0))

    def table(self, t, names: list[str], sample_frac: float | None = None, rng=None, require_target=True):
        """Rows for one issue date: features, persistence, target. Returns DataFrame (+ flat cell indices)."""
        F = self.features(t)
        y, ny_ = self.target(t)
        m = self.active_mask(F) & np.isfinite(F["sic_d0"])
        if require_target:
            m &= np.isfinite(y)
        idx = np.flatnonzero(m)
        if sample_frac is not None and sample_frac < 1:
            idx = idx[rng.random(idx.size) < sample_frac]
        df = pd.DataFrame({n: F[n].ravel()[idx] for n in names})
        df["persistence"] = F["sic_d0"].ravel()[idx]
        df["target"] = y.ravel()[idx]
        df["cell"] = idx.astype(np.int32)
        df["issue_date"] = pd.Timestamp(t)
        df["area_km2"] = self.area.ravel()[idx].astype(np.float32)
        return df, F, y
