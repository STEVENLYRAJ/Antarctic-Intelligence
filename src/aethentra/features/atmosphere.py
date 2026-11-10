"""Atmospheric predictors (interim source: NCEP/NCAR R1 daily means) mapped onto the SIC grid.

Only days <= issue date are used. Bilinear interpolation (continuous fields) from the 2.5 deg
Gaussian-free regular lat/lon grid to SIC cell centres, with longitude wrap-around. Anomalies use a
day-of-year climatology fitted on the training period only.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from ..config import ROOT, load
from .climatology import doy_index


class Atmosphere:
    def __init__(self, data: dict, lat: np.ndarray, lon: np.ndarray, grid_lat: np.ndarray, grid_lon: np.ndarray):
        self.data = data            # var -> pd.Series of dates -> index, array (T, nlat, nlon)
        self.lat, self.lon = lat, lon
        self._weights(grid_lat, grid_lon)
        self.clim: dict[str, np.ndarray] = {}

    @classmethod
    def load(cls, grid_lat, grid_lon, variables=None) -> "Atmosphere | None":
        cfg = load("data_sources")["atmosphere_interim"]
        d = ROOT / cfg["local_dir"]
        variables = variables or list(cfg["variables"])
        data, lat, lon = {}, None, None
        for v in variables:
            files = sorted(d.glob(f"ncep_r1_{v}_*_south.nc"))
            if not files:
                return None
            arrs, times = [], []
            for f in files:
                with xr.open_dataset(f) as ds:
                    arrs.append(ds[v].values.astype(np.float32))
                    times.append(pd.DatetimeIndex(ds["time"].values).normalize())
                    lat, lon = ds["lat"].values, ds["lon"].values
            t = times[0].append(times[1:]) if len(times) > 1 else times[0]
            a = np.concatenate(arrs, axis=0)
            order = np.argsort(t.values, kind="stable")
            t, a = t[order], a[order]
            keep = ~t.duplicated()
            data[v] = (t[keep], a[keep])
        return cls(data, lat, lon, grid_lat, grid_lon)

    def _weights(self, glat, glon):
        lat = self.lat                                   # descending (-35 .. -90)
        lon = np.append(self.lon, 360.0)                 # wrap
        L = np.mod(glon, 360.0)
        fi = np.interp(glat, lat[::-1], np.arange(len(lat))[::-1])   # fractional lat index
        fj = np.interp(L, lon, np.arange(len(lon)))
        i0 = np.clip(np.floor(fi).astype(int), 0, len(lat) - 2)
        j0 = np.clip(np.floor(fj).astype(int), 0, len(lon) - 2)
        self.i0, self.j0, self.wi, self.wj = i0, j0, fi - i0, fj - j0
        self.nlon = len(self.lon)

    def to_grid(self, field: np.ndarray) -> np.ndarray:
        f = np.concatenate([field, field[:, :1]], axis=1)
        i0, j0, wi, wj = self.i0, self.j0, self.wi, self.wj
        return ((1 - wi) * (1 - wj) * f[i0, j0] + (1 - wi) * wj * f[i0, j0 + 1]
                + wi * (1 - wj) * f[i0 + 1, j0] + wi * wj * f[i0 + 1, j0 + 1]).astype(np.float32)

    def window_mean_coarse(self, var: str, end_date, n_days: int) -> tuple[np.ndarray | None, int]:
        t, a = self.data[var]
        sel = (t > pd.Timestamp(end_date) - pd.Timedelta(days=n_days)) & (t <= pd.Timestamp(end_date))
        if sel.sum() == 0:
            return None, 0
        return np.nanmean(a[sel], axis=0), int(sel.sum())

    def fit_climatology(self, start: str, end: str, half_width: int = 7):
        for v, (t, a) in self.data.items():
            sel = (t >= pd.Timestamp(start)) & (t <= pd.Timestamp(end))
            k = doy_index(t[sel])
            s = np.zeros((365, *a.shape[1:])); n = np.zeros(365)
            np.add.at(s, k, a[sel]); np.add.at(n, k, 1)
            ext_s = np.concatenate([s[-half_width:], s, s[:half_width]]); ext_n = np.concatenate([n[-half_width:], n, n[:half_width]])
            w = 2 * half_width + 1
            cs = np.cumsum(np.concatenate([np.zeros((1, *s.shape[1:])), ext_s]), axis=0)
            cn = np.cumsum(np.concatenate([[0], ext_n]))
            self.clim[v] = ((cs[w:] - cs[:-w]) / (cn[w:] - cn[:-w])[:, None, None]).astype(np.float32)
        self.clim_period = (start, end)

    def window_clim_coarse(self, var: str, end_date, n_days: int) -> np.ndarray:
        k = doy_index(pd.date_range(end=pd.Timestamp(end_date), periods=n_days, freq="D"))
        return self.clim[var][k].mean(axis=0)

    def coverage(self) -> dict:
        return {v: {"first": str(t[0].date()), "last": str(t[-1].date()), "days": int(len(t)),
                    "missing_days_in_span": int(len(pd.date_range(t[0], t[-1])) - len(t))} for v, (t, a) in self.data.items()}
