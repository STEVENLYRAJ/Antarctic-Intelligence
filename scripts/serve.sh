#!/usr/bin/env bash
# Local service: API + viewer at http://127.0.0.1:${AETHENTRA_API_PORT:-8000}/  (loopback only; not a production deployment)
set -euo pipefail
cd "$(dirname "$0")/.."
exec python -m uvicorn api.main:app --host 127.0.0.1 --port "${AETHENTRA_API_PORT:-8000}"
