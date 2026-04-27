# Storage monitoring and alerting

Production live readiness requires alerting on the storage source of truth, analytics path, artifact store, and runtime accelerators. This document defines the minimum signals; it does not provision external alerting by itself.

## Primary command

Use the JSON health command as the operator-facing probe:

```bash
prediction-core storage-health
```

For static readiness material:

```bash
prediction-core storage-readiness --section monitoring --pretty
```

## Required alert signals

| Signal | Severity | Expected source | Action |
| --- | --- | --- | --- |
| Postgres unavailable | Critical | `storage-health.postgres.ok=false` | Stop live launch; preserve paper/dry-run only. |
| Migration mismatch or missing Alembic version | Critical | Postgres health/migration check | Block live launch until migrations are reviewed. |
| Timescale extension missing | Critical | Postgres health/timescale check | Block live launch; operational time-series assumptions are invalid. |
| ClickHouse unavailable | Warning/Critical by mode | `storage-health.clickhouse.ok=false` | Analytics degraded; live launch requires operator approval if analytics are mandatory. |
| Redis degraded | Warning | `summary.degraded_services` | Cache/lease acceleration degraded; confirm Postgres source of truth remains healthy. |
| NATS degraded | Warning | `summary.degraded_services` | Event fanout degraded; confirm workers can continue safely. |
| S3 unavailable | Critical for artifact-producing flows | `summary.degraded_services` | Do not start flows that require immutable artifact persistence. |
| `ready_for_live=false` | Critical | `summary.ready_for_live` | Block live launch. |
| Backup age exceeded | Critical | backup scheduler/provider metrics | Run and verify fresh backup. |
| Restore drill stale | Critical | drill evidence/runbook record | Complete disposable restore drill before launch. |
| Audit/idempotency write failures | Critical | runtime logs/Postgres metrics | Stop live path and reconcile before retry. |

## Grafana and dashboards

Existing dashboards live under:

- `infra/analytics/grafana/dashboards/`
- `infra/analytics/grafana/provisioning/dashboards/prediction-core.yml`

Production alerting should be implemented through Grafana Alerting, Prometheus/Alertmanager, or the provider-native equivalent. Contact points must be configured outside this repo with approved on-call routing.

## Minimum launch review

Before a live launch window, capture:

- `prediction-core storage-health` JSON;
- `prediction-core storage-readiness --section monitoring --pretty` JSON;
- current backup timestamp;
- latest restore drill timestamp;
- alert contact point owner;
- escalation channel.

Do not paste secret-bearing URLs or credentials into alert annotations. Use redacted labels and provider object references.
