# Storage staging validation checklist

Use this checklist before any live launch window. Staging validation must not require production secrets and must not submit live orders.

## CI and repository hygiene

- [ ] Latest storage CI is green.
- [ ] `git diff --check` passes.
- [ ] No generated JSONL, parquet, dump, cache, `.env`, key, or certificate files are tracked.
- [ ] `python/uv.lock` is present and CI installs with `uv sync --locked`.

## Infra configuration

- [ ] Storage compose config validates:

```bash
cd /home/jul/P-core/infra/storage
PYTHONNOUSERSITE=1 docker-compose --env-file .env.example config >/dev/null
```

- [ ] Analytics and Panoptique compose configs validate.
- [ ] No service defaults bind to `0.0.0.0`.
- [ ] No compose image uses `latest`.

## Database and migrations

- [ ] PostgreSQL/Timescale staging target is separate from production.
- [ ] Alembic migrations apply cleanly to staging.
- [ ] `prediction_runs`, `job_runs`, `execution_idempotency_keys`, `execution_audit_events`, and `storage_artifacts` are present.
- [ ] Timescale extension is installed where required.

## Storage health evidence

Capture and archive:

```bash
cd /home/jul/P-core
python/scripts/prediction-core storage-health
python/scripts/prediction-core storage-readiness --section all --pretty
```

- [ ] `summary.ready_for_paper` is true.
- [ ] `summary.ready_for_live` is true only when every configured storage dependency is healthy.
- [ ] Output contains no secret values.

## Artifact and audit dry-runs

- [ ] Artifact mirror plan succeeds with `--dry-run`.
- [ ] JSONL audit replay plan succeeds with `--dry-run`.
- [ ] S3 bucket write/read/delete probe, if performed externally, uses a staging-only object prefix.

## Backup and restore drill

- [ ] Fresh backup exists and checksum verifies.
- [ ] Restore structural check passes.
- [ ] Disposable restore drill target is clearly non-production.
- [ ] RPO/RTO evidence is recorded.

## Polymarket safety

- [ ] `polymarket-live-preflight` is executed as read-only.
- [ ] Dry-run execution rehearsal uses explicit risk caps, idempotency, and audit logs.
- [ ] No live order is submitted during staging validation.
- [ ] Operator approval, rollback owner, and escalation channel are documented.
