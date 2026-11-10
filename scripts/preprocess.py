"""Build the native-grid daily SIC cube + masks/areas/QA (data/interim/aethentra/).

    python scripts/preprocess.py [--force]
"""
import argparse
import json

import _bootstrap

log = _bootstrap.setup("preprocess")
from aethentra.preprocessing.cube import build_cube  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--force", action="store_true")
meta = build_cube(force=ap.parse_args().force)
print(json.dumps({k: meta[k] for k in ("start", "end", "shape", "days_present", "days_missing", "ocean_cells")}, indent=2))
