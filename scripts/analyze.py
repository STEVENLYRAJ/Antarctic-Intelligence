"""Feature analysis (validation), final-model interpretation + spatial plausibility checks (after the single test run).

    python scripts/analyze.py features      # validation-period feature analysis (candidate model)
    python scripts/analyze.py final         # TreeSHAP / sensitivity / PDP for the final model + spatial checks
"""
import json
import sys

import _bootstrap

what = sys.argv[1] if len(sys.argv) > 1 else "features"
_bootstrap.setup(f"analyze_{what}")
from aethentra.evaluation import analysis as A  # noqa: E402

if what == "features":
    r = A.feature_analysis()
    print(json.dumps({k: r[k] for k in ("high_collinearity_pairs_abs_spearman_ge_0.9", "shap_top10_by_season")}, indent=1)[:3000])
else:
    r = A.final_interpretation()
    s = A.spatial_checks()
    print(json.dumps({k: v for k, v in r.items() if k != "partial_dependence"}, indent=1)[:3000])
    print(json.dumps(s, indent=1))
