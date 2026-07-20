#!/usr/bin/env bash
# Apply migrations and seed a local tenant + API key.
# The plaintext API key is printed once to stdout and never stored.
#
# Usage (from repo root):
#   ./scripts/seed-local-tenant.sh
#
# Env:
#   DATABASE_URL          (required; or loaded from .env)
#   SEED_TENANT_ID        (default: ten_local_dev)
#   SEED_TENANT_NAME      (default: Local Dev)
#   SEED_API_KEY          (optional; generated if unset)
#   DEFAULT_TENANT_ID     (alias for SEED_TENANT_ID)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "error: set DATABASE_URL in the environment or .env" >&2
  exit 1
fi

SEED_TENANT_ID="${SEED_TENANT_ID:-${DEFAULT_TENANT_ID:-ten_local_dev}}"
SEED_TENANT_NAME="${SEED_TENANT_NAME:-Local Dev}"

echo "Running migrations..."
omnimsg-migrate upgrade head

echo "Seeding tenant '${SEED_TENANT_ID}'..."
SEED_TENANT_ID="${SEED_TENANT_ID}" \
SEED_TENANT_NAME="${SEED_TENANT_NAME}" \
SEED_API_KEY="${SEED_API_KEY:-}" \
python3 - <<'PY'
from __future__ import annotations

import os
import sys

from omnimsg_common.auth import generate_api_key, hash_api_key, key_display_prefix
from omnimsg_common.db.models import ApiKey, Tenant
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from sqlalchemy import select

tenant_id = os.environ["SEED_TENANT_ID"]
tenant_name = os.environ["SEED_TENANT_NAME"]
raw_key = os.environ.get("SEED_API_KEY") or generate_api_key()
key_hash = hash_api_key(raw_key)
prefix = key_display_prefix(raw_key)

with session_scope() as session:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        session.add(
            Tenant(id=tenant_id, name=tenant_name, status="active"),
        )
    else:
        tenant.name = tenant_name
        tenant.status = "active"

    existing = session.scalars(
        select(ApiKey).where(ApiKey.key_hash == key_hash)
    ).first()
    if existing is None:
        for key in session.scalars(
            select(ApiKey).where(
                ApiKey.tenant_id == tenant_id,
                ApiKey.status == "active",
            )
        ).all():
            key.status = "revoked"
        session.add(
            ApiKey(
                id=new_id("key"),
                tenant_id=tenant_id,
                key_prefix=prefix,
                key_hash=key_hash,
                status="active",
            )
        )

print(raw_key)
print(
    f"Seeded tenant={tenant_id} key_prefix={prefix} "
    "(plaintext key printed above; store it securely)",
    file=sys.stderr,
)
PY
