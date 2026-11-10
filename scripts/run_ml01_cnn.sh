#!/usr/bin/env bash
# ML-01 U-Net addendum (fail-fast; the CNN test runs once, after the validation-only decision record is frozen).
set -euo pipefail
cd "$(dirname "$0")/.."
for s in stacks train validate decide refit test; do echo "== train_cnn.py $s"; python scripts/train_cnn.py "$s"; done
echo ML01_CNN_DONE
