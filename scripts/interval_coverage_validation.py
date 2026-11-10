"""Recompute q10/q90 interval coverage on ALL validation issue dates.  python scripts/interval_coverage_validation.py"""
import json

import _bootstrap

_bootstrap.setup("interval_coverage_validation")
from aethentra.config import load  # noqa: E402
from aethentra.features.build import feature_names  # noqa: E402
from aethentra.training import pipeline as P  # noqa: E402

tr0, tr1 = load("training")["splits"]["train"]
ctx = P.make_context(tr0, tr1)
print(json.dumps(P.interval_coverage(ctx, P.split_dates("validation"), feature_names(ctx.atmos is not None), "validation"), indent=2))
