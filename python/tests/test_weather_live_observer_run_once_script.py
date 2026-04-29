import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "weather_live_observer_run_once.py"
DOC = ROOT / "docs" / "weather-live-observer-config.md"


def _config_text(base_dir: Path, *, enabled: bool = True, dry_run: bool = False) -> str:
    return f"""
version: 1
active_scenario: minimal
collection:
  enabled: {str(enabled).lower()}
  dry_run: {str(dry_run).lower()}
  reason: script_test
streams:
  market_snapshots:
    enabled: true
  bin_surfaces:
    enabled: true
  forecasts:
    enabled: true
  account_trades:
    enabled: true
scenarios:
  minimal:
    market_limit: 100
    surface_limit: 25
    followed_account_limit: 10
    compact_market_snapshot_interval_seconds: 300
    bin_surface_snapshot_interval_seconds: 300
    forecast_snapshot_interval_seconds: 1800
    trade_trigger_poll_interval_seconds: 300
storage:
  enabled: true
  primary: local_jsonl
  analytics: clickhouse
  archive: local_parquet
paths:
  base_dir: {base_dir}
  jsonl_dir: {base_dir}/jsonl
  parquet_dir: {base_dir}/parquet
  reports_dir: {base_dir}/reports
  manifests_dir: {base_dir}/manifests
safety:
  paper_only: true
  live_order_allowed: false
"""


def _run(args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_weather_live_observer_operator_doc_covers_run_once_and_scheduling() -> None:
    text = DOC.read_text(encoding="utf-8")
    for label in [
        "scenario changes",
        "local path",
        "NAS path",
        "NAS/MinIO",
        "estimate",
        "dry-run",
        "rollback local",
        "kill switch",
        "paper-only",
        "weather_live_observer_run_once.py",
        "cron",
        "systemd",
        "no cron or systemd unit is installed by this repo",
    ]:
        assert label in text


def test_run_once_script_fixture_writes_json_and_markdown_reports(tmp_path):
    config_path = tmp_path / "config.yaml"
    base_dir = tmp_path / "observer"
    config_path.write_text(_config_text(base_dir), encoding="utf-8")
    json_report = tmp_path / "reports" / "summary.json"
    md_report = tmp_path / "reports" / "summary.md"

    result = _run([
        "--config",
        str(config_path),
        "--source",
        "fixture",
        "--summary-json",
        str(json_report),
        "--summary-md",
        str(md_report),
    ])

    assert result.returncode == 0, result.stderr
    stdout_payload = json.loads(result.stdout)
    report_payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert stdout_payload == report_payload
    assert report_payload["source"] == "fixture"
    assert report_payload["snapshots"]["compact_market_snapshot"] == 1
    assert "# Weather Live Observer Run Summary" in md_report.read_text(encoding="utf-8")
    assert "Paper-only: true" in md_report.read_text(encoding="utf-8")


def test_run_once_script_live_readonly_success_writes_public_market_summary(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_config_text(tmp_path / "observer"), encoding="utf-8")

    result = _run(["--config", str(config_path), "--source", "live", "--dry-run"])

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["source"] == "live"
    assert payload["errors"] == []
    assert payload["snapshots"].get("compact_market_snapshot", 0) >= 0


def test_run_once_script_invalid_config_exits_nonzero(tmp_path):
    config_path = tmp_path / "bad.yaml"
    config_path.write_text("active_scenario: unknown\nscenarios: {}\n", encoding="utf-8")

    result = _run(["--config", str(config_path), "--source", "fixture"])

    assert result.returncode != 0
    assert "unknown active_scenario" in result.stderr


def test_run_once_script_refuses_summary_path_without_writable_parent(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_config_text(tmp_path / "observer"), encoding="utf-8")
    missing_parent_report = tmp_path / "missing" / "summary.json"

    result = _run([
        "--config",
        str(config_path),
        "--source",
        "fixture",
        "--summary-json",
        str(missing_parent_report),
        "--no-create-report-dirs",
    ])

    assert result.returncode != 0
    assert "summary parent directory does not exist" in result.stderr
