"""ML-01 U-Net addendum:  python scripts/train_cnn.py stacks|train|validate|decide|refit|test"""
import argparse
import json

import _bootstrap

ap = argparse.ArgumentParser()
ap.add_argument("stage", choices=["stacks", "train", "validate", "decide", "refit", "test"])
a = ap.parse_args()
log = _bootstrap.setup(f"cnn_{a.stage}")
from aethentra.training import deep as D  # noqa: E402

r = {"stacks": D.stage_stacks, "train": D.train, "validate": D.validate, "decide": D.decide, "refit": D.refit, "test": D.test_once}[a.stage]()
keys = ("best_epoch", "best_val_metric", "epochs_run", "seconds", "n_parameters", "n_issue_dates", "cnn_better_on", "cnn_replaces_operational_model")
print(json.dumps({k: v for k, v in r.items() if k in keys} if a.stage != "stacks" else r, default=str))
print("done", a.stage)
