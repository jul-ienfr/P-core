# Prediction Core ClickHouse + Grafana Runbook

ClickHouse + Grafana is the final analytics cockpit stack for Prediction Core.

- **ClickHouse** is the append-only analytical source of truth for normalized strategy/profile events, profile decisions, debug rows, paper ledger rows, positions, PnL, and metrics.
- **Grafana** is the single operator cockpit for dashboards and future alerting, reading ClickHouse directly through the provisioned ClickHouse datasource.
- Python services keep domain logic in code, then emit comparable `strategy_id × profile_id × market_id` analytics rows into the `prediction_core` ClickHouse database.

## Launch the local stack

Preferred Docker Compose v2 command:

```bash
cd /home/jul/P-core-clickhouse-grafana/infra/analytics
docker compose up -d
```

Fallback for systems that only have legacy Compose v1:

```bash
cd /home/jul/P-core-clickhouse-grafana/infra/analytics
PYTHONNOUSERSITE=1 docker-compose up -d
```

The smoke scripts auto-select `docker compose` first and then `PYTHONNOUSERSITE=1 docker-compose` when v2 is absent.

Default service bindings:

- Grafana is the only operator UI exposed on the LAN by default: `http://0.0.0.0:3000`, reachable as `http://<host-lan-ip>:3000`.
- ClickHouse is the backend analytical database. Its HTTP and native ports stay localhost-only by default: `127.0.0.1:8123` and `127.0.0.1:9000`.

On Julien's current ubuntuserver, verify the LAN IP with `hostname -I`; at setup time it was `192.168.31.101`, so the operator URL was:

```text
Grafana: http://192.168.31.101:3000
```

Do not expose ClickHouse to the LAN for normal use. It is not a dashboard; Grafana queries it from the container network/local host and provides the visual cockpit.

## Verify ClickHouse

Check readiness with `/ping`:

```bash
curl -fsS http://127.0.0.1:8123/ping
```

Expected response:

```text
Ok.
```

To verify the schema without putting credentials in a URL, pass credentials with curl auth flags:

```bash
CLICKHOUSE_USER=prediction \
CLICKHOUSE_PASSWORD=prediction \
CLICKHOUSE_DB=prediction_core \
curl -fsS \
  --get \
  --user "${CLICKHOUSE_USER}:${CLICKHOUSE_PASSWORD}" \
  --data-urlencode "database=${CLICKHOUSE_DB}" \
  --data-urlencode "query=SELECT count() FROM system.tables WHERE database = '${CLICKHOUSE_DB}' AND name = 'profile_decisions'" \
  http://127.0.0.1:8123/
```

## Run smoke scripts

From the repository root:

```bash
cd /home/jul/P-core-clickhouse-grafana
infra/analytics/scripts/smoke_clickhouse.sh
```

This starts ClickHouse if needed, waits for `/ping`, verifies `SELECT 1`, checks that the `profile_decisions` table exists, and prints the current row count.

Run the weather export smoke:

```bash
cd /home/jul/P-core-clickhouse-grafana
infra/analytics/scripts/smoke_weather_export.sh
```

This first runs the weather shortlist export in dry-run mode. If ClickHouse is reachable, it then performs a real configured export of the fixture and queries back the inserted row.

Current local environment quirk: this environment does not have Docker Compose v2, and the installed legacy `docker-compose` may fail through its Python Docker client with `Not supported URL scheme http+docker`. The scripts already auto-select v2/v1, but real smoke execution may require fixing/installing the Docker Compose plugin before containers can start.

## Export a weather shortlist

Dry-run export is safe and does not require ClickHouse configuration:

```bash
cd /home/jul/P-core-clickhouse-grafana
PYTHONPATH=python/src python3 -m weather_pm.cli export-analytics-clickhouse \
  --shortlist-json python/tests/fixtures/weather_analytics_shortlist.json \
  --dry-run
```

Expected output for the included fixture:

```text
analytics.profile_decisions.rows=1
analytics.enabled=false
```

Real configured export requires ClickHouse to be reachable and analytics environment variables to be set:

```bash
cd /home/jul/P-core-clickhouse-grafana
export PREDICTION_CORE_CLICKHOUSE_URL=http://127.0.0.1:8123
export PREDICTION_CORE_CLICKHOUSE_HOST=127.0.0.1
export PREDICTION_CORE_CLICKHOUSE_PORT=8123
export PREDICTION_CORE_CLICKHOUSE_USER=prediction
export PREDICTION_CORE_CLICKHOUSE_PASSWORD='<set-from-local-secret-store>'
export PREDICTION_CORE_CLICKHOUSE_DATABASE=prediction_core
PYTHONPATH=python/src python3 -m weather_pm.cli export-analytics-clickhouse \
  --shortlist-json python/tests/fixtures/weather_analytics_shortlist.json
```

When configured successfully, the CLI prints:

```text
analytics.profile_decisions.rows=<n>
analytics.enabled=true
```

## Dashboards

Grafana provisions these dashboards from `infra/analytics/grafana/dashboards`:

- **Strategy vs Profile** — compares strategy/profile metrics such as PnL, trade count, skip count, and average edge.
- **Decision Debug** — inspects decision statuses, blockers, skip reasons, source/orderbook/risk gates, and debug rows.
- **Paper Ledger** — monitors paper PnL snapshots, paper positions, paper orders, and net PnL.

## Environment variables

Runtime analytics writer variables:

| Variable | Purpose | Default |
| --- | --- | --- |
| `PREDICTION_CORE_CLICKHOUSE_URL` | Optional HTTP URL used to enable analytics and derive host/port/database when present. Do not include passwords in this URL. | unset |
| `PREDICTION_CORE_CLICKHOUSE_HOST` | ClickHouse host; also enables analytics when URL is unset. | unset / `localhost` after enabling |
| `PREDICTION_CORE_CLICKHOUSE_PORT` | ClickHouse HTTP port. | `8123` |
| `PREDICTION_CORE_CLICKHOUSE_USER` | ClickHouse username. | `prediction` |
| `PREDICTION_CORE_CLICKHOUSE_PASSWORD` | ClickHouse password. | `prediction` for local only |
| `PREDICTION_CORE_CLICKHOUSE_DATABASE` | ClickHouse database. | `prediction_core` |

Compose-local variables such as `CLICKHOUSE_DB`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_HTTP_PORT`, `CLICKHOUSE_NATIVE_PORT`, `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`, and `GRAFANA_PORT` control the local containers.

## Security rules

- Do not put secrets in `raw` JSON payloads, ClickHouse rows, Grafana dashboard JSON, docs, fixtures, or committed config.
- Do not paste passwords in ClickHouse URLs or curl query strings.
- Use environment variables or a local secret store for passwords.
- Keep dashboard queries and docs free of tokens, API keys, account identifiers, and private order credentials.
- Local defaults are for development only; rotate and override them outside local development.
