#!/usr/bin/env bash
# Boutique Microservices - Safe Local PostgreSQL Database Restoration Script
# Restores verified PostgreSQL backup into a clean local container environment.
# Safe & Idempotent:
#   - Exits 0 safely if all 4 databases are already restored and populated.
#   - Restores only into a genuinely clean database instance.
#   - Aborts with non-zero exit code if database state is inconsistent or partial.
#   - Unsafe --force overwrite mechanism has been removed.

set -euo pipefail

BACKUP_DIR="${HOME}/.aws_project_backups"
SQL_BACKUP="${BACKUP_DIR}/postgres_dumpall_20261102_024638.sql"
ENC_BACKUP="${BACKUP_DIR}/all_backups_encrypted.tar.gz.enc"
KEY_FILE="${BACKUP_DIR}/backup_key.txt"
CONTAINER_NAME="${CONTAINER_NAME:-boutique-postgres}"
DB_USER="${POSTGRES_USER:-postgres}"

TEMP_DECRYPTED=""
RESTORE_LOG=""

# Clean temporary files on every exit path
cleanup() {
  local exit_code=$?
  if [ -n "${TEMP_DECRYPTED:-}" ] && [ -f "${TEMP_DECRYPTED}" ]; then
    rm -f "${TEMP_DECRYPTED}"
  fi
  if [ -n "${RESTORE_LOG:-}" ] && [ -f "${RESTORE_LOG}" ]; then
    rm -f "${RESTORE_LOG}"
  fi
  exit "${exit_code}"
}
trap cleanup EXIT INT TERM

# Parse command line flags
for arg in "$@"; do
  case "$arg" in
    --help|-h)
      echo "Usage: $0"
      echo "  Restores verified database backup into a clean local PostgreSQL container."
      echo "  - Safely exits (code 0) if all four databases are already populated."
      echo "  - Aborts (code 1) if database state is inconsistent or partially populated."
      exit 0
      ;;
    --force)
      echo "Error: The unsafe --force overwrite mechanism has been removed." >&2
      echo "Database restoration is only permitted on a genuinely clean database instance." >&2
      exit 1
      ;;
    *)
      echo "Error: Unrecognized option: $arg" >&2
      echo "Run with --help for usage." >&2
      exit 1
      ;;
  esac
done

echo "=== Boutique Microservices - Local Database Restore ==="

# 1. Verify container is running and healthy
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "Error: Container '${CONTAINER_NAME}' is not running." >&2
  echo "Start the database container first with: docker compose -f application/docker-compose.yml up -d postgres" >&2
  exit 1
fi

echo "[1/4] Checking container '${CONTAINER_NAME}' health..."
if ! docker exec "${CONTAINER_NAME}" pg_isready -U "${DB_USER}" >/dev/null 2>&1; then
  echo "Error: PostgreSQL service in container '${CONTAINER_NAME}' is not accepting connections." >&2
  exit 1
fi
echo "      PostgreSQL service is healthy and accepting connections."

# 2. Inspect all four databases reliably
echo "[2/4] Inspecting database state across all 4 application databases..."

POPULATED_COUNT=0
CLEAN_COUNT=0
STATUS_SUMMARY=""
DETAILS_SUMMARY=""

for db_name in auth_db products_db orders_db users_db; do
  case "${db_name}" in
    auth_db)     table_name="users" ;;
    products_db) table_name="products" ;;
    orders_db)   table_name="orders" ;;
    users_db)    table_name="users" ;;
  esac

  # Check if database exists in PostgreSQL
  set +e
  db_exists=$(docker exec "${CONTAINER_NAME}" psql -v ON_ERROR_STOP=1 -U "${DB_USER}" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${db_name}';" 2>&1)
  query_status=$?
  set -e

  if [ $query_status -ne 0 ]; then
    echo "Error: Failed to query pg_database for '${db_name}':" >&2
    echo "${db_exists}" >&2
    exit 1
  fi

  if [ "${db_exists}" != "1" ]; then
    # Database does not exist -> Clean
    CLEAN_COUNT=$((CLEAN_COUNT + 1))
    STATUS_SUMMARY="${STATUS_SUMMARY} ${db_name}=MISSING"
    continue
  fi

  # Database exists, check if target table exists
  set +e
  tbl_exists=$(docker exec "${CONTAINER_NAME}" psql -v ON_ERROR_STOP=1 -U "${DB_USER}" -d "${db_name}" -tAc "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='${table_name}';" 2>&1)
  query_status=$?
  set -e

  if [ $query_status -ne 0 ]; then
    echo "Error: Failed to inspect information_schema for '${db_name}.${table_name}':" >&2
    echo "${tbl_exists}" >&2
    exit 1
  fi

  if [ "${tbl_exists}" != "1" ]; then
    # Database exists but table does not -> Inconsistent / Empty database
    STATUS_SUMMARY="${STATUS_SUMMARY} ${db_name}=NO_TABLE"
    continue
  fi

  # Table exists, query row count
  set +e
  row_count=$(docker exec "${CONTAINER_NAME}" psql -v ON_ERROR_STOP=1 -U "${DB_USER}" -d "${db_name}" -tAc "SELECT count(*) FROM public.${table_name};" 2>&1)
  query_status=$?
  set -e

  if [ $query_status -ne 0 ]; then
    echo "Error: Failed to query record count for '${db_name}.${table_name}':" >&2
    echo "${row_count}" >&2
    exit 1
  fi

  row_count=$(echo "${row_count}" | tr -d '[:space:]')
  if ! [[ "${row_count}" =~ ^[0-9]+$ ]]; then
    echo "Error: Invalid non-numeric row count returned for '${db_name}.${table_name}': ${row_count}" >&2
    exit 1
  fi

  if [ "${row_count}" -gt 0 ]; then
    POPULATED_COUNT=$((POPULATED_COUNT + 1))
    STATUS_SUMMARY="${STATUS_SUMMARY} ${db_name}.${table_name}=${row_count}"
    DETAILS_SUMMARY="${DETAILS_SUMMARY}\n  - ${db_name}.${table_name}: ${row_count} records"
  else
    STATUS_SUMMARY="${STATUS_SUMMARY} ${db_name}.${table_name}=0"
  fi
done

# Evaluate overall database state
if [ "${POPULATED_COUNT}" -eq 4 ]; then
  echo "All four databases are already correctly restored:"
  echo -e "${DETAILS_SUMMARY}"
  echo "Database instance is complete and active. Safely exiting without modifications."
  exit 0
fi

if [ "${CLEAN_COUNT}" -eq 4 ]; then
  echo "      Genuinely clean database instance confirmed. Proceeding with restoration."
else
  echo "Error: Inconsistent or partially populated database state detected." >&2
  echo "Status breakdown:${STATUS_SUMMARY}" >&2
  echo "Aborting restoration to prevent data loss or corruption." >&2
  echo "To restore cleanly, start with a fresh volume instance." >&2
  exit 1
fi

# 3. Locate or decrypt verified backup SQL dump
echo "[3/4] Locating verified database backup..."
if [ -f "${SQL_BACKUP}" ]; then
  RESTORE_FILE="${SQL_BACKUP}"
  echo "      Found verified SQL dump: ${SQL_BACKUP}"
elif [ -f "${ENC_BACKUP}" ] && [ -f "${KEY_FILE}" ]; then
  echo "      SQL dump not found, decrypting archive ${ENC_BACKUP}..."
  TEMP_DECRYPTED=$(mktemp)
  if ! openssl enc -d -aes-256-cbc -pbkdf2 -pass file:"${KEY_FILE}" -in "${ENC_BACKUP}" | tar -xOz postgres_dumpall_*.sql > "${TEMP_DECRYPTED}"; then
    echo "Error: Failed to decrypt backup archive." >&2
    exit 1
  fi
  RESTORE_FILE="${TEMP_DECRYPTED}"
  echo "      Successfully decrypted archive into temporary restore stream."
else
  echo "Error: Backup SQL dump not found at ${SQL_BACKUP} and encrypted archive not available." >&2
  exit 1
fi

# 4. Stream restore into PostgreSQL using ON_ERROR_STOP=1
echo "[4/4] Restoring database objects and schemas via psql (ON_ERROR_STOP=1)..."
RESTORE_LOG=$(mktemp)

set +e
docker exec -i "${CONTAINER_NAME}" psql -v ON_ERROR_STOP=1 -U "${DB_USER}" < "${RESTORE_FILE}" > "${RESTORE_LOG}" 2>&1
RESTORE_STATUS=$?
set -e

if [ $RESTORE_STATUS -ne 0 ]; then
  echo "Error: PostgreSQL restore failed with exit status ${RESTORE_STATUS}:" >&2
  cat "${RESTORE_LOG}" >&2
  exit 1
fi

# Post-restoration verification gate: verify all four databases are now populated
echo "Verifying restored databases and table counts..."
VERIFIED_COUNT=0
POST_SUMMARY=""

for db_name in auth_db products_db orders_db users_db; do
  case "${db_name}" in
    auth_db)     table_name="users" ;;
    products_db) table_name="products" ;;
    orders_db)   table_name="orders" ;;
    users_db)    table_name="users" ;;
  esac
  count=$(docker exec "${CONTAINER_NAME}" psql -v ON_ERROR_STOP=1 -U "${DB_USER}" -d "${db_name}" -tAc "SELECT count(*) FROM public.${table_name};")
  count=$(echo "${count}" | tr -d '[:space:]')
  if [ "${count}" -gt 0 ]; then
    VERIFIED_COUNT=$((VERIFIED_COUNT + 1))
    POST_SUMMARY="${POST_SUMMARY}\n  - ${db_name}.${table_name}: ${count} records"
  fi
done

if [ "${VERIFIED_COUNT}" -ne 4 ]; then
  echo "Error: Post-restoration verification failed. Not all four databases were populated." >&2
  exit 1
fi

echo "Restoration Verification Results:"
echo -e "${POST_SUMMARY}"
echo "Database restoration completed and verified successfully!"
exit 0
