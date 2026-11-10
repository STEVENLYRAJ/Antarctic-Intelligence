#!/usr/bin/env bash
# Remaining ML-01 stages after `train.py candidates`. Fails fast: any stage error stops the chain (test never runs after a failure).
set -euo pipefail
cd "$(dirname "$0")/.."
for stage in "train.py tune" "train.py select" "train.py final" "train.py test" "analyze.py final" "make_figures.py" "predict.py"; do
  echo "== $stage"
  python scripts/$stage
done
echo CHAIN_DONE
