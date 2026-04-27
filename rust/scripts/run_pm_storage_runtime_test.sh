#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace_dir="$repo_root"
target_dir="${CARGO_TARGET_DIR:-/tmp/pm_storage_runtime_target}"
registry_dir="${CARGO_REGISTRY_DIR:-/tmp/pm_storage_runtime_registry}"
git_dir="${CARGO_GIT_DIR:-/tmp/pm_storage_runtime_git}"
crate_name="pm_storage"
postgres_image="${POSTGRES_IMAGE:-postgres:16}"
rust_image="${RUST_IMAGE:-rust:1.89-bookworm}"
database_name="${PM_STORAGE_TEST_DB:-pm_storage_runtime}"
postgres_password="${POSTGRES_PASSWORD:-postgres}"
docker_bin="${DOCKER_BIN:-$(command -v docker || true)}"

default_tests=(
  "sqlx_runtime_allows_repeated_schema_apply_against_real_postgres"
  "sqlx_runtime_preserves_insertability_after_repeated_schema_apply_against_real_postgres"
  "sqlx_runtime_commits_multi_table_transaction_against_real_postgres"
  "sqlx_runtime_rejects_duplicate_market_event_insert_against_real_postgres"
)

if [[ -z "$docker_bin" ]]; then
  echo "docker is required" >&2
  echo "PATH=$PATH" >&2
  exit 1
fi

if [[ ! -f "$workspace_dir/Cargo.toml" ]]; then
  echo "Rust workspace not found at $workspace_dir" >&2
  exit 1
fi

if [[ $# -gt 0 ]]; then
  tests=("$@")
else
  tests=("${default_tests[@]}")
fi

run_one() {
  local test_name="$1"
  local network="pm_storage_runtime_test_$(date +%s)_$RANDOM"
  local container="pm-storage-pg-$RANDOM"
  local masked_database_url="postgres://postgres:***@${container}:5432/${database_name}"
  local database_url="postgres://postgres:${postgres_password}@${container}:5432/${database_name}"

  cleanup() {
    "$docker_bin" rm -f "$container" >/dev/null 2>&1 || true
    "$docker_bin" network rm "$network" >/dev/null 2>&1 || true
  }

  trap cleanup RETURN

  "$docker_bin" network create "$network" >/dev/null

  "$docker_bin" run -d \
    --name "$container" \
    --network "$network" \
    -e POSTGRES_PASSWORD="$postgres_password" \
    -e POSTGRES_DB="$database_name" \
    "$postgres_image" >/dev/null

  until "$docker_bin" exec "$container" pg_isready -U postgres -d "$database_name" >/dev/null 2>&1; do
    sleep 1
  done

  cargo_args=(test -p "$crate_name" "$test_name" -- --nocapture)

  echo "[pm_storage runtime] DATABASE_URL=${masked_database_url}"
  echo "[pm_storage runtime] cargo ${cargo_args[*]}"

  mkdir -p "$target_dir" "$registry_dir" "$git_dir"

  "$docker_bin" run --rm \
    --network "$network" \
    -v "$repo_root":/workspace:ro \
    -v "$target_dir":/cargo-target \
    -v "$registry_dir":/usr/local/cargo/registry \
    -v "$git_dir":/usr/local/cargo/git \
    -w /workspace \
    -e CARGO_TARGET_DIR=/cargo-target \
    -e DATABASE_URL="$database_url" \
    "$rust_image" \
    bash -lc 'export PATH=/usr/local/cargo/bin:$PATH; cargo "$@"' bash "${cargo_args[@]}"
}

for test_name in "${tests[@]}"; do
  run_one "$test_name"
done
