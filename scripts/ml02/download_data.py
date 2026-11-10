"""ML-02 data acquisition (resumable; complete files are skipped).

    python scripts/ml02/download_data.py --stations          # Zenodo 17164992 + GHCN-Daily (anonymous)
    python scripts/ml02/download_data.py --era5 [--vars t2m msl ...] [--workers 4]   # needs %USERPROFILE%\.cdsapirc
    python scripts/ml02/download_data.py --ncep-interim      # NCEP/NCAR R1 2 m air temperature (interim, anonymous)
"""
import argparse
import collections

import _boot

log = _boot.setup("download")
from aethentra.temperature.data import acquisition as A  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--stations", action="store_true")
ap.add_argument("--era5", action="store_true")
ap.add_argument("--ncep-interim", action="store_true")
ap.add_argument("--vars", nargs="*")
ap.add_argument("--workers", type=int, default=4)
a = ap.parse_args()
if a.stations:
    for name, fn in (("zenodo", A.acquire_zenodo), ("ghcnd", A.acquire_ghcnd)):
        r = fn()
        log.info("%s: %s", name, dict(collections.Counter(x["status"] for x in r)))
if a.ncep_interim:
    r = A.acquire_ncep_interim(a.workers)
    log.info("ncep interim: %s", dict(collections.Counter(x["status"] for x in r)))
if a.era5:
    r = A.acquire_era5(a.vars, a.workers)
    log.info("era5: %s", dict(collections.Counter(x["status"] for x in r)))
    failed = [x["file"] for x in r if x["status"] == "failed"]
    if failed:
        log.warning("failed: %s", failed)
