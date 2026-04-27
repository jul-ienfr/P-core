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
Usage: ./minio_lifecycle_dry_run.sh [--prefix PREFIX] [--older-than DAYS]

Lists local MinIO artifacts that would be candidates for archive/expiry review.
This script is intentionally read-only: it runs mc find without --exec, rm, or
lifecycle mutations. Use it to size retention changes before applying a reviewed
bucket lifecycle policy outside this script.

Environment (defaults match infra/storage/.env.example):
  PREDICTION_CORE_S3_ENDPOINT_URL       http://localhost:9002
  PREDICTION_CORE_S3_ACCESS_KEY_ID      prediction
  PREDICTION_CORE_S3_SECRET_ACCESS_KEY  prediction-secret
  PREDICTION_CORE_S3_BUCKET             prediction-core-artifacts
  PREDICTION_CORE_MINIO_ALIAS           local-pcore
USAGE
}

PREFIX=""
OLDER_THAN="${PREDICTION_CORE_ARTIFACT_REVIEW_OLDER_THAN_DAYS:-90}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix)
      PREFIX="${2:?--prefix requires a value}"
      shift 2
      ;;
    --older-than)
      OLDER_THAN="${2:?--older-than requires a day count}"
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

if ! command -v mc >/dev/null 2>&1; then
  echo "MinIO client 'mc' is required for lifecycle dry-runs" >&2
  exit 127
fi

ENDPOINT="${PREDICTION_CORE_S3_ENDPOINT_URL:-http://localhost:9002}"
ACCESS_KEY="${PREDICTION_CORE_S3_ACCESS_KEY_ID:-prediction}"
SECRET_KEY="${PREDICTION_CORE_S3_SECRET_ACCESS_KEY:-prediction-secret}"
BUCKET="${PREDICTION_CORE_S3_BUCKET:-prediction-core-artifacts}"
ALIAS="${PREDICTION_CORE_MINIO_ALIAS:-local-pcore}"
TARGET="${ALIAS}/${BUCKET}"
if [ -n "${PREFIX}" ]; then
  TARGET="${TARGET}/${PREFIX#/}"
fi

mc alias set "${ALIAS}" "${ENDPOINT}" "${ACCESS_KEY}" "${SECRET_KEY}" >/dev/null
printf 'Read-only retention candidates older than %s days under %s:\n' "${OLDER_THAN}" "${TARGET}"
mc find "${TARGET}" --older-than "${OLDER_THAN}d" --print
