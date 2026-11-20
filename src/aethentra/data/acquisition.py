"""Resumable, checksum-verified acquisition of the primary SIC CDR and interim atmospheric predictors.

* NSIDC G02202 v6 yearly aggregate NetCDF files over public HTTPS (HTTP Range resume, MD5 vs NSIDC .mnf manifest).
* NCEP/NCAR R1 daily means via public OPeNDAP, subset south of ``lat_max`` and written as local NetCDF.

Every file gets a ``.provenance.json`` sidecar (source URL, retrieval time, version, parameters, checksum).
No credentials are used. Existing verified files are never re-downloaded or overwritten.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import requests

from ..config import ROOT, load, rel

LOG = logging.getLogger("aethentra.acquisition")
UA = {"User-Agent": "aethentra-ml-task01/0.1 (scientific research; contact via repository owner)"}


def _now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


# Plausible ranges in the SOURCE units (NCEP R1 / ERA5 short names). SLP allows plateau-extrapolated values (> 1100 hPa).
PLAUSIBLE = {"air": (150, 330), "t2m": (150, 330), "skt": (150, 340), "slp": (85_000, 113_500), "msl": (85_000, 113_500),
             "uwnd": (-100, 100), "vwnd": (-100, 100), "u10": (-100, 100), "v10": (-100, 100), "rhum": (0, 110),
             "prate": (0, 0.02), "tcdc": (0, 100.5), "hgt500": (4000, 6500), "hgt": (-1000, 40_000)}


class ContentError(ValueError):
    """Downloaded array is structurally valid but its CONTENT is implausible (e.g. all zeros)."""


def content_check(data: np.ndarray, var: str, max_flat_day_fraction: float = 0.01, max_zero_fraction: float = 0.9) -> dict:
    """Reject arrays that cannot be real geophysical fields (added after three all-zero NCEP files passed the
    day-count check in ML-04, 2026-11-11). Checks: some finite data; not mostly zeros; per-day spatial variance > 0
    on (almost) every day with data; values inside the plausible range for the variable. Raises ContentError."""
    a = np.asarray(data, dtype=np.float64)
    fin = np.isfinite(a)
    if not fin.any():
        raise ContentError(f"{var}: no finite values")
    flat = a.reshape(a.shape[0], -1) if a.ndim >= 2 else a[:, None]
    finite_days = np.isfinite(flat).any(1)
    with np.errstate(invalid="ignore"):
        day_std = np.nanstd(flat[finite_days], 1)
    flat_days = int((day_std == 0).sum()) if flat.shape[1] > 1 else 0
    zero_frac = float((a[fin] == 0).mean())
    lo, hi = float(np.nanmin(a)), float(np.nanmax(a))
    rep = {"finite_fraction": round(float(fin.mean()), 4), "days_with_data": int(finite_days.sum()), "flat_days": flat_days,
           "zero_fraction": round(zero_frac, 4), "min": lo, "max": hi}
    if zero_frac > max_zero_fraction:
        raise ContentError(f"{var}: {zero_frac:.0%} of values are exactly 0 ({rep})")
    if flat_days > max_flat_day_fraction * max(int(finite_days.sum()), 1):
        raise ContentError(f"{var}: {flat_days} days with a spatially constant field ({rep})")
    if var in PLAUSIBLE:
        plo, phi = PLAUSIBLE[var]
        if lo < plo or hi > phi:
            raise ContentError(f"{var}: values {lo:.4g}..{hi:.4g} outside plausible {plo}..{phi} ({rep})")
        rep["plausible_range"] = [plo, phi]
    rep["status"] = "passed"
    return rep


def md5sum(path: Path, chunk=4 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def _write_prov(path: Path, info: dict):
    Path(str(path) + ".provenance.json").write_text(json.dumps(info, indent=2), encoding="utf-8")


def read_prov(path: Path) -> dict | None:
    p = Path(str(path) + ".provenance.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# --------------------------------------------------------------------------- SIC CDR
def list_cdr_files(cfg: dict) -> list[str]:
    """Complete-year files plus the most recent partial-year aggregate (resolved from the live index)."""
    y0, y1 = cfg["years"]
    names = [cfg["file_pattern"].format(year=y) for y in range(y0, y1 + 1)]
    try:
        html = requests.get(cfg["base_url"], headers=UA, timeout=60).text
        rx = re.compile(cfg["partial_year_file_regex"])
        partial = {m.group(0): m.group(2) for m in rx.finditer(html) if int(m.group(1)) > y1}
        if partial:
            names.append(max(partial, key=partial.get))      # latest end date of the newest (partial) year
    except requests.RequestException as e:
        LOG.warning("Could not list partial-year files: %s", e)
    return names


def _manifest(cfg: dict, name: str) -> tuple[str, int] | None:
    try:
        r = requests.get(cfg["checksum_url"] + name + ".mnf", headers=UA, timeout=60)
        r.raise_for_status()
        _, md5, size = r.text.strip().split(",")
        return md5, int(size)
    except Exception as e:
        LOG.warning("No manifest for %s: %s", name, e)
        return None


def download_cdr_file(cfg: dict, name: str, retries: int = 5) -> dict:
    out_dir = ROOT / cfg["local_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / name
    man = _manifest(cfg, name)
    prov = read_prov(dst)
    if dst.exists() and prov and prov.get("verified") and (not man or prov.get("md5") == man[0]):
        return {"file": name, "status": "already_verified"}
    url = cfg["base_url"] + name
    part = dst.with_suffix(dst.suffix + ".part")
    if dst.exists() and not part.exists():
        dst.rename(part)                                  # unverified complete file -> verify path below
    for attempt in range(1, retries + 1):
        try:
            have = part.stat().st_size if part.exists() else 0
            if man and have == man[1]:
                break
            hdr = dict(UA, **({"Range": f"bytes={have}-"} if have else {}))
            with requests.get(url, headers=hdr, stream=True, timeout=120) as r:
                if r.status_code == 416:
                    break
                r.raise_for_status()
                mode = "ab" if (have and r.status_code == 206) else "wb"
                with open(part, mode) as f:
                    for b in r.iter_content(1 << 20):
                        f.write(b)
            break
        except requests.RequestException as e:
            LOG.warning("%s attempt %d failed: %s", name, attempt, e)
            time.sleep(10 * attempt)
    else:
        return {"file": name, "status": "failed_download"}
    digest = md5sum(part)
    ok = (man is None) or (digest == man[0] and part.stat().st_size == man[1])
    if not ok:
        part.unlink()
        return {"file": name, "status": "failed_checksum", "md5": digest, "expected": man}
    part.rename(dst)
    info = {"dataset": cfg["id"], "product": cfg["name"], "version": cfg["version"], "doi": cfg["doi"], "source_url": url,
            "original_filename": name, "retrieved_utc": _now(), "bytes": dst.stat().st_size, "md5": digest,
            "md5_manifest": man[0] if man else None, "verified": man is not None, "access": cfg["access"]}
    _write_prov(dst, info)
    return {"file": name, "status": "downloaded", "verified": info["verified"]}


def acquire_cdr(workers: int = 4) -> list[dict]:
    cfg = load("data_sources")["sea_ice_concentration"]
    names = list_cdr_files(cfg)
    LOG.info("CDR: %d files to ensure", len(names))
    res = []
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(download_cdr_file, cfg, n): n for n in names}
        for f in as_completed(futs):
            r = f.result()
            LOG.info("CDR %s: %s", r["file"], r["status"])
            res.append(r)
    return sorted(res, key=lambda r: r["file"])


# --------------------------------------------------------------------------- NCEP R1 (OPeNDAP)
def download_ncep_var_year(cfg: dict, var: str, year: int, retries: int = 4) -> dict:
    import netCDF4
    import xarray as xr
    out_dir = ROOT / cfg["local_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"ncep_r1_{var}_{year}_south.nc"
    prov = read_prov(dst)
    current_year = dt.date.today().year
    if dst.exists() and prov and prov.get("complete_year") and year < current_year:
        return {"file": dst.name, "status": "already_present"}
    url = cfg["opendap_base"] + cfg["variables"][var]["path"].format(year=year)
    for attempt in range(1, retries + 1):
        try:
            with netCDF4.Dataset(url) as d:
                lat = d["lat"][:]
                idx = np.nonzero(lat <= cfg["lat_max"])[0]
                v = d[var]
                arr = v[:, idx[0]:idx[-1] + 1, :]
                data = np.ma.filled(arr.astype("float32"), np.nan)
                qa = content_check(data, var)                 # raises ContentError -> retried, never written
                t = netCDF4.num2date(d["time"][:], d["time"].units, only_use_cftime_datetimes=False)
                attrs = {k: v.getncattr(k) for k in v.ncattrs() if k in ("units", "long_name", "level_desc", "statistic", "dataset")}
                ds = xr.Dataset({var: (("time", "lat", "lon"), data, attrs)},
                                coords={"time": np.array(t, dtype="datetime64[ns]"), "lat": lat[idx], "lon": d["lon"][:]},
                                attrs={"source": url, "subset": f"lat <= {cfg['lat_max']}", "retrieved_utc": _now()})
            tmp = dst.with_suffix(".nc.part")
            ds.to_netcdf(tmp, encoding={var: {"zlib": True, "complevel": 4}})
            tmp.replace(dst)
            n_days = int(ds.sizes["time"])
            info = {"dataset": cfg["id"], "product": cfg["name"], "variable": var, "year": year, "source_url": url,
                    "retrieved_utc": _now(), "days": n_days, "complete_year": n_days >= 365, "md5": md5sum(dst),
                    "subset": f"lat <= {cfg['lat_max']}", "units": attrs.get("units"), "access": cfg["access"], "content_check": qa}
            _write_prov(dst, info)
            return {"file": dst.name, "status": "downloaded", "days": n_days}
        except Exception as e:
            LOG.warning("NCEP %s %d attempt %d failed: %s", var, year, attempt, str(e)[:200])
            time.sleep(15 * attempt)
    return {"file": dst.name, "status": "failed"}


def acquire_ncep(workers: int = 4) -> list[dict]:
    cfg = load("data_sources")["atmosphere_interim"]
    y0, y1 = cfg["years"]
    jobs = [(v, y) for y in range(y0, y1 + 1) for v in cfg["variables"]]
    res = []
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(download_ncep_var_year, cfg, v, y) for v, y in jobs]
        for f in as_completed(futs):
            r = f.result()
            LOG.info("NCEP %s: %s", r["file"], r["status"])
            res.append(r)
    return sorted(res, key=lambda r: r["file"])
