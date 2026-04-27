from __future__ import annotations

from pathlib import Path
from typing import Any, Final

SECTION_NAMES: Final = ("infra", "secrets", "backup_restore", "monitoring", "launch_gates", "staging")
ROOT: Final = Path(__file__).resolve().parents[4]


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


def storage_live_validation_report(
    *,
    health: dict[str, Any] | None = None,
    backup_evidence: str | None = None,
    restore_drill_evidence: str | None = None,
    monitoring_evidence: str | None = None,
    staging_evidence: str | None = None,
    operator_approval: str | None = None,
) -> dict[str, Any]:
    if health is None:
        from prediction_core.storage.health import storage_health

        health = storage_health()
    readiness = storage_readiness_bundle()
    checks = [
        _check("readiness_bundle", readiness.get("live_trading_enabled") is False and len(readiness.get("sections", {})) == len(SECTION_NAMES), "storage readiness bundle is materialized and live-disabled"),
        _check("storage_health_ready_for_live", bool(health.get("summary", {}).get("ready_for_live")), "storage-health summary.ready_for_live is true"),
        _check("storage_health_not_degraded", not bool(health.get("summary", {}).get("degraded")), "storage-health reports no degraded configured dependencies"),
        _check("source_of_truth_live_disabled", health.get("source_of_truth", {}).get("live_trading_enabled") is False, "storage source-of-truth metadata does not enable live trading"),
        _evidence_check("backup_evidence", backup_evidence, "backup evidence file exists"),
        _evidence_check("restore_drill_evidence", restore_drill_evidence, "restore drill evidence file exists"),
        _evidence_check("monitoring_evidence", monitoring_evidence, "monitoring/alerting evidence file exists"),
        _evidence_check("staging_evidence", staging_evidence, "staging validation evidence file exists"),
        _evidence_check("operator_approval", operator_approval, "operator approval evidence file exists"),
    ]
    blocking_failures = [check for check in checks if not check["ok"]]
    return {
        "schema_version": "prediction_core.storage_live_validation.v1",
        "dry_run": True,
        "destructive": False,
        "provisions_external_services": False,
        "live_trading_enabled": False,
        "decision": "GO" if not blocking_failures else "NO_GO",
        "ready_for_live": not blocking_failures,
        "checks": checks,
        "blocking_failures": blocking_failures,
        "required_evidence": {
            "backup_evidence": backup_evidence,
            "restore_drill_evidence": restore_drill_evidence,
            "monitoring_evidence": monitoring_evidence,
            "staging_evidence": staging_evidence,
            "operator_approval": operator_approval,
        },
    }


def _check(name: str, ok: bool, description: str) -> dict[str, Any]:
    return {"name": name, "ok": ok, "description": description}


def _evidence_check(name: str, path: str | None, description: str) -> dict[str, Any]:
    if not path:
        return {"name": name, "ok": False, "description": description, "error": "missing_path"}
    evidence_path = Path(path)
    if not evidence_path.is_absolute():
        evidence_path = ROOT / evidence_path
    try:
        resolved = evidence_path.resolve(strict=False)
    except OSError as exc:
        return {"name": name, "ok": False, "description": description, "path": str(evidence_path), "error": type(exc).__name__}
    try:
        relative = resolved.relative_to(ROOT)
    except ValueError:
        return {"name": name, "ok": False, "description": description, "path": str(resolved), "error": "outside_repo_root"}
    return {
        "name": name,
        "ok": resolved.is_file(),
        "description": description,
        "path": str(relative),
        **({} if resolved.is_file() else {"error": "file_not_found"}),
    }
