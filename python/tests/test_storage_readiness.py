import json
import subprocess
from pathlib import Path

from prediction_core.storage.health import storage_health
from prediction_core.storage.readiness import SECTION_NAMES, storage_live_validation_report, storage_readiness_bundle, storage_readiness_section


SCRIPT = str(Path(__file__).resolve().parents[1] / "scripts" / "prediction-core")


def test_storage_readiness_bundle_contains_six_safe_sections():
    bundle = storage_readiness_bundle()

    assert set(bundle["sections"]) == set(SECTION_NAMES)
    assert bundle["dry_run"] is True
    assert bundle["requires_cloud_credentials"] is False
    assert bundle["provisions_external_services"] is False
    assert bundle["live_trading_enabled"] is False

    for section in bundle["sections"].values():
        assert section["dry_run"] is True
        assert section["requires_cloud_credentials"] is False
        assert section["provisions_external_services"] is False
        assert section["live_trading_enabled"] is False
        assert section["required_files"]
        assert section["validation_commands"]
        assert section["checks"]


def test_secrets_contract_exposes_names_only():
    section = storage_readiness_section("secrets")
    text = json.dumps(section)

    assert "PREDICTION_CORE_DATABASE_URL" in section["secret_names"]
    assert "PREDICTION_CORE_S3_SECRET_ACCESS_KEY" in section["secret_names"]
    assert section["value_policy"] == "names_and_references_only_never_values"
    assert "postgresql://user:pass" not in text
    assert "private_key_value" not in text
    assert "prediction-secret" not in text


def test_launch_gates_cover_storage_and_polymarket_preflight():
    section = storage_readiness_section("launch_gates")

    assert "storage_health_ready_for_live_true" in section["gates"]
    assert "backup_restore_drill_current" in section["gates"]
    assert "monitoring_alerting_reviewed" in section["gates"]
    assert "staging_validation_complete" in section["gates"]
    assert "polymarket_live_preflight_read_only_reviewed" in section["gates"]
    assert section["blocking_rule"] == "any_failed_gate_blocks_live_launch"


def test_storage_readiness_cli_outputs_json_for_every_section():
    for section in ("all", *SECTION_NAMES):
        result = subprocess.run(
            [SCRIPT, "storage-readiness", "--section", section],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["live_trading_enabled"] is False
        assert payload["dry_run"] is True
        assert result.stderr == ""


def test_storage_readiness_cli_pretty_outputs_sorted_json():
    result = subprocess.run(
        [SCRIPT, "storage-readiness", "--section", "monitoring", "--pretty"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "\n  " in result.stdout
    payload = json.loads(result.stdout)
    assert "ready_for_live_false" in payload["alerts"]


def test_storage_health_points_to_materialized_readiness(monkeypatch):
    monkeypatch.delenv("PREDICTION_CORE_SYNC_DATABASE_URL", raising=False)
    monkeypatch.delenv("PANOPTIQUE_SYNC_DATABASE_URL", raising=False)
    health = storage_health()

    assert health["source_of_truth"]["live_trading_enabled"] is False
    assert health["source_of_truth"]["production_readiness_materialized"] is True
    assert health["source_of_truth"]["readiness_command"] == "prediction-core storage-readiness --section all"


def test_storage_live_validation_reports_no_go_without_evidence():
    health = {
        "summary": {"ready_for_live": True, "degraded": False},
        "source_of_truth": {"live_trading_enabled": False},
    }

    report = storage_live_validation_report(health=health)

    assert report["decision"] == "NO_GO"
    assert report["ready_for_live"] is False
    assert report["dry_run"] is True
    assert report["destructive"] is False
    assert {failure["name"] for failure in report["blocking_failures"]} == {
        "backup_evidence",
        "restore_drill_evidence",
        "monitoring_evidence",
        "staging_evidence",
        "operator_approval",
    }


def test_storage_live_validation_reports_go_with_ready_health_and_evidence(tmp_path):
    evidence = {}
    for name in ("backup", "restore", "monitoring", "staging", "approval"):
        path = tmp_path / f"{name}.json"
        path.write_text('{"ok": true}', encoding="utf-8")
        evidence[name] = str(path)
    health = {
        "summary": {"ready_for_live": True, "degraded": False},
        "source_of_truth": {"live_trading_enabled": False},
    }

    report = storage_live_validation_report(
        health=health,
        backup_evidence=evidence["backup"],
        restore_drill_evidence=evidence["restore"],
        monitoring_evidence=evidence["monitoring"],
        staging_evidence=evidence["staging"],
        operator_approval=evidence["approval"],
    )

    assert report["decision"] == "NO_GO"
    assert report["ready_for_live"] is False
    assert {failure["name"] for failure in report["blocking_failures"]} == {
        "backup_evidence",
        "restore_drill_evidence",
        "monitoring_evidence",
        "staging_evidence",
        "operator_approval",
    }
    assert {failure["error"] for failure in report["blocking_failures"]} == {"outside_repo_root"}


def test_storage_live_validation_reports_go_for_repo_local_evidence(tmp_path):
    repo_evidence_dir = tmp_path / "repo"
    repo_evidence_dir.mkdir()
    health = {
        "summary": {"ready_for_live": True, "degraded": False},
        "source_of_truth": {"live_trading_enabled": False},
    }
    from prediction_core.storage import readiness

    original_root = readiness.ROOT
    readiness.ROOT = repo_evidence_dir
    try:
        paths = []
        for name in ("backup", "restore", "monitoring", "staging", "approval"):
            path = repo_evidence_dir / f"{name}.json"
            path.write_text('{"ok": true}', encoding="utf-8")
            paths.append(str(path))

        report = storage_live_validation_report(
            health=health,
            backup_evidence=paths[0],
            restore_drill_evidence=paths[1],
            monitoring_evidence=paths[2],
            staging_evidence=paths[3],
            operator_approval=paths[4],
        )
    finally:
        readiness.ROOT = original_root

    assert report["decision"] == "GO"
    assert report["ready_for_live"] is True
    assert report["blocking_failures"] == []


def test_storage_live_validate_cli_outputs_no_go_json():
    result = subprocess.run(
        [SCRIPT, "storage-live-validate", "--pretty"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["decision"] == "NO_GO"
    assert payload["live_trading_enabled"] is False
    assert payload["destructive"] is False
