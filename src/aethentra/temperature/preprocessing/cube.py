"""Daily multi-variable cube for ML-02 on the ML-01 25 km EPSG:3412 grid (cells south of 60 S).

Layout (``data/interim/ml02/<source>/``):
  ``grid.npz``          static fields of the N domain cells (lat, lon, area, land, elevation, dist_coast, region, row/col)
  ``<var>.npy``         int16 memmap (n_days, N); value = int * scale; fill -32768
  ``calendar.csv``      date and per-variable presence
  ``daily_qa.csv``      per-day domain statistics and flags
  ``cube_meta.json``    source, unit conversions, interpolation, input files + checksums
Source fields are daily means on regular or Gaussian lat-lon grids; they are interpolated bilinearly (continuous
variables only). The land/ocean mask is the CDR surface-type mask already on the target grid (never interpolated).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage

from ...config import ROOT, rel
from ...data.acquisition import md5sum, read_prov
from ..paths import load

LOG = logging.getLogger("aethentra.ml02.cube")
FILL = np.int16(-32768)
REGIONS = ["southern_ocean", "antarctic_peninsula", "west_antarctica", "east_antarctica"]


# --------------------------------------------------------------------------------------------- interpolation
def bilinear_weights(src_lat: np.ndarray, src_lon: np.ndarray, lat: np.ndarray, lon: np.ndarray):
    """Weights for bilinear interpolation from a (possibly descending / Gaussian) lat x periodic-lon grid.

    Returns (lat_order, i0, i1, wi, j0, j1, wj) to be used by :func:`apply_weights`. Target latitudes outside the source
    range are clamped to the edge row (e.g. the pole for Gaussian grids, documented).
    """
    order = np.argsort(src_lat)
    sl = np.asarray(src_lat, float)[order]
    slon = np.mod(np.asarray(src_lon, float), 360.0)
    if np.any(np.diff(slon) <= 0):
        raise ValueError("source longitudes must be strictly increasing")
    la = np.clip(lat, sl[0], sl[-1])
    i1 = np.clip(np.searchsorted(sl, la, side="right"), 1, len(sl) - 1)
    i0 = i1 - 1
    wi = (la - sl[i0]) / (sl[i1] - sl[i0])
    lo = np.mod(lon, 360.0)
    ext = np.concatenate([slon, [slon[0] + 360.0]])
    j1 = np.clip(np.searchsorted(ext, np.where(lo < slon[0], lo + 360.0, lo), side="right"), 1, len(ext) - 1)
    j0 = j1 - 1
    lo2 = np.where(lo < slon[0], lo + 360.0, lo)
    wj = (lo2 - ext[j0]) / (ext[j1] - ext[j0])
    return order, i0, i1, wi, j0 % len(slon), j1 % len(slon), wj


def apply_weights(a: np.ndarray, w) -> np.ndarray:
    """a: (..., lat, lon) in the ORIGINAL latitude order -> (..., N)."""
    order, i0, i1, wi, j0, j1, wj = w
    a = a[..., order, :]
    return ((1 - wi) * (1 - wj) * a[..., i0, j0] + (1 - wi) * wj * a[..., i0, j1]
            + wi * (1 - wj) * a[..., i1, j0] + wi * wj * a[..., i1, j1])


# --------------------------------------------------------------------------------------------- unit handling
def to_target_units(var: str, a: np.ndarray, units: str | None) -> tuple[np.ndarray, str]:
    u = (units or "").strip()
    if var in ("t2m", "d2m", "t850"):
        if u in ("K", "degK", "kelvin", "Kelvin"):
            return a - 273.15, f"{u} -> degC (minus 273.15)"
        if u in ("degC", "C", "celsius"):
            return a, "already degC"
        raise ValueError(f"{var}: unknown temperature units {units!r}")
    if var == "msl":
        if u in ("Pa", "Pascals", "pascal", "Pascal"):
            return a / 100.0, "Pa -> hPa"
        if u in ("hPa", "mb", "millibars"):
            return a, "already hPa"
        raise ValueError(f"msl: unknown units {units!r}")
    if var == "z500":
        if u in ("m**2 s**-2", "m2 s-2", "m^2/s^2"):
            return a / 9.80665, "geopotential / g -> gpm"
        if u in ("m", "gpm"):
            return a, "already gpm"
        raise ValueError(f"z500: unknown units {units!r}")
    return a, f"unchanged ({u})"


def _open_field(path: Path, var: str | None):
    import xarray as xr
    ds = xr.open_dataset(path)
    v = var if var and var in ds.data_vars else [k for k in ds.data_vars if ds[k].ndim >= 2][0]
    da = ds[v].squeeze(drop=True)
    for extra in [d for d in da.dims if d not in ("time", "valid_time", "lat", "latitude", "lon", "longitude")]:
        da = da.isel({extra: 0})
    tname = "valid_time" if "valid_time" in da.dims else ("time" if "time" in da.dims else None)
    latn = "latitude" if "latitude" in da.dims else "lat"
    lonn = "longitude" if "longitude" in da.dims else "lon"
    times = pd.to_datetime(da[tname].values).normalize() if tname else None
    arr = da.transpose(*([tname] if tname else []), latn, lonn).values.astype("float32")
    out = (arr, da[latn].values, da[lonn].values, times, da.attrs.get("units"))
    ds.close()
    return out


# --------------------------------------------------------------------------------------------- static grid
def build_grid(cfg: dict) -> dict:
    g = np.load(ROOT / cfg["grid_source"])
    dom = g["lat"] <= cfg["domain_lat_max"]
    rows, cols = np.nonzero(dom)
    land2d = ~g["ocean_mask"]
    lat, lon = g["lat"][dom], g["lon"][dom]
    land = land2d[dom]
    d_to_ocean = ndimage.distance_transform_edt(land2d) * 25.0       # km from a land cell to the nearest ocean cell
    d_to_land = ndimage.distance_transform_edt(~land2d) * 25.0
    dist = np.where(land2d, d_to_ocean, d_to_land)[dom]
    lon180 = ((lon + 180) % 360) - 180
    region = np.zeros(lat.size, np.int8)                              # 0 southern ocean
    pen = land & (lon180 >= -80) & (lon180 <= -55) & (lat >= -75)
    west = land & ~pen & (lon180 < -30) & (lon180 >= -180)
    east = land & ~pen & ~west
    region[pen], region[west], region[east] = 1, 2, 3
    return {"rows": rows.astype(np.int16), "cols": cols.astype(np.int16), "lat": lat, "lon": lon, "area_km2": g["cell_area_km2"][dom],
            "land": land, "dist_coast_km": dist, "coastal": land & (dist <= cfg["coastal_km"]), "region": region,
            "region_names": np.array(REGIONS), "shape": np.array(g["lat"].shape), "x": g["x"], "y": g["y"]}


def _orography(src_cfg: dict, grid: dict) -> tuple[np.ndarray, str]:
    o = src_cfg.get("orography")
    if not o:
        return np.zeros(grid["lat"].size, "float32"), "none"
    if "file" in o:
        p = ROOT / o["file"]
        if not p.exists():
            return np.full(grid["lat"].size, np.nan, "float32"), f"missing {o['file']}"
        a, la, lo, _, _ = _open_field(p, o["var"])
        src = rel(p)
    else:
        import netCDF4
        with netCDF4.Dataset(o["opendap"]) as d:
            a = np.ma.filled(d[o["var"]][0].astype("float32"), np.nan)
            la, lo = d["lat"][:], d["lon"][:]
        src = o["opendap"]
    a = a.reshape(a.shape[-2:]) / o["divide_by"]
    z = apply_weights(a, bilinear_weights(la, lo, grid["lat"], grid["lon"]))
    z = np.where(grid["land"], np.maximum(z, 0.0), 0.0)
    return z.astype("float32"), src


# --------------------------------------------------------------------------------------------- build
def build_cube(source: str | None = None, variables: list[str] | None = None, years: tuple[int, int] | None = None) -> Path:
    cfg = load("preprocessing")
    source = source or load("data_sources")["primary"]
    scfg = cfg["sources"][source]
    out = ROOT / cfg["out_dir"] / source
    out.mkdir(parents=True, exist_ok=True)
    grid = build_grid(cfg)
    grid["elevation_m"], oro_src = _orography(scfg, grid)
    np.savez_compressed(out / "grid.npz", **grid)
    start, end = pd.Timestamp(cfg["start"]), pd.Timestamp(cfg["end"])
    if years:
        start, end = max(start, pd.Timestamp(f"{years[0]}-01-01")), min(end, pd.Timestamp(f"{years[1]}-12-31"))
    dates = pd.date_range(start, end, freq="D")
    n = grid["lat"].size
    variables = [v for v in (variables or [k for k in scfg if k in cfg["variables"]]) if v in scfg and v in cfg["variables"]]
    meta = {"source": source, "created_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), "n_cells": int(n),
            "start": str(dates[0].date()), "end": str(dates[-1].date()), "grid": "ML-01 NSIDC 25 km EPSG:3412, lat <= -60",
            "interpolation": cfg["interpolation"], "orography_source": oro_src, "variables": {}}
    cal = pd.DataFrame({"date": dates})
    qa = pd.DataFrame({"date": dates})
    for var in variables:
        vc, sc = cfg["variables"][var], scfg[var]
        arr = np.lib.format.open_memmap(out / f"{var}.npy.part", mode="w+", dtype="int16", shape=(len(dates), n))
        arr[:] = FILL
        present = np.zeros(len(dates), bool)
        dmin, dmax, dmean = (np.full(len(dates), np.nan) for _ in range(3))
        files, conv, w, n_range, n_dup, n_flag = [], set(), None, 0, 0, 0
        for year in range(dates[0].year, dates[-1].year + 1):
            p = ROOT / sc["glob"].format(year=year)
            if not p.exists():
                continue
            a, la, lo, times, units = _open_field(p, sc.get("var"))
            a, c = to_target_units(var, a, units)
            conv.add(c)
            if w is None:
                w = bilinear_weights(la, lo, grid["lat"], grid["lon"])
            n_dup += int(pd.Index(times).duplicated().sum())
            keep = ~pd.Index(times).duplicated()
            v = apply_weights(a[keep], w)
            idx = dates.get_indexer(times[keep])
            ok = idx >= 0
            v, idx = v[ok], idx[ok]
            lo_, hi_ = vc["range"]
            bad = ~np.isfinite(v) | (v < lo_) | (v > hi_)
            n_range += int((np.isfinite(v) & ((v < lo_) | (v > hi_))).sum())
            if "flag" in vc:
                n_flag += int((~bad & ((v < vc["flag"][0]) | (v > vc["flag"][1]))).sum())
            q = np.where(bad, FILL, np.round(v / vc["scale"])).astype("int16")
            arr[idx] = q
            present[idx] = (~bad).any(axis=1)
            vv = np.where(bad, np.nan, v)
            dmin[idx], dmax[idx], dmean[idx] = np.nanmin(vv, 1), np.nanmax(vv, 1), np.nanmean(vv, 1)
            prov = read_prov(p) or {}
            files.append({"file": rel(p), "md5": prov.get("md5") or md5sum(p), "units_in_file": units})
            LOG.info("%s %s %d: %d days", source, var, year, int(ok.sum()))
        arr.flush()
        del arr
        (out / f"{var}.npy.part").replace(out / f"{var}.npy")
        cal[var] = present
        qa[f"{var}_min"], qa[f"{var}_max"], qa[f"{var}_mean"] = dmin, dmax, dmean
        meta["variables"][var] = {"units": vc["units"], "scale": vc["scale"], "fill": int(FILL), "unit_conversion": sorted(conv),
                                  "days_present": int(present.sum()), "first": str(dates[present][0].date()) if present.any() else None,
                                  "last": str(dates[present][-1].date()) if present.any() else None, "values_out_of_range_set_missing": n_range,
                                  "values_flagged_doubtful_kept": n_flag, "flag_range": vc.get("flag"),
                                  "duplicate_timestamps_dropped": n_dup, "files": files}
    if "t2m_mean" in qa:
        jump = qa["t2m_mean"].diff().abs()
        qa["t2m_jump_flag"] = jump > cfg["qa"]["max_domain_mean_daily_jump_degC"]
        meta["t2m_domain_mean_jump_days"] = qa.loc[qa.t2m_jump_flag, "date"].dt.strftime("%Y-%m-%d").tolist()
    cal.to_csv(out / "calendar.csv", index=False)
    qa.to_csv(out / "daily_qa.csv", index=False)
    (out / "cube_meta.json").write_text(json.dumps(meta, indent=1))
    return out


class Cube:
    """Read access to a built ML-02 cube (values in physical units, NaN for fill)."""

    def __init__(self, source: str | None = None, directory: Path | None = None):
        cfg = load("preprocessing")
        self.source = source or load("data_sources")["primary"]
        self.dir = directory or ROOT / cfg["out_dir"] / self.source
        self.meta = json.loads((self.dir / "cube_meta.json").read_text())
        self.calendar = pd.read_csv(self.dir / "calendar.csv", parse_dates=["date"])
        self.dates = pd.DatetimeIndex(self.calendar.date)
        z = np.load(self.dir / "grid.npz")
        self.grid = {k: z[k] for k in z.files}
        self.n = self.grid["lat"].size
        self._arr = {}

    @property
    def variables(self) -> list[str]:
        return list(self.meta["variables"])

    def raw(self, var: str) -> np.ndarray:
        if var not in self._arr:
            self._arr[var] = np.load(self.dir / f"{var}.npy", mmap_mode="r")
        return self._arr[var]

    def idx(self, t) -> int:
        return int((pd.Timestamp(t) - self.dates[0]).days)

    def window(self, var: str, end, n: int) -> np.ndarray:
        """Days end-n+1 .. end inclusive -> float32 (n, N) with NaN for missing / out of record."""
        i1 = self.idx(end) + 1
        i0 = i1 - n
        out = np.full((n, self.n), np.nan, np.float32)
        a0, a1 = max(i0, 0), min(i1, len(self.dates))
        if a1 > a0:
            q = np.asarray(self.raw(var)[a0:a1])
            out[a0 - i0:a1 - i0] = np.where(q == FILL, np.nan, q * np.float32(self.meta["variables"][var]["scale"]))
        return out

    @cached_property
    def doy(self) -> np.ndarray:
        from ..climatology.climatology import doy_index
        return doy_index(self.dates)

    def to_grid(self, v: np.ndarray, fill=np.nan) -> np.ndarray:
        g = np.full(tuple(self.grid["shape"]), fill, dtype=np.float32)
        g[self.grid["rows"], self.grid["cols"]] = v
        return g
