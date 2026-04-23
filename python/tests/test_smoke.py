from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_cli_help_exits_cleanly() -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root / "src")

    result = subprocess.run(
        [sys.executable, "-m", "weather_pm.cli", "--help"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0
    assert "fetch-markets" in result.stdout
    assert "fetch-event-book" in result.stdout
    assert "paper-cycle" in result.stdout


def test_cli_fetch_event_book_fixture_emits_event_container_json() -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root / "src")

    result = subprocess.run(
        [sys.executable, "-m", "weather_pm.cli", "fetch-event-book", "--market-id", "denver-daily-highs", "--source", "fixture"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0
    payload = __import__("json").loads(result.stdout)
    assert payload["event"]["id"] == "denver-daily-highs"
    assert payload["event"]["category"] == "weather"
    assert payload["event"]["rules"] is not None
    assert payload["markets"][0]["id"] == "denver-high-64"
    assert payload["markets"][0]["spread"] == 0.03
    assert payload["markets"][0]["volume_usd"] == 14000.0
