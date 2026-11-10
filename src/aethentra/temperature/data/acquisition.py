"""ML-02 data acquisition: ERA5 daily statistics (CDS API), station observations, interim NCEP R1 2 m temperature.

* ERA5: one CDS request per (variable, year), NetCDF, area-restricted to 55-90 S. Credentials are read by ``cdsapi`` from
  ``%USERPROFILE%\\.cdsapirc`` or ``CDSAPI_URL``/``CDSAPI_KEY``; nothing is stored in the repository.
* Stations: Zenodo record 17164992 (MD5 verified against the record) and GHCN-Daily per-station CSV files.
* Every file gets a ``.provenance.json`` sidecar. Complete files are never re-downloaded or overwritten.
"""
from __future__ import annotations

import logging
import os
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

from ...config import ROOT
from ...data.acquisition import UA, _now, _write_prov, download_ncep_var_year, md5sum, read_prov
from ..paths import load

LOG = logging.getLogger("aethentra.ml02.acquisition")
MONTHS = [f"{m:02d}" for m in range(1, 13)]
DAYS = [f"{d:02d}" for d in range(1, 32)]


def cds_credentials_available() -> bool:
    return Path(os.path.expanduser("~/.cdsapirc")).exists() or bool(os.environ.get("CDSAPI_KEY"))


def _unpack(tmp: Path, dst: Path):
    """CDS may return a zip (one NetCDF inside) or a bare NetCDF."""
    with open(tmp, "rb") as f:
        magic = f.read(4)
    if magic[:2] == b"PK":
        with zipfile.ZipFile(tmp) as z:
            names = [n for n in z.namelist() if n.endswith(".nc")]
            if len(names) != 1:
                raise ValueError(f"unexpected zip content {z.namelist()}")
            dst.write_bytes(z.read(names[0]))
        tmp.unlink()
    else:
        tmp.replace(dst)


def _check_nc(path: Path, short: str | None, n_days: int | None) -> dict:
    import xarray as xr
    with xr.open_dataset(path) as ds:
        var = short if short in ds.data_vars else list(ds.data_vars)[0]
        tdim = "valid_time" if "valid_time" in ds.dims else ("time" if "time" in ds.dims else None)
        nt = int(ds.sizes[tdim]) if tdim else 1
        if n_days is not None and nt != n_days:
            raise ValueError(f"{path.name}: {nt} time steps, expected {n_days}")
        return {"variable_in_file": var, "time_steps": nt, "dims": {k: int(v) for k, v in ds.sizes.items()},
                "units": ds[var].attrs.get("units")}


def era5_request(kind: str, key: str, year: int | None) -> tuple[str, dict]:
    cfg = load("data_sources")["era5"]
    if kind == "invariant":
        v = cfg["invariants"][key]
        return cfg["dataset_invariant"], {"product_type": ["reanalysis"], "variable": [v["cds"]], "year": ["1979"], "month": ["01"],
                                          "day": ["01"], "time": ["00:00"], "data_format": "netcdf", "download_format": "unarchived",
                                          "area": cfg["area"]}
    common = {"product_type": "reanalysis", "year": str(year), "month": MONTHS, "day": DAYS,
              "daily_statistic": cfg["daily_statistic"], "time_zone": cfg["time_zone"], "frequency": cfg["frequency"],
              "area": cfg["area"]}
    if kind == "single":
        return cfg["dataset_single"], {**common, "variable": [cfg["single_levels"][key]["cds"]]}
    v = cfg["pressure_levels"][key]
    return cfg["dataset_pressure"], {**common, "variable": [v["cds"]], "pressure_level": [str(v["level"])]}


def download_era5(kind: str, key: str, year: int | None = None, retries: int = 3) -> dict:
    import cdsapi
    cfg = load("data_sources")["era5"]
    out = ROOT / cfg["local_dir"] / ("invariant" if kind == "invariant" else key)
    out.mkdir(parents=True, exist_ok=True)
    dst = out / (f"era5_{key}_invariant.nc" if kind == "invariant" else f"era5_daily_mean_{key}_{year}.nc")
    prov = read_prov(dst)
    if dst.exists() and prov and prov.get("validated"):
        return {"file": dst.name, "status": "already_present"}
    dataset, req = era5_request(kind, key, year)
    n_days = None if kind == "invariant" else (366 if pd.Timestamp(year=year, month=12, day=31).dayofyear == 366 else 365)
    for attempt in range(1, retries + 1):
        try:
            t0 = time.time()
            c = cdsapi.Client(quiet=True, progress=False)
            tmp = dst.with_suffix(".nc.part")
            c.retrieve(dataset, req).download(str(tmp))
            _unpack(tmp, dst)
            chk = _check_nc(dst, key if kind != "invariant" else None, n_days)
            info = {"dataset": dataset, "product": cfg["name"], "doi": cfg["doi"], "variable": key, "year": year, "request": req,
                    "retrieved_utc": _now(), "seconds": round(time.time() - t0, 1), "md5": md5sum(dst), "bytes": dst.stat().st_size,
                    "validated": True, **chk, "licence": cfg["licence"]}
            _write_prov(dst, info)
            LOG.info("ERA5 %s %s %s: %.0f MB in %.0f s", kind, key, year, dst.stat().st_size / 1e6, time.time() - t0)
            return {"file": dst.name, "status": "downloaded"}
        except Exception as e:  # noqa: BLE001 - CDS errors are heterogeneous; logged and retried
            LOG.warning("ERA5 %s %s %s attempt %d failed: %s", kind, key, year, attempt, str(e)[:300])
            time.sleep(30 * attempt)
    return {"file": dst.name, "status": "failed"}


def acquire_era5(variables: list[str] | None = None, workers: int = 4) -> list[dict]:
    if not cds_credentials_available():
        raise RuntimeError("No CDS credentials: create %USERPROFILE%\\.cdsapirc (see docs/ml_task_02/MISSING_PREREQUISITES.md)")
    cfg = load("data_sources")["era5"]
    y0, y1 = cfg["years"]
    jobs = [("invariant", k, None) for k in cfg["invariants"]]
    order = variables or list(cfg["single_levels"]) + list(cfg["pressure_levels"])
    for k in order:
        kind = "single" if k in cfg["single_levels"] else "pressure"
        jobs += [(kind, k, y) for y in range(y1, y0 - 1, -1)]      # newest first: test/validation years complete earliest
    res = []
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(download_era5, *j) for j in jobs]
        for f in as_completed(futs):
            res.append(f.result())
    return res


# ----------------------------------------------------------------------------------------------- stations
def acquire_zenodo() -> list[dict]:
    cfg = load("data_sources")["stations"]["zenodo"]
    out = ROOT / cfg["local_dir"]
    out.mkdir(parents=True, exist_ok=True)
    rec = requests.get(cfg["api"], headers=UA, timeout=60).json()
    (out / "zenodo_record.json").write_text(pd.Series(rec).to_json(indent=1, default_handler=str))
    res = []
    for f in rec["files"]:
        dst = out / f["key"]
        want = f["checksum"].split(":", 1)[1]
        if dst.exists() and md5sum(dst) == want:
            res.append({"file": f["key"], "status": "already_present"})
            continue
        r = requests.get(f["links"]["self"], headers=UA, timeout=120)
        r.raise_for_status()
        dst.write_bytes(r.content)
        ok = md5sum(dst) == want
        _write_prov(dst, {"dataset": cfg["id"], "name": cfg["name"], "record": cfg["record"], "version_date": rec["metadata"].get("publication_date"),
                          "source_url": f["links"]["self"], "retrieved_utc": _now(), "md5": want, "md5_verified": ok, "licence": cfg["licence"],
                          "reference": cfg["reference"]})
        res.append({"file": f["key"], "status": "downloaded" if ok else "md5_mismatch"})
    return res


def ghcnd_station_table() -> pd.DataFrame:
    cfg = load("data_sources")["stations"]["ghcnd"]
    out = ROOT / cfg["local_dir"]
    out.mkdir(parents=True, exist_ok=True)
    for u in (cfg["stations_url"], cfg["inventory_url"]):
        p = out / u.rsplit("/", 1)[1]
        if not p.exists():
            p.write_bytes(requests.get(u, headers=UA, timeout=120).content)
    st = pd.read_fwf(out / "ghcnd-stations.txt", colspecs=[(0, 11), (12, 20), (21, 30), (31, 37), (41, 71), (80, 85)],
                     names=["id", "lat", "lon", "elev_m", "name", "wmo"], dtype={"wmo": str})
    inv = pd.read_csv(out / "ghcnd-inventory.txt", sep=r"\s+", names=["id", "lat", "lon", "element", "first", "last"])
    st = st[st.lat <= cfg["lat_max"]]
    y0, y1 = cfg["require_tavg_years"]
    tavg = inv[(inv.element == "TAVG") & (inv["first"] <= y0) & (inv["last"] >= y1)].set_index("id")
    st = st[st.id.isin(tavg.index)].copy()
    st["tavg_first"], st["tavg_last"] = tavg.loc[st.id, "first"].values, tavg.loc[st.id, "last"].values
    return st.reset_index(drop=True)


def acquire_ghcnd(workers: int = 6) -> list[dict]:
    cfg = load("data_sources")["stations"]["ghcnd"]
    out = ROOT / cfg["local_dir"]
    st = ghcnd_station_table()
    st.to_csv(out / "antarctic_stations_selected.csv", index=False)

    def one(sid):
        dst = out / f"{sid}.csv"
        if dst.exists() and read_prov(dst):
            return {"file": dst.name, "status": "already_present"}
        url = cfg["station_csv_url"].format(id=sid)
        r = requests.get(url, headers=UA, timeout=180)
        r.raise_for_status()
        dst.write_bytes(r.content)
        _write_prov(dst, {"dataset": cfg["id"], "name": cfg["name"], "doi": cfg["doi"], "source_url": url, "retrieved_utc": _now(),
                          "md5": md5sum(dst), "bytes": dst.stat().st_size})
        return {"file": dst.name, "status": "downloaded"}
    with ThreadPoolExecutor(workers) as ex:
        return [f.result() for f in as_completed([ex.submit(one, s) for s in st.id])]


def acquire_ncep_interim(workers: int = 4) -> list[dict]:
    cfg = load("data_sources")["ncep_interim"]
    y0, y1 = cfg["years"]
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(download_ncep_var_year, cfg, v, y) for v in cfg["variables"] for y in range(y0, y1 + 1)]
        return [f.result() for f in as_completed(futs)]


def read_zenodo_station(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"])

