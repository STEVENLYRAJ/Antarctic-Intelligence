"""Training pipeline stages (run in order; each stage is cached / idempotent).

    python scripts/train.py tables       # build train/validation tables (train-only climatology)
    python scripts/train.py candidates   # baselines + LightGBM/XGBoost/RF + ablations, validation evaluation
    python scripts/train.py tune         # Optuna (validation only)
    python scripts/train.py select       # freeze final configuration BEFORE test
    python scripts/train.py final        # refit on 1979-2020
    python scripts/train.py test         # single evaluation on 2021-2025 (refuses to rerun)
"""
import json
import sys

import _bootstrap

stage = sys.argv[1]
log = _bootstrap.setup(f"train_{stage}")
from aethentra.training import pipeline as P  # noqa: E402

fn = {"tables": P.stage_tables, "candidates": P.train_candidates, "tune": P.tune, "select": P.select,
      "final": P.final_refit, "test": P.test_once}[stage]
res = fn()
if stage == "tables":
    print("rows:", len(res[0]), len(res[1]), "features:", len(res[2]))
elif stage in ("select", "final"):
    print(json.dumps(res, indent=2, default=str)[:3000])
else:
    print("done", stage)
