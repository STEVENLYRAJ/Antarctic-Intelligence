"""ML-02 U-Net addendum:  python scripts/ml02/train_cnn.py stacks|train|validate|decide|refit|test [--source ncep_r1|era5]"""
import argparse
import json

import _boot

ap = argparse.ArgumentParser()
ap.add_argument("stage", choices=["stacks", "train", "validate", "decide", "refit", "test"])
ap.add_argument("--source")
a = ap.parse_args()
log = _boot.setup(f"cnn_{a.stage}")
from aethentra.temperature.training import deep as D  # noqa: E402

if a.stage == "decide":
    print(json.dumps(D.decide(), indent=1, default=str))
else:
    fn = {"stacks": D.stage_stacks, "train": D.train, "validate": D.validate, "refit": D.refit, "test": D.test_once}[a.stage]
    r = fn(a.source)
    print(json.dumps({k: v for k, v in r.items() if k in ("best_epoch", "best_val_metric", "epochs_run", "seconds", "n_parameters", "n_issue_dates")}
                     if isinstance(r, dict) else r, default=str))
    print("done", a.stage)
