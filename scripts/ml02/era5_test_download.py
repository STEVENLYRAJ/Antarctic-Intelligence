"""Small ERA5 access test before any bulk download (no credentials in code: cdsapi.Client() reads %USERPROFILE%\\.cdsapirc).

    python scripts/ml02/era5_test_download.py                         # 2 m temperature daily mean, 2026-11-01..03, 55-90 S
    python scripts/ml02/era5_test_download.py --start 2026-03-15 --days 3

Uses the dataset and area documented in configs/ml02/data_sources.yaml (era5). Writes to data/raw/era5/_test/ (git-ignored).
Reports authentication / licence errors verbatim; never prints or logs the API key.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from aethentra.config import load  # noqa: E402
from aethentra.data.acquisition import content_check  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--start", default="2026-11-01")
ap.add_argument("--days", type=int, default=3)
ap.add_argument("--variable", default="t2m")
a = ap.parse_args()

cfg = load("ml02/data_sources")["era5"]
days = pd.date_range(a.start, periods=a.days, freq="D")
if days.month.nunique() != 1:
    raise SystemExit("keep the test inside one calendar month")
req = {"product_type": "reanalysis", "variable": [cfg["single_levels"][a.variable]["cds"]], "year": str(days[0].year),
       "month": [f"{days[0].month:02d}"], "day": [f"{d.day:02d}" for d in days], "daily_statistic": cfg["daily_statistic"],
       "time_zone": cfg["time_zone"], "frequency": cfg["frequency"], "area": cfg["area"]}
out = ROOT / cfg["local_dir"] / "_test"
out.mkdir(parents=True, exist_ok=True)
dst = out / f"era5_test_{a.variable}_{days[0]:%Y%m%d}_{a.days}d.nc"

import cdsapi  # noqa: E402

report = {"dataset": cfg["dataset_single"], "request": req}
try:
    c = cdsapi.Client(quiet=True, progress=False)          # configuration from ~/.cdsapirc (never printed)
    report["client"] = {"class": type(c).__name__, "url": c.url}
except Exception as e:  # noqa: BLE001
    print(json.dumps({"stage": "client_init", "error_type": type(e).__name__, "error": str(e)}, indent=1))
    raise SystemExit(2)

t0 = time.time()
try:
    tmp = dst.with_suffix(".part")
    c.retrieve(cfg["dataset_single"], req).download(str(tmp))
except Exception as e:  # noqa: BLE001
    print(json.dumps({**report, "stage": "retrieve", "error_type": type(e).__name__, "error": str(e)}, indent=1))
    raise SystemExit(3)

from aethentra.temperature.data.acquisition import _unpack  # noqa: E402  (zip or bare NetCDF)

_unpack(tmp, dst)
import xarray as xr  # noqa: E402

with xr.open_dataset(dst) as ds:
    var = list(ds.data_vars)[0]
    tname = "valid_time" if "valid_time" in ds.coords else "time"
    t = pd.DatetimeIndex(ds[tname].values)
    report |= {"stage": "ok", "seconds": round(time.time() - t0, 1), "file": str(dst.relative_to(ROOT)), "bytes": dst.stat().st_size,
               "variables": {v: {"dims": list(ds[v].dims), "shape": list(ds[v].shape), "units": ds[v].attrs.get("units"),
                                 "long_name": ds[v].attrs.get("long_name")} for v in ds.data_vars},
               "coordinates": {k: {"size": int(ds[k].size), "min": str(ds[k].values.min()), "max": str(ds[k].values.max())}
                               for k in ds.coords if ds[k].ndim == 1},
               "time_coverage": [str(t.min().date()), str(t.max().date()), int(t.size)],
               "content_check": content_check(ds[var].values, var),
               "value_range_K": [float(ds[var].min()), float(ds[var].max())]}
(out / "era5_test_report.json").write_text(json.dumps(report, indent=1, default=str))
print(json.dumps(report, indent=1, default=str))
