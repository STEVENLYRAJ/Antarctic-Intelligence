"""ML-02 weekly forecast.   python scripts/ml02/predict.py [--issue-date YYYY-MM-DD] [--layers]"""
import argparse

import _boot

log = _boot.setup("predict")
from aethentra.temperature.inference.predict import run_forecast  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--issue-date")
ap.add_argument("--layers", action="store_true", help="also export frontend layers")
a = ap.parse_args()
s, _ = run_forecast(a.issue_date, write=True, layers=a.layers)
print(s.model_dump_json(indent=1)[:3500])
