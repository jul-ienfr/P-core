import json
import subprocess
import sys
from pathlib import Path

from weather_pm.live_observer_config import load_live_observer_config
from weather_pm.live_observer_storage_estimator import estimate_live_observer_storage


def test_realistic_storage_estimate_is_about_four_gb_per_month(monkeypatch):
    monkeypatch.setenv("WEATHER_LIVE_OBSERVER_SCENARIO", "realistic")
    config = load_live_observer_config(Path("config/weather_live_observer.yaml"))

    estimate = estimate_live_observer_storage(config)

    assert estimate.scenario == "realistic"
    assert estimate.collection_enabled is True
    assert estimate.collection_active is True
    assert estimate.estimate_applies_if_enabled is False
    assert 120 <= estimate.mb_per_day <= 140
    assert 3.5 <= estimate.gb_per_month <= 4.1


def test_disabled_streams_reduce_only_that_stream_to_zero(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: 1
active_scenario: minimal
collection:
  enabled: true
  dry_run: false
streams:
  forecasts:
    enabled: false
  account_trades:
    enabled: false
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
  primary: local_jsonl
safety:
  paper_only: true
  live_order_allowed: false
""",
        encoding="utf-8",
    )
    config = load_live_observer_config(path)

    estimate = estimate_live_observer_storage(config)

    assert estimate.collection_enabled is True
    assert estimate.collection_active is True
    assert estimate.streams["forecast_source_snapshot"].enabled is False
    assert estimate.streams["forecast_source_snapshot"].bytes_per_day == 0
    assert estimate.streams["followed_account_trade_trigger"].enabled is False
    assert estimate.streams["followed_account_trade_trigger"].bytes_per_day == 0
    assert estimate.streams["compact_market_snapshot"].bytes_per_day > 0
    assert estimate.streams["weather_bin_surface_snapshot"].bytes_per_day > 0


def test_default_live_estimate_is_active_minimal_local_jsonl():
    config = load_live_observer_config(Path("config/weather_live_observer.yaml"))

    estimate = estimate_live_observer_storage(config)

    assert estimate.scenario == "minimal"
    assert estimate.collection_enabled is True
    assert estimate.collection_active is True
    assert estimate.estimate_applies_if_enabled is False
    assert estimate.mb_per_day > 0
    assert estimate.active_mb_per_day > 0
    assert estimate.storage_primary == "local_jsonl"
    assert estimate.base_dir == "/mnt/truenas/p-core/polymarket/live_observer"
    assert estimate.paper_only is True
    assert estimate.live_order_allowed is False


def test_cli_live_observer_config_estimate_outputs_json():
    result = subprocess.run(
        [sys.executable, "-m", "weather_pm.cli", "live-observer-config", "estimate"],
        cwd=Path.cwd(),
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)

    assert payload["scenario"] == "minimal"
    assert payload["collection_enabled"] is True
    assert payload["collection_active"] is True
    assert payload["estimate_applies_if_enabled"] is False
    assert payload["mb_per_day"] > 0
    assert payload["gb_per_month"] > 0
    assert payload["active_mb_per_day"] > 0
    assert payload["storage_primary"] == "local_jsonl"
    assert payload["base_dir"] == "/mnt/truenas/p-core/polymarket/live_observer"
    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
