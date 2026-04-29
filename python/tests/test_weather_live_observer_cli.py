import json
import subprocess
import sys
from pathlib import Path


def _copy_default_config(tmp_path: Path) -> Path:
    path = tmp_path / "weather_live_observer.yaml"
    path.write_text(Path("config/weather_live_observer.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    return path


def _run_cli(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "weather_pm.cli", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_live_observer_config_show_json_includes_redacted_config_and_estimate(tmp_path):
    config_path = _copy_default_config(tmp_path)

    payload = _run_cli("live-observer-config", "show", "--json", "--config", str(config_path))

    assert payload["config"]["active_scenario"] == "minimal"
    assert payload["config"]["safety"]["paper_only"] is True
    assert payload["config"]["safety"]["live_order_allowed"] is False
    assert payload["config"]["collection"]["enabled"] is True
    assert payload["config"]["collection"]["dry_run"] is False
    assert len(payload["config"]["followed_accounts"]) == 10
    assert "estimate" in payload
    assert payload["estimate"]["scenario"] == "minimal"


def test_set_scenario_realistic_modifies_only_active_scenario(tmp_path):
    config_path = _copy_default_config(tmp_path)
    before = config_path.read_text(encoding="utf-8")

    payload = _run_cli("live-observer-config", "set-scenario", "realistic", "--config", str(config_path))
    after = config_path.read_text(encoding="utf-8")

    assert payload["active_scenario"] == "realistic"
    assert "active_scenario: realistic" in after
    assert before.replace("active_scenario: minimal      #", "active_scenario: realistic   #") == after


def test_set_storage_and_set_path_update_expected_yaml_fields(tmp_path):
    config_path = _copy_default_config(tmp_path)

    storage = _run_cli(
        "live-observer-config",
        "set-storage",
        "--primary",
        "local_jsonl",
        "--analytics",
        "clickhouse",
        "--archive",
        "local_parquet",
        "--config",
        str(config_path),
    )
    paths = _run_cli(
        "live-observer-config",
        "set-path",
        "--base-dir",
        "/mnt/truenas/p-core/polymarket/live_observer",
        "--config",
        str(config_path),
    )

    assert storage["storage"] == {
        "primary": "local_jsonl",
        "analytics": "clickhouse",
        "archive": "local_parquet",
    }
    assert paths["paths"]["jsonl_dir"] == "/mnt/truenas/p-core/polymarket/live_observer/jsonl"
    shown = _run_cli("live-observer-config", "show", "--json", "--config", str(config_path))
    assert shown["config"]["storage"]["primary"] == "local_jsonl"


def test_live_observer_run_once_fixture_dry_run_outputs_summary_json(tmp_path):
    config_path = _copy_default_config(tmp_path)

    payload = _run_cli("live-observer", "run-once", "--source", "fixture", "--dry-run", "--config", str(config_path))

    assert payload["source"] == "fixture"
    assert payload["dry_run"] is True
    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    assert payload["snapshots"]["compact_market_snapshot"] == 1


def test_toggle_commands_with_reason_reflected_in_show_json(tmp_path):
    config_path = _copy_default_config(tmp_path)

    _run_cli("live-observer-config", "enable", "collection", "--reason", "test_enable", "--config", str(config_path))
    _run_cli("live-observer-config", "disable", "stream", "forecasts", "--reason", "test_pause", "--config", str(config_path))
    _run_cli("live-observer-config", "disable", "profile", "shadow_coldmath_v0", "--reason", "profile_pause", "--config", str(config_path))
    payload = _run_cli("live-observer-config", "show", "--json", "--config", str(config_path))

    assert payload["config"]["collection"]["enabled"] is True
    assert payload["config"]["collection"]["reason"] == "test_enable"
    assert payload["config"]["streams"]["forecasts"]["enabled"] is False
    assert payload["config"]["streams"]["forecasts"]["reason"] == "test_pause"
    assert payload["config"]["profiles"]["shadow_coldmath_v0"]["enabled"] is False
    assert payload["config"]["profiles"]["shadow_coldmath_v0"]["reason"] == "profile_pause"
