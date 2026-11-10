"""Make `src/` importable and configure logging for the CLI scripts."""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def setup(name: str):
    log_dir = ROOT / "experiments" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(log_dir / f"{name}.log", encoding="utf-8")])
    import warnings
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    return logging.getLogger(name)
