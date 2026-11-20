"""MERRA-2 download for AETHENTRA Phase 1 (approved items M1, M2, M3). Credentials: %USERPROFILE%\\_netrc via requests (never read
or printed here). Resumable: existing validated subsets are skipped.

    python scripts/merra2_download.py                 # M1, M2, then M3
    python scripts/merra2_download.py --only M1
    python scripts/merra2_download.py --status

Each global GES DISC file is streamed to a temporary file, subset to 50-90 S and the listed variables, content-checked, written
with a provenance sidecar, and the temporary global file is deleted (the global originals are re-downloadable from GES DISC).
  M1  M2TMNXSLV v5.12.4 monthly single-level diagnostics 1980-01 .. latest  -> data/raw/merra2/M2TMNXSLV/
  M2  M2TMNXFLX v5.12.4 monthly surface fluxes (PRECTOT, PRECSNO)            -> data/raw/merra2/M2TMNXFLX/
  M3  M2SDNXSLV v5.12.4 daily statistics (T2M mean/max/min)                  -> data/raw/merra2/M2SDNXSLV/<year>.nc (one file per year)
MERRA-2 stream numbers: 100 (1980-91), 200 (1992-2000), 300 (2001-10), 400 (2011-), with 401 re-runs (e.g. 2020-09, 2021-06..09).
"""
import argparse
import datetime as dt
import hashlib
import json
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import _bootstrap  # noqa: E402

log = _bootstrap.setup("merra2_download")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402
import xarray as xr  # noqa: E402

from aethentra.data.acquisition import ContentError, content_check  # noqa: E402

BASE = "https://goldsmr4.gesdisc.eosdis.nasa.gov/data"
OUT = ROOT / "data" / "raw" / "merra2"
TMP = Path(tempfile.gettempdir()) / "aethentra_merra2"
LAT_MAX = -50.0
ITEMS = {
    "M1": {"coll": "M2TMNXSLV", "dir": "MERRA2_MONTHLY/M2TMNXSLV.5.12.4", "tag": "tavgM_2d_slv_Nx", "freq": "M",
           "vars": ["T2M", "T2MDEW", "QV2M", "SLP", "PS", "U10M", "V10M", "TS", "OMEGA500", "H500", "T500", "T850", "U500", "V500",
                    "U850", "V850", "TQV", "H850"]},
    "M2": {"coll": "M2TMNXFLX", "dir": "MERRA2_MONTHLY/M2TMNXFLX.5.12.4", "tag": "tavgM_2d_flx_Nx", "freq": "M",
           "vars": ["PRECTOT", "PRECSNO"]},
    "M3": {"coll": "M2SDNXSLV", "dir": "MERRA2/M2SDNXSLV.5.12.4", "tag": "statD_2d_slv_Nx", "freq": "D",
           "vars": ["T2MMEAN", "T2MMAX", "T2MMIN"]},
}
PLAUS = {"T2M": "t2m", "SLP": "slp", "T2MMEAN": "t2m", "T2MMAX": "t2m", "T2MMIN": "t2m"}
_local = threading.local()


def sess() -> requests.Session:
    if not hasattr(_local, "s"):
        _local.s = requests.Session()               # netrc auth for urs.earthdata.nasa.gov is applied by requests
    return _local.s


def streams(year: int) -> list[int]:
    s = 100 if year <= 1991 else 200 if year <= 2000 else 300 if year <= 2010 else 400
    return [s, 401] if s == 400 else [s]


def fetch(item: dict, day: pd.Timestamp) -> tuple[Path, str] | None:
    """Stream one global file to TMP; returns (path, url) or None if not published (404)."""
    sub = f"{day.year}" if item["freq"] == "M" else f"{day.year}/{day.month:02d}"
    stamp = f"{day:%Y%m}" if item["freq"] == "M" else f"{day:%Y%m%d}"
    TMP.mkdir(parents=True, exist_ok=True)
    network_failed = False
    for st in streams(day.year):
        url = f"{BASE}/{item['dir']}/{sub}/MERRA2_{st}.{item['tag']}.{stamp}.nc4"
        for attempt in range(1, 7):
            try:
                with sess().get(url, stream=True, timeout=300) as r:
                    if r.status_code == 404:
                        break
                    r.raise_for_status()
                    tmp = TMP / f"{item['coll']}_{stamp}_{threading.get_ident()}.nc4"
                    with open(tmp, "wb") as f:
                        for b in r.iter_content(8 << 20):
                            f.write(b)
                    return tmp, url
            except requests.RequestException as e:
                log.warning("%s attempt %d: %s", url.rsplit("/", 1)[-1], attempt, str(e)[:200])
                time.sleep(20 * attempt)
                if attempt == 6:
                    network_failed = True
    if network_failed:
        raise ConnectionError(f"network failure for {stamp}")      # not 'not published': retried on the next run
    return None


def subset(path: Path, item: dict) -> xr.Dataset:
    with xr.open_dataset(path) as ds:
        out = ds[item["vars"]].sel(lat=slice(-90, LAT_MAX)).load()
    for v in item["vars"]:
        a = out[v].values
        content_check(a.reshape(a.shape[0], -1), PLAUS.get(v, v), max_zero_fraction=0.995 if v.startswith("PREC") else 0.9)
    return out


def md5(p: Path) -> str:
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(4 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write(ds: xr.Dataset, dst: Path, prov: dict):
    dst.parent.mkdir(parents=True, exist_ok=True)
    ds.attrs.update({"aethentra_subset": f"lat <= {LAT_MAX}, variables {list(ds.data_vars)}",
                     "source": "NASA GMAO MERRA-2 via GES DISC (https://disc.gsfc.nasa.gov)"})
    tmp = dst.with_suffix(".nc.part")
    ds.to_netcdf(tmp, encoding={v: {"zlib": True, "complevel": 4} for v in ds.data_vars})
    tmp.replace(dst)
    prov |= {"md5": md5(dst), "bytes": dst.stat().st_size, "validated": True,
             "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    (dst.parent / (dst.name + ".provenance.json")).write_text(json.dumps(prov, indent=1, default=str))


def done(dst: Path) -> bool:
    p = dst.parent / (dst.name + ".provenance.json")
    return dst.exists() and p.exists() and json.loads(p.read_text()).get("validated")


def one_month(key: str, m: pd.Timestamp) -> str:
    item = ITEMS[key]
    dst = OUT / item["coll"] / f"MERRA2_{item['coll']}_{m:%Y%m}_50S-90S.nc"
    if done(dst):
        return "present"
    try:
        got = fetch(item, m)
    except ConnectionError:
        return "network_failed"
    if got is None:
        return "not_published"
    tmp, url = got
    try:
        ds = subset(tmp, item)
        write(ds, dst, {"collection": item["coll"], "version": "5.12.4", "month": f"{m:%Y-%m}", "source_url": url,
                        "global_file_bytes": tmp.stat().st_size, "variables": item["vars"], "subset": "lat <= -50"})
        return "downloaded"
    except ContentError as e:
        log.warning("content check failed %s: %s", url.rsplit("/", 1)[-1], e)
        return "content_failed"
    finally:
        tmp.unlink(missing_ok=True)


def one_day(m3: dict, d: pd.Timestamp):
    try:
        got = fetch(m3, d)
    except ConnectionError:
        return d, None, None
    if got is None:
        return d, None, None
    tmp, url = got
    try:
        return d, subset(tmp, m3), url
    finally:
        tmp.unlink(missing_ok=True)


def run_monthly(key: str, workers: int):
    months = pd.date_range("1980-01-01", pd.Timestamp.today().normalize().replace(day=1) - pd.offsets.MonthBegin(1), freq="MS")
    res = {}
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(one_month, key, m): m for m in months}
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            res[r] = res.get(r, 0) + 1
            if i % 25 == 0:
                log.info("%s: %d/%d %s", key, i, len(months), res)
    log.info("%s finished: %s", key, res)
    return res


def run_daily(workers: int):
    m3 = ITEMS["M3"]
    today = pd.Timestamp.today().normalize()
    res = {}
    for y in range(today.year, 1979, -1):                     # newest year first
        dst = OUT / m3["coll"] / f"MERRA2_{m3['coll']}_{y}_50S-90S.nc"
        complete = y < today.year
        if done(dst) and json.loads((dst.parent / (dst.name + ".provenance.json")).read_text()).get("complete_year", True):
            res["present"] = res.get("present", 0) + 1
            continue
        days = pd.date_range(f"{y}-01-01", min(pd.Timestamp(f"{y}-12-31"), today - pd.Timedelta(days=1)), freq="D")
        parts, missing, urls = [], [], []
        with ThreadPoolExecutor(workers) as ex:
            for d, ds, url in ex.map(lambda d: one_day(m3, d), days):
                if ds is None:
                    missing.append(str(d.date()))
                else:
                    parts.append(ds)
                    urls.append(url)
        if not parts:
            continue
        yr = xr.concat(sorted(parts, key=lambda x: x.time.values[0]), dim="time")
        write(yr, dst, {"collection": m3["coll"], "version": "5.12.4", "year": y, "days": int(yr.sizes["time"]),
                        "missing_days": missing, "complete_year": complete and not missing, "variables": m3["vars"],
                        "first_url": urls[0], "subset": "lat <= -50"})
        res["years"] = res.get("years", 0) + 1
        log.info("M3 %d: %d days, %d missing", y, yr.sizes["time"], len(missing))
    log.info("M3 finished: %s", res)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=list(ITEMS))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status:
        for k, it in ITEMS.items():
            n = len(list((OUT / it["coll"]).glob("*.nc"))) if (OUT / it["coll"]).exists() else 0
            print(k, it["coll"], n, "files")
        raise SystemExit(0)
    for k in ([a.only] if a.only else ["M1", "M2", "M3"]):
        (run_daily if k == "M3" else (lambda w, k=k: run_monthly(k, w)))(a.workers)
    log.info("MERRA-2 download complete")
