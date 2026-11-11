#!/usr/bin/env bash
# ML-03 end-to-end after acquisition (fail-fast: the single test never runs after a failed stage).
set -euo pipefail
cd "$(dirname "$0")/../.."
run() { echo "== $*"; python "$@"; }
for s in prepare samples baselines tiles unet validate select final test; do run scripts/ml03/train.py "$s"; done
echo ML03_CHAIN_DONE
