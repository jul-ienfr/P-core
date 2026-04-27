import json
import subprocess

from prediction_core.storage.health import storage_health
from prediction_core.storage.readiness import SECTION_NAMES, storage_readiness_bundle, storage_readiness_section


SCRIPT = "../python/scripts/prediction-core"


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
