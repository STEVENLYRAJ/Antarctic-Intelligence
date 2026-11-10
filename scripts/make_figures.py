"""Regenerate evaluation figures from saved metrics.  python scripts/make_figures.py"""
import _bootstrap

_bootstrap.setup("make_figures")
from aethentra.visualization.figures import make_all  # noqa: E402

for m in make_all():
    print(m["file"])
