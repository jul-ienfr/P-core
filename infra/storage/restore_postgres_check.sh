#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./restore_postgres_check.sh BACKUP.dump

Performs a non-destructive restore validation by verifying an adjacent .sha256
checksum when present, then listing the contents of a PostgreSQL custom-format
dump with pg_restore --list. This does not connect to a database and does not
restore, drop, or overwrite any data.

Use the generated list as a preflight artifact before any manually reviewed
restore run. Production restores must be executed only from an explicit runbook
with operator approval and a verified target database.
USAGE
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage
  exit 0
fi

BACKUP_FILE="${1:?backup dump path is required}"
if [ ! -f "${BACKUP_FILE}" ]; then
  echo "Backup file not found: ${BACKUP_FILE}" >&2
  exit 1
fi

if ! command -v pg_restore >/dev/null 2>&1; then
  echo "pg_restore is required for local dump validation" >&2
  exit 127
fi

CHECKSUM_FILE="${BACKUP_FILE}.sha256"
if [ -f "${CHECKSUM_FILE}" ]; then
  sha256sum --check "${CHECKSUM_FILE}"
fi

pg_restore --list "${BACKUP_FILE}" >/dev/null
printf 'Backup structure is readable: %s\n' "${BACKUP_FILE}"
