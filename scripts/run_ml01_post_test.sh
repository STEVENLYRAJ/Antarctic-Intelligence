#!/usr/bin/env bash
# ML-01 stages after the single test (fail-fast).
set -euo pipefail
cd "$(dirname "$0")/.."
for stage in "analyze.py final" "make_figures.py" "predict.py"; do
  echo "== $stage"
  python scripts/$stage
done
echo CHAIN_DONE
