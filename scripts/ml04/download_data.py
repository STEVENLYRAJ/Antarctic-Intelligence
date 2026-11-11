"""ML-04 Phase 1: acquire the extra NCEP/NCAR R1 daily variables (public OPeNDAP, no credentials)."""
import argparse
import json

from _boot import setup

log = setup("download")
from aethentra.anomaly.acquisition import acquire  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--workers", type=int, default=4)
a = ap.parse_args()
res = acquire(a.workers)
failed = [r for r in res if r["status"] == "failed"]
log.info("done: %d files, %d failed", len(res), len(failed))
print(json.dumps({"files": len(res), "failed": [r["file"] for r in failed]}))
raise SystemExit(1 if failed else 0)
