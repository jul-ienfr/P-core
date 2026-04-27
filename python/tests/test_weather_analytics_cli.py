from pathlib import Path
import json
import os
import stat
import subprocess
import sys

from weather_pm import cli

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "python" / "tests" / "fixtures" / "weather_analytics_shortlist.json"
SMOKE_CLICKHOUSE = ROOT / "infra" / "analytics" / "scripts" / "smoke_clickhouse.sh"
SMOKE_WEATHER_EXPORT = ROOT / "infra" / "analytics" / "scripts" / "smoke_weather_export.sh"


def test_weather_analytics_export_dry_run(tmp_path: Path) -> None:
    payload = {
        "run_id": "run-1",
        "generated_at": "2026-04-27T12:00:00+00:00",
        "rows": [
            {
                "market_id": "m1",
                "strategy_id": "weather_bookmaker_v1",
                "strategy_profile_id": "surface_grid_trader",
                "decision_status": "skip",
                "execution_blocker": "edge_below_threshold",
            }
        ],
    }
    input_path = tmp_path / "shortlist.json"
    input_path.write_text(json.dumps(payload))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "export-analytics-clickhouse",
            "--shortlist-json",
            str(input_path),
            "--dry-run",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONPATH": "src"},
        text=True,
        capture_output=True,
        check=True,
    )

    assert result.stdout.strip().splitlines() == [
        "analytics.profile_decisions.rows=1",
        "analytics.enabled=false",
    ]


def test_weather_analytics_smoke_fixture_dry_runs() -> None:
    payload = json.loads(FIXTURE.read_text())
    assert payload["run_id"] == "smoke-run-1"
    assert payload["rows"][0]["strategy_profile_id"] == "surface_grid_trader"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "export-analytics-clickhouse",
            "--shortlist-json",
            str(FIXTURE),
            "--dry-run",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": "python/src"},
        text=True,
        capture_output=True,
        check=True,
    )

    assert result.stdout.strip().splitlines() == [
        "analytics.profile_decisions.rows=1",
        "analytics.enabled=false",
    ]


def test_weather_analytics_smoke_scripts_are_executable_and_safe() -> None:
    for script in [SMOKE_CLICKHOUSE, SMOKE_WEATHER_EXPORT]:
        text = script.read_text()
        assert script.stat().st_mode & stat.S_IXUSR
        assert "docker compose version" in text
        assert "docker-compose" in text
        assert "password=prediction" not in text
        assert "password=***" not in text
        assert "--user \"${CLICKHOUSE_USER}:${CLICKHOUSE_PASSWORD}\"" in text


def test_weather_analytics_export_without_clickhouse_config_is_noop(tmp_path: Path) -> None:
    input_path = tmp_path / "shortlist.json"
    input_path.write_text(json.dumps({"run_id": "run-1", "rows": []}))
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PREDICTION_CORE_CLICKHOUSE_")
    }
    env["PYTHONPATH"] = "src"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "export-analytics-clickhouse",
            "--shortlist-json",
            str(input_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert result.stdout.strip().splitlines() == [
        "analytics.profile_decisions.rows=0",
        "analytics.enabled=false",
    ]


def test_weather_analytics_export_inserts_with_env_writer(monkeypatch, tmp_path: Path, capsys) -> None:
    payload = {
        "run_id": "run-1",
        "generated_at": "2026-04-27T12:00:00+00:00",
        "rows": [
            {
                "market_id": "m1",
                "strategy_id": "weather_bookmaker_v1",
                "profile_id": "strict_micro",
                "decision_status": "trade_small",
            }
        ],
    }
    input_path = tmp_path / "shortlist.json"
    input_path.write_text(json.dumps(payload))
    inserted = {}

    class FakeWriter:
        def insert_rows(self, table, rows):
            inserted[table] = rows

    monkeypatch.setattr(cli, "create_clickhouse_writer_from_env", lambda: FakeWriter())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "weather-pm",
            "export-analytics-clickhouse",
            "--shortlist-json",
            str(input_path),
        ],
    )

    assert cli.main() == 0

    assert capsys.readouterr().out.strip().splitlines() == [
        "analytics.profile_decisions.rows=1",
        "analytics.enabled=true",
    ]
    assert inserted["profile_decisions"][0]["run_id"] == "run-1"
    assert inserted["profile_decisions"][0]["profile_id"] == "strict_micro"
    assert inserted["profile_decisions"][0]["market_id"] == "m1"
    assert inserted["debug_decisions"][0]["run_id"] == "run-1"
    assert inserted["profile_metrics"][0]["decision_count"] == 1
    assert inserted["strategy_metrics"][0]["signal_count"] == 1
