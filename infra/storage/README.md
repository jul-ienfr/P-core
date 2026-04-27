# P-core storage stack

This compose stack runs the complete local storage layer for P-core:

- PostgreSQL/TimescaleDB for operational state, runs, jobs, idempotency, audit, and artifact metadata.
- Redis for ephemeral hot cache and short-lived leases.
- NATS with JetStream for realtime event fanout.
- MinIO for local S3-compatible immutable artifacts.
- ClickHouse for analytics events, decisions, metrics, PnL, and backtests.
- Grafana for operator dashboards.

Start it locally:

```bash
cd /home/jul/P-core/infra/storage
cp .env.example .env
# For anything beyond local fixtures, edit .env and replace all placeholder passwords/keys.
docker compose --env-file .env up -d
```

The checked-in `.env.example` is intentionally loopback-only and contains placeholder local credentials. Keep `.env` untracked, do not paste production secrets into docs or shell history, and do not change bind addresses to `0.0.0.0` unless network exposure has been explicitly approved. This stack is for local storage development and smoke tests only; it must not be used to enable live trading or store wallet/exchange credentials.

If Compose v2 is unavailable and legacy `docker-compose` is installed through Python user-site packages, run it with user-site packages disabled to avoid dependency conflicts:

```bash
PYTHONNOUSERSITE=1 docker-compose up -d
```

Run existing ClickHouse smoke checks:

```bash
cd /home/jul/P-core/infra/analytics
./scripts/smoke_clickhouse.sh
PATH=/home/jul/P-core/.venv/bin:$PATH ./scripts/smoke_weather_export.sh
```

`smoke_weather_export.sh` uses `python3`; keep the local venv first on `PATH` when the global Python environment does not include `clickhouse_connect`.

Run Panoptique migrations against the local PostgreSQL/TimescaleDB service. The operational-state migration is revision `0003_operational_state`:

```bash
cd /home/jul/P-core
PREDICTION_CORE_DATABASE_URL=postgresql+asyncpg://panoptique:panoptique@localhost:5432/panoptique \
/home/jul/P-core/.venv/bin/alembic -c migrations/panoptique/alembic/alembic.ini upgrade head
```

Redis and NATS are runtime accelerators only. PostgreSQL/TimescaleDB and immutable artifacts remain the durable operational sources; ClickHouse remains the analytics source for dashboards.

## Local versus production storage

This directory is a local development stack. It binds services to `127.0.0.1` by default and uses example credentials so developers can run smoke checks without external dependencies. Do not reuse the default `.env.example` passwords, local ports, or single-node volume layout for production.

Production storage should be separated from local data by account/project, network, bucket, database, credential, and backup location. Production restores should target an explicitly reviewed database or bucket, never a developer laptop default. Keep live-trading enablement outside this stack; these storage helpers do not place orders or change execution mode.

## Backups and restore preflight

Create a compressed, custom-format PostgreSQL backup from the local compose database:

```bash
cd /home/jul/P-core/infra/storage
./backup_postgres.sh --output-dir /secure/local/backup/path
```

The script is read-only against the database and writes `0600` dump and checksum files. Dumps can contain sensitive operational data; keep them encrypted or inside an access-controlled backup location and never commit them.

Validate that a dump is structurally readable before planning any restore:

```bash
./restore_postgres_check.sh /secure/local/backup/path/postgres-panoptique-YYYYMMDDTHHMMSSZ.dump
```

`restore_postgres_check.sh` verifies an adjacent `.sha256` file when present, then runs `pg_restore --list`; it does not connect to a database and does not restore, drop, or overwrite data. Actual production restore commands are intentionally not automated here. Never target production without explicit operator approval, checksum verification, a documented rollback plan, and a disposable target restore verification first.

## Retention, compression, and lifecycle notes

- PostgreSQL backups should use compressed custom-format dumps (`pg_dump --format=custom --compress=9`) and a checksum; keep at least one recently validated restore point before pruning older backups.
- MinIO artifacts should be treated as immutable. Review object age and prefix before applying lifecycle expiry or archive policies.
- ClickHouse tables are monthly-partitioned by `observed_at`; prefer partition-aware retention reviews and backups over row-by-row deletes. Do not run retention mutations from ad-hoc shells.
- Redis is configured as ephemeral cache (`--save "" --appendonly no`) and should not be treated as a durable backup source.
- NATS JetStream local volume data is runtime state; production retention and replication should be configured in the production NATS deployment, not via this local compose file.

List MinIO lifecycle candidates without modifying the bucket:

```bash
./minio_lifecycle_dry_run.sh --older-than 90
```

The lifecycle helper is intentionally non-destructive; it lists review candidates only and never deletes objects or installs bucket lifecycle rules.
