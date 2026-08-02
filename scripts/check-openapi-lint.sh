#!/usr/bin/env bash
# Validate packages/contracts/openapi/openapi.yaml with openapi-spec-validator.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
exec "$PYTHON" - <<'PY'
from pathlib import Path

from openapi_spec_validator import validate
from openapi_spec_validator.readers import read_from_filename

path = Path("packages/contracts/openapi/openapi.yaml")
spec, _ = read_from_filename(str(path))
validate(spec)
print(f"openapi-spec-validator OK: {path}")
PY
