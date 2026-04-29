# Weather Live Observer Config — operator guide

This page is the practical runbook for the configurable, paper-only weather live observer. The source of truth is `config/weather_live_observer.yaml`; Grafana is read-only in v1.

## Safety model

- `active_scenario` only selects the prepared intensity. It does **not** start collection by itself.
- `collection.enabled` is the master kill switch. When it is `false`, live collection is off even if the scenario is `aggressive`.
- `collection.dry_run: true` previews the run and prevents snapshot writes.
- The observer is paper-only: `paper_only: true`, `live_order_allowed: false`, `allow_wallet: false`, and `allow_signing: false` must remain set.
- Live network collection is deferred in v1. `--source live` returns a safe `read_only_unavailable` summary rather than performing network calls.

## Scenario changes

Use the CLI/YAML workflow for scenario changes:

```bash
cd /home/jul/P-core
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config show
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config set-scenario realistic
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config estimate
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config validate
```

Recommended order:

1. Set `collection.enabled: false` before changing intensity.
2. Change `active_scenario` to `minimal`, `realistic`, or `aggressive`.
3. Run `estimate` and `validate`.
4. Smoke-test with `scripts/weather_live_observer_run_once.py --source fixture --dry-run`.
5. Only then consider setting `collection.enabled: true` and `collection.dry_run: false`.

## Storage paths: local path, NAS path, NAS/MinIO

Default operator target is the NAS path:

```yaml
paths:
  base_dir: /mnt/truenas/p-core/polymarket/live_observer
safety:
  require_mountpoint: /mnt/truenas
  refuse_if_not_mounted: true
```

Before enabling writes, verify the mount and write permission manually:

```bash
mountpoint /mnt/truenas
test -w /mnt/truenas
```

For a temporary local path, use an explicit P-core directory, for example:

```bash
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config set-path \
  --base-dir /home/jul/P-core/data/polymarket/live_observer
```

For NAS/MinIO archival, keep secrets out of YAML. Store bucket/credentials in environment variables and configure only non-secret fields:

```yaml
storage:
  archive: s3_archive
s3:
  bucket_env: PREDICTION_CORE_S3_BUCKET
  prefix: polymarket/live_observer
```

## Estimate and dry-run

Estimate storage before switching scenarios or backends:

```bash
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config estimate
```

Run a local smoke dry-run without live network:

```bash
PYTHONPATH=python/src python3 scripts/weather_live_observer_run_once.py \
  --config config/weather_live_observer.yaml \
  --source fixture \
  --dry-run \
  --summary-json /tmp/weather-live-observer-summary.json \
  --summary-md /tmp/weather-live-observer-summary.md
```

## Run once wrapper

`scripts/weather_live_observer_run_once.py` is the scheduler-safe wrapper. It is idempotent for repeated one-shot invocations and has no install/update behavior.

Examples:

```bash
# Safe live-mode check: exits 0 for read_only_unavailable in v1.
PYTHONPATH=python/src python3 scripts/weather_live_observer_run_once.py \
  --config config/weather_live_observer.yaml \
  --source live

# Fixture smoke with reports.
PYTHONPATH=python/src python3 scripts/weather_live_observer_run_once.py \
  --config config/weather_live_observer.yaml \
  --source fixture \
  --summary-json /home/jul/P-core/data/polymarket/live_observer/reports/last-run.json \
  --summary-md /home/jul/P-core/data/polymarket/live_observer/reports/last-run.md
```

Exit behavior:

- `0`: usable summary, including fixture success, `collection_disabled`, or v1 `read_only_unavailable`.
- non-zero: invalid config or summary path/write failure.

## Scheduler recommendation only

Important: no cron or systemd unit is installed by this repo. If an operator chooses to schedule it outside the repo, use a command like:

```cron
*/5 * * * * cd /home/jul/P-core && PYTHONPATH=python/src python3 scripts/weather_live_observer_run_once.py --config config/weather_live_observer.yaml --source live --summary-json /home/jul/P-core/data/polymarket/live_observer/reports/last-run.json --summary-md /home/jul/P-core/data/polymarket/live_observer/reports/last-run.md
```

A systemd service/timer should execute the same command, run as the normal repo user, and rely on the YAML kill switch. Do not embed secrets in unit files.

## Rollback local

If NAS validation fails and you need a rollback local smoke target:

1. Set `collection.enabled: false`.
2. Set the base path to `/home/jul/P-core/data/polymarket/live_observer`.
3. Set `active_scenario: minimal`.
4. Run `validate`, `estimate`, then a fixture `dry-run`.
5. Re-enable writes only if the local path is intentional and disk capacity is acceptable.

## Kill switches

Global kill switch:

```yaml
collection:
  enabled: false
  dry_run: true
  reason: operator_pause
```

Per-stream stop:

```yaml
streams:
  forecasts:
    enabled: false
    reason: provider_outage
```

Per-profile/account stop:

```yaml
profiles:
  shadow_coldmath_v0:
    enabled: false
    reason: under_review
followed_accounts:
  ColdMath:
    enabled: false
    reason: under_review
```

## Dashboard

Grafana dashboard `Weather Live Observer Config` (`prediction-core-weather-live-observer-config`) covers active scenario, storage estimate, primary/backend, base/archive target, snapshot intervals, limits, last run status, snapshot freshness, error count by source, and paper-only guardrails. It is an operator visibility surface, not a config editor in v1.
