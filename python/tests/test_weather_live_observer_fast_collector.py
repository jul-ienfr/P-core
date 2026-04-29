import json
import subprocess
import sys
from pathlib import Path

from weather_pm.live_observer_config import load_live_observer_config


BASE_CONFIG = """
version: 1
active_scenario: minimal
collection:
  enabled: true
  dry_run: false
  reason: test_fast_collector
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
  analytics: null
  archive: local_jsonl
paths:
  base_dir: {base_dir}
  jsonl_dir: {base_dir}/jsonl
  parquet_dir: {base_dir}/parquet
  reports_dir: {base_dir}/reports
  manifests_dir: {base_dir}/manifests
safety:
  paper_only: true
  live_order_allowed: false
  allow_wallet: false
  allow_signing: false
"""


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "weather_live_observer.yaml"
    path.write_text(BASE_CONFIG.format(base_dir=tmp_path / "observer"), encoding="utf-8")
    return path


def test_fast_collector_dry_run_uses_trade_poll_interval_and_marks_non_report_mode(tmp_path):
    from weather_pm.live_observer import run_live_observer_fast_collector

    config = load_live_observer_config(_write_config(tmp_path))

    payload = run_live_observer_fast_collector(config, source="fixture", dry_run=True, max_iterations=1).to_dict()

    assert payload["mode"] == "fast_collector"
    assert payload["report_delivery"] == "none"
    assert payload["poll_interval_seconds"] == 300
    assert payload["iterations"] == 1
    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    assert payload["runs"][0]["source"] == "fixture"
    assert payload["runs"][0]["snapshots"]["followed_account_trade_trigger"] == 1
    assert payload["snapshots_total"]["followed_account_trade_trigger"] == 1
    assert not (tmp_path / "observer").exists()


def test_fast_collector_never_writes_report_artifacts_even_when_rows_are_persisted(tmp_path):
    from weather_pm.live_observer import run_live_observer_fast_collector

    config = load_live_observer_config(_write_config(tmp_path))

    payload = run_live_observer_fast_collector(config, source="fixture", dry_run=False, max_iterations=1).to_dict()

    assert payload["mode"] == "fast_collector"
    assert payload["report_delivery"] == "none"
    assert payload["runs"][0]["storage_results"]["followed_account_trade_trigger"]["status"] == "written"
    assert (tmp_path / "observer" / "jsonl" / "followed_account_trade_trigger.jsonl").exists()
    assert not (tmp_path / "observer" / "reports").exists()
    assert not (tmp_path / "observer" / "manifests").exists()


def test_live_observer_cli_fast_collector_outputs_json_without_report_delivery(tmp_path):
    config_path = _write_config(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "live-observer",
            "fast-collector",
            "--source",
            "fixture",
            "--dry-run",
            "--max-iterations",
            "1",
            "--config",
            str(config_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["mode"] == "fast_collector"
    assert payload["report_delivery"] == "none"
    assert payload["runs"][0]["source"] == "fixture"
