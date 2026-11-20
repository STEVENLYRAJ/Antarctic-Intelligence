"""Scan raw NetCDF files with the shared content check (all-zero / constant / implausible fields). Read-only.

    python scripts/check_raw_content.py                      # all NCEP R1 files of ML-01, ML-02 and ML-04
    python scripts/check_raw_content.py path/to/a.nc ...     # specific files
Exit code 1 if any file fails.
"""
import glob
import json
import sys

from _bootstrap import setup

log = setup("check_raw_content")
import xarray as xr  # noqa: E402

from aethentra.data.acquisition import ContentError, content_check  # noqa: E402

files = sys.argv[1:] or sorted(glob.glob("data/raw/aethentra/ncep_r1/*.nc") + glob.glob("data/raw/ncep_r1_2m/*.nc")
                               + glob.glob("data/raw/ml04/ncep_r1/*.nc"))
bad = []
for f in files:
    with xr.open_dataset(f) as d:
        v = list(d.data_vars)[0]
        try:
            content_check(d[v].values, v)
        except ContentError as e:
            bad.append({"file": f, "error": str(e)[:300]})
log.info("checked %d files, %d failed", len(files), len(bad))
print(json.dumps({"checked": len(files), "failed": bad}, indent=1))
sys.exit(1 if bad else 0)
