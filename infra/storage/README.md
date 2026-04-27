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
docker compose up -d
```

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
