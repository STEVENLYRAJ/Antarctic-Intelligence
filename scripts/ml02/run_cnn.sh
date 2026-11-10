#!/usr/bin/env bash
# ML-02 U-Net addendum (fail-fast; the CNN test runs once, after the validation-only decision record is frozen).
#   bash scripts/ml02/run_cnn.sh [source]
set -euo pipefail
cd "$(dirname "$0")/../.."
SRC="${1:-ncep_r1}"
run() { echo "== $*"; python "$@"; }
for s in stacks train validate decide refit test; do run scripts/ml02/train_cnn.py "$s" --source "$SRC"; done
echo ML02_CNN_DONE
