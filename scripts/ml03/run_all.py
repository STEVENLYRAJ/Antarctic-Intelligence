"""ML-03 chain after acquisition, fail-fast (the single test never runs after a failed stage).
    python scripts/ml03/run_all.py [--from STAGE]
Python driver, launched detached so the chain survives editor sessions."""
import argparse
import subprocess
import sys
from pathlib import Path

STAGES = ["prepare", "samples", "baselines", "tiles", "unet", "validate", "select", "final", "test"]
ap = argparse.ArgumentParser()
ap.add_argument("--from", dest="start", default=STAGES[0], choices=STAGES)
a = ap.parse_args()
root = Path(__file__).resolve().parents[2]
for s in STAGES[STAGES.index(a.start):]:
    print(f"== train.py {s}", flush=True)
    subprocess.run([sys.executable, str(root / "scripts" / "ml03" / "train.py"), s], cwd=root, check=True)
print("== analyze.py", flush=True)
subprocess.run([sys.executable, str(root / "scripts" / "ml03" / "analyze.py")], cwd=root, check=True)
print("ML03_CHAIN_DONE", flush=True)
