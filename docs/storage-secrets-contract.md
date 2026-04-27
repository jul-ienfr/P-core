# Storage secrets manager contract

This contract defines the production storage secret references P-core expects. It does not contain secret values and must stay value-free.

## Provider requirement

Production secrets must come from an approved secrets manager such as Vault, AWS Secrets Manager, GCP Secret Manager, Kubernetes External Secrets, or an equivalent audited provider. Production must not load storage credentials from committed files or shared `.env` files.

## Required storage secret references

| Environment variable | Purpose | Rotation | Notes |
| --- | --- | --- | --- |
| `PREDICTION_CORE_DATABASE_URL` | Async PostgreSQL/Timescale operational store URL | Required | Must point to production operational DB only. |
| `PREDICTION_CORE_SYNC_DATABASE_URL` | Sync PostgreSQL/Timescale URL for migrations/health/repository writes | Required | Must use a production-safe driver and least-privilege role. |
| `PREDICTION_CORE_REDIS_URL` | Redis cache/lease endpoint | Required if Redis is configured | Redis is never source of truth. |
| `PREDICTION_CORE_NATS_URL` | NATS runtime event endpoint | Required if NATS is configured | NATS is never durable source of truth for business state. |
| `PREDICTION_CORE_NATS_MONITOR_URL` | NATS monitor health endpoint | Required for live readiness when NATS is configured | Must be network-restricted. |
| `PREDICTION_CORE_S3_ENDPOINT_URL` | S3-compatible endpoint | Optional for AWS S3, required for MinIO/private S3 | Do not expose credentials in query params. |
| `PREDICTION_CORE_S3_ACCESS_KEY_ID` | Artifact store access key reference | Required for S3 writer/health | Inject at runtime only. |
| `PREDICTION_CORE_S3_SECRET_ACCESS_KEY` | Artifact store secret key reference | Required for S3 writer/health | Inject at runtime only. |
| `PREDICTION_CORE_S3_BUCKET` | Immutable artifact bucket | Required for artifact mirroring | Bucket must have encryption and lifecycle review. |
| `PREDICTION_CORE_S3_REGION` | Artifact bucket region | Required for AWS, optional for local MinIO | Use provider region identifier. |
| `PREDICTION_CORE_S3_FORCE_PATH_STYLE` | S3 path-style flag | Environment-specific | Usually `false` for AWS, `true` for MinIO. |
| `PREDICTION_CORE_CLICKHOUSE_URL` | ClickHouse HTTP endpoint | Required for analytics health/export | Must not include inline credentials unless URL masking is verified. |
| `PREDICTION_CORE_CLICKHOUSE_USER` | ClickHouse user | Required if ClickHouse auth is enabled | Least privilege for analytics writes/reads. |
| `PREDICTION_CORE_CLICKHOUSE_PASSWORD` | ClickHouse password | Required if ClickHouse auth is enabled | Inject at runtime only. |

## Separation from trading credentials

Storage secrets are separate from Polymarket live credentials. Wallet/private-key variables such as `POLYMARKET_PRIVATE_KEY`, `POLYMARKET_FUNDER_ADDRESS`, and exchange credentials are governed by `docs/polymarket-live-ready-runbook.md` and must not be added to storage compose files, storage examples, or storage CI.

## Operational controls

- Store secret values only in the approved provider.
- Inject secrets through runtime environment, mounted secret files, or workload identity integrations.
- Rotate credentials on a documented schedule and immediately after suspected exposure.
- Log access to production secrets.
- Verify `prediction-core storage-health` and `prediction-core storage-readiness --section secrets` outputs never print secret values.
- Treat screenshots, shell history, CI logs, and tickets as public unless proven otherwise.
