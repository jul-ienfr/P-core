from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from prediction_core.app import build_parser
from prediction_core.orchestrator import consume_weather_markets, run_weather_workflow


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    env["PYTHONUNBUFFERED"] = "1"
    return env


def test_build_parser_accepts_serve_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["serve", "--host", "127.0.0.1", "--port", "8080"])
    assert args.command == "serve"
    assert args.host == "127.0.0.1"
    assert args.port == 8080


def test_build_parser_accepts_weather_workflow_command() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "weather-workflow",
            "--base-url",
            "http://127.0.0.1:8080",
            "--question",
            "Will the highest temperature in Denver be 64F or higher?",
            "--yes-price",
            "0.53",
            "--run-id",
            "run-cli-1",
            "--market-id",
            "market-denver-64f",
        ]
    )
    assert args.command == "weather-workflow"
    assert args.base_url == "http://127.0.0.1:8080"
    assert args.yes_price == 0.53
    assert args.run_id == "run-cli-1"
    assert args.market_id == "market-denver-64f"


def test_build_parser_accepts_consume_markets_command() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "consume-markets",
            "--base-url",
            "http://127.0.0.1:8080",
            "--source",
            "fixture",
            "--limit",
            "2",
            "--min-status",
            "watchlist",
        ]
    )
    assert args.command == "consume-markets"
    assert args.base_url == "http://127.0.0.1:8080"
    assert args.source == "fixture"
    assert args.limit == 2
    assert args.min_status == "watchlist"


def test_module_help_exits_cleanly() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "prediction_core.app", "--help"],
        capture_output=True,
        text=True,
        env=_env(),
        check=False,
    )
    assert result.returncode == 0
    assert "serve" in result.stdout


def test_serve_help_exits_cleanly() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "prediction_core.app", "serve", "--help"],
        capture_output=True,
        text=True,
        env=_env(),
        check=False,
    )
    assert result.returncode == 0
    assert "--host" in result.stdout
    assert "--port" in result.stdout


def test_weather_workflow_help_exits_cleanly() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "prediction_core.app", "weather-workflow", "--help"],
        capture_output=True,
        text=True,
        env=_env(),
        check=False,
    )
    assert result.returncode == 0
    assert "--base-url" in result.stdout
    assert "--question" in result.stdout
    assert "--yes-price" in result.stdout


def test_consume_markets_help_exits_cleanly() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "prediction_core.app", "consume-markets", "--help"],
        capture_output=True,
        text=True,
        env=_env(),
        check=False,
    )
    assert result.returncode == 0
    assert "--limit" in result.stdout
    assert "--min-status" in result.stdout


def test_serve_command_starts_server_and_answers_healthcheck() -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "prediction_core.app", "serve", "--host", "127.0.0.1", "--port", "8091"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_env(),
    )
    try:
        ready_line = process.stdout.readline()
        assert "prediction_core server listening on http://127.0.0.1:8091" in ready_line

        response = subprocess.run(
            ["curl", "-sS", "http://127.0.0.1:8091/health"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert response.returncode == 0
        assert '"status": "ok"' in response.stdout
        assert '"service": "prediction_core_python"' in response.stdout
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_run_weather_workflow_sequences_health_parse_score_and_optional_paper_cycle() -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "prediction_core.app", "serve", "--host", "127.0.0.1", "--port", "8092"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_env(),
    )
    try:
        ready_line = process.stdout.readline()
        assert "prediction_core server listening on http://127.0.0.1:8092" in ready_line

        result = run_weather_workflow(
            base_url="http://127.0.0.1:8092",
            question="Will the highest temperature in Denver be 64F or higher?",
            yes_price=0.53,
            run_id="run-cli-2",
            market_id="market-denver-64f",
            requested_quantity=4,
        )
        assert result["health"]["status"] == "ok"
        assert result["parse_market"]["city"] == "Denver"
        assert result["score_market"]["decision"]["status"] == "trade_small"
        assert result["paper_cycle"]["simulation"]["run_id"] == "run-cli-2"
        assert result["paper_cycle"]["simulation"]["status"] == "filled"
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_run_weather_workflow_requires_run_id_and_market_id_together() -> None:
    try:
        run_weather_workflow(
            base_url="http://127.0.0.1:8092",
            question="Will the highest temperature in Denver be 64F or higher?",
            yes_price=0.53,
            run_id="run-cli-3",
        )
    except ValueError as exc:
        assert "run_id and market_id" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_consume_weather_markets_filters_tradeable_candidates() -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "prediction_core.app", "serve", "--host", "127.0.0.1", "--port", "8093"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_env(),
    )
    try:
        ready_line = process.stdout.readline()
        assert "prediction_core server listening on http://127.0.0.1:8093" in ready_line

        payload = consume_weather_markets(
            base_url="http://127.0.0.1:8093",
            source="fixture",
            limit=3,
            min_status="trade",
        )
        assert payload["summary"]["fetched"] == 3
        assert payload["summary"]["selected"] == 2
        assert payload["markets"][0]["market_id"] == "denver-high-64"
        assert payload["markets"][0]["decision"]["status"] == "trade"
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_weather_workflow_command_runs_against_live_server() -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "prediction_core.app", "serve", "--host", "127.0.0.1", "--port", "8092"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_env(),
    )
    try:
        ready_line = process.stdout.readline()
        assert "prediction_core server listening on http://127.0.0.1:8092" in ready_line

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "prediction_core.app",
                "weather-workflow",
                "--base-url",
                "http://127.0.0.1:8092",
                "--question",
                "Will the highest temperature in Denver be 64F or higher?",
                "--yes-price",
                "0.53",
                "--run-id",
                "run-cli-4",
                "--market-id",
                "market-denver-64f",
                "--requested-quantity",
                "4",
            ],
            capture_output=True,
            text=True,
            env=_env(),
            check=False,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["health"]["status"] == "ok"
        assert payload["parse_market"]["city"] == "Denver"
        assert payload["score_market"]["decision"]["status"] == "trade_small"
        assert payload["paper_cycle"]["simulation"]["run_id"] == "run-cli-4"
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_consume_markets_command_runs_against_live_server() -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "prediction_core.app", "serve", "--host", "127.0.0.1", "--port", "8094"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_env(),
    )
    try:
        ready_line = process.stdout.readline()
        assert "prediction_core server listening on http://127.0.0.1:8094" in ready_line

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "prediction_core.app",
                "consume-markets",
                "--base-url",
                "http://127.0.0.1:8094",
                "--source",
                "fixture",
                "--limit",
                "3",
                "--min-status",
                "trade",
            ],
            capture_output=True,
            text=True,
            env=_env(),
            check=False,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["summary"]["selected"] == 2
        assert payload["markets"][0]["market_id"] == "denver-high-64"
    finally:
        process.terminate()
        process.wait(timeout=5)
