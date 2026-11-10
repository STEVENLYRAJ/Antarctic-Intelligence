"""Generate the weekly SIC forecast (default: from the latest available observation day).

    python scripts/predict.py [--issue-date YYYY-MM-DD]
"""
import _bootstrap

_bootstrap.setup("predict")
from aethentra.inference.predict import main  # noqa: E402

main()
