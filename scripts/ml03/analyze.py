"""ML-03 post-test:  python scripts/ml03/analyze.py [--skip-analysis]   (error analysis -> figures -> documents)"""
import argparse
import json

import _boot

ap = argparse.ArgumentParser()
ap.add_argument("--skip-analysis", action="store_true")
a = ap.parse_args()
log = _boot.setup("analyze")
from aethentra.sar import analysis, figures, reporting  # noqa: E402

if not a.skip_analysis:
    r = analysis.error_analysis()
    print(json.dumps({k: v for k, v in r.items() if k in ("pixels", "overall_error_rate", "dmi_asip_comparison")}, indent=1, default=str))
print(figures.make_all())
reporting.build_all()
print("docs written")
