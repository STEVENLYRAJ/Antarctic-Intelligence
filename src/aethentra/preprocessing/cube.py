"""Build the daily SIC cube on the native NSIDC 25 km polar-stereographic grid.

Outputs (data/interim/aethentra/):
  sic_daily.npy        uint8 (T, 332, 316): SIC in % (0..100); 255 = missing / not observed / non-ocean flag
  sic_stdev_daily.npy  uint8 (T, 332, 316): CDR source-estimated standard deviation in % (rounded); 255 = missing
  grid.npz             x, y, lat, lon, ocean_mask, cell_area_km2, dist_coast_km, sector
  calendar.csv         one row per calendar day: date, source file, present flag
  daily_qa.csv         per-day QA statistics (missing cells, interpolation, flags, extent, area, invalid values)
  cube_meta.json       provenance: input files + md5, shapes, start date, build time

No values are interpolated, regridded or filled. Missing calendar days are stored as all-255 layers and listed.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd
from pyproj import Proj
from scipy import ndimage

from ..config import ROOT, load, rel

LOG = logging.getLogger("aethentra.cube")
MISSING = 255


def cube_dir() -> Path:
    return ROOT / load("preprocessing")["cube"]["out_dir"]


def input_files() -> list[Path]:
    cfg = load("data_sources")["sea_ice_concentration"]
    d = ROOT / cfg["local_dir"]
    files = sorted(d.glob("sic_pss25_*_v06r00.nc"))
    by_year: dict[int, Path] = {}
    for f in files:                      # one file per year; for the partial year keep the latest end date
        m = re.match(r"sic_pss25_(\d{4})0101-(\d{8})_v06r00\.nc", f.name)
        if not m:
            continue
        y = int(m.group(1))
        if y not in by_year or f.name > by_year[y].name:
            by_year[y] = f
    return [by_year[y] for y in sorted(by_year)]


def cell_area_km2(lat: np.ndarray, lon: np.ndarray, proj4: str, res_m: float) -> np.ndarray:
    """Exact cell area = nominal (25 km)^2 divided by the areal scale factor of the polar stereographic projection."""
    f = Proj(proj4).get_factors(lon.ravel(), lat.ravel())
    return (res_m ** 2 / np.asarray(f.areal_scale)).reshape(lat.shape) / 1e6


def sector_ids(lon: np.ndarray, sectors: dict) -> np.ndarray:
    """Integer sector id per cell (order of the config dict, 0-based)."""
    out = np.full(lon.shape, -1, dtype=np.int8)
    for i, (_, (a, b)) in enumerate(sectors.items()):
        sel = (lon >= a) & (lon < b) if a < b else (lon >= a) | (lon < b)   # Ross wraps the dateline
        out[sel] = i
    return out


def build_cube(force: bool = False) -> dict:
    pcfg, fcfg = load("preprocessing"), load("features")
    out = cube_dir()
    out.mkdir(parents=True, exist_ok=True)
    files = input_files()
    if not files:
        raise FileNotFoundError("No G02202 v6 files found; run scripts/download_data.py --cdr")
    meta_path = out / "cube_meta.json"
    sig = [(f.name, f.stat().st_size) for f in files]
    if not force and meta_path.exists() and json.loads(meta_path.read_text())["input_signature"] == sig:
        LOG.info("Cube up to date (%d input files)", len(files))
        return json.loads(meta_path.read_text())

    start = pd.Timestamp(pcfg["cube"]["start"])
    # last date = end of the last file's time axis
    with netCDF4.Dataset(files[-1]) as d:
        last = pd.Timestamp(netCDF4.num2date(d["time"][-1], d["time"].units, only_use_cftime_datetimes=False))
    dates = pd.date_range(start, last, freq="D")
    T, ny, nx = len(dates), *pcfg["grid"]["shape"]
    LOG.info("Building cube %s .. %s (%d days) from %d files", dates[0].date(), dates[-1].date(), T, len(files))
    sic = np.lib.format.open_memmap(out / "sic_daily.npy", mode="w+", dtype=np.uint8, shape=(T, ny, nx))
    sd = np.lib.format.open_memmap(out / "sic_stdev_daily.npy", mode="w+", dtype=np.uint8, shape=(T, ny, nx))
    sic[:] = MISSING
    sd[:] = MISSING
    present = np.zeros(T, bool)
    src = np.array([""] * T, dtype=object)
    ocean_days = np.zeros((ny, nx), np.int32)
    lat = lon = x = y = None
    qa_rows = []
    in_meta = []
    for f in files:
        with netCDF4.Dataset(f) as d:
            d.set_auto_maskandscale(False)
            tt = pd.DatetimeIndex(netCDF4.num2date(d["time"][:], d["time"].units, only_use_cftime_datetimes=False))
            if lat is None:
                sup = d.groups["cdr_supplementary"]
                lat, lon = sup["latitude"][:], sup["longitude"][:]
                x, y = d["x"][:], d["y"][:]
            sup = d.groups["cdr_supplementary"]
            prov = json.loads(Path(str(f) + ".provenance.json").read_text()) if Path(str(f) + ".provenance.json").exists() else {}
            in_meta.append({"file": f.name, "days": len(tt), "first": str(tt[0].date()), "last": str(tt[-1].date()),
                            "md5": prov.get("md5"), "md5_verified": prov.get("verified"), "source_url": prov.get("source_url")})
            for k, t in enumerate(tt):
                i = (t - start).days
                if i < 0 or i >= T:
                    continue
                c = d["cdr_seaice_conc"][k]
                s = d["cdr_seaice_conc_stdev"][k]
                st = sup["surface_type_mask"][k]
                qa = d["cdr_seaice_conc_qa_flag"][k]
                ti = d["cdr_seaice_conc_interp_temporal_flag"][k]
                ocean = st == pcfg["masks"]["surface_type_ocean_value"]
                ocean_days += ocean
                if present[i]:
                    qa_rows.append({"date": t.date(), "duplicate_day": True})
                    continue
                present[i] = True
                src[i] = f.name
                sic[i] = c
                sv = np.where(s >= 0, np.clip(np.rint(s * 100), 0, 100), MISSING).astype(np.uint8)
                sd[i] = sv
                oc = c[ocean]
                qa_rows.append({
                    "date": t.date(), "duplicate_day": False, "ocean_cells": int(ocean.sum()),
                    "ocean_missing": int((oc == MISSING).sum()),
                    "ocean_invalid_gt100": int(((oc > 100) & (oc != MISSING)).sum()),
                    "ocean_temporally_interpolated": int((ti[ocean] > 0).sum()),
                    "ocean_no_input_flag": int(((qa[ocean] & 8) > 0).sum()),
                    "nonocean_with_value": int(((c[~ocean] <= 100)).sum()),
                })
        LOG.info("  %s: %d days", f.name, len(tt))
    sic.flush(); sd.flush()

    ocean_mask = ocean_days >= pcfg["masks"]["ocean_min_fraction_of_days"] * present.sum()
    area = cell_area_km2(lat, lon, pcfg["grid"]["proj4"], pcfg["grid"]["resolution_m"])
    dist_coast = ndimage.distance_transform_edt(ocean_mask) * pcfg["grid"]["resolution_m"] / 1e3
    sector = sector_ids(lon, fcfg["sectors"])
    np.savez_compressed(out / "grid.npz", x=x, y=y, lat=lat, lon=lon, ocean_mask=ocean_mask, cell_area_km2=area,
                        dist_coast_km=dist_coast, sector=sector, ocean_days=ocean_days,
                        sector_names=np.array(list(fcfg["sectors"].keys())))

    # Per-day extent / area on the static ocean mask (observed fields)
    thr = pcfg["qa"]["sic_threshold"]
    ext, ar, nvalid = np.full(T, np.nan), np.full(T, np.nan), np.zeros(T, int)
    for i in np.nonzero(present)[0]:
        c = sic[i][ocean_mask]
        v = c <= 100
        nvalid[i] = v.sum()
        a = area[ocean_mask]
        ice = v & (c >= thr)
        ext[i] = a[ice].sum() / 1e6
        ar[i] = (a[ice] * c[ice] / 100.0).sum() / 1e6
    cal = pd.DataFrame({"date": dates.date, "present": present, "source_file": src, "valid_ocean_cells": nvalid,
                        "extent_mkm2": ext, "area_mkm2": ar})
    cal.to_csv(out / "calendar.csv", index=False)
    qa = pd.DataFrame(qa_rows)
    qa.to_csv(out / "daily_qa.csv", index=False)
    meta = {"built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "start": str(dates[0].date()),
            "end": str(dates[-1].date()), "shape": [T, ny, nx], "missing_value": MISSING, "units": "percent",
            "days_present": int(present.sum()), "days_missing": int((~present).sum()),
            "ocean_cells": int(ocean_mask.sum()), "ocean_area_mkm2": float(area[ocean_mask].sum() / 1e6),
            "cell_area_km2_range": [float(area.min()), float(area.max())],
            "inputs": in_meta, "input_signature": sig, "grid": pcfg["grid"],
            "transformations": ["uint8 storage of cdr_seaice_conc in percent (scale_factor 0.01 undone, values unchanged)",
                                "cdr_seaice_conc_stdev (0..1) -> percent rounded to integer",
                                "no regridding, no interpolation, no gap filling"]}
    meta_path.write_text(json.dumps(meta, indent=2))
    LOG.info("Cube written: %s days present, %s missing", meta["days_present"], meta["days_missing"])
    return meta


class Cube:
    """Read-only accessor (memory-mapped)."""

    def __init__(self, directory: Path | None = None):
        d = directory or cube_dir()
        self.dir = d
        self.sic = np.load(d / "sic_daily.npy", mmap_mode="r")
        self.stdev = np.load(d / "sic_stdev_daily.npy", mmap_mode="r")
        self.meta = json.loads((d / "cube_meta.json").read_text())
        g = np.load(d / "grid.npz", allow_pickle=False)
        self.grid = {k: g[k] for k in g.files}
        self.start = pd.Timestamp(self.meta["start"])
        self.dates = pd.date_range(self.start, self.meta["end"], freq="D")
        self.calendar = pd.read_csv(d / "calendar.csv", parse_dates=["date"])
        self.ocean = self.grid["ocean_mask"].astype(bool)
        self.area = self.grid["cell_area_km2"]

    def idx(self, date) -> int:
        return (pd.Timestamp(date) - self.start).days

    def day(self, date) -> np.ndarray:
        """float32 SIC % with NaN for missing / non-ocean."""
        i = self.idx(date)
        if i < 0 or i >= len(self.dates):
            return np.full(self.ocean.shape, np.nan, np.float32)
        a = self.sic[i].astype(np.float32)
        a[(a > 100) | ~self.ocean] = np.nan
        return a

    def window(self, end_date, n_days: int) -> np.ndarray:
        """(n, ny, nx) float32 for days end-n+1 .. end (NaN where missing)."""
        i1 = self.idx(end_date) + 1
        i0 = i1 - n_days
        out = np.full((n_days, *self.ocean.shape), np.nan, np.float32)
        lo, hi = max(i0, 0), min(i1, len(self.dates))
        if hi > lo:
            a = self.sic[lo:hi].astype(np.float32)
            a[(a > 100) | ~self.ocean[None]] = np.nan
            out[lo - i0:hi - i0] = a
        return out
