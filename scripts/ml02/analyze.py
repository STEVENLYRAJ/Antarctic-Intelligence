"""ML-02 analysis.  python scripts/ml02/analyze.py features | final | stations"""
import json
import sys

import _boot

stage = sys.argv[1]
log = _boot.setup(f"analyze_{stage}")
from aethentra.temperature.evaluation import analysis as A  # noqa: E402

if stage == "features":
    r = A.feature_analysis()
elif stage == "final":
    r = A.final_interpretation()
    r["spatial_smoothness"] = A.spatial_smoothness()
elif stage == "stations":
    from aethentra.temperature.evaluation.stations import evaluate_stations  # noqa: E402
    from aethentra.temperature.training.pipeline import make_context  # noqa: E402
    r = evaluate_stations(make_context())
    r = {k: v for k, v in r.items() if k != "stations"}
print(json.dumps(r, indent=1, default=str)[:3000])
