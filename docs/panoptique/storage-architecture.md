# Panoptique storage architecture

Panoptique uses PostgreSQL 16+ with TimescaleDB as the primary queryable store from Phase 1.

## Roles

- PostgreSQL/TimescaleDB: source of truth for queryable operational state and timestamped facts.
- Alembic: schema migration path under `migrations/panoptique/alembic/`.
- Redis: ephemeral latest-state/live cache only; never source of truth.
- JSONL/Parquet: append-only audit/replay archives under `data/panoptique/`.
- DuckDB: offline analytics/backtests over Parquet exports, not the live database.

## Safety

This storage layer is read-only/paper-only. It introduces no wallet credentials, private keys, or live order execution.

## Phase 9 optimization policy

Phase 9 optimizes the already-selected PostgreSQL/TimescaleDB store; it does **not** change source-of-truth semantics.

### Audit and sizing checks

Before enabling or tuning retention in a production database, record these read-only checks in an operator note:

```sql
SELECT hypertable_name, num_chunks
FROM timescaledb_information.hypertables
ORDER BY hypertable_name;

SELECT hypertable_name, compression_enabled
FROM timescaledb_information.hypertables
ORDER BY hypertable_name;

SELECT schemaname, relname, n_live_tup, n_dead_tup
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC;
```

The `panoptique db-health` command emits a safe read-only fixture/local health report with latest snapshot age, table row counts as growth-rate inputs, failed ingestion count, compression status placeholder, and migration version.

### Compression

Migration `0002_storage_optimization` enables Timescale compression for the high-volume hypertables identified in the plan:

- `market_price_snapshots`
- `orderbook_snapshots`
- `trade_events`
- `ingestion_health`

Compression is delayed by age (`7d`, `14d`, or `30d`) so recent ingest/update windows stay uncompressed.

### Continuous aggregates

Migration `0002_storage_optimization` defines continuous aggregates for:

- 1m/5m/15m market price buckets
- 5m trade volume buckets
- 5m top-of-book spread/liquidity buckets
- 15m shadow prediction outcome buckets

The materialized views are created `WITH NO DATA`; refresh policies populate them incrementally. Operators can manually backfill after verifying DB load.

### Retention and raw replay archives

Destructive retention is **not executed automatically** by Phase 9. Raw JSONL/Parquet archives under `data/panoptique/` remain canonical replay/audit material and must outlive DB retention windows.

Retention may only be added after documenting:

1. the regulatory/research replay requirement for the affected table,
2. where raw archives for the same interval live,
3. the latest backup artifact path,
4. a restore smoke-test result,
5. the operator and timestamp approving retention.

Manual example only, not run by migration:

```sql
-- Example after audit coverage is documented:
-- SELECT add_retention_policy('orderbook_snapshots', INTERVAL '180 days', if_not_exists => TRUE);
-- SELECT add_retention_policy('trade_events', INTERVAL '365 days', if_not_exists => TRUE);
```

## Backup and restore runbook

### Local backup command

Use a local-only connection string and never paste secrets into shell history. Prefer `.pgpass` or a restricted environment file.

```bash
cd /home/jul/prediction_core
pg_dump --format=custom --no-owner --no-acl \
  --file data/panoptique/backups/panoptique_$(date -u +%Y%m%dT%H%M%SZ).dump \
  "$PANOPTIQUE_SYNC_DATABASE_URL"
```

### Restore smoke test

Restore into a disposable database, never over the primary DB:

```bash
createdb panoptique_restore_smoke
pg_restore --clean --if-exists --no-owner --dbname panoptique_restore_smoke \
  data/panoptique/backups/<backup-file>.dump
psql panoptique_restore_smoke -c "SELECT COUNT(*) FROM shadow_predictions;"
dropdb panoptique_restore_smoke
```

### Migration rollback rule

Rollback only in local/staging or after taking a fresh backup. For production-like data, prefer a forward fix unless a failed migration has not yet accepted writes. Retention policies require an extra manual audit note before rollback or re-application.

### Never-store-secrets rule

Do not store wallet private keys, API tokens, bearer headers, seed phrases, exchange credentials, or database passwords in Panoptique tables, raw archives, Parquet exports, or operator reports. Export tooling redacts obvious secret-bearing JSON keys, but redaction is a safety net rather than permission to ingest secrets.

Keep local `.env` files, `.pgpass`, database dumps, Parquet/JSONL exports, and key material out of git. The checked-in compose examples bind services to `127.0.0.1`; do not expose PostgreSQL, Redis, NATS, MinIO, ClickHouse, or Grafana on public interfaces without an explicit operator approval and a credential rotation plan. Storage CI/smoke jobs must use disposable local credentials and must not depend on production services.
