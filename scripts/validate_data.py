"""Validate the preprocessed SIC cube and atmospheric predictors.

    python scripts/validate_data.py
"""
import json

import _bootstrap

log = _bootstrap.setup("validate_data")
from aethentra.validation.validate import run  # noqa: E402

rep = run()
print(json.dumps({k: rep[k] for k in ("cube", "missing_day_ranges", "duplicate_days", "ocean_invalid_gt100_total",
                                      "days_with_ocean_missing_gt_1pct", "extent_jumps_gt_threshold")}, indent=2, default=str)[:4000])
