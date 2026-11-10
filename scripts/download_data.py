"""Download and verify AETHENTRA Task 01 datasets (resumable; safe to rerun).

    python scripts/download_data.py --cdr          # NSIDC G02202 v6 SH aggregates (~3.3 GB)
    python scripts/download_data.py --ncep         # NCEP/NCAR R1 daily (OPeNDAP subset, ~0.1 GB)
    python scripts/download_data.py --all
"""
import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aethentra.config import EXPERIMENTS_DIR  # noqa: E402
from aethentra.data import acquisition  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdr", action="store_true")
    ap.add_argument("--ncep", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = {}
    if a.cdr or a.all:
        out["cdr"] = acquisition.acquire_cdr(a.workers)
    if a.ncep or a.all:
        out["ncep"] = acquisition.acquire_ncep(a.workers)
    log = EXPERIMENTS_DIR / "logs" / "download_results.json"
    log.parent.mkdir(parents=True, exist_ok=True)
    prev = json.loads(log.read_text()) if log.exists() else {}
    prev.update(out)
    log.write_text(json.dumps(prev, indent=2))
    for k, v in out.items():
        bad = [r for r in v if r["status"] not in ("downloaded", "already_verified", "already_present")]
        print(f"{k}: {len(v)} files, {len(bad)} problems {bad[:5]}")


if __name__ == "__main__":
    main()
