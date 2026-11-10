"""Re-export frontend layers for an existing ML-02 forecast (or create one).   python scripts/ml02/export_forecast.py --issue-date YYYY-MM-DD"""
import argparse

import _boot

log = _boot.setup("export_forecast")
from aethentra.temperature.inference.layers import export_layers  # noqa: E402
from aethentra.temperature.inference.predict import load_bundle, run_forecast  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--issue-date")
a = ap.parse_args()
b = load_bundle()
s, fields = run_forecast(a.issue_date, bundle=b, write=True)
man = export_layers(s, fields, b.ctx)
print(s.forecast_id, "->", len(man["layers"]), "layers")
