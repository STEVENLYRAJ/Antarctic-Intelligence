"""ML-04 Phase 2: standardised daily and monthly cubes on the analysis grid.

Analysis grid: NCEP/NCAR R1 native 2.5 deg regular lat/lon, 87.5 S ... 50 S (16 x 144 cells).
* 2.5 deg NCEP fields (air, slp, uwnd, vwnd, rhum, hgt500): native grid, row subset only (no resampling).
* T62 Gaussian NCEP fields (prate, tcdc; ~1.9 deg): linear interpolation in latitude onto the 2.5 deg rows; longitudes are
  re-gridded with periodic linear interpolation. This mildly smooths the finer field; documented in the preprocessing report.
* SIC (NSIDC CDR v6, 25 km EPSG:3412): area-weighted mean of valid ocean pixels whose centre falls inside the 2.5 deg cell;
  cells with < ocean_fraction_min ocean coverage get no SIC value. The native 25 km grid is also kept (monthly) for maps.

Units: t2m degC, slp hPa, wspd m/s (speed of the daily-mean vector; underestimates mean instantaneous speed), rhum %, prate mm/day,
tcdc %, z500 m, sic %. Time axis: daily UTC dates 1979-01-01 ... last SIC day (NCEP R1 ends 2026-03-17 -> NaN afterwards).
Monthly means need >= 80 % valid days, else NaN.
"""
from __future__ import annotations

import datetime as dt
import json
import logging

import numpy as np
import pandas as pd

from ..config import ROOT
from .acquisition import raw_path
from .paths import INTERIM, PROCESSED, load

LOG = logging.getLogger("aethentra.ml04.preprocessing")
SIC_INTERIM = ROOT / "data" / "interim" / "aethentra"
ATM_VARS = ["t2m", "slp", "wspd", "rhum", "prate", "tcdc", "z500"]
ALL_VARS = ATM_VARS + ["sic"]
MIN_MONTH_FRACTION = 0.8
EARTH_R_KM = 6371.0


def grid() -> dict:
    c = load("anomaly")["domain"]
    lat = np.arange(c["lat_max"], c["lat_min"] - 1e-6, -2.5)          # -50 ... -87.5 (north -> south)
    lon = np.arange(0, 360, 2.5)
    phi1, phi2 = np.deg2rad(np.clip(lat - 1.25, -90, 90)), np.deg2rad(np.clip(lat + 1.25, -90, 90))
    area = EARTH_R_KM ** 2 * np.deg2rad(2.5) * (np.sin(phi2) - np.sin(phi1))   # km2 per cell, per row
    return {"lat": lat, "lon": lon, "cell_area_km2": np.repeat(area[:, None], lon.size, 1)}


def calendar() -> pd.DatetimeIndex:
    cal = pd.read_csv(SIC_INTERIM / "calendar.csv", usecols=["date"])
    return pd.DatetimeIndex(pd.to_datetime(cal["date"]))


def _read_year(var: str, year: int, g: dict) -> tuple[np.ndarray, np.ndarray] | None:
    import xarray as xr
    src = {"t2m": "air", "z500": "hgt500"}.get(var, var)
    p = raw_path(src, year)
    if not p.exists():
        return None
    with xr.open_dataset(p) as ds:
        a = ds[src].values.astype(np.float32)
        lat, lon = ds["lat"].values, ds["lon"].values
        t = pd.DatetimeIndex(ds["time"].values).normalize()
    if np.allclose(np.diff(lat), -2.5):                      # regular grid: row subset
        rows = [int(np.argmin(np.abs(lat - x))) for x in g["lat"]]
        a = a[:, rows, :]
    else:                                                     # Gaussian grid: interpolate lat, then periodic lon
        order = np.argsort(lat)
        la, aa = lat[order], a[:, order, :]
        out = np.empty((a.shape[0], g["lat"].size, lon.size), np.float32)
        for k, y in enumerate(g["lat"]):
            i = np.clip(np.searchsorted(la, y), 1, la.size - 1)
            w = (y - la[i - 1]) / (la[i] - la[i - 1])
            out[:, k] = (1 - w) * aa[:, i - 1] + w * aa[:, i]
        lon_ext = np.concatenate([lon, lon[:1] + 360])
        out = np.concatenate([out, out[:, :, :1]], 2)
        a = np.stack([np.stack([np.interp(g["lon"], lon_ext, out[d, k]) for k in range(out.shape[1])]) for d in range(out.shape[0])]
                     ).astype(np.float32)
    return a, t.values


def convert(var: str, a: np.ndarray) -> np.ndarray:
    if var == "t2m":
        return a - 273.15
    if var == "slp":
        return a / 100.0
    if var == "prate":
        return np.clip(a, 0, None) * 86400.0                  # kg m-2 s-1 -> mm/day
    return a


def build_daily_atm(var: str, force: bool = False) -> dict:
    INTERIM.mkdir(parents=True, exist_ok=True)
    dst = INTERIM / f"daily_{var}.npy"
    if dst.exists() and not force:
        return {"var": var, "status": "exists"}
    g, cal = grid(), calendar()
    out = np.lib.format.open_memmap(dst.with_suffix(".part.npy"), "w+", np.float32, (cal.size, g["lat"].size, g["lon"].size))
    out[:] = np.nan
    idx = pd.Series(np.arange(cal.size), index=cal)
    for y in range(cal[0].year, cal[-1].year + 1):
        if var == "wspd":
            ru, rv = _read_year("uwnd", y, g), _read_year("vwnd", y, g)
            if ru is None or rv is None:
                continue
            common, iu, iv = np.intersect1d(ru[1], rv[1], return_indices=True)   # 2026: uwnd and vwnd differ in length
            a, t = np.hypot(ru[0][iu], rv[0][iv]), common
        else:
            r = _read_year(var, y, g)
            if r is None:
                continue
            a, t = convert(var, r[0]), r[1]
        t = pd.DatetimeIndex(t)
        ok = t.isin(cal) & (t.year == y)     # guard: the PSL 2026 uwnd file repeats 2025 dates (all NaN) after 2026-03-17
        out[idx[t[ok]].values] = a[ok]
    out.flush()
    del out
    dst.with_suffix(".part.npy").replace(dst)
    return {"var": var, "status": "built"}


def _sic_matrix(g: dict):
    """Sparse (cells x ocean pixels) area-weight matrix mapping 25 km pixels into 2.5 deg cells."""
    from scipy import sparse
    z = np.load(SIC_INTERIM / "grid.npz")
    ocean = z["ocean_mask"].astype(bool)
    rr, cc = np.nonzero(ocean)
    lat, lon, area = z["lat"][rr, cc], np.mod(z["lon"][rr, cc], 360), z["cell_area_km2"][rr, cc]
    i = np.round((g["lat"][0] - lat) / 2.5).astype(int)
    j = np.mod(np.round(lon / 2.5).astype(int), g["lon"].size)
    keep = (i >= 0) & (i < g["lat"].size)
    cell = i[keep] * g["lon"].size + j[keep]
    M = sparse.csr_matrix((area[keep], (cell, np.flatnonzero(keep))), shape=(g["lat"].size * g["lon"].size, rr.size))
    frac = np.asarray(M.sum(1)).ravel() / g["cell_area_km2"].ravel()
    return M, (rr, cc), frac.reshape(g["lat"].size, g["lon"].size)


def build_daily_sic(force: bool = False) -> dict:
    dst = INTERIM / "daily_sic.npy"
    if dst.exists() and not force:
        return {"var": "sic", "status": "exists"}
    g, cal = grid(), calendar()
    M, (rr, cc), frac = _sic_matrix(g)
    cube = np.load(SIC_INTERIM / "sic_daily.npy", mmap_mode="r")
    out = np.lib.format.open_memmap(dst.with_suffix(".part.npy"), "w+", np.float32, (cal.size, g["lat"].size, g["lon"].size))
    fmin = load("anomaly")["domain"]["ocean_fraction_min"]
    bad = frac < fmin
    for s in range(0, cal.size, 365):
        blk = cube[s:s + 365][:, rr, cc].astype(np.float32)        # (days, pixels)
        valid = blk <= 100
        v = np.where(valid, blk, 0).T                               # (pixels, days)
        num, den = M @ v, M @ valid.T.astype(np.float32)
        with np.errstate(invalid="ignore", divide="ignore"):
            m = (num / den).T.reshape(-1, g["lat"].size, g["lon"].size)
        m[:, bad] = np.nan
        out[s:s + blk.shape[0]] = m
    out.flush()
    del out
    dst.with_suffix(".part.npy").replace(dst)
    np.save(INTERIM / "ocean_fraction.npy", frac.astype(np.float32))
    return {"var": "sic", "status": "built"}


def month_index(cal: pd.DatetimeIndex | None = None) -> pd.DatetimeIndex:
    cal = calendar() if cal is None else cal
    return pd.date_range(cal[0].replace(day=1), cal[-1].replace(day=1), freq="MS")


def build_monthly(force: bool = False) -> dict:
    """Monthly means (>= 80 % valid days) for all variables -> monthly_<var>.npy (months x lat x lon)."""
    cal = calendar()
    months = month_index(cal)
    key = cal.to_period("M")
    res = {}
    for v in ALL_VARS:
        dst = PROCESSED / f"monthly_{v}.npy"
        PROCESSED.mkdir(parents=True, exist_ok=True)
        if dst.exists() and not force:
            res[v] = "exists"
            continue
        d = np.load(INTERIM / f"daily_{v}.npy", mmap_mode="r")
        out = np.full((months.size,) + d.shape[1:], np.nan, np.float32)
        for k, m in enumerate(months):
            sel = np.flatnonzero(key == m.to_period("M"))
            blk = np.asarray(d[sel[0]:sel[-1] + 1])
            n = np.isfinite(blk).sum(0)
            with np.errstate(invalid="ignore"):
                mean = np.nanmean(blk, 0)
            mean[n < MIN_MONTH_FRACTION * m.days_in_month] = np.nan
            out[k] = mean
        np.save(dst, out)
        res[v] = "built"
    pd.Series(months.strftime("%Y-%m")).to_csv(PROCESSED / "months.csv", index=False, header=["month"])
    return res


def build_native_sic_monthly(force: bool = False) -> dict:
    """Monthly mean SIC on the native 25 km EPSG:3412 grid (kept for full-resolution sea-ice anomaly maps)."""
    dst = PROCESSED / "monthly_sic_native25km.npy"
    if dst.exists() and not force:
        return {"status": "exists"}
    cal = calendar()
    months = month_index(cal)
    key = cal.to_period("M")
    cube = np.load(SIC_INTERIM / "sic_daily.npy", mmap_mode="r")
    out = np.lib.format.open_memmap(dst, "w+", np.float32, (months.size,) + cube.shape[1:])
    for k, m in enumerate(months):
        sel = np.flatnonzero(key == m.to_period("M"))
        blk = np.asarray(cube[sel[0]:sel[-1] + 1]).astype(np.float32)
        blk[blk > 100] = np.nan
        n = np.isfinite(blk).sum(0)
        with np.errstate(invalid="ignore"):
            mean = np.nanmean(blk, 0)
        mean[n < MIN_MONTH_FRACTION * m.days_in_month] = np.nan
        out[k] = mean
    out.flush()
    return {"status": "built"}


def extent_indices(force: bool = False) -> pd.DataFrame:
    """Daily sea-ice extent (SIC >= 15 %) total and per sector from the 25 km CDR (10^6 km2)."""
    dst = PROCESSED / "sea_ice_extent_daily.csv"
    if dst.exists() and not force:
        return pd.read_csv(dst, parse_dates=["date"])
    z = np.load(SIC_INTERIM / "grid.npz")
    cal = calendar()
    cube = np.load(SIC_INTERIM / "sic_daily.npy", mmap_mode="r")
    ocean = z["ocean_mask"].astype(bool)
    area, sector, names = z["cell_area_km2"], z["sector"], [str(s) for s in z["sector_names"]]
    rows = []
    for s in range(0, cal.size, 365):
        blk = np.asarray(cube[s:s + 365])
        for k in range(blk.shape[0]):
            a = blk[k]
            ok = ocean & (a <= 100)
            ice = ok & (a >= 15)
            r = {"date": cal[s + k], "valid": bool(ok.sum() > 0.95 * ocean.sum()), "total": float(area[ice].sum() / 1e6)}
            for i, n in enumerate(names):
                r[n] = float(area[ice & (sector == i)].sum() / 1e6)
            rows.append(r)
    df = pd.DataFrame(rows)
    df.loc[~df["valid"], ["total"] + names] = np.nan
    df.to_csv(dst, index=False)
    return df


def quality_report() -> dict:
    """Coverage / range / missing-value report for every daily cube (written to data/processed/ml04/quality_report.json)."""
    cal = calendar()
    g = grid()
    plaus = {"t2m": (-90, 25), "slp": (900, 1130), "wspd": (0, 40), "rhum": (0, 110), "prate": (0, 200), "tcdc": (0, 100.5),
             "z500": (4000, 6200), "sic": (0, 100)}
    rep = {"generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "grid": {
        "lat": [float(g["lat"][0]), float(g["lat"][-1])], "lon": [0.0, 357.5], "shape": [int(g["lat"].size), int(g["lon"].size)],
        "crs": "EPSG:4326 (regular 2.5 deg, cell centres)"}, "calendar": [str(cal[0].date()), str(cal[-1].date())], "variables": {}}
    for v in ALL_VARS:
        d = np.load(INTERIM / f"daily_{v}.npy", mmap_mode="r")
        day_ok = np.array([np.isfinite(d[k]).any() for k in range(d.shape[0])])
        last = cal[np.flatnonzero(day_ok)[-1]]
        s = np.asarray(d[::7])
        lo, hi = float(np.nanmin(s)), float(np.nanmax(s))
        rep["variables"][v] = {"days_with_data": int(day_ok.sum()), "days_total": int(cal.size), "first": str(cal[np.argmax(day_ok)].date()),
                               "last": str(last.date()), "missing_days_inside_record": int((~day_ok[:np.flatnonzero(day_ok)[-1] + 1]).sum()),
                               "sampled_min": lo, "sampled_max": hi, "plausible_range": plaus[v],
                               "range_ok": bool(lo >= plaus[v][0] and hi <= plaus[v][1]),
                               "cells_never_valid": int((~np.isfinite(s).any(0)).sum())}
    (PROCESSED / "quality_report.json").write_text(json.dumps(rep, indent=1))
    return rep
