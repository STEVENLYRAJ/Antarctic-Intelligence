"""Shared bootstrap for ML-02 CLI scripts (reuses scripts/_bootstrap.py; logs to experiments/logs/ml02_<name>.log)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: E402


def setup(name: str):
    return _bootstrap.setup(f"ml02_{name}")
