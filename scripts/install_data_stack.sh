#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
WITH_LIVE="${WITH_LIVE:-0}"
WITH_SYSTEM_PACKAGES="${WITH_SYSTEM_PACKAGES:-0}"
START_SERVICES="${START_SERVICES:-1}"
SMOKE="${SMOKE:-1}"
UPGRADE="${UPGRADE:-0}"
FORCE_RECREATE_VENV="${FORCE_RECREATE_VENV:-0}"

log() { printf '\n[%s] %s\n' "p-core-install" "$*"; }
warn() { printf '\n[%s] WARNING: %s\n' "p-core-install" "$*" >&2; }
run() {
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    printf '+ '
    printf '%q ' "$@"
    printf '\n'
  else
    "$@"
  fi
}

compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    PYTHONNOUSERSITE=1 docker-compose "$@"
  else
    warn "Neither 'docker compose' nor 'docker-compose' is installed. Install Docker Compose, then rerun."
    return 127
  fi
}

apt_installed() {
  dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q "install ok installed"
}

install_system_packages() {
  if [[ "$WITH_SYSTEM_PACKAGES" != "1" ]]; then
    log "Skipping system packages. Set WITH_SYSTEM_PACKAGES=1 to install/update apt prerequisites."
    return 0
  fi
  if ! command -v apt-get >/dev/null 2>&1; then
    warn "apt-get not found; install Docker, Compose, Python venv, curl, git manually for this OS."
    return 0
  fi

  local packages=(python3 python3-venv python3-pip git curl ca-certificates docker.io docker-compose)
  local missing=()
  for pkg in "${packages[@]}"; do
    if ! apt_installed "$pkg"; then
      missing+=("$pkg")
    fi
  done

  if [[ "${#missing[@]}" -eq 0 && "$UPGRADE" != "1" ]]; then
    log "System prerequisites already installed; skipping apt install. Set UPGRADE=1 to update them."
    return 0
  fi

  if [[ "$UPGRADE" == "1" ]]; then
    log "Updating apt metadata and upgrading/installing system prerequisites"
    if [[ "${DRY_RUN:-0}" == "1" ]]; then
      echo "+ sudo apt-get update"
      echo "+ sudo apt-get install --only-upgrade -y ${packages[*]}"
      echo "+ sudo apt-get install -y ${missing[*]:-}"
    else
      sudo apt-get update
      sudo apt-get install --only-upgrade -y "${packages[@]}" || true
      if [[ "${#missing[@]}" -gt 0 ]]; then
        sudo apt-get install -y "${missing[@]}"
      fi
    fi
  else
    log "Installing missing system prerequisites only: ${missing[*]}"
    if [[ "${DRY_RUN:-0}" == "1" ]]; then
      echo "+ sudo apt-get update"
      echo "+ sudo apt-get install -y ${missing[*]}"
    else
      sudo apt-get update
      sudo apt-get install -y "${missing[@]}"
    fi
  fi
}

python_module_present() {
  local python="$1"
  local module="$2"
  "$python" - "$module" <<'PY'
import importlib.util
import sys
raise SystemExit(0 if importlib.util.find_spec(sys.argv[1]) else 1)
PY
}

venv_python() {
  printf '%s/bin/python' "$VENV_DIR"
}

ensure_venv() {
  if [[ "$FORCE_RECREATE_VENV" == "1" && -d "$VENV_DIR" ]]; then
    log "Removing existing virtualenv because FORCE_RECREATE_VENV=1: $VENV_DIR"
    if [[ "${DRY_RUN:-0}" == "1" ]]; then
      echo "+ rm -rf $VENV_DIR"
    else
      rm -rf "$VENV_DIR"
    fi
  fi

  if [[ -x "$(venv_python)" ]]; then
    log "Python virtualenv already exists: $VENV_DIR"
  else
    log "Creating Python virtualenv: $VENV_DIR"
    run "$PYTHON_BIN" -m venv "$VENV_DIR"
  fi
}

install_python_env() {
  ensure_venv
  local py="$(venv_python)"

  local storage_modules=(clickhouse_connect sqlalchemy psycopg asyncpg redis nats boto3)
  local missing=()
  if [[ "${DRY_RUN:-0}" != "1" ]]; then
    for module in "${storage_modules[@]}"; do
      if ! python_module_present "$py" "$module"; then
        missing+=("$module")
      fi
    done
  else
    missing=("checked-at-runtime")
  fi

  if [[ "$UPGRADE" == "1" ]]; then
    log "Installing/updating P-core Python storage extras in editable mode"
    run "$py" -m pip install --upgrade pip setuptools wheel
    run "$py" -m pip install --upgrade -e "$ROOT_DIR/python[storage]"
  elif [[ "${#missing[@]}" -gt 0 ]]; then
    log "Missing Python storage modules detected (${missing[*]}), installing storage extra"
    run "$py" -m pip install --upgrade pip setuptools wheel
    run "$py" -m pip install -e "$ROOT_DIR/python[storage]"
  else
    log "Python storage dependencies already present; skipping pip install. Set UPGRADE=1 to update."
  fi

  if [[ "$WITH_LIVE" == "1" ]]; then
    if [[ "$UPGRADE" == "1" ]] || [[ "${DRY_RUN:-0}" == "1" ]] || ! python_module_present "$py" py_clob_client; then
      log "Installing/updating optional Polymarket live/CLOB extra"
      local pip_args=(-e "$ROOT_DIR/python[polymarket-live]")
      if [[ "$UPGRADE" == "1" ]]; then
        run "$py" -m pip install --upgrade "${pip_args[@]}"
      else
        run "$py" -m pip install "${pip_args[@]}"
      fi
    else
      log "Optional Polymarket live/CLOB dependency already present; skipping. Set UPGRADE=1 to update."
    fi
  else
    log "Skipping live/CLOB client. Set WITH_LIVE=1 to install py-clob-client."
  fi
}

service_containers_exist() {
  local names=(prediction-core-clickhouse prediction-core-grafana prediction-core-postgres prediction-core-redis prediction-core-nats prediction-core-minio)
  local name
  for name in "${names[@]}"; do
    if ! docker ps -a --filter "name=$name" --format '{{.Names}}' 2>/dev/null | grep -q .; then
      return 1
    fi
  done
  return 0
}

start_services() {
  if [[ "$START_SERVICES" != "1" ]]; then
    log "Skipping Docker services. Set START_SERVICES=1 to start them."
    return 0
  fi
  local compose_file="$ROOT_DIR/infra/analytics/docker-compose.yml"
  if [[ ! -f "$compose_file" ]]; then
    warn "Compose file not found: $compose_file"
    return 0
  fi
  if ! command -v docker >/dev/null 2>&1; then
    warn "Docker is not installed. Set WITH_SYSTEM_PACKAGES=1 on Debian/Ubuntu or install Docker manually."
    return 0
  fi

  if service_containers_exist && [[ "$UPGRADE" != "1" ]]; then
    log "P-core service containers already exist; ensuring they are running without recreating."
    if [[ "${DRY_RUN:-0}" == "1" ]]; then
      echo "+ compose -f $compose_file up -d --no-recreate"
    elif ! compose -f "$compose_file" up -d --no-recreate; then
      warn "Compose could not adopt/start existing containers. If a container exists outside this compose project, remove or rename only that conflicting container, then rerun."
      return 1
    fi
  else
    log "Creating/updating P-core data services with Docker Compose"
    if [[ "${DRY_RUN:-0}" == "1" ]]; then
      echo "+ compose -f $compose_file pull"
      echo "+ compose -f $compose_file up -d"
    else
      if [[ "$UPGRADE" == "1" ]]; then
        compose -f "$compose_file" pull || true
      fi
      compose -f "$compose_file" up -d
    fi
  fi
}

smoke_check() {
  if [[ "$SMOKE" != "1" ]]; then
    log "Skipping smoke checks. Set SMOKE=1 to run them."
    return 0
  fi
  log "Running local smoke checks"
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    cat <<EOF
+ $(venv_python) - <<'PY'
import importlib.util
for m in ['clickhouse_connect','sqlalchemy','psycopg','asyncpg','redis','nats','boto3']:
    assert importlib.util.find_spec(m), m
print('python storage deps ok')
PY
+ curl -fsS http://127.0.0.1:8123/ping
+ curl -fsS http://127.0.0.1:3000/api/health
EOF
    return 0
  fi
  "$(venv_python)" - <<'PY'
import importlib.util
mods = ['clickhouse_connect','sqlalchemy','psycopg','asyncpg','redis','nats','boto3']
missing = [m for m in mods if importlib.util.find_spec(m) is None]
if missing:
    raise SystemExit(f"missing Python modules: {missing}")
print('python storage deps ok')
PY
  curl -fsS --max-time 5 http://127.0.0.1:8123/ping >/dev/null && echo "clickhouse ok"
  curl -fsS --max-time 5 http://127.0.0.1:3000/api/health >/dev/null && echo "grafana ok"
}

main() {
  log "P-core reproducible, idempotent data-stack install"
  log "Root: $ROOT_DIR"
  install_system_packages
  install_python_env
  start_services
  smoke_check
  log "Done"
  cat <<EOF

Next commands:
  source "$VENV_DIR/bin/activate"
  cd "$ROOT_DIR"
  PYTHONPATH=python/src python3 scripts/weather_cron_monitor_refresh.py

Options:
  DRY_RUN=1              print commands without running them
  WITH_SYSTEM_PACKAGES=1 install missing apt prerequisites
  UPGRADE=1              update apt packages, Python deps and Docker images
  WITH_LIVE=1            install optional py-clob-client live/CLOB extra
  START_SERVICES=0       only install Python dependencies
  SMOKE=0                skip health checks
  FORCE_RECREATE_VENV=1  delete and recreate the virtualenv
EOF
}

main "$@"
