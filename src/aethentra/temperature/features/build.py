"""Leakage-safe features for ML-02. Every input window ends at the issue day t (inclusive); labels use t+1 .. t+7.

All transformations that are fitted (climatology, sigma, damped-persistence coefficients) are fitted on training years only
(see training.pipeline); tree models need no scaling. Missing predictors stay NaN.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy import ndimage

from ..climatology.climatology import Climatology, doy_index
from ..labels.labels import Sigma, categorize, weekly_labels
from ..paths import load

T_FEATURES = ["t2m_d0", "t2m_w1", "anom_d0", "anom_w1", "anom_w2", "anom_w3", "anom_w4", "anom_m8", "anom_std_w1", "anom_std_w4",
              "anom_tend", "anom_d0_minus_w1", "t2m_range_w1", "nbr_anom_w1", "domain_anom_w1", "region_anom_w1",
              "clim_target", "clim_change"]
SEASON_FEATURES = ["doy_sin", "doy_cos", "month"]
STATIC_FEATURES = ["lat", "lon_sin", "lon_cos", "elevation_m", "dist_coast_km", "land", "coastal", "region"]
ATM_FEATURES = {"msl": ["msl_anom_d0", "msl_anom_w1", "msl_tend"], "u10": ["u10_w1"], "v10": ["v10_w1"],
                "wspd": ["wspd_w1"], "d2m": ["d2m_anom_w1"], "tcc": ["tcc_w1"], "z500": ["z500_anom_w1"], "t850": ["t850_anom_w1"]}
SIC_FEATURES = ["sic_w1", "sic_change_w4"]
CATEGORICAL = ["region", "month"]


def feature_names(cube_vars, use_sic: bool = True, temperature_only: bool = False) -> list[str]:
    names = T_FEATURES + SEASON_FEATURES + STATIC_FEATURES
    if temperature_only:
        return names
    for v, fs in ATM_FEATURES.items():
        if v in cube_vars or (v == "wspd" and {"u10", "v10"} <= set(cube_vars)):
            names += fs
    return names + (SIC_FEATURES if use_sic else [])


def issue_dates(start, end) -> pd.DatetimeIndex:
    """Issue dates on the fixed 7-day cadence whose whole target window lies inside [start, end] and that have the
    full input history inside the record."""
    cfg = load("features")
    h, hist = cfg["labels"]["horizon_days"], cfg["issue"]["history_days"]
    anchor = pd.Timestamp(cfg["issue"]["anchor"])
    d = pd.date_range(anchor, pd.Timestamp(end) - pd.Timedelta(days=h), freq=f"{cfg['issue']['cadence_days']}D")
    return d[(d >= pd.Timestamp(start)) & (d - pd.Timedelta(days=hist - 1) >= pd.Timestamp("1979-01-01"))]


def _masked_mean_filter(grid_vals: np.ndarray, size: int) -> np.ndarray:
    ok = np.isfinite(grid_vals)
    num = ndimage.uniform_filter(np.where(ok, grid_vals, 0.0), size, mode="constant")
    den = ndimage.uniform_filter(ok.astype(float), size, mode="constant")
    out = np.where(den > 1e-6, num / np.maximum(den, 1e-6), np.nan)
    return out


class FeatureContext:
    def __init__(self, cube, clim: Climatology, sigma: Sigma | None = None, sic_cube=None):
        self.cube, self.clim, self.sigma, self.sic_cube = cube, clim, sigma, sic_cube
        g = cube.grid
        self.area = g["area_km2"].astype(np.float32)
        self.static = {"lat": g["lat"].astype(np.float32), "lon_sin": np.sin(np.radians(g["lon"])).astype(np.float32),
                       "lon_cos": np.cos(np.radians(g["lon"])).astype(np.float32), "elevation_m": g["elevation_m"].astype(np.float32),
                       "dist_coast_km": g["dist_coast_km"].astype(np.float32), "land": g["land"].astype(np.float32),
                       "coastal": g["coastal"].astype(np.float32), "region": g["region"].astype(np.float32)}
        self.region = g["region"].astype(int)
        self.region_names = [str(x) for x in g["region_names"]]
        self.nbr = load("features")["neighbourhood_cells"]

    # -- helpers
    def _anom(self, var: str, t, n: int) -> np.ndarray:
        w = self.cube.window(var, t, n)
        dates = pd.date_range(pd.Timestamp(t) - pd.Timedelta(days=n - 1), periods=n, freq="D")
        return w - self.clim.mean[var][doy_index(dates)]

    def _area_mean(self, v: np.ndarray, m=None) -> float:
        ok = np.isfinite(v) & (True if m is None else m)
        return float((v[ok] * self.area[ok]).sum() / self.area[ok].sum()) if ok.any() else np.nan

    # -- public
    def labels(self, t):
        return weekly_labels(self.cube, self.clim, t)

    def features(self, t) -> dict:
        t = pd.Timestamp(t)
        h = load("features")["labels"]["horizon_days"]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            T = self.cube.window("t2m", t, 7)
            A = self._anom("t2m", t, 56)                   # days t-55 .. t
            F = {"t2m_d0": T[-1], "t2m_w1": np.nanmean(T, 0), "anom_d0": A[-1], "anom_w1": np.nanmean(A[-7:], 0),
                 "anom_w2": np.nanmean(A[-14:-7], 0), "anom_w3": np.nanmean(A[-21:-14], 0), "anom_w4": np.nanmean(A[-28:-21], 0),
                 "anom_m8": np.nanmean(A, 0), "anom_std_w1": np.nanstd(A[-7:], 0), "anom_std_w4": np.nanstd(A[-28:], 0),
                 "t2m_range_w1": np.nanmax(T, 0) - np.nanmin(T, 0)}
            F["anom_tend"] = F["anom_w1"] - F["anom_w2"]
            F["anom_d0_minus_w1"] = F["anom_d0"] - F["anom_w1"]
            F["nbr_anom_w1"] = self.cube.to_grid(F["anom_w1"])
            F["nbr_anom_w1"] = _masked_mean_filter(F["nbr_anom_w1"], self.nbr)[self.cube.grid["rows"], self.cube.grid["cols"]]
            F["domain_anom_w1"] = np.full(self.cube.n, self._area_mean(F["anom_w1"]), np.float32)
            reg = np.zeros(self.cube.n, np.float32)
            for r in np.unique(self.region):
                reg[self.region == r] = self._area_mean(F["anom_w1"], self.region == r)
            F["region_anom_w1"] = reg
            F["clim_target"] = self.clim.window_mean("t2m", t + pd.Timedelta(days=1), h)
            F["clim_change"] = F["clim_target"] - self.clim.window_mean("t2m", t - pd.Timedelta(days=6), 7)
            mid = t + pd.Timedelta(days=(h + 1) // 2)
            ang = 2 * np.pi * (doy_index([mid])[0] + 0.5) / 365.0
            F["doy_sin"] = np.full(self.cube.n, np.sin(ang), np.float32)
            F["doy_cos"] = np.full(self.cube.n, np.cos(ang), np.float32)
            F["month"] = np.full(self.cube.n, mid.month, np.float32)
            F.update(self.static)
            cv = self.cube.variables
            if "msl" in cv:
                M = self._anom("msl", t, 14)
                F["msl_anom_d0"], F["msl_anom_w1"] = M[-1], np.nanmean(M[-7:], 0)
                F["msl_tend"] = F["msl_anom_w1"] - np.nanmean(M[:7], 0)
            if {"u10", "v10"} <= set(cv):
                U, V = self.cube.window("u10", t, 7), self.cube.window("v10", t, 7)
                F["u10_w1"], F["v10_w1"], F["wspd_w1"] = np.nanmean(U, 0), np.nanmean(V, 0), np.nanmean(np.hypot(U, V), 0)
            for v, key in (("d2m", "d2m_anom_w1"), ("z500", "z500_anom_w1"), ("t850", "t850_anom_w1")):
                if v in cv:
                    F[key] = np.nanmean(self._anom(v, t, 7), 0)
            if "tcc" in cv:
                F["tcc_w1"] = np.nanmean(self.cube.window("tcc", t, 7), 0)
            if self.sic_cube is not None:
                r, c = self.cube.grid["rows"], self.cube.grid["cols"]
                S = self.sic_cube.window(t, 28)[:, r, c]
                F["sic_w1"] = np.nanmean(S[-7:], 0)
                F["sic_change_w4"] = F["sic_w1"] - np.nanmean(S[:7], 0)
        return {k: np.asarray(v, np.float32) for k, v in F.items()}

    def categories(self, anom: np.ndarray, t) -> np.ndarray:
        if self.sigma is None:
            raise ValueError("sigma not fitted")
        return categorize(anom, self.sigma.for_date(t))

    def table(self, t, names, frac: float = 1.0, rng=None) -> pd.DataFrame:
        F = self.features(t)
        tw, aw, cw = self.labels(t)
        ok = np.isfinite(aw) & np.isfinite(F["anom_w1"])
        idx = np.flatnonzero(ok)
        if frac < 1.0:
            idx = idx[rng.random(idx.size) < frac]
        df = pd.DataFrame({k: F[k][idx] for k in names})
        df["cell"] = idx.astype(np.int32)
        df["issue_date"] = pd.Timestamp(t)
        df["target_anom"], df["target_t2m"], df["clim_week"] = aw[idx], tw[idx], cw[idx]
        df["area_km2"] = self.area[idx]
        return df
