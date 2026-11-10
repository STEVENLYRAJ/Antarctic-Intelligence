#!/usr/bin/env bash
# ML-02 end-to-end after preprocessing (fail-fast: the single test never runs after a failed stage).
#   bash scripts/ml02/run_all.sh [source]       source = ncep_r1 (interim) | era5
set -euo pipefail
cd "$(dirname "$0")/../.."
SRC="${1:-ncep_r1}"
run() { echo "== $*"; python "$@"; }
run scripts/ml02/train.py tables --source "$SRC"
run scripts/ml02/train.py candidates --source "$SRC"
run scripts/ml02/analyze.py features
run scripts/ml02/train.py tune --source "$SRC"
run scripts/ml02/train.py select
run scripts/ml02/train.py final --source "$SRC"
run scripts/ml02/train.py test --source "$SRC"
run scripts/ml02/analyze.py final
run scripts/ml02/analyze.py stations
run scripts/ml02/make_figures.py
run scripts/ml02/predict.py --layers
echo ML02_CHAIN_DONE
