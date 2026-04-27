# Storage backup and restore drill

This runbook makes backup and restore readiness explicit without automating destructive production restores from this repository.

## Scope

- PostgreSQL/Timescale is the operational source of truth.
- ClickHouse is the analytics store and needs partition-aware backup/retention outside hot-path execution.
- S3-compatible storage contains immutable artifacts and must use encryption, versioning, and lifecycle review.
- Redis and NATS are runtime accelerators and are not durable backup sources.

## PostgreSQL backup

Use the local helper as the shape of the production backup command:

```bash
cd /home/jul/P-core/infra/storage
./backup_postgres.sh --output-dir /secure/local/backup/path
```

Production requirements:

- write backups outside the repo;
- encrypt backups at rest;
- create and retain checksum evidence;
- record backup timestamp, database name, migration version, operator, and target environment;
- keep permissions restricted to the backup operator/service account.

## Structural restore check

Validate a dump before any restore planning:

```bash
cd /home/jul/P-core/infra/storage
./restore_postgres_check.sh /secure/local/backup/path/postgres-panoptique-YYYYMMDDTHHMMSSZ.dump
```

The helper verifies dump readability and checks an adjacent `.sha256` file when present. It must not connect to production or overwrite data.

## Disposable restore drill

A production restore drill must target a disposable database or isolated staging environment only.

Required evidence:

- approved target name clearly indicates disposable/staging;
- dump checksum verified;
- migration version recorded before and after restore;
- representative queries against `prediction_runs`, `job_runs`, `execution_idempotency_keys`, `execution_audit_events`, and `storage_artifacts` succeed;
- RPO and RTO are recorded;
- rollback/delete of the disposable target is documented.

Never run `pg_restore --clean`, `dropdb`, or destructive restore commands against a production target from an ad-hoc shell.

## Artifact lifecycle review

Review MinIO/S3 candidates without deleting objects:

```bash
cd /home/jul/P-core/infra/storage
./minio_lifecycle_dry_run.sh --older-than 90
```

Production lifecycle changes require separate approval because artifacts may be needed for replay, audit, and incident reconstruction.

## Required launch gate

Before any live launch window:

- latest PostgreSQL backup is present and checksum-verified;
- latest restore drill is within the approved freshness window;
- S3 lifecycle review is current;
- ClickHouse backup/retention review is current;
- Redis/NATS are confirmed non-durable and excluded from source-of-truth recovery plans.
