"""Build the ML-02 daily cube on the 25 km grid.   python scripts/ml02/preprocess.py [--source era5|ncep_r1] [--vars t2m msl]"""
import argparse

import _boot

log = _boot.setup("preprocess")
from aethentra.temperature.preprocessing.cube import build_cube  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--source")
ap.add_argument("--vars", nargs="*")
a = ap.parse_args()
print("cube:", build_cube(a.source, a.vars))
