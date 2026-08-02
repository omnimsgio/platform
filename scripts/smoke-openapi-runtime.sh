#!/usr/bin/env bash
# Runtime smoke: boot gateway via uvicorn, curl discovery/docs/openapi.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT="${OPENAPI_SMOKE_PORT:-18080}"
export OPENAPI_CONTRACT_PATH="${OPENAPI_CONTRACT_PATH:-$ROOT/packages/contracts/openapi/openapi.yaml}"
export APP_ENV="${APP_ENV:-development}"
PYTHON="${PYTHON:-python3}"

"$PYTHON" -m uvicorn omnimsg_gateway.main:app --host 127.0.0.1 --port "$PORT" &
PID=$!
cleanup() { kill "$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true; }
trap cleanup EXIT

for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null; then
    break
  fi
  sleep 0.25
done

curl -sf "http://127.0.0.1:${PORT}/" | grep -q '"status":"ok"'
curl -sf "http://127.0.0.1:${PORT}/version" | grep -q '"contract_version"'
curl -sf -D /tmp/omnimsg-openapi-headers.txt -o /tmp/omnimsg-openapi.json \
  "http://127.0.0.1:${PORT}/openapi.json"
grep -qi '^etag:' /tmp/omnimsg-openapi-headers.txt
grep -qi 'cache-control:.*max-age=300' /tmp/omnimsg-openapi-headers.txt
"$PYTHON" -c "import json; d=json.load(open('/tmp/omnimsg-openapi.json')); assert 'paths' in d"
curl -sf "http://127.0.0.1:${PORT}/docs" | grep -qi 'swagger'
curl -sf "http://127.0.0.1:${PORT}/redoc" | grep -qi 'redoc'
echo "openapi runtime smoke OK (port ${PORT})"
