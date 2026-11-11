"""ML-04 Phase 3: climatological baselines and univariate anomaly definitions.

Two FIXED baselines (configs/ml04/anomaly.yaml):
* reporting 1991-2020 (WMO normal): univariate anomaly products, maps and summaries;
* model 1981-2010 (inside the 1979-2010 training period): every ML feature, every severity threshold and all evaluation, so no
  validation/test year ever enters a baseline that is used for evaluation.

Monthly baselines are per cell and per calendar month (no season mixing). Daily baselines are per cell and per day of year with a
+-15 day window (Feb 29 uses Feb 28's climatology). For each baseline sample we store mean, standard deviation (ddof=1),
median, MAD (scaled by 1.4826), 5/10/90/95th percentiles, min/max and the sorted sample (for empirical percentile ranks).

Anomaly definitions:
  absolute     x - mean
  z-score      (x - mean) / max(std, floor)
  robust       (x - median) / max(MAD, floor)
  percentile   empirical non-exceedance probability, Weibull plotting position rank / (n + 1) of x in the baseline sample
               (with n = 30 the 5th/95th percentiles rest on 1-2 values per tail: coarse by construction)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .paths import CLIM, INTERIM, PROCESSED, load
from .preprocessing import ALL_VARS, calendar, month_index

QUANTILES = (0.05, 0.10, 0.90, 0.95)


def floors() -> dict:
    return load("anomaly")["std_floor"]


def baseline_years(name: str) -> tuple[int, int]:
    b = load("anomaly")["baselines"][name]
    return int(b["start"]), int(b["end"])


def monthly(var: str) -> np.ndarray:
    return np.load(PROCESSED / f"monthly_{var}.npy", mmap_mode="r")


def _stats(sample: np.ndarray) -> dict:
    """sample: (n, ...) -> dict of baseline statistics over axis 0 (NaN-aware)."""
    with np.errstate(invalid="ignore"):
        med = np.nanmedian(sample, 0)
        out = {"mean": np.nanmean(sample, 0), "std": np.nanstd(sample, 0, ddof=1), "median": med,
               "mad": 1.4826 * np.nanmedian(np.abs(sample - med), 0), "min": np.nanmin(sample, 0), "max": np.nanmax(sample, 0),
               "n": np.isfinite(sample).sum(0).astype(np.int16)}
        q = np.nanquantile(sample, QUANTILES, axis=0)
    for k, p in enumerate(QUANTILES):
        out[f"p{int(p * 100):02d}"] = q[k]
    return {k: v.astype(np.float32) if k != "n" else v for k, v in out.items()}


def build_monthly_climatology(name: str) -> dict:
    """Per variable: arrays (12, lat, lon) + sorted sample (12, n_years, lat, lon) -> CLIM/monthly_<name>_<var>.npz."""
    CLIM.mkdir(parents=True, exist_ok=True)
    y0, y1 = baseline_years(name)
    months = month_index()
    res = {}
    for v in ALL_VARS + ["dsic"]:
        X = monthly_dsic() if v == "dsic" else np.asarray(monthly(v))
        st, srt = {}, []
        for m in range(12):
            sel = (months.month == m + 1) & (months.year >= y0) & (months.year <= y1)
            s = X[sel]
            srt.append(np.sort(s, 0))
            for k, a in _stats(s).items():
                st.setdefault(k, []).append(a)
        np.savez_compressed(CLIM / f"monthly_{name}_{v}.npz", sorted=np.stack(srt).astype(np.float32),
                            **{k: np.stack(a) for k, a in st.items()}, years=np.array([y0, y1]))
        res[v] = int(sel.sum())
    return res


def monthly_dsic() -> np.ndarray:
    """Month-to-month SIC change (pp), x[m] - x[m-1] (uses only the current and previous month: no future information)."""
    s = np.asarray(monthly("sic"))
    d = np.full_like(s, np.nan)
    d[1:] = s[1:] - s[:-1]
    return d


def load_clim(name: str, var: str) -> dict:
    z = np.load(CLIM / f"monthly_{name}_{var}.npz")
    return {k: z[k] for k in z.files}


def percentile_rank(x: np.ndarray, sorted_sample: np.ndarray) -> np.ndarray:
    """Weibull plotting position of x within a sorted baseline sample along axis 0 (NaNs in the sample ignored)."""
    n = np.isfinite(sorted_sample).sum(0)
    below = (sorted_sample < x[None]).sum(0) + 0.5 * (sorted_sample == x[None]).sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        p = (below + 0.5) / (n + 1.0)
    p = np.where((n > 0) & np.isfinite(x), p, np.nan)
    return p.astype(np.float32)


def anomalies(var: str, x: np.ndarray, month_of_year: np.ndarray, name: str, clim: dict | None = None) -> dict:
    """x: (T, lat, lon) monthly values, month_of_year: (T,) 1..12 -> absolute, z, robust, percentile (+ record flags)."""
    c = clim or load_clim(name, var)
    f = floors().get(var if var != "dsic" else "sic", 0.0)
    i = month_of_year - 1
    mean, std, med, mad = c["mean"][i], np.maximum(c["std"][i], f), c["median"][i], np.maximum(c["mad"][i], f)
    pr = np.stack([percentile_rank(x[t], c["sorted"][i[t]]) for t in range(x.shape[0])])
    return {"absolute": (x - mean).astype(np.float32), "z": ((x - mean) / std).astype(np.float32),
            "robust": ((x - med) / mad).astype(np.float32), "percentile": pr,
            "above_record": x > c["max"][i], "below_record": x < c["min"][i]}


def rolling_z(var: str, window: int = 30, min_years: int = 20) -> np.ndarray:
    """'Rolling-window' reference method: z-score vs the trailing `window` years (Y-window .. Y-1), per calendar month.
    Undefined (NaN) until >= min_years of history exist. Uses only past information."""
    X = monthly_dsic() if var == "dsic" else np.asarray(monthly(var))
    months = month_index()
    out = np.full(X.shape, np.nan, np.float32)
    f = floors().get(var if var != "dsic" else "sic", 0.0)
    for m in range(12):
        idx = np.flatnonzero(months.month == m + 1)
        yrs = months.year[idx]
        for k, t in enumerate(idx):
            past = idx[(yrs < yrs[k]) & (yrs >= yrs[k] - window)]
            if past.size < min_years:
                continue
            s = X[past]
            with np.errstate(invalid="ignore"):
                n = np.isfinite(s).sum(0)
                mu, sd = np.nanmean(s, 0), np.nanstd(s, 0, ddof=1)
            z = (X[t] - mu) / np.maximum(sd, f)
            z[n < min_years] = np.nan
            out[t] = z
    return out


def seasonal_z(var: str, name: str = "model") -> np.ndarray:
    """'Seasonal climatology comparison': trailing 3-month mean (m-2..m) vs the baseline climatology of the same 3-month means."""
    X = monthly_dsic() if var == "dsic" else np.asarray(monthly(var))
    S = np.full(X.shape, np.nan, np.float32)
    S[2:] = (X[2:] + X[1:-1] + X[:-2]) / 3.0
    months = month_index()
    y0, y1 = baseline_years(name)
    f = floors().get(var if var != "dsic" else "sic", 0.0)
    out = np.full(X.shape, np.nan, np.float32)
    for m in range(12):
        sel = months.month == m + 1
        base = sel & (months.year >= y0) & (months.year <= y1)
        with np.errstate(invalid="ignore"):
            mu, sd = np.nanmean(S[base], 0), np.nanstd(S[base], 0, ddof=1)
        out[sel] = (S[sel] - mu) / np.maximum(sd, f)
    return out


# ---------------------------------------------------------------- daily baselines
def noleap_doy(dates: pd.DatetimeIndex) -> np.ndarray:
    d = dates.dayofyear.values.copy()
    leap = dates.is_leap_year & (dates.month > 2)
    d[leap] -= 1                                   # Feb 29 (doy 60 in leap years) -> 59 shares Feb 28; later days shift back
    feb29 = (dates.month == 2) & (dates.day == 29)
    d[feb29] = 59
    return d


def build_daily_climatology(name: str, variables=None) -> dict:
    """Per day of year (365) with a +-15 day circular window: mean, std, p05/p10/p90/p95 -> CLIM/daily_<name>_<var>.npz."""
    CLIM.mkdir(parents=True, exist_ok=True)
    cal = calendar()
    y0, y1 = baseline_years(name)
    half = load("anomaly")["baselines"]["daily_window_days"] // 2
    doy = noleap_doy(cal)
    inb = (cal.year >= y0) & (cal.year <= y1)
    res = {}
    for v in variables or ALL_VARS:
        d = np.load(INTERIM / f"daily_{v}.npy", mmap_mode="r")
        base_idx = np.flatnonzero(inb)
        B = np.asarray(d[base_idx[0]:base_idx[-1] + 1])
        bd = doy[base_idx]
        shp = B.shape[1:]
        acc = {k: np.full((365,) + shp, np.nan, np.float32) for k in ("mean", "std", "p05", "p10", "p90", "p95")}
        cols = np.isfinite(B).any(0).ravel()
        for k in range(1, 366):
            dist = np.abs(bd - k)
            dist = np.minimum(dist, 365 - dist)
            s = B[dist <= half].reshape(-1, int(np.prod(shp)))[:, cols]
            with np.errstate(invalid="ignore"):
                acc["mean"][k - 1].ravel()[cols] = np.nanmean(s, 0)
                acc["std"][k - 1].ravel()[cols] = np.nanstd(s, 0, ddof=1)
                q = np.quantile(s, [0.05, 0.10, 0.90, 0.95], axis=0) if not np.isnan(s).any() else \
                    np.nanquantile(s, [0.05, 0.10, 0.90, 0.95], axis=0)
            for j, key in enumerate(("p05", "p10", "p90", "p95")):
                acc[key][k - 1].ravel()[cols] = q[j]
        np.savez_compressed(CLIM / f"daily_{name}_{v}.npz", **acc, years=np.array([y0, y1]), window_days=2 * half + 1)
        res[v] = int(inb.sum())
    return res


def load_daily_clim(name: str, var: str) -> dict:
    z = np.load(CLIM / f"daily_{name}_{var}.npz")
    return {k: z[k] for k in z.files}
