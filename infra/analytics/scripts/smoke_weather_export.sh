#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
ANALYTICS_DIR="${REPO_ROOT}/infra/analytics"
FIXTURE="${REPO_ROOT}/python/tests/fixtures/weather_analytics_shortlist.json"

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

cd "${REPO_ROOT}"
PYTHONPATH=python/src python3 -m weather_pm.cli export-analytics-clickhouse \
  --shortlist-json "${FIXTURE}" \
  --dry-run

CLICKHOUSE_HTTP_PORT="${CLICKHOUSE_HTTP_PORT:-8123}"
CLICKHOUSE_USER="${CLICKHOUSE_USER:-prediction}"
CLICKHOUSE_PASSWORD="${CLICKHOUSE_PASSWORD:-prediction}"
CLICKHOUSE_DB="${CLICKHOUSE_DB:-prediction_core}"
CLICKHOUSE_URL="http://127.0.0.1:${CLICKHOUSE_HTTP_PORT}"

if ! curl -fsS "${CLICKHOUSE_URL}/ping" >/dev/null 2>&1; then
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    if ! (cd "${ANALYTICS_DIR}" && compose_cmd up -d clickhouse); then
      echo "Compose up failed once; removing stale ClickHouse compose containers and retrying" >&2
      docker ps -a --filter "label=com.docker.compose.project=analytics" --filter "label=com.docker.compose.service=clickhouse" --format '{{.ID}}' \
        | xargs -r docker rm -f >/dev/null 2>&1 || true
      docker rm -f prediction-core-clickhouse >/dev/null 2>&1 || true
      (cd "${ANALYTICS_DIR}" && compose_cmd up -d clickhouse)
    fi
    for i in $(seq 1 90); do
      if curl -fsS "${CLICKHOUSE_URL}/ping" >/dev/null 2>&1; then
        break
      fi
      if [ "${i}" = 90 ]; then
        echo "ClickHouse is not reachable; dry-run passed, skipping real export" >&2
        exit 0
      fi
      sleep 1
    done
  else
    echo "Docker/ClickHouse is not available; dry-run passed, skipping real export" >&2
    exit 0
  fi
fi

PREDICTION_CORE_CLICKHOUSE_URL="${CLICKHOUSE_URL}" \
PREDICTION_CORE_CLICKHOUSE_HOST="127.0.0.1" \
PREDICTION_CORE_CLICKHOUSE_PORT="${CLICKHOUSE_HTTP_PORT}" \
PREDICTION_CORE_CLICKHOUSE_USER="${CLICKHOUSE_USER}" \
PREDICTION_CORE_CLICKHOUSE_PASSWORD="${CLICKHOUSE_PASSWORD}" \
PREDICTION_CORE_CLICKHOUSE_DATABASE="${CLICKHOUSE_DB}" \
PYTHONPATH=python/src python3 -m weather_pm.cli export-analytics-clickhouse \
  --shortlist-json "${FIXTURE}"

curl -fsS \
  --get \
  --user "${CLICKHOUSE_USER}:${CLICKHOUSE_PASSWORD}" \
  --data-urlencode "database=${CLICKHOUSE_DB}" \
  --data-urlencode "query=SELECT run_id, strategy_id, profile_id, market_id FROM ${CLICKHOUSE_DB}.profile_decisions WHERE run_id = 'smoke-run-1' ORDER BY observed_at DESC LIMIT 1 FORMAT TSVWithNames" \
  "${CLICKHOUSE_URL}/"
