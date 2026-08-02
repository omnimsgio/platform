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
#   META_WABA_ID / META_PHONE_NUMBER_ID / META_BUSINESS_ACCESS_TOKEN
#                         (optional; when all set, upsert tenant_whatsapp_accounts)

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
META_WABA_ID="${META_WABA_ID:-}" \
META_PHONE_NUMBER_ID="${META_PHONE_NUMBER_ID:-}" \
META_BUSINESS_ACCESS_TOKEN="${META_BUSINESS_ACCESS_TOKEN:-}" \
python3 - <<'PY'
from __future__ import annotations

import os
import sys

from omnimsg_common.auth import generate_api_key, hash_api_key, key_display_prefix
from omnimsg_common.db.models import ApiKey, Tenant, TenantWhatsappAccount
from omnimsg_common.db.session import session_scope
from omnimsg_common.ids import new_id
from omnimsg_common.whatsapp_lifecycle import READY, bootstrap_ready
from sqlalchemy import select

tenant_id = os.environ["SEED_TENANT_ID"]
tenant_name = os.environ["SEED_TENANT_NAME"]
raw_key = os.environ.get("SEED_API_KEY") or generate_api_key()
key_hash = hash_api_key(raw_key)
prefix = key_display_prefix(raw_key)

meta_waba_id = (os.environ.get("META_WABA_ID") or "").strip()
meta_phone_number_id = (os.environ.get("META_PHONE_NUMBER_ID") or "").strip()
meta_business_access_token = (
    os.environ.get("META_BUSINESS_ACCESS_TOKEN") or ""
).strip()
seed_whatsapp = bool(
    meta_waba_id and meta_phone_number_id and meta_business_access_token
)

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

    if seed_whatsapp:
        account = session.scalars(
            select(TenantWhatsappAccount).where(
                TenantWhatsappAccount.phone_number_id == meta_phone_number_id
            )
        ).first()
        if account is None:
            account = session.scalars(
                select(TenantWhatsappAccount).where(
                    TenantWhatsappAccount.tenant_id == tenant_id
                )
            ).first()
        if account is None:
            account = TenantWhatsappAccount(
                id=new_id("twa"),
                tenant_id=tenant_id,
                waba_id=meta_waba_id,
                phone_number_id=meta_phone_number_id,
                business_access_token=meta_business_access_token,
                credit_line_attached=False,
                status=READY,
                lifecycle_version=1,
            )
            session.add(account)
            bootstrap_ready(account, correlation_id="req_seed_local")
        else:
            account.tenant_id = tenant_id
            account.waba_id = meta_waba_id
            account.phone_number_id = meta_phone_number_id
            account.business_access_token = meta_business_access_token
            bootstrap_ready(account, correlation_id="req_seed_local")

print(raw_key)
print(
    f"Seeded tenant={tenant_id} key_prefix={prefix} "
    "(plaintext key printed above; store it securely)",
    file=sys.stderr,
)
if seed_whatsapp:
    print(
        f"Seeded WhatsApp account phone_number_id={meta_phone_number_id} "
        f"waba_id={meta_waba_id}",
        file=sys.stderr,
    )
else:
    print(
        "WhatsApp account not seeded "
        "(set META_WABA_ID, META_PHONE_NUMBER_ID, META_BUSINESS_ACCESS_TOKEN)",
        file=sys.stderr,
    )
PY
