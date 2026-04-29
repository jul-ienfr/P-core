from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from weather_pm.account_learning import build_shadow_profile_deep_dive, build_shadow_profiles, load_account_trade_backfill

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "account_trades_backfill.json"


def _run_weather_pm(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "weather_pm.cli", *args],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
    )


def test_load_account_trade_backfill_normalizes_weather_profile_buckets() -> None:
    payload = load_account_trade_backfill(FIXTURE)

    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    assert payload["trade_count"] == 3
    assert payload["accounts"] == 2
    first = payload["trades"][0]
    assert first["wallet"] == "0xrain"
    assert first["city"] == "NYC"
    assert first["market_type"] == "threshold"
    assert first["timing_bucket"] == "same_day_close"
    assert first["size_bucket"] == "small_10_100"
    assert first["price_bucket"] == "25_50c"


def test_build_shadow_profiles_summarizes_sizing_timing_city_type_and_abstention() -> None:
    trades = load_account_trade_backfill(FIXTURE)
    report = build_shadow_profiles(trades)

    assert report["artifact"] == "shadow_profiles"
    assert report["summary"]["accounts"] == 2
    storm, rain = report["profiles"]
    assert storm["wallet"] == "0xstorm"
    assert storm["sizing_buckets"] == {"large_1000_plus": 1}
    assert storm["price_buckets"] == {"90_100c": 1}
    assert "sparse_public_weather_sample" in storm["abstention_signals"]
    assert rain["city_buckets"] == {"NYC": 2}
    assert rain["type_buckets"] == {"exact_bin_or_temp_surface": 1, "threshold": 1}
    assert rain["timing_buckets"] == {"one_to_three_days": 1, "same_day_close": 1}


def test_deep_dive_selects_profile_by_handle() -> None:
    profiles = build_shadow_profiles(load_account_trade_backfill(FIXTURE))
    report = build_shadow_profile_deep_dive(profiles, handle="RainProbe")

    assert report["profile"]["wallet"] == "0xrain"
    assert report["operator_notes"][0].startswith("Use as account-learning prior only")


def test_account_learning_cli_pipeline_writes_json_and_markdown(tmp_path: Path) -> None:
    result = _run_weather_pm(
        "account-learning-backfill",
        "--input-json",
        str(FIXTURE),
        "--output-dir",
        str(tmp_path),
        "--run-id",
        "test-run",
    )

    assert result.returncode == 0, result.stderr
    stdout_payload = json.loads(result.stdout)
    assert stdout_payload["run_id"] == "test-run"
    trades_json = tmp_path / "account_trades.json"
    profiles_json = tmp_path / "shadow_profiles.json"
    profiles_md = tmp_path / "shadow_profiles.md"
    assert trades_json.exists()
    assert profiles_json.exists()
    assert profiles_md.exists()
    assert json.loads(trades_json.read_text(encoding="utf-8"))["trade_count"] == 3
    assert "Read-only profile artifact" in profiles_md.read_text(encoding="utf-8")


def test_shadow_profiles_deep_dive_cli_writes_markdown(tmp_path: Path) -> None:
    trades_json = tmp_path / "account_trades.json"
    profiles_json = tmp_path / "shadow_profiles.json"
    deep_dive_md = tmp_path / "rain.md"
    import_result = _run_weather_pm("account-trades-import", "--input-json", str(FIXTURE), "--output-json", str(trades_json))
    assert import_result.returncode == 0, import_result.stderr
    report_result = _run_weather_pm("shadow-profiles-report", "--trades-json", str(trades_json), "--output-json", str(profiles_json))
    assert report_result.returncode == 0, report_result.stderr

    deep_dive_result = _run_weather_pm(
        "shadow-profiles-deep-dive",
        "--profiles-json",
        str(profiles_json),
        "--handle",
        "RainProbe",
        "--output-md",
        str(deep_dive_md),
    )

    assert deep_dive_result.returncode == 0, deep_dive_result.stderr
    assert "Shadow profile deep dive: RainProbe" in deep_dive_md.read_text(encoding="utf-8")
