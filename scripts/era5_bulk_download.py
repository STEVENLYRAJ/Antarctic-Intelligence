"""Queue-safe ERA5 bulk download for AETHENTRA Phase 1 (ML-01, ML-02, ML-04). Resumable; credentials only via cdsapi.Client().

    python scripts/era5_bulk_download.py                 # run until every job is done (state kept in data/raw/era5/_state.json)
    python scripts/era5_bulk_download.py --status        # print progress only

Why this script (2026-11-14): CDS rejects users with too many queued requests ("Maximum number queued requests ... request data
sequentially"), and the derived daily-statistics dataset queued > 50 min per year-variable job. This downloader keeps at most
MAX_ACTIVE jobs in the CDS queue, re-attaches to submitted jobs after a restart (job ids in _state.json, no resubmission), backs
off on queue-limit rejections and validates every file with the shared content check.

Products (area 50-90 S, all git-ignored under data/raw/era5/):
  invariant/      land-sea mask + surface geopotential (0.25 deg)
  monthly/        ERA5 monthly means 1979-2026, 0.25 deg: single levels (11 variables) + pressure levels 500/850 hPa (z, t, w, pv)
  _6hourly/       ERA5 hourly data at 00/06/12/18 UTC, 0.5 deg, 4-year chunks; TRANSIENT: deleted after the validated daily
                  conversion (name, size and md5 kept in _state.json; re-downloadable from CDS) to keep disk use ~30-40 GB
  <var>/          daily means = mean of the four 6-hourly values (an approximation of the 24-hour mean, documented), written as
                  era5_daily_mean_<var>_<year>.nc = the layout read by scripts/ml02/preprocess.py --source era5
                  tp / sf daily = mean of four hourly accumulations x 24 (m/day; sampled estimate, noisier than the true total)
When every daily job is done, scripts/ml02/preprocess.py --source era5 is run (documented ML-02 preprocessing).
"""
import argparse
import datetime as dt
import hashlib
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import _bootstrap  # noqa: E402

log = _bootstrap.setup("era5_bulk")
logging.getLogger("ecmwf").setLevel(logging.WARNING)
logging.getLogger("cdsapi").setLevel(logging.WARNING)

import numpy as np  # noqa: E402
import xarray as xr  # noqa: E402

from aethentra.data.acquisition import ContentError, content_check  # noqa: E402

OUT = ROOT / "data" / "raw" / "era5"
STATE = OUT / "_state.json"
MAX_ACTIVE = 2          # per CDS dataset
TOTAL_ACTIVE = 3        # per user: a 4th queued request was rejected by CDS on 2026-11-15
AREA = [-50, -180, -90, 180]
TODAY = dt.date.today()
YEARS = list(range(1979, TODAY.year + 1))
SINGLE = {"t2m": "2m_temperature", "msl": "mean_sea_level_pressure", "u10": "10m_u_component_of_wind",
          "v10": "10m_v_component_of_wind", "d2m": "2m_dewpoint_temperature", "tcc": "total_cloud_cover", "tp": "total_precipitation",
          "sf": "snowfall", "sd": "snow_depth", "sp": "surface_pressure", "siconc": "sea_ice_cover"}
PRESSURE = {"z": "geopotential", "t": "temperature", "w": "vertical_velocity", "pv": "potential_vorticity"}
LEVELS = ["500", "850"]
ZERO_OK = {"tp", "sf", "sd", "siconc"}                       # legitimately mostly zero (dry days, open ocean, no snow on sea)
CORE_SINGLE = ["t2m", "msl", "u10", "v10"]                 # first block (2026-11-17: d2m, tcc moved to the head of the second
SECOND_SINGLE = ["d2m", "tcc"]                              # block to finish the ML-02 core sooner; ML-02 features treat them as optional)
CORE_PRESSURE = {"z": "500", "t": "850"}                    # -> z500, t850; one level per job (2 levels x 4 years exceed the
                                                            # CDS cost limit, 2026-11-16); z850, t500 follow with the extras
MONTHS = [f"{m:02d}" for m in range(1, 13)]
DAYS = [f"{d:02d}" for d in range(1, 32)]


def jobs() -> list[dict]:
    """~31 jobs (restructured 2026-11-14: the CDS queue wait per job dominates, so jobs are merged).
    Keys of jobs submitted before the restructure (invariant, monthly_single_t2m, monthly_single_msl) are kept."""
    J = [{"key": "invariant", "dataset": "reanalysis-era5-single-levels", "out": OUT / "invariant" / "era5_invariant.nc",
          "request": {"product_type": ["reanalysis"], "variable": ["land_sea_mask", "geopotential"], "year": ["2020"], "month": ["01"],
                      "day": ["01"], "time": ["00:00"], "data_format": "netcdf", "download_format": "unarchived", "area": AREA}}]
    yrs = [str(y) for y in YEARS]
    mon = {"product_type": ["monthly_averaged_reanalysis"], "year": yrs, "month": MONTHS, "time": ["00:00"], "data_format": "netcdf",
           "download_format": "unarchived", "area": AREA}
    for s in ("t2m", "msl"):                                   # submitted individually before the restructure
        J.append({"key": f"monthly_single_{s}", "dataset": "reanalysis-era5-single-levels-monthly-means",
                  "out": OUT / "monthly" / f"era5_monthly_{s}_1979_{TODAY.year}.nc", "request": {**mon, "variable": [SINGLE[s]]}})
    rest = [SINGLE[k] for k in SINGLE if k not in ("t2m", "msl")] + ["sea_surface_temperature"]      # incl. E1 (SST)
    J.append({"key": "monthly_single_multi", "dataset": "reanalysis-era5-single-levels-monthly-means", "split_monthly": True,
              "out": OUT / "monthly" / f"era5_monthly_single_multi_1979_{TODAY.year}.nc", "request": {**mon, "variable": rest}})
    J.append({"key": "monthly_pressure_multi", "dataset": "reanalysis-era5-pressure-levels-monthly-means", "split_monthly": True,
              "out": OUT / "monthly" / f"era5_monthly_pl_multi_1979_{TODAY.year}.nc",
              "request": {**mon, "variable": list(PRESSURE.values()), "pressure_level": LEVELS}})
    chunks = [[TODAY.year]] + [list(range(max(1979, y - 3), y + 1)) for y in range(TODAY.year - 1, 1978, -4)]

    def base(ch):
        months = MONTHS if ch[-1] < TODAY.year else [f"{m:02d}" for m in range(1, TODAY.month)]
        return {"product_type": ["reanalysis"], "year": [str(y) for y in ch], "month": months, "day": DAYS,
                "time": ["00:00", "06:00", "12:00", "18:00"], "data_format": "netcdf", "download_format": "unarchived", "area": AREA,
                "grid": [0.5, 0.5]}

    def tag(ch):
        return f"{ch[0]}" if len(ch) == 1 else f"{ch[0]}_{ch[-1]}"
    ch = chunks[0]                                             # current year: submitted as merged jobs (split by CDS, kept as is)
    J.append({"key": f"6h_single_{tag(ch)}", "dataset": "reanalysis-era5-single-levels", "years": ch,
              "out": OUT / "_6hourly" / f"era5_6h_single_{tag(ch)}.nc", "request": {**base(ch), "variable": list(SINGLE.values())}})
    J.append({"key": f"6h_pressure_{tag(ch)}", "dataset": "reanalysis-era5-pressure-levels", "years": ch,
              "out": OUT / "_6hourly" / f"era5_6h_pressure_{tag(ch)}.nc",
              "request": {**base(ch), "variable": list(PRESSURE.values()), "pressure_level": LEVELS}})
    # Earlier years (reordered 2026-11-16): one variable per job (CDS rejects merged variables on cost), and the variables
    # ML-02 preprocessing needs (CORE) for ALL years before the extra variables, so the ERA5 cube can be built first.
    for tier in (CORE_SINGLE, SECOND_SINGLE + [k for k in SINGLE if k not in CORE_SINGLE + SECOND_SINGLE]):
        for ch in chunks[1:]:
            for sh in tier:
                J.append({"key": f"6h_single_{tag(ch)}__{sh}", "dataset": "reanalysis-era5-single-levels", "years": ch,
                          "out": OUT / "_6hourly" / f"era5_6h_single_{tag(ch)}__{sh}.nc", "request": {**base(ch), "variable": [SINGLE[sh]]}})
        if tier is CORE_SINGLE:
            ptier = [(sh, [lev]) for sh, lev in CORE_PRESSURE.items()]
        else:
            ptier = [(sh, [lev]) for sh, core_lev in CORE_PRESSURE.items() for lev in LEVELS if lev != core_lev] +                     [(sh, [lev]) for sh in PRESSURE if sh not in CORE_PRESSURE for lev in LEVELS]
        for ch in chunks[1:]:
            for sh, lev in ptier:
                if tag(ch) == "2022_2025" and sh == "z":           # already submitted with both levels (split per year by CDS)
                    if tier is CORE_SINGLE:
                        J.append({"key": f"6h_pressure_{tag(ch)}__z", "dataset": "reanalysis-era5-pressure-levels", "years": ch,
                                  "out": OUT / "_6hourly" / f"era5_6h_pressure_{tag(ch)}__z.nc",
                                  "request": {**base(ch), "variable": [PRESSURE["z"]], "pressure_level": LEVELS}})
                    continue
                k = f"{sh}{lev[0]}"
                J.append({"key": f"6h_pressure_{tag(ch)}__{k}", "dataset": "reanalysis-era5-pressure-levels", "years": ch,
                          "out": OUT / "_6hourly" / f"era5_6h_pressure_{tag(ch)}__{k}.nc",
                          "request": {**base(ch), "variable": [PRESSURE[sh]], "pressure_level": lev}})
    # 2026-11-18: within each block, finish whole year-chunks (newest first) for all its variables before older chunks,
    # so complete recent years are available early (stable sort keeps the variable order inside a chunk).
    n0 = next(i for i, j in enumerate(J) if j["key"].startswith("6h_") and "2026" not in j["key"])
    rank = {tag(ch): i for i, ch in enumerate(chunks)}

    def core(j):
        r = j["request"]
        return any(SINGLE[c] in r["variable"] for c in CORE_SINGLE) or             any(PRESSURE[c] in r["variable"] and lev in r.get("pressure_level", []) for c, lev in CORE_PRESSURE.items())
    J[n0:] = sorted(J[n0:], key=lambda j: (0 if core(j) else 1, rank[j["key"].split("__")[0].split("_", 2)[2]]))
    return J


def core_done(J: list[dict], st: dict) -> bool:
    """All daily jobs for the ML-02 variables are finished (every year)."""
    core = [j for j in J if j["key"].startswith("6h_") and
            (any(v in (SINGLE[c] for c in CORE_SINGLE) for v in j["request"]["variable"]) or
             any(PRESSURE[c] in j["request"]["variable"] and lev in j["request"].get("pressure_level", [])
                 for c, lev in CORE_PRESSURE.items()))]
    return bool(core) and all(st.get(j["key"], {}).get("status") == "done" for j in core)


def split_monthly(files: list[Path]) -> list[str]:
    """Write one monthly file per variable (and level) from a merged monthly download."""
    out = []
    ds = xr.open_mfdataset([str(f) for f in files], combine="by_coords") if len(files) > 1 else xr.open_dataset(files[0])
    for v in ds.data_vars:
        if ds[v].ndim < 2:
            continue
        levels = [int(x) for x in ds[v]["pressure_level"].values] if "pressure_level" in ds[v].dims else [None]
        for lev in levels:
            x = ds[v].sel(pressure_level=lev) if lev is not None else ds[v]
            name = f"{v}{lev}" if lev is not None else v
            dst = OUT / "monthly" / f"era5_monthly_{name}_1979_{TODAY.year}.nc"
            x.rename(name).to_dataset().to_netcdf(dst, encoding={name: {"zlib": True, "complevel": 4, "dtype": "float32"}})
            out.append(dst.name)
    ds.close()
    return out


CDS2SHORT = {**{v: k for k, v in SINGLE.items()}, **{v: k for k, v in PRESSURE.items()}, "sea_surface_temperature": "sst"}


def _ser(j: dict) -> dict:
    return {**j, "out": str(j["out"])}


def _de(j: dict) -> dict:
    return {**j, "out": Path(j["out"])}


def split_job(j: dict) -> list[dict]:
    """CDS refused the job on cost ('Your request is too large'): split by variable, then by year, then into month halves."""
    req, out = j["request"], Path(j["out"])
    kids = []
    if len(req["variable"]) > 1:
        for v in req["variable"]:
            sh = CDS2SHORT.get(v, v)
            kids.append({**j, "key": f"{j['key']}__{sh}", "request": {**req, "variable": [v]}, "out": out.with_name(f"{out.stem}__{sh}{out.suffix}")})
    elif len(req["year"]) > 1:                     # halve the years (2026-11-18): 4 -> 2+2 -> 1+1, keeps the largest accepted size
        ys = req["year"]
        for part in (ys[:len(ys) // 2], ys[len(ys) // 2:]):
            t = part[0] if len(part) == 1 else f"{part[0]}_{part[-1]}"
            kids.append({**j, "key": f"{j['key']}__{t}", "request": {**req, "year": part},
                         "years": [int(y) for y in part] if "years" in j else j.get("years"),
                         "out": out.with_name(f"{out.stem}__{t}{out.suffix}")})
    elif len(req.get("month", [])) > 1:
        m = req["month"]
        for i, part in enumerate((m[:len(m) // 2], m[len(m) // 2:])):
            kids.append({**j, "key": f"{j['key']}__m{i}", "request": {**req, "month": part}, "out": out.with_name(f"{out.stem}__m{i}{out.suffix}")})
    return kids


def expand(J: list[dict], st: dict) -> list[dict]:
    """Replace split jobs by their children (recursively, children definitions are stored in the state file)."""
    out = []
    for j in J:
        s = st.get(j["key"], {})
        if s.get("status") == "split":
            out += expand([_de(c) for c in s["children"]], st)
        else:
            out.append(j)
    return out


def load_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_state(st: dict):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1, default=str))
    tmp.replace(STATE)


def md5(p: Path) -> str:
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(4 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _unzip_if_needed(p: Path):
    import zipfile
    with open(p, "rb") as f:
        if f.read(2) != b"PK":
            return [p]
    outs = []
    with zipfile.ZipFile(p) as z:
        for n in z.namelist():
            if n.endswith(".nc"):
                o = p.with_name(p.stem + "__" + Path(n).name)
                o.write_bytes(z.read(n))
                outs.append(o)
    p.unlink()
    return outs


def validate(paths: list[Path]) -> dict:
    rep = {}
    for p in paths:
        with xr.open_dataset(p) as ds:
            for v in ds.data_vars:
                if ds[v].ndim < 2:
                    continue
                a = ds[v].values
                a = a.reshape(a.shape[0], -1) if a.ndim > 2 else a
                rep[v] = content_check(a, v, max_zero_fraction=0.995 if v in ZERO_OK else 0.9)
    return rep


def to_daily(job: dict, files: list[Path]) -> list[str]:
    """6-hourly -> daily means in the ML-02 layout (one file per variable and YEAR; a job may hold several years)."""
    written = []
    full = xr.open_mfdataset([str(f) for f in files], combine="by_coords") if len(files) > 1 else xr.open_dataset(files[0])
    tname = "valid_time" if "valid_time" in full.coords else "time"
    for y in job["years"]:
        ds = full.sel({tname: str(y)})
        if ds.sizes[tname] == 0:
            continue
        written += _daily_year(job, ds, tname, y, files)
    full.close()
    return written


def _daily_year(job: dict, ds, tname: str, y: int, files: list[Path]) -> list[str]:
    written = []
    for v in ds.data_vars:
        da = ds[v]
        if tname not in da.dims:
            continue
        levels = [None]
        if "pressure_level" in da.dims:
            levels = [int(x) for x in da["pressure_level"].values]
        elif len(job["request"].get("pressure_level", [])) == 1:      # single-level request: CDS may squeeze the level dim
            levels = [int(job["request"]["pressure_level"][0])]
        for lev in levels:
            x = da.sel(pressure_level=lev) if lev is not None and "pressure_level" in da.dims else da
            daily = x.resample({tname: "1D"}).mean()
            if v in ("tp", "sf"):
                daily = daily * 24.0                           # mean hourly accumulation x 24 -> m/day (sampled estimate)
                daily.attrs.update(units="m day-1")
            name = f"{v}{lev}" if lev is not None else v
            daily.attrs.update({k: x.attrs[k] for k in ("long_name", "standard_name") if k in x.attrs})
            if v not in ("tp", "sf"):
                daily.attrs["units"] = x.attrs.get("units")
            daily.attrs["aethentra_daily_method"] = ("mean of 00/06/12/18 UTC hourly values" if v not in ("tp", "sf")
                                                     else "mean of the 00/06/12/18 UTC hourly accumulations x 24")
            dst = OUT / name / f"era5_daily_mean_{name}_{y}.nc"
            dst.parent.mkdir(parents=True, exist_ok=True)
            out = daily.rename(name).to_dataset()
            if dst.exists():                                   # job was split into month parts: merge with what exists
                with xr.open_dataset(dst) as old:
                    prev = old.load()
                out = xr.concat([prev, out], dim=tname)
                out = out.sortby(tname).drop_duplicates(tname)
            out.attrs.update({"source": f"ERA5 {job['dataset']} (Copernicus C3S), 0.5 deg, area 50-90 S", "year": y,
                              "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})
            tmp = dst.with_suffix(".nc.part")
            out.to_netcdf(tmp, encoding={name: {"zlib": True, "complevel": 4, "dtype": "float32"}})
            tmp.replace(dst)
            qa = content_check(out[name].values.reshape(out.sizes[tname], -1), name, max_zero_fraction=0.995 if v in ZERO_OK else 0.9)
            (dst.parent / (dst.name + ".provenance.json")).write_text(json.dumps({
                "dataset": job["dataset"], "doi": "10.24381/cds.adbb2d47" if "single" in job["dataset"] else "10.24381/cds.bd0915c6",
                "variable": name, "year": y, "days": int(out.sizes[tname]), "complete_year": y < TODAY.year and int(out.sizes[tname]) >= 365,
                "daily_method": daily.attrs["aethentra_daily_method"], "grid": "0.5 deg regular lat/lon (CDS interpolation)",
                "from_files": [f.name for f in files], "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "md5": md5(dst), "validated": True, "content_check": qa,
                "licence": "Licence to use Copernicus products (accepted by the user on the CDS website)"}, indent=1, default=str))
            written.append(dst.name)
    return written


def error_text(remote) -> str:
    try:
        remote.get_results()
        return ""
    except Exception as e:  # noqa: BLE001
        return str(e)


def main(status_only=False):
    import cdsapi
    inner = cdsapi.Client(quiet=True, progress=False).client      # configuration from %USERPROFILE%\.cdsapirc (never printed)
    J = jobs()
    st = load_state()
    if not status_only and "_adopted" not in st:                  # adopt a matching job already queued by an earlier run
        for jid in inner.get_jobs(limit=50).request_ids:
            r = inner.get_remote(jid)
            if r.status not in ("accepted", "running", "successful"):
                continue
            req = r.json.get("metadata", {}).get("request", {}).get("ids", {})
            for j in J:
                if j["key"] not in st and j["dataset"] == r.json.get("processID") and req.get("variable") == j["request"]["variable"] \
                        and sorted(req.get("year", [])) == sorted(j["request"]["year"]) and req.get("area") == j["request"]["area"]:
                    st[j["key"]] = {"id": jid, "status": "submitted", "adopted": True}
                    log.info("adopted queued job for %s", j["key"])
        st["_adopted"] = True
        save_state(st)
    while True:
        try:
            if _cycle(inner, J, status_only):
                if status_only:
                    return
                break
        except Exception as e:  # noqa: BLE001  network outages (DNS, SSL EOF, timeouts): wait and continue, never crash
            log.warning("transient error (%s): %s; retrying in 120 s", type(e).__name__, str(e)[:200])
            time.sleep(120)
            continue
        if status_only:
            return
    _finish()


def _cycle(inner, J, status_only) -> bool:
    """One poll/submit cycle. Returns True when every job is finished."""
    if True:
        st = load_state()
        J = expand(J, st)
        done = [j for j in J if st.get(j["key"], {}).get("status") == "done"]
        failed = [j for j in J if st.get(j["key"], {}).get("status") == "failed"]
        active = [j for j in J if st.get(j["key"], {}).get("status") == "submitted"]
        todo = [j for j in J if j["key"] not in st or st[j["key"]].get("status") in ("rejected_queue",)]
        log.info("progress: %d/%d done, %d active, %d waiting, %d failed", len(done), len(J), len(active), len(todo), len(failed))
        if not status_only and not st.get("_core_preprocessed") and core_done(J, st):
            st["_core_preprocessed"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            save_state(st)
            log.info("all ML-02 ERA5 variables downloaded: starting scripts/ml02/preprocess.py --source era5 (background)")
            with open(ROOT / "experiments" / "logs" / "ml02_era5_preprocess.out", "ab") as fo:
                subprocess.Popen([sys.executable, str(ROOT / "scripts" / "ml02" / "preprocess.py"), "--source", "era5",
                                  "--vars", *CORE_SINGLE, "z500", "t850"],
                                 stdout=fo, stderr=subprocess.STDOUT, cwd=str(ROOT))
        if status_only:
            print(json.dumps({"done": len(done), "total": len(J), "active": [j["key"] for j in active], "failed": [j["key"] for j in failed]}))
            return True
        if not active and not todo:
            return True
        for j in active:                                           # poll
            s = st[j["key"]]
            r = inner.get_remote(s["id"])
            stat = r.status
            if stat == "successful":
                j["out"].parent.mkdir(parents=True, exist_ok=True)
                part = j["out"].with_suffix(".nc.part")
                r.download(str(part))
                part.replace(j["out"])
                files = _unzip_if_needed(j["out"])
                try:
                    qa = validate(files)
                    daily = to_daily(j, files) if j["key"].startswith("6h_") else (split_monthly(files) if j.get("split_monthly") else [])
                    raw_info = [{"name": f.name, "bytes": f.stat().st_size, "md5": md5(f)} for f in files]
                    if j["key"].startswith("6h_") and daily:      # transient 6-hourly download: delete after validated daily conversion
                        for f in files:
                            f.unlink()
                    st[j["key"]] = {**s, "status": "done", "files": raw_info, "raw_deleted_after_daily": j["key"].startswith("6h_"),
                                    "bytes": sum(r["bytes"] for r in raw_info),
                                    "content_check": {k: v["status"] for k, v in qa.items()}, "daily_files": daily,
                                    "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
                    log.info("DONE %s (%.0f MB, %d daily files)", j["key"], st[j["key"]]["bytes"] / 1e6, len(daily))
                except ContentError as e:
                    log.warning("content check failed for %s: %s -> resubmit", j["key"], e)
                    for f in files:
                        f.rename(f.with_suffix(".rejected"))
                    st[j["key"]] = {"status": "rejected_queue", "attempts": s.get("attempts", 0) + 1}
            elif stat in ("failed", "rejected", "dismissed", "deleted"):
                msg = error_text(r)
                if "Maximum number queued requests" in msg or "queued" in msg.lower():
                    st[j["key"]] = {"status": "rejected_queue", "attempts": s.get("attempts", 0), "retry_after": time.time() + 900}
                    log.info("queue limit for %s; retry in 15 min", j["key"])
                else:
                    n = s.get("attempts", 0) + 1
                    st[j["key"]] = {"status": "failed" if n >= 3 else "rejected_queue", "attempts": n, "error": msg[:500]}
                    log.warning("job %s %s (attempt %d): %s", j["key"], stat, n, msg[:300])
            save_state(st)
        st = load_state()
        J = expand(J, st)
        active = [j for j in J if st.get(j["key"], {}).get("status") == "submitted"]
        todo = [j for j in J if j["key"] not in st or st[j["key"]].get("status") == "rejected_queue"]
        busy = {}
        for a in active:
            busy[a["dataset"]] = busy.get(a["dataset"], 0) + 1
        now = time.time()
        free = [j for j in todo if busy.get(j["dataset"], 0) < MAX_ACTIVE and st.get(j["key"], {}).get("retry_after", 0) <= now]
        if len(active) >= TOTAL_ACTIVE:                           # CDS accepted 3 queued jobs per user (observed 2026-11-15)
            free = []
        if free:                                                  # submit the next job on a dataset with queue room
            j = free[0]
            try:
                r = inner.submit(j["dataset"], j["request"])
            except Exception as e:  # noqa: BLE001
                resp = getattr(e, "response", None)
                if resp is not None and resp.status_code == 403 and "cost limits" in resp.text:
                    kids = split_job(j)
                    if not kids:
                        st[j["key"]] = {"status": "failed", "error": "too large and cannot be split further"}
                    else:
                        st[j["key"]] = {"status": "split", "children": [_ser(k) for k in kids], "reason": "CDS cost limit"}
                        log.info("split %s into %d jobs (CDS cost limit)", j["key"], len(kids))
                    save_state(st)
                    return False
                raise
            st[j["key"]] = {"id": r.request_id, "status": "submitted", "submitted_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                            "attempts": st.get(j["key"], {}).get("attempts", 0)}
            save_state(st)
            log.info("submitted %s", j["key"])
            time.sleep(20)
            return False
        time.sleep(60)
        return False


def _finish():
    st = load_state()
    J = expand(jobs(), st)
    done = [j for j in J if st.get(j["key"], {}).get("status") == "done"]
    failed = [j for j in J if st.get(j["key"], {}).get("status") == "failed"]
    log.info("all ERA5 jobs finished: %d done, %d failed", len(done), len(failed))
    if not failed:
        log.info("running documented ML-02 preprocessing: scripts/ml02/preprocess.py --source era5")
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "ml02" / "preprocess.py"), "--source", "era5"])
        log.info("ML-02 ERA5 preprocessing exit code %s", r.returncode)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    main(ap.parse_args().status)
