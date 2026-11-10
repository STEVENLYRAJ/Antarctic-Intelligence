"""ML-02 stages:  python scripts/ml02/train.py tables|candidates|tune|select|final|test [--source ncep_r1|era5]"""
import argparse
import json

import _boot

ap = argparse.ArgumentParser()
ap.add_argument("stage", choices=["tables", "candidates", "tune", "select", "final", "test"])
ap.add_argument("--source")
a = ap.parse_args()
log = _boot.setup(f"train_{a.stage}")
from aethentra.temperature.training import pipeline as P  # noqa: E402

if a.stage == "select":
    print(json.dumps(P.select(), indent=1, default=str)[:3000])
else:
    fn = {"tables": P.stage_tables, "candidates": P.train_candidates, "tune": P.tune, "final": P.final_refit, "test": P.test_once}[a.stage]
    fn(a.source)
    print("done", a.stage)
