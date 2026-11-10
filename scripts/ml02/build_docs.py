"""Regenerate the artefact-driven ML-02 documents in docs/ml_task_02/.   python scripts/ml02/build_docs.py"""
import _boot

_boot.setup("build_docs")
from aethentra.temperature.reporting.docs import build_all  # noqa: E402

build_all()
print("ML-02 docs written")
