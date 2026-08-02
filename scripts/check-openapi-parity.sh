#!/usr/bin/env bash
# Fail if public /v1 path+method sets diverge between OpenAPI YAML and FastAPI API app.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
exec "$PYTHON" - <<'PY'
from __future__ import annotations

from omnimsg_api.main import app
from omnimsg_common.openapi_contract import load_openapi_contract, public_v1_operations

contract = load_openapi_contract()
yaml_ops = public_v1_operations(contract.document)

api_ops: set[tuple[str, str]] = set()
for route in app.routes:
    path = getattr(route, "path", None)
    methods = getattr(route, "methods", None)
    if not path or not methods:
        continue
    if not path.startswith("/v1"):
        continue
    for method in methods:
        if method in {"HEAD", "OPTIONS"}:
            continue
        api_ops.add((method.upper(), path))

only_yaml = sorted(yaml_ops - api_ops)
only_api = sorted(api_ops - yaml_ops)
if only_yaml or only_api:
    print("OpenAPI ↔ API path/method parity FAILED")
    if only_yaml:
        print("  in contract only:")
        for item in only_yaml:
            print(f"    {item[0]} {item[1]}")
    if only_api:
        print("  in API only:")
        for item in only_api:
            print(f"    {item[0]} {item[1]}")
    raise SystemExit(1)
print(f"openapi parity OK: {len(yaml_ops)} /v1 operations")
PY
