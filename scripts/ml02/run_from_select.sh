#!/usr/bin/env bash
# Resume the ML-02 chain at the selection stage (fail-fast).
set -euo pipefail
cd "$(dirname "$0")/../.."
SRC="${1:-ncep_r1}"
run() { echo "== $*"; python "$@"; }
run scripts/ml02/train.py select
run scripts/ml02/train.py final --source "$SRC"
run scripts/ml02/train.py test --source "$SRC"
run scripts/ml02/analyze.py final
run scripts/ml02/analyze.py stations
run scripts/ml02/make_figures.py
run scripts/ml02/predict.py --layers
echo ML02_CHAIN_DONE
