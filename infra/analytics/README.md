# Prediction Core Analytics Stack

Final cockpit stack:

- ClickHouse: analytical source of truth
- Grafana: dashboards and alerting

Start locally:

```bash
cd /home/jul/P-core/infra/analytics
docker compose up -d
```

Open Grafana:

- URL: http://127.0.0.1:3000
- Default local user: `admin`
- Default local password: `admin`

Never use these defaults outside local development.

## Storage hardening notes

The standalone analytics compose stack is for local dashboards and smoke tests. Keep production ClickHouse and Grafana separated from this local stack by network, credential, database, and backup location. The local Grafana bind address may be widened for dashboard sharing in development; do not expose production Grafana without reviewed authentication, TLS, and network controls.

ClickHouse tables are partitioned monthly by `observed_at` in `/home/jul/P-core/infra/analytics/clickhouse/init/001_prediction_core_schema.sql`. For production retention, prefer reviewed partition-level lifecycle procedures and backups instead of ad-hoc row deletes or mutations. Validate retention windows against dashboard needs before applying them.

Back up analytics data with environment-specific ClickHouse backup tooling or storage snapshots. Keep backups compressed, checksummed, access-controlled, and separate from local developer volumes. Do not commit dumps or exported dashboard data that may include market, strategy, or operational details.

For the full local storage backup/restore preflight and non-destructive MinIO lifecycle dry-run helpers, see `/home/jul/P-core/infra/storage/README.md`.

## Weather operator cockpit

Grafana provisions `weather-operator-cockpit.json` as the weather-specific paper operator cockpit. It reads existing ClickHouse analytics tables (`strategy_signals`, `profile_decisions`, `debug_decisions`, `paper_orders`, `paper_pnl_snapshots`, and `resolution_events`) to show tracked markets, profile decisions, abstentions, edge, simulated paper orders, paper PnL, source freshness, and official resolution status without wallet, signature, or real-order controls.
