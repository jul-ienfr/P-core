from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "weather_account_learning"
PYTHON_SRC = Path(__file__).resolve().parents[1] / "src"


def _run_weather_pm(*args: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-m", "weather_pm.cli", *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(PYTHON_SRC)},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_weather_account_learning_top10_to_patterns_to_paper_replay_smoke(tmp_path: Path) -> None:
    """Replay the paper-only account-learning path without network access."""
    analysis_dir = tmp_path / "data" / "polymarket" / "account-analysis"
    analysis_dir.mkdir(parents=True)

    raw_trades = FIXTURE_DIR / "public_account_trades_backfilled.json"
    followlist = FIXTURE_DIR / "weather_followlist_top10.csv"
    markets = FIXTURE_DIR / "markets.json"
    orderbooks = FIXTURE_DIR / "orderbooks.json"
    forecasts = FIXTURE_DIR / "forecasts.json"
    resolutions = FIXTURE_DIR / "resolutions.json"
    assert all(path.exists() for path in (raw_trades, followlist, markets, orderbooks, forecasts, resolutions))

    weather_trades = analysis_dir / "weather_trades.json"
    profiles = analysis_dir / "account_profiles.json"
    dataset = analysis_dir / "trade_no_trade_dataset.json"
    profile_report = analysis_dir / "shadow_profile_report.json"
    patterns = analysis_dir / "learned_patterns.json"
    patterns_md = analysis_dir / "learned_patterns.md"
    paper_orders = analysis_dir / "shadow_paper_orders.json"

    import_result = _run_weather_pm(
        "import-account-trades",
        "--trades-json",
        str(raw_trades),
        "--trades-out",
        str(weather_trades),
        "--profiles-out",
        str(profiles),
    )
    assert import_result["summary"]["weather_trades"] >= 1

    profile_result = _run_weather_pm(
        "shadow-profile-report",
        "--weather-trades-json",
        str(weather_trades),
        "--markets-json",
        str(markets),
        "--dataset-out",
        str(dataset),
        "--report-out",
        str(profile_report),
        "--accounts-csv",
        str(followlist),
        "--limit-accounts",
        "10",
    )
    assert profile_result["summary"]["trade_examples"] >= 1
    assert profile_result["summary"]["no_trade_examples"] >= 1

    patterns_result = _run_weather_pm(
        "shadow-patterns-report",
        "--dataset-json",
        str(dataset),
        "--output-json",
        str(patterns),
        "--output-md",
        str(patterns_md),
        "--limit",
        "10",
    )
    assert patterns_result["summary"]["trade_examples"] >= 1
    assert patterns_result["summary"]["no_trade_examples"] >= 1

    paper_result = _run_weather_pm(
        "shadow-paper-runner",
        "--dataset-json",
        str(dataset),
        "--orderbooks-json",
        str(orderbooks),
        "--forecasts-json",
        str(forecasts),
        "--run-id",
        "weather-account-learning-smoke",
        "--output-json",
        str(paper_orders),
    )
    assert paper_result["summary"]["paper_orders"] >= 1

    for artifact in (weather_trades, profiles, dataset, profile_report, patterns, patterns_md, paper_orders):
        assert artifact.exists(), artifact

    json_artifacts = (weather_trades, profiles, dataset, profile_report, patterns, paper_orders)
    for artifact in json_artifacts:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        assert payload["paper_only"] is True, artifact
        assert payload["live_order_allowed"] is False, artifact

    dataset_payload = json.loads(dataset.read_text(encoding="utf-8"))
    assert dataset_payload["summary"]["trade_examples"] >= 1
    assert dataset_payload["summary"]["no_trade_examples"] >= 1

    order_payload = json.loads(paper_orders.read_text(encoding="utf-8"))
    assert order_payload["summary"]["paper_orders"] >= 1
    assert all(order["paper_only"] is True and order["live_order_allowed"] is False for order in order_payload["orders"])
