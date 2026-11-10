"""ML-02 evaluation figures.   python scripts/ml02/make_figures.py"""
import _boot

log = _boot.setup("figures")
from aethentra.temperature.visualization.figures import make_all  # noqa: E402

print(make_all())
