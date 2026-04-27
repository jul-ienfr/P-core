#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

usage() {
  cat <<'USAGE'
Usage: ./backup_postgres.sh [--output-dir DIR]

Creates a non-destructive compressed PostgreSQL custom-format backup from the
local storage compose stack. The script reads only from the database container;
it does not drop, truncate, migrate, or modify data.

Environment (defaults match infra/storage/.env.example):
  PREDICTION_CORE_POSTGRES_DB       panoptique
  PREDICTION_CORE_POSTGRES_USER     panoptique
  PREDICTION_CORE_POSTGRES_PASSWORD panoptique
  PREDICTION_CORE_POSTGRES_SERVICE  postgres

Output files are written with mode 0600 because dumps may contain sensitive data.
USAGE
}

OUTPUT_DIR="${PREDICTION_CORE_BACKUP_DIR:-${SCRIPT_DIR}/backups}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output-dir)
      OUTPUT_DIR="${2:?--output-dir requires a directory}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    PYTHONNOUSERSITE=1 docker-compose "$@"
  else
    echo "Neither 'docker compose' nor 'docker-compose' is available" >&2
    return 127
  fi
}

DB_NAME="${PREDICTION_CORE_POSTGRES_DB:-panoptique}"
DB_USER="${PREDICTION_CORE_POSTGRES_USER:-panoptique}"
DB_PASSWORD="${PREDICTION_CORE_POSTGRES_PASSWORD:-panoptique}"
DB_SERVICE="${PREDICTION_CORE_POSTGRES_SERVICE:-postgres}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${OUTPUT_DIR}"
chmod 700 "${OUTPUT_DIR}"
OUT_FILE="${OUTPUT_DIR}/postgres-${DB_NAME}-${STAMP}.dump"

umask 077
compose_cmd exec -T \
  -e PGPASSWORD="${DB_PASSWORD}" \
  "${DB_SERVICE}" \
  pg_dump --format=custom --compress=9 --no-owner --no-acl \
    --username "${DB_USER}" \
    --dbname "${DB_NAME}" \
  > "${OUT_FILE}"

sha256sum "${OUT_FILE}" > "${OUT_FILE}.sha256"
printf 'Wrote PostgreSQL backup: %s\n' "${OUT_FILE}"
printf 'Wrote checksum: %s.sha256\n' "${OUT_FILE}"
