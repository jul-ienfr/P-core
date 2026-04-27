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
        "analytics.debug_decisions.rows=1",
        "analytics.execution_events.rows=0",
        "analytics.paper_orders.rows=0",
        "analytics.paper_pnl_snapshots.rows=0",
        "analytics.paper_positions.rows=0",
        "analytics.profile_decisions.rows=1",
        "analytics.profile_metrics.rows=1",
        "analytics.strategy_metrics.rows=1",
        "analytics.strategy_signals.rows=1",
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
        "analytics.debug_decisions.rows=1",
        "analytics.execution_events.rows=0",
        "analytics.paper_orders.rows=0",
        "analytics.paper_pnl_snapshots.rows=0",
        "analytics.paper_positions.rows=0",
        "analytics.profile_decisions.rows=1",
        "analytics.profile_metrics.rows=1",
        "analytics.strategy_metrics.rows=1",
        "analytics.strategy_signals.rows=1",
        "analytics.enabled=false",
    ]


def test_weather_analytics_export_paper_ledger_dry_run(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "run_id": "ledger-run-1",
                "generated_at": "2026-04-27T12:00:00+00:00",
                "summary": {
                    "orders": 1,
                    "filled_usdc": 5.0,
                    "pnl_usdc": 1.0,
                    "opening_fee_usdc": 0.1,
                    "estimated_exit_fee_usdc": 0.2,
                    "net_pnl_after_all_costs": 0.7,
                },
                "orders": [
                    {
                        "order_id": "order-1",
                        "created_at": "2026-04-27T12:00:00+00:00",
                        "updated_at": "2026-04-27T12:05:00+00:00",
                        "market_id": "m1",
                        "token_id": "t1",
                        "side": "NO",
                        "status": "filled",
                        "strict_limit": 0.3,
                        "filled_usdc": 5.0,
                        "shares": 17.5,
                        "avg_fill_price": 0.285714,
                        "mtm_usdc": 6.0,
                    }
                ],
            }
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "export-analytics-clickhouse",
            "--paper-ledger-json",
            str(ledger_path),
            "--dry-run",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONPATH": "src"},
        text=True,
        capture_output=True,
        check=True,
    )

    assert result.stdout.strip().splitlines() == [
        "analytics.debug_decisions.rows=0",
        "analytics.execution_events.rows=0",
        "analytics.paper_orders.rows=1",
        "analytics.paper_pnl_snapshots.rows=1",
        "analytics.paper_positions.rows=1",
        "analytics.profile_decisions.rows=0",
        "analytics.profile_metrics.rows=0",
        "analytics.strategy_metrics.rows=0",
        "analytics.strategy_signals.rows=0",
        "analytics.enabled=false",
    ]


def test_weather_analytics_export_operator_report_as_paper_ledger_dry_run(tmp_path: Path) -> None:
    ledger_path = tmp_path / "operator-report.json"
    ledger_path.write_text(
        json.dumps(
            {
                "report_type": "polymarket_weather_production_operator",
                "artifacts": {"generated_at": "2026-04-27T12:00:00+00:00"},
                "top_current_candidates": [
                    {
                        "market_id": "m1",
                        "side": "YES",
                        "strict_limit": 0.5,
                        "execution": {"fill_status": "filled", "avg_fill_price": 0.5, "fillable_spend": 5.0},
                    }
                ],
            }
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "export-analytics-clickhouse",
            "--paper-ledger-json",
            str(ledger_path),
            "--dry-run",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONPATH": "src"},
        text=True,
        capture_output=True,
        check=True,
    )

    assert result.stdout.strip().splitlines() == [
        "analytics.debug_decisions.rows=0",
        "analytics.execution_events.rows=0",
        "analytics.paper_orders.rows=1",
        "analytics.paper_pnl_snapshots.rows=1",
        "analytics.paper_positions.rows=1",
        "analytics.profile_decisions.rows=0",
        "analytics.profile_metrics.rows=0",
        "analytics.strategy_metrics.rows=0",
        "analytics.strategy_signals.rows=0",
        "analytics.enabled=false",
    ]


def test_weather_analytics_export_execution_events_dry_run(tmp_path: Path) -> None:
    execution_path = tmp_path / "execution.json"
    execution_path.write_text(
        json.dumps(
            {
                "run_id": "exec-run-1",
                "mode": "live",
                "live_orders": [
                    {
                        "order_id": "live-1",
                        "created_at": "2026-04-27T12:00:00+00:00",
                        "strategy_id": "weather_profile_surface_grid_trader_v1",
                        "profile_id": "surface_grid_trader",
                        "market_id": "m1",
                        "status": "submitted",
                    }
                ],
            }
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "export-analytics-clickhouse",
            "--execution-events-json",
            str(execution_path),
            "--dry-run",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONPATH": "src"},
        text=True,
        capture_output=True,
        check=True,
    )

    assert result.stdout.strip().splitlines() == [
        "analytics.debug_decisions.rows=0",
        "analytics.execution_events.rows=1",
        "analytics.paper_orders.rows=0",
        "analytics.paper_pnl_snapshots.rows=0",
        "analytics.paper_positions.rows=0",
        "analytics.profile_decisions.rows=0",
        "analytics.profile_metrics.rows=0",
        "analytics.strategy_metrics.rows=0",
        "analytics.strategy_signals.rows=0",
        "analytics.enabled=false",
    ]


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
        "analytics.debug_decisions.rows=0",
        "analytics.execution_events.rows=0",
        "analytics.paper_orders.rows=0",
        "analytics.paper_pnl_snapshots.rows=0",
        "analytics.paper_positions.rows=0",
        "analytics.profile_decisions.rows=0",
        "analytics.profile_metrics.rows=0",
        "analytics.strategy_metrics.rows=0",
        "analytics.strategy_signals.rows=0",
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
        "analytics.debug_decisions.rows=1",
        "analytics.execution_events.rows=0",
        "analytics.paper_orders.rows=0",
        "analytics.paper_pnl_snapshots.rows=0",
        "analytics.paper_positions.rows=0",
        "analytics.profile_decisions.rows=1",
        "analytics.profile_metrics.rows=1",
        "analytics.strategy_metrics.rows=1",
        "analytics.strategy_signals.rows=1",
        "analytics.enabled=true",
    ]
    assert inserted["profile_decisions"][0]["run_id"] == "run-1"
    assert inserted["profile_decisions"][0]["profile_id"] == "strict_micro"
    assert inserted["profile_decisions"][0]["market_id"] == "m1"
    assert inserted["debug_decisions"][0]["run_id"] == "run-1"
    assert inserted["strategy_signals"][0]["run_id"] == "run-1"
    assert inserted["strategy_signals"][0]["strategy_id"] == "weather_bookmaker_v1"
    assert inserted["strategy_signals"][0]["profile_id"] == "strict_micro"
    assert inserted["profile_metrics"][0]["decision_count"] == 1
    assert inserted["strategy_metrics"][0]["signal_count"] == 1
