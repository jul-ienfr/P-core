#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANALYTICS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ANALYTICS_DIR}"

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

CLICKHOUSE_HTTP_PORT="${CLICKHOUSE_HTTP_PORT:-8123}"
CLICKHOUSE_USER="${CLICKHOUSE_USER:-prediction}"
CLICKHOUSE_PASSWORD="${CLICKHOUSE_PASSWORD:-prediction}"
CLICKHOUSE_DB="${CLICKHOUSE_DB:-prediction_core}"
CLICKHOUSE_URL="http://127.0.0.1:${CLICKHOUSE_HTTP_PORT}"

if ! compose_cmd up -d clickhouse; then
  echo "Compose up failed once; removing stale ClickHouse compose containers and retrying" >&2
  docker ps -a --filter "label=com.docker.compose.project=analytics" --filter "label=com.docker.compose.service=clickhouse" --format '{{.ID}}' \
    | xargs -r docker rm -f >/dev/null 2>&1 || true
  docker rm -f prediction-core-clickhouse >/dev/null 2>&1 || true
  compose_cmd up -d clickhouse
fi

for i in $(seq 1 90); do
  if curl -fsS "${CLICKHOUSE_URL}/ping" >/dev/null 2>&1; then
    break
  fi
  if [ "${i}" = 90 ]; then
    echo "ClickHouse did not become ready at ${CLICKHOUSE_URL}" >&2
    compose_cmd ps clickhouse >&2 || true
    exit 1
  fi
  sleep 1
done

query_clickhouse() {
  curl -fsS \
    --get \
    --user "${CLICKHOUSE_USER}:${CLICKHOUSE_PASSWORD}" \
    --data-urlencode "database=${CLICKHOUSE_DB}" \
    --data-urlencode "query=$1" \
    "${CLICKHOUSE_URL}/"
}

query_clickhouse "SELECT 1" >/dev/null
query_clickhouse "SELECT count() FROM system.tables WHERE database = '${CLICKHOUSE_DB}' AND name = 'profile_decisions'" | grep -qx "1"
count="$(query_clickhouse "SELECT count() FROM ${CLICKHOUSE_DB}.profile_decisions")"
printf 'profile_decisions count=%s\n' "${count}"
