import json
from dataclasses import replace
from pathlib import Path

from weather_pm.live_observer import run_live_observer_once
from weather_pm.live_observer_config import load_live_observer_config


def _config_text(base_dir: Path, *, enabled: bool = False, dry_run: bool = True) -> str:
    enabled_text = "true" if enabled else "false"
    dry_run_text = "true" if dry_run else "false"
    return f"""
version: 1
active_scenario: minimal
collection:
  enabled: {enabled_text}
  dry_run: {dry_run_text}
  reason: test_reason
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
  require_mountpoint: null
  refuse_if_not_mounted: true
"""


def _load_config(tmp_path: Path, *, enabled: bool = False, dry_run: bool = True):
    path = tmp_path / "config.yaml"
    path.write_text(_config_text(tmp_path / "observer", enabled=enabled, dry_run=dry_run), encoding="utf-8")
    return load_live_observer_config(path)


def test_fixture_dry_run_produces_json_compatible_summary_without_writes(tmp_path):
    config = _load_config(tmp_path, enabled=False, dry_run=True)

    summary = run_live_observer_once(config, source="fixture", dry_run=True)
    payload = summary.to_dict()

    assert payload["scenario"] == "minimal"
    assert payload["source"] == "fixture"
    assert payload["dry_run"] is True
    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    assert payload["snapshots"] == {
        "compact_market_snapshot": 1,
        "weather_bin_surface_snapshot": 1,
        "forecast_source_snapshot": 1,
        "followed_account_trade_trigger": 1,
    }
    assert set(payload["storage_results"]) == set(payload["snapshots"])
    assert all(result["status"] == "dry_run" for result in payload["storage_results"].values())
    assert payload["errors"] == []
    json.dumps(payload)
    assert not (tmp_path / "observer").exists()


def test_disabled_collection_non_dry_fixture_is_noop(tmp_path):
    config = _load_config(tmp_path, enabled=False, dry_run=False)

    payload = run_live_observer_once(config, source="fixture", dry_run=False).to_dict()

    assert payload["collection_active"] is False
    assert payload["snapshots"] == {}
    assert payload["storage_results"] == {}
    assert payload["errors"][0]["code"] == "collection_disabled"
    assert not (tmp_path / "observer").exists()


def test_enabled_fixture_run_writes_local_jsonl_rows(tmp_path):
    config = _load_config(tmp_path, enabled=True, dry_run=False)

    payload = run_live_observer_once(config, source="fixture", dry_run=False).to_dict()

    assert payload["collection_active"] is True
    assert payload["errors"] == []
    assert payload["snapshots"]["compact_market_snapshot"] == 1
    result = payload["storage_results"]["compact_market_snapshot"]
    assert result["status"] == "written"
    assert result["row_count"] == 1
    output_path = Path(result["path_or_uri"])
    assert output_path.exists()
    row = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])
    for key in ("retention_policy", "compressed", "source", "captured_at", "paper_only", "live_order_allowed"):
        assert key in row
    assert row["retention_policy"] == "raw_days=None;compact_days=None;aggregate_days=None"
    assert row["compressed"] is False
    assert row["source"] == "weather_pm.live_observer.fixture"
    assert row["paper_only"] is True
    assert row["live_order_allowed"] is False


def test_winner_pattern_watchlist_mode_limits_live_capture_scope(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        _config_text(tmp_path / "observer", enabled=True, dry_run=False)
        + """
streams:
  market_snapshots:
    enabled: true
  bin_surfaces:
    enabled: true
  forecasts:
    enabled: true
  account_trades:
    enabled: true
  full_books:
    enabled: true
followed_accounts:
  ColdMath:
    enabled: true
""",
        encoding="utf-8",
    )
    config = load_live_observer_config(config_path)
    calls = []

    def fake_list_weather_markets(*, source, limit):
        calls.append(("markets", source, limit))
        return [
            {
                "id": "paris-high-22",
                "event_id": "paris-weather-2026-05-04",
                "slug": "paris-high-22",
                "question": "Will the highest temperature in Paris be 22C or higher on May 4, 2026?",
                "best_bid": 0.40,
                "best_ask": 0.42,
                "active": True,
                "closed": False,
            }
        ]

    def fake_list_followed_account_trades(*, accounts, limit, after_timestamp=None):
        calls.append(("account_trades", tuple(accounts), limit, after_timestamp))
        return [
            {
                "userName": "ColdMath",
                "transactionHash": "0xwatch",
                "conditionId": "paris-high-22",
                "side": "BUY",
                "price": 0.41,
                "size": 12,
                "timestamp": "2026-04-29T12:00:00+00:00",
                "title": "Will the highest temperature in Paris be 22C or higher on May 4, 2026?",
            }
        ]

    monkeypatch.setattr("weather_pm.live_observer.list_weather_markets", fake_list_weather_markets)
    monkeypatch.setattr("weather_pm.live_observer.list_followed_account_trades", fake_list_followed_account_trades)

    payload = run_live_observer_once(config, source="live", dry_run=False, mode="winner_pattern_watchlist").to_dict()

    assert payload["mode"] == "winner_pattern_watchlist"
    assert payload["watchlist_capture_scope"] == [
        "current_orderbook_compact_snapshots_for_matched_surfaces",
        "full_book_only_on_account_trade_large_movement_or_candidate_trigger",
        "forecast_snapshots",
        "market_surface_snapshots",
        "observed_account_trades",
    ]
    assert payload["full_book_policy"] == "account_trade_large_movement_or_candidate_trigger_only"
    assert payload["snapshots"] == {"compact_market_snapshot": 1, "followed_account_trade_trigger": 1}
    assert calls == [("markets", "live", 100), ("account_trades", ("ColdMath",), 10, None)]


def test_live_observer_refuses_unmounted_truenas_write_before_creating_files(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    fake_mount = tmp_path / "mnt" / "truenas"
    fake_base = fake_mount / "p-core" / "polymarket" / "live_observer"
    config_path.write_text(
        _config_text(fake_base, enabled=True, dry_run=False).replace(
            "require_mountpoint: null",
            f"require_mountpoint: {fake_mount}",
        ),
        encoding="utf-8",
    )
    config = load_live_observer_config(config_path)
    monkeypatch.setattr("os.path.ismount", lambda path: False)

    payload = run_live_observer_once(config, source="fixture", dry_run=False).to_dict()

    assert payload["snapshots"]["compact_market_snapshot"] == 1
    assert payload["errors"][0]["code"] == "storage_error"
    assert "not a mountpoint" in payload["errors"][0]["message"]
    assert all(result["status"] == "error" for result in payload["storage_results"].values())
    assert not (fake_base / "jsonl" / "compact_market_snapshot.jsonl").exists()


def test_live_source_collects_bounded_public_weather_snapshots_when_active(monkeypatch, tmp_path):
    config = _load_config(tmp_path, enabled=True, dry_run=False)

    calls = []

    def fake_list_weather_markets(*, source, limit):
        calls.append((source, limit))
        return [
            {
                "id": "nyc-high-50",
                "event_id": "nyc-weather-2026-01-02",
                "slug": "nyc-high-50",
                "question": "Will the highest temperature in New York City be 50F or higher on Jan 2, 2026?",
                "best_bid": 0.48,
                "best_ask": 0.52,
                "yes_price": 0.50,
                "volume": 1000,
                "liquidity": 500,
                "active": True,
                "closed": False,
            },
            {
                "id": "london-high-11",
                "event_id": "london-weather-2026-01-02",
                "slug": "london-high-11",
                "question": "Will the highest temperature in London be exactly 11C on January 2?",
                "best_bid": 0.30,
                "best_ask": 0.34,
                "yes_price": 0.32,
                "volume": 2000,
                "liquidity": 750,
                "active": True,
                "closed": False,
            },
        ]

    monkeypatch.setattr("weather_pm.live_observer.list_weather_markets", fake_list_weather_markets)

    payload = run_live_observer_once(config, source="live", dry_run=False).to_dict()

    assert calls == [("live", 100)]
    assert payload["source"] == "live"
    assert payload["errors"] == []
    assert payload["snapshots"]["compact_market_snapshot"] == 2
    assert payload["snapshots"].get("followed_account_trade_trigger", 0) == 0
    result = payload["storage_results"]["compact_market_snapshot"]
    assert result["status"] == "written"
    rows = Path(result["path_or_uri"]).read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 2
    first = json.loads(rows[0])
    assert first["paper_only"] is True
    assert first["live_order_allowed"] is False
    assert first["metadata"]["source"] == "live_gamma_public"


def test_live_source_respects_market_limit_and_dry_run(monkeypatch, tmp_path):
    config = _load_config(tmp_path, enabled=True, dry_run=False)
    calls = []

    def fake_list_weather_markets(*, source, limit):
        calls.append((source, limit))
        return []

    monkeypatch.setattr("weather_pm.live_observer.list_weather_markets", fake_list_weather_markets)

    payload = run_live_observer_once(config, source="live", dry_run=True).to_dict()

    assert calls == [("live", 100)]
    assert payload["dry_run"] is True
    assert payload["errors"] == []
    assert payload["snapshots"] == {}
    assert not (tmp_path / "observer").exists()


def test_live_source_includes_only_enabled_followed_accounts(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        _config_text(tmp_path / "observer", enabled=True, dry_run=False)
        + """
followed_accounts:
  ColdMath:
    enabled: true
  DisabledWhale:
    enabled: false
    reason: paused
  RainEdge:
    enabled: true
""",
        encoding="utf-8",
    )
    config = load_live_observer_config(config_path)

    calls = []

    def fake_list_weather_markets(*, source, limit):
        return []

    def fake_list_followed_account_trades(*, accounts, limit, after_timestamp=None):
        calls.append((tuple(accounts), limit, after_timestamp))
        return [
            {
                "account": "ColdMath",
                "profile_id": "shadow_coldmath_v0",
                "transaction_hash": "0xabc",
                "market_id": "weather-1",
                "side": "yes",
                "price": 0.57,
                "size": 42,
                "observed_at": "2026-01-01T00:00:00+00:00",
                "event_id": "event-1",
            }
        ]

    monkeypatch.setattr("weather_pm.live_observer.list_weather_markets", fake_list_weather_markets)
    monkeypatch.setattr("weather_pm.live_observer.list_followed_account_trades", fake_list_followed_account_trades)

    payload = run_live_observer_once(config, source="live", dry_run=False).to_dict()

    assert calls == [(("ColdMath", "RainEdge"), 10, None)]
    assert payload["errors"] == []
    assert payload["snapshots"]["followed_account_trade_trigger"] == 1
    result = payload["storage_results"]["followed_account_trade_trigger"]
    rows = Path(result["path_or_uri"]).read_text(encoding="utf-8").strip().splitlines()
    trigger = json.loads(rows[0])
    assert trigger["account"] == "ColdMath"
    assert trigger["paper_decision"] == "capture_rich_snapshot"
    assert trigger["paper_only"] is True
    assert trigger["live_order_allowed"] is False


def test_live_source_deduplicates_public_account_trade_triggers(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        _config_text(tmp_path / "observer", enabled=True, dry_run=False)
        + """
followed_accounts:
  ColdMath:
    enabled: true
""",
        encoding="utf-8",
    )
    config = load_live_observer_config(config_path)

    def fake_list_weather_markets(*, source, limit):
        return []

    def fake_list_followed_account_trades(*, accounts, limit, after_timestamp=None):
        return [
            {
                "proxyWallet": "0xabc",
                "userName": "ColdMath",
                "transactionHash": "0xdup",
                "conditionId": "weather-1",
                "side": "BUY",
                "price": 0.57,
                "size": 42,
                "timestamp": 1777420036,
                "title": "Will the highest temperature in London be 20C or higher on April 25?",
                "eventSlug": "london-weather-april-25",
            },
            {
                "proxyWallet": "0xabc",
                "userName": "ColdMath",
                "transactionHash": "0xdup",
                "conditionId": "weather-1",
                "side": "BUY",
                "price": 0.57,
                "size": 42,
                "timestamp": 1777420036,
                "title": "Will the highest temperature in London be 20C or higher on April 25?",
            },
            {
                "proxyWallet": "0xabc",
                "userName": "ColdMath",
                "transactionHash": "0xnonweather",
                "conditionId": "sports-1",
                "side": "BUY",
                "price": 0.57,
                "size": 42,
                "timestamp": 1777420037,
                "title": "Will CA San Lorenzo de Almagro vs. Santos FC end in a draw?",
            },
        ]

    monkeypatch.setattr("weather_pm.live_observer.list_weather_markets", fake_list_weather_markets)
    monkeypatch.setattr("weather_pm.live_observer.list_followed_account_trades", fake_list_followed_account_trades)

    payload = run_live_observer_once(config, source="live", dry_run=False).to_dict()

    assert payload["errors"] == []
    assert payload["snapshots"]["followed_account_trade_trigger"] == 1
    rows = Path(payload["storage_results"]["followed_account_trade_trigger"]["path_or_uri"]).read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1
    trigger = json.loads(rows[0])
    assert trigger["transaction_hash"] == "0xdup"
    assert trigger["market_id"] == "weather-1"
    assert trigger["metadata"]["source"] == "polymarket_public_trades"
    assert trigger["metadata"]["dedupe_key"] == "0xdup:weather-1:0xabc"
