#!/usr/bin/env bash
# ML-03 after the scene catalogue: download scenes, then the full fail-fast training/evaluation chain.
set -euo pipefail
cd "$(dirname "$0")/../.."
echo "== download scenes"
python scripts/ml03/download_data.py --scenes --workers 12
bash scripts/ml03/run_all.sh
