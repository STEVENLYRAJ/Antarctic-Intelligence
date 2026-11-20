"""ML-04 acquisition: extra NCEP/NCAR R1 daily variables (rhum, prate, tcdc, 500 hPa height) via public OPeNDAP.

Subset south of ``lat_max``; written as local NetCDF with a ``.provenance.json`` sidecar (URL, retrieval time, MD5).
Variables already acquired for ML-01/ML-02 (air, slp, uwnd, vwnd) are reused in place. No credentials are used.
Complete past years are never re-downloaded; the current year is refreshed.
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

from ..config import ROOT
from ..data.acquisition import _now, _write_prov, content_check, md5sum, read_prov
from .paths import load

LOG = logging.getLogger("aethentra.ml04.acquisition")


def raw_path(var: str, year: int):
    cfg = load("data_sources")["ncep_r1"]
    if var in cfg["reused"]:
        return ROOT / cfg["reused"][var]["dir"] / f"ncep_r1_{var}_{year}_south.nc"
    return ROOT / cfg["local_dir"] / f"ncep_r1_{var}_{year}_south.nc"


def download_var_year(var: str, year: int, retries: int = 4) -> dict:
    import netCDF4
    import xarray as xr
    cfg = load("data_sources")["ncep_r1"]
    spec = cfg["new"][var]
    dst = raw_path(var, year)
    dst.parent.mkdir(parents=True, exist_ok=True)
    prov = read_prov(dst)
    if dst.exists() and prov and prov.get("complete_year") and year < dt.date.today().year:
        return {"file": dst.name, "status": "already_present"}
    url = cfg["opendap_base"] + spec["path"].format(year=year)
    name = spec.get("var", var)
    for attempt in range(1, retries + 1):
        try:
            with netCDF4.Dataset(url) as d:
                lat = d["lat"][:]
                idx = np.nonzero(lat <= cfg["lat_max"])[0]
                v = d[name]
                if "level" in v.dimensions:
                    k = int(np.nonzero(d["level"][:] == spec["level"])[0][0])
                    arr = v[:, k, idx[0]:idx[-1] + 1, :]
                else:
                    arr = v[:, idx[0]:idx[-1] + 1, :]
                data = np.ma.filled(arr.astype("float32"), np.nan)
                qa = content_check(data, var)                 # raises ContentError -> retried, never written
                t = netCDF4.num2date(d["time"][:], d["time"].units, only_use_cftime_datetimes=False)
                attrs = {k: v.getncattr(k) for k in v.ncattrs() if k in ("units", "long_name", "level_desc", "statistic", "dataset")}
                if "level" in spec:
                    attrs["level_hPa"] = spec["level"]
                ds = xr.Dataset({var: (("time", "lat", "lon"), data, attrs)},
                                coords={"time": np.array(t, dtype="datetime64[ns]"), "lat": lat[idx], "lon": d["lon"][:]},
                                attrs={"source": url, "subset": f"lat <= {cfg['lat_max']}", "retrieved_utc": _now()})
            tmp = dst.with_suffix(".nc.part")
            ds.to_netcdf(tmp, encoding={var: {"zlib": True, "complevel": 4}})
            tmp.replace(dst)
            n = int(ds.sizes["time"])
            info = {"dataset": cfg["id"], "product": cfg["name"], "variable": var, "year": year, "source_url": url,
                    "retrieved_utc": _now(), "days": n, "complete_year": n >= 365, "md5": md5sum(dst),
                    "subset": f"lat <= {cfg['lat_max']}" + (f", level {spec['level']} hPa" if "level" in spec else ""),
                    "units": attrs.get("units"), "grid": spec["grid"], "access": cfg["access"], "content_check": qa}
            _write_prov(dst, info)
            return {"file": dst.name, "status": "downloaded", "days": n}
        except Exception as e:  # noqa: BLE001
            LOG.warning("NCEP %s %d attempt %d failed: %s", var, year, attempt, str(e)[:200])
            time.sleep(10 * attempt)
    return {"file": dst.name, "status": "failed"}


def acquire(workers: int = 4) -> list[dict]:
    cfg = load("data_sources")["ncep_r1"]
    y0, y1 = cfg["years"]
    jobs = [(v, y) for y in range(y0, y1 + 1) for v in cfg["new"]]
    out = []
    with ThreadPoolExecutor(workers) as ex:
        for f in as_completed([ex.submit(download_var_year, v, y) for v, y in jobs]):
            r = f.result()
            LOG.info("%s: %s", r["file"], r["status"])
            out.append(r)
    return sorted(out, key=lambda r: r["file"])
