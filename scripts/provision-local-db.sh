#!/usr/bin/env bash
# Create Postgres database + role `omnimsgio` on the shared postgis container.
# Does not alter other databases. Requires container `postgis` to be healthy.
#
# Usage (from repo root):
#   cp .env.example .env   # set DATABASE_URL password
#   ./scripts/provision-local-db.sh
#
# Env:
#   POSTGIS_CONTAINER  (default: postgis)
#   OMNIMSGIO_DB       (default: omnimsgio)
#   OMNIMSGIO_USER     (default: omnimsgio)
#   OMNIMSGIO_PASSWORD (required unless parsed from DATABASE_URL / .env)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POSTGIS_CONTAINER="${POSTGIS_CONTAINER:-postgis}"
OMNIMSGIO_DB="${OMNIMSGIO_DB:-omnimsgio}"
OMNIMSGIO_USER="${OMNIMSGIO_USER:-omnimsgio}"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

if [[ -z "${OMNIMSGIO_PASSWORD:-}" && -n "${DATABASE_URL:-}" ]]; then
  OMNIMSGIO_PASSWORD="$(
    python3 -c 'import sys; from urllib.parse import urlparse, unquote; print(unquote(urlparse(sys.argv[1]).password or ""))' \
      "${DATABASE_URL}"
  )"
fi

if [[ -z "${OMNIMSGIO_PASSWORD:-}" ]]; then
  echo "error: set OMNIMSGIO_PASSWORD or DATABASE_URL (with password) in .env" >&2
  exit 1
fi

if ! docker inspect -f '{{.State.Running}}' "${POSTGIS_CONTAINER}" 2>/dev/null | grep -qx true; then
  echo "error: container '${POSTGIS_CONTAINER}' is not running" >&2
  echo "Bring up shared data stack first (see /opt/stacks/data/AGENTS.md)." >&2
  exit 1
fi

POSTGRES_USER="$(
  docker exec "${POSTGIS_CONTAINER}" printenv POSTGRES_USER 2>/dev/null || echo postgres
)"

echo "Provisioning role/database '${OMNIMSGIO_DB}' on ${POSTGIS_CONTAINER}..."

SQL="$(
  OMNIMSGIO_DB="${OMNIMSGIO_DB}" OMNIMSGIO_USER="${OMNIMSGIO_USER}" OMNIMSGIO_PASSWORD="${OMNIMSGIO_PASSWORD}" \
    python3 - <<'PY'
import os

db = os.environ["OMNIMSGIO_DB"]
user = os.environ["OMNIMSGIO_USER"]
password = os.environ["OMNIMSGIO_PASSWORD"]


def quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


role = quote_ident(user)
database = quote_ident(db)
pwd = quote_literal(password)
user_lit = quote_literal(user)
db_lit = quote_literal(db)

print(f"""
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = {user_lit}) THEN
    CREATE ROLE {role} LOGIN PASSWORD {pwd};
  ELSE
    ALTER ROLE {role} WITH LOGIN PASSWORD {pwd};
  END IF;
END
$$;

SELECT 'CREATE DATABASE {database} OWNER {role}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = {db_lit})\\gexec
""")
PY
)"

docker exec -i "${POSTGIS_CONTAINER}" \
  psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d postgres <<<"${SQL}"

GRANT_SQL="$(
  OMNIMSGIO_DB="${OMNIMSGIO_DB}" OMNIMSGIO_USER="${OMNIMSGIO_USER}" \
    python3 - <<'PY'
import os

db = os.environ["OMNIMSGIO_DB"]
user = os.environ["OMNIMSGIO_USER"]


def quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


role = quote_ident(user)
database = quote_ident(db)
print(f"""
GRANT CONNECT, TEMPORARY ON DATABASE {database} TO {role};
GRANT ALL ON SCHEMA public TO {role};
ALTER SCHEMA public OWNER TO {role};
ALTER DATABASE {database} OWNER TO {role};
""")
PY
)"

docker exec -i "${POSTGIS_CONTAINER}" \
  psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${OMNIMSGIO_DB}" <<<"${GRANT_SQL}"

echo "Verifying connectivity as ${OMNIMSGIO_USER}..."
docker exec -i \
  -e PGPASSWORD="${OMNIMSGIO_PASSWORD}" \
  "${POSTGIS_CONTAINER}" \
  psql -v ON_ERROR_STOP=1 -U "${OMNIMSGIO_USER}" -d "${OMNIMSGIO_DB}" \
  -c "SELECT current_database() AS db, current_user AS role;"

echo "Done. Grants are limited to database '${OMNIMSGIO_DB}'."
