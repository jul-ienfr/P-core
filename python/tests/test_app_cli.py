from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from prediction_core.app import build_parser
from prediction_core.orchestrator import consume_weather_markets, run_weather_paper_batch, run_weather_workflow


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREDICTION_CORE_SCRIPT = PROJECT_ROOT / "scripts" / "prediction-core"


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
            "--explain-filtered",
        ]
    )
    assert args.command == "consume-markets"
    assert args.base_url == "http://127.0.0.1:8080"
    assert args.source == "fixture"
    assert args.limit == 2
    assert args.min_status == "watchlist"
    assert args.explain_filtered is True


def test_build_parser_accepts_paper_batch_command() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "paper-batch",
            "--base-url",
            "http://127.0.0.1:8080",
            "--source",
            "live",
            "--limit",
            "10",
            "--min-status",
            "trade_small",
            "--run-id-prefix",
            "live-meteo",
            "--bankroll-usd",
            "1000",
        ]
    )
    assert args.command == "paper-batch"
    assert args.source == "live"
    assert args.limit == 10
    assert args.min_status == "trade_small"
    assert args.run_id_prefix == "live-meteo"
    assert args.bankroll_usd == 1000.0


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


def test_repo_script_help_exits_cleanly_without_manual_pythonpath() -> None:
    result = subprocess.run(
        [str(PREDICTION_CORE_SCRIPT), "--help"],
        capture_output=True,
        text=True,
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


def test_repo_script_serve_command_starts_server_and_answers_healthcheck() -> None:
    process = subprocess.Popen(
        [str(PREDICTION_CORE_SCRIPT), "serve", "--host", "127.0.0.1", "--port", "8096"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        ready_line = process.stdout.readline()
        assert "prediction_core server listening on http://127.0.0.1:8096" in ready_line

        response = subprocess.run(
            ["curl", "-sS", "http://127.0.0.1:8096/health"],
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
        assert payload["summary"]["selected"] == 1
        assert payload["markets"][0]["market_id"] == "denver-high-65"
        assert payload["markets"][0]["decision"]["status"] == "trade"
        assert payload["markets"][0]["model"]["probability_yes"] == 0.57
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_run_weather_paper_batch_fetches_scores_and_runs_paper_cycles_for_selected_candidates() -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "prediction_core.app", "serve", "--host", "127.0.0.1", "--port", "8097"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_env(),
    )
    try:
        ready_line = process.stdout.readline()
        assert "prediction_core server listening on http://127.0.0.1:8097" in ready_line

        payload = run_weather_paper_batch(
            base_url="http://127.0.0.1:8097",
            source="fixture",
            limit=3,
            min_status="trade",
            run_id_prefix="batch-test",
            bankroll_usd=1000,
        )

        assert payload["summary"]["fetched"] == 3
        assert payload["summary"]["selected"] == 1
        assert payload["summary"]["paper_cycles"] == 1
        assert payload["paper_cycles"][0]["market_id"] == "denver-high-65"
        assert payload["paper_cycles"][0]["run_id"] == "batch-test-denver-high-65"
        assert payload["paper_cycles"][0]["simulation"]["status"] == "skipped"
        assert payload["paper_cycles"][0]["score_bundle"]["decision"]["status"] == "skip"
        assert payload["paper_cycles"][0]["decision"]["status"] == "trade"
        assert payload["markets"][0]["model"]["method"] == "calibrated_threshold_v1"
        assert payload["markets"][0]["edge"]["market_implied_yes_probability"] == 0.37
        assert payload["markets"][0]["edge"]["probability_edge"] == 0.2
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_consume_weather_markets_filters_extreme_or_illiquid_live_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def __init__(self, base_url: str) -> None:
            self.base_url = base_url

        def health(self) -> dict[str, object]:
            return {"status": "ok", "service": "prediction_core_python"}

        def fetch_markets(self, *, source: str = "fixture", limit: int = 100) -> list[dict[str, object]]:
            assert source == "live"
            return [
                {"id": "keep-1", "question": "Keep me", "yes_price": 0.42},
                {"id": "drop-price", "question": "Drop extreme price", "yes_price": 0.001},
                {"id": "drop-liquidity", "question": "Drop illiquid", "yes_price": 0.44},
            ]

        def score_market(self, *, market_id: str, source: str | None = None, **payload: object) -> dict[str, object]:
            bundles = {
                "keep-1": {
                    "decision": {"status": "trade"},
                    "score": {"total_score": 82.0, "raw_edge": 0.14},
                    "model": {"probability_yes": 0.56, "confidence": 0.75, "method": "calibrated_threshold_v1"},
                    "market": {"city": "Hong Kong"},
                    "resolution": {"provider": "hong_kong_observatory"},
                    "execution": {"fillable_size_usd": 180.0, "slippage_risk": "low", "spread": 0.02},
                },
                "drop-price": {
                    "decision": {"status": "trade"},
                    "score": {"total_score": 90.0, "raw_edge": 0.60},
                    "model": {"probability_yes": 0.61, "confidence": 0.75, "method": "calibrated_threshold_v1"},
                    "market": {"city": "Hong Kong"},
                    "resolution": {"provider": "hong_kong_observatory"},
                    "execution": {"fillable_size_usd": 180.0, "slippage_risk": "low", "spread": 0.02},
                },
                "drop-liquidity": {
                    "decision": {"status": "trade_small"},
                    "score": {"total_score": 78.0, "raw_edge": 0.12},
                    "model": {"probability_yes": 0.56, "confidence": 0.7, "method": "calibrated_threshold_v1"},
                    "market": {"city": "Hong Kong"},
                    "resolution": {"provider": "hong_kong_observatory"},
                    "execution": {"fillable_size_usd": 1.5, "slippage_risk": "high", "spread": 0.08},
                },
            }
            return bundles[market_id]

    monkeypatch.setattr("prediction_core.orchestrator.PredictionCoreClient", FakeClient)

    payload = consume_weather_markets(
        base_url="http://127.0.0.1:9999",
        source="live",
        limit=3,
        min_status="watchlist",
    )

    assert payload["summary"]["fetched"] == 3
    assert payload["summary"]["selected"] == 1
    assert payload["summary"]["filtered_out"] == 2
    assert payload["markets"][0]["market_id"] == "keep-1"
    assert payload["markets"][0]["model"]["probability_yes"] == 0.56
    assert payload["markets"][0]["edge"]["probability_edge"] == 0.14


def test_consume_weather_markets_can_explain_filtered_live_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def __init__(self, base_url: str) -> None:
            self.base_url = base_url

        def health(self) -> dict[str, object]:
            return {"status": "ok", "service": "prediction_core_python"}

        def fetch_markets(self, *, source: str = "fixture", limit: int = 100) -> list[dict[str, object]]:
            assert source == "live"
            return [
                {"id": "drop-status", "question": "Drop status", "yes_price": 0.42},
                {"id": "drop-price", "question": "Drop extreme price", "yes_price": 0.001},
                {"id": "drop-spread", "question": "Drop spread", "yes_price": 0.44},
            ]

        def score_market(self, *, market_id: str, source: str | None = None, **payload: object) -> dict[str, object]:
            bundles = {
                "drop-status": {
                    "decision": {"status": "skip"},
                    "score": {"total_score": 54.0, "raw_edge": 0.03, "grade": "C"},
                    "execution": {"fillable_size_usd": 180.0, "slippage_risk": "low", "spread": 0.02},
                },
                "drop-price": {
                    "decision": {"status": "trade"},
                    "score": {"total_score": 90.0, "raw_edge": 0.60, "grade": "A"},
                    "execution": {"fillable_size_usd": 180.0, "slippage_risk": "low", "spread": 0.02},
                },
                "drop-spread": {
                    "decision": {"status": "trade_small"},
                    "score": {"total_score": 78.0, "raw_edge": 0.12, "grade": "B"},
                    "execution": {"fillable_size_usd": 180.0, "slippage_risk": "low", "spread": 0.08},
                },
            }
            return bundles[market_id]

    monkeypatch.setattr("prediction_core.orchestrator.PredictionCoreClient", FakeClient)

    payload = consume_weather_markets(
        base_url="http://127.0.0.1:9999",
        source="live",
        limit=3,
        min_status="watchlist",
        explain_filtered=True,
    )

    assert payload["summary"]["selected"] == 0
    assert payload["summary"]["filtered_out"] == 3
    assert len(payload["filtered_markets"]) == 3
    assert payload["filtered_markets"][0]["market_id"] == "drop-status"
    assert payload["filtered_markets"][0]["filter_reason"] == "decision_below_min_status"
    assert payload["filtered_markets"][1]["filter_reason"] == "extreme_yes_price"
    assert payload["filtered_markets"][2]["filter_reason"] == "wide_spread"
    assert payload["filtered_markets"][2]["score"]["total_score"] == 78.0
    assert payload["filtered_markets"][2]["execution"]["spread"] == 0.08



def test_consume_weather_markets_preserves_execution_costs_for_live_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def __init__(self, base_url: str) -> None:
            self.base_url = base_url

        def health(self) -> dict[str, object]:
            return {"status": "ok", "service": "prediction_core_python"}

        def fetch_markets(self, *, source: str = "fixture", limit: int = 100) -> list[dict[str, object]]:
            assert source == "live"
            return [{"id": "keep-2", "question": "Keep me", "yes_price": 0.42}]

        def score_market(self, *, market_id: str, source: str | None = None, **payload: object) -> dict[str, object]:
            assert market_id == "keep-2"
            return {
                "decision": {"status": "trade"},
                "score": {"total_score": 82.0, "raw_edge": 0.14},
                "model": {"probability_yes": 0.56, "confidence": 0.75, "method": "calibrated_threshold_v1"},
                "market": {"city": "Hong Kong"},
                "resolution": {"provider": "hong_kong_observatory"},
                "execution": {"fillable_size_usd": 180.0, "slippage_risk": "low", "spread": 0.02},
                "execution_costs": {
                    "quoted_best_bid": 0.42,
                    "quoted_best_ask": 0.45,
                    "estimated_filled_quantity": 20.0,
                    "total_execution_cost": 0.4182,
                    "total_all_in_cost": 3.4637,
                    "effective_unit_price": 0.628185,
                },
            }

    monkeypatch.setattr("prediction_core.orchestrator.PredictionCoreClient", FakeClient)

    payload = consume_weather_markets(
        base_url="http://127.0.0.1:9999",
        source="live",
        limit=1,
        min_status="watchlist",
    )

    assert payload["summary"]["selected"] == 1
    assert payload["markets"][0]["execution_costs"]["quoted_best_bid"] == 0.42
    assert payload["markets"][0]["execution_costs"]["quoted_best_ask"] == 0.45
    assert payload["markets"][0]["execution_costs"]["total_all_in_cost"] == 3.4637


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
        assert payload["summary"]["selected"] == 1
        assert payload["markets"][0]["market_id"] == "denver-high-65"
    finally:
        process.terminate()
        process.wait(timeout=5)
