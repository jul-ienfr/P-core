from __future__ import annotations

from typing import Any, Final

SECTION_NAMES: Final = ("infra", "secrets", "backup_restore", "monitoring", "launch_gates", "staging")


def _base_section(name: str, *, required_files: list[str], validation_commands: list[str], checks: list[str]) -> dict[str, Any]:
    return {
        "section": name,
        "dry_run": True,
        "requires_cloud_credentials": False,
        "provisions_external_services": False,
        "live_trading_enabled": False,
        "required_files": required_files,
        "validation_commands": validation_commands,
        "checks": checks,
    }


def production_infra_spec() -> dict[str, Any]:
    section = _base_section(
        "infra",
        required_files=["infra/storage/production-readiness.template.yml", "infra/storage/docker-compose.yml", "infra/analytics/docker-compose.yml", "infra/panoptique/docker-compose.yml"],
        validation_commands=[
            "PYTHONNOUSERSITE=1 docker-compose --env-file infra/storage/.env.example -f infra/storage/docker-compose.yml config >/dev/null",
            "PYTHONNOUSERSITE=1 docker-compose -f infra/analytics/docker-compose.yml config >/dev/null",
            "PYTHONNOUSERSITE=1 docker-compose --env-file infra/panoptique/.env.example -f infra/panoptique/docker-compose.yml config >/dev/null",
        ],
        checks=[
            "production template is declarative only",
            "no external provisioning is executed",
            "all local defaults remain loopback-only",
            "no compose image uses latest tags",
        ],
    )
    section["components"] = {
        "postgres_timescale": "operational source of truth",
        "clickhouse": "analytics source",
        "s3_artifacts": "immutable artifact store",
        "redis": "ephemeral cache and short leases",
        "nats": "runtime event fanout",
        "grafana": "operator observability",
    }
    return section


def secrets_manager_contract() -> dict[str, Any]:
    secret_names = [
        "PREDICTION_CORE_DATABASE_URL",
        "PREDICTION_CORE_SYNC_DATABASE_URL",
        "PREDICTION_CORE_REDIS_URL",
        "PREDICTION_CORE_NATS_URL",
        "PREDICTION_CORE_NATS_MONITOR_URL",
        "PREDICTION_CORE_S3_ENDPOINT_URL",
        "PREDICTION_CORE_S3_ACCESS_KEY_ID",
        "PREDICTION_CORE_S3_SECRET_ACCESS_KEY",
        "PREDICTION_CORE_S3_BUCKET",
        "PREDICTION_CORE_S3_REGION",
        "PREDICTION_CORE_S3_FORCE_PATH_STYLE",
        "PREDICTION_CORE_CLICKHOUSE_URL",
        "PREDICTION_CORE_CLICKHOUSE_USER",
        "PREDICTION_CORE_CLICKHOUSE_PASSWORD",
    ]
    section = _base_section(
        "secrets",
        required_files=["docs/storage-secrets-contract.md", "python/src/prediction_core/storage/config.py"],
        validation_commands=["prediction-core storage-readiness --section secrets --pretty", "prediction-core storage-health"],
        checks=[
            "secret values are never stored in this repo",
            "production uses an external secrets manager",
            "storage secrets are separated from Polymarket live keys",
            "health/readiness output is redacted",
        ],
    )
    section["provider"] = "external-secrets-manager"
    section["secret_names"] = secret_names
    section["value_policy"] = "names_and_references_only_never_values"
    return section


def backup_restore_drill_plan() -> dict[str, Any]:
    section = _base_section(
        "backup_restore",
        required_files=["docs/storage-backup-restore-drill.md", "infra/storage/backup_postgres.sh", "infra/storage/restore_postgres_check.sh", "infra/storage/minio_lifecycle_dry_run.sh"],
        validation_commands=[
            "bash -n infra/storage/backup_postgres.sh infra/storage/restore_postgres_check.sh infra/storage/minio_lifecycle_dry_run.sh",
            "infra/storage/restore_postgres_check.sh <dump-file>",
            "infra/storage/minio_lifecycle_dry_run.sh --older-than 90",
        ],
        checks=[
            "backup has checksum evidence",
            "restore drill targets disposable database only",
            "RPO/RTO evidence is recorded by operator",
            "S3 lifecycle changes are reviewed before mutation",
        ],
    )
    section["durable_sources"] = ["postgres_timescale", "clickhouse", "s3_artifacts"]
    section["non_durable_sources"] = ["redis", "nats"]
    return section


def monitoring_alerting_rules() -> dict[str, Any]:
    alerts = [
        "postgres_unavailable",
        "postgres_migration_mismatch",
        "timescale_extension_missing",
        "clickhouse_unavailable",
        "redis_degraded",
        "nats_degraded",
        "s3_unavailable",
        "ready_for_live_false",
        "backup_age_exceeded",
        "restore_drill_stale",
        "audit_idempotency_write_failures",
    ]
    section = _base_section(
        "monitoring",
        required_files=["docs/storage-monitoring-alerting.md", "python/src/prediction_core/storage/health.py", "infra/analytics/grafana/dashboards"],
        validation_commands=["prediction-core storage-health", "prediction-core storage-readiness --section monitoring --pretty"],
        checks=[
            "ready_for_live false blocks launch",
            "configured degraded services are visible",
            "backup and restore drill freshness are monitored externally",
            "alert contact points are configured outside this repo",
        ],
    )
    section["alerts"] = alerts
    return section


def launch_runbook_gates() -> dict[str, Any]:
    gates = [
        "storage_readiness_bundle_reviewed",
        "storage_health_ready_for_live_true",
        "backup_restore_drill_current",
        "monitoring_alerting_reviewed",
        "staging_validation_complete",
        "polymarket_live_preflight_read_only_reviewed",
        "operator_approval_recorded",
        "rollback_owner_available",
    ]
    section = _base_section(
        "launch_gates",
        required_files=["docs/polymarket-live-ready-runbook.md", "docs/storage-staging-validation-checklist.md"],
        validation_commands=["prediction-core storage-readiness --section launch_gates --pretty", "prediction-core polymarket-live-preflight"],
        checks=gates,
    )
    section["gates"] = gates
    section["blocking_rule"] = "any_failed_gate_blocks_live_launch"
    return section


def staging_validation_workflow() -> dict[str, Any]:
    section = _base_section(
        "staging",
        required_files=["docs/storage-staging-validation-checklist.md", ".github/workflows/storage-ci.yml"],
        validation_commands=[
            "git diff --check",
            "prediction-core storage-health",
            "prediction-core storage-readiness --section all --pretty",
            "prediction-core mirror-artifacts-s3 --input-dir data/polymarket --bucket <staging-bucket> --dry-run",
            "prediction-core replay-jsonl-audit --jsonl <audit.jsonl> --dry-run",
        ],
        checks=[
            "CI is green",
            "staging is isolated from production",
            "storage health JSON is archived",
            "artifact and audit dry-runs complete",
            "Polymarket preflight remains read-only",
            "no secret values appear in logs",
        ],
    )
    section["environment"] = "staging_only"
    return section


def storage_readiness_bundle() -> dict[str, Any]:
    sections = {
        "infra": production_infra_spec(),
        "secrets": secrets_manager_contract(),
        "backup_restore": backup_restore_drill_plan(),
        "monitoring": monitoring_alerting_rules(),
        "launch_gates": launch_runbook_gates(),
        "staging": staging_validation_workflow(),
    }
    return {
        "schema_version": "prediction_core.storage_readiness.v1",
        "dry_run": True,
        "requires_cloud_credentials": False,
        "provisions_external_services": False,
        "live_trading_enabled": False,
        "sections": sections,
    }


def storage_readiness_section(section: str) -> dict[str, Any]:
    if section == "all":
        return storage_readiness_bundle()
    bundle = storage_readiness_bundle()
    try:
        return bundle["sections"][section]
    except KeyError as exc:
        raise ValueError(f"unknown storage readiness section: {section}") from exc
