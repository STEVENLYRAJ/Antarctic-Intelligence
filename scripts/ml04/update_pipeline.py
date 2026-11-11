"""ML-04 Phase 16: periodic update / backfill (run manually or from a scheduler; no scheduler is registered by this repo).

    python scripts/ml04/update_pipeline.py --check      # report whether new source data exist (no changes)
    python scripts/ml04/update_pipeline.py              # refresh the current-year downloads, then recompute products
    python scripts/ml04/update_pipeline.py --backfill   # rebuild every derived product from the raw files

Frozen parts are never refitted by an update: climatologies (fixed baselines), detectors, thresholds, the validation decision
and the single test evaluation. A new model or dataset version = a new decision + version string (documented in the model card).
Source update frequencies (verified 2026-11-11): NSIDC G02202 v6 daily file for the current year is updated about monthly;
NCEP/NCAR R1 at NOAA PSL ends 2026-03-17 (no further updates observed).
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

from _boot import setup

log = setup("update")
HERE = Path(__file__).resolve().parent


def remote_last_ncep() -> str | None:
    import netCDF4
    y = dt.date.today().year
    try:
        with netCDF4.Dataset(f"https://psl.noaa.gov/thredds/dodsC/Datasets/ncep.reanalysis/Dailies/surface/air.sig995.{y}.nc") as d:
            return str(netCDF4.num2date(d["time"][-1], d["time"].units).date())
    except Exception as e:  # noqa: BLE001
        log.warning("NCEP check failed: %s", e)
        return None


def local_state() -> dict:
    from aethentra.anomaly.paths import PROCESSED
    q = json.loads((PROCESSED / "quality_report.json").read_text())
    return {"ncep_last": q["variables"]["t2m"]["last"], "sic_last": q["variables"]["sic"]["last"]}


def run(*args):
    r = subprocess.run([sys.executable, str(HERE / "run_all.py"), *args])
    if r.returncode:
        raise SystemExit(r.returncode)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    a = ap.parse_args()
    loc, rem = local_state(), remote_last_ncep()
    status = {"local": loc, "remote_ncep_last": rem, "new_ncep": bool(rem and rem > loc["ncep_last"])}
    log.info("status: %s", status)
    if a.check:
        print(json.dumps(status))
        raise SystemExit(0)
    # SIC: the shared ML-01 cube is refreshed by the ML-01 pipeline (scripts/download_data.py + preprocessing)
    run("--only", "download")
    run("--only", "preprocess", "--force")
    for s in (["climatology", "features"] if a.backfill else ["features"]):
        run("--only", s)
    for s in ("score", "products", "export", "store"):
        run("--only", s)
    log.info("update complete")
