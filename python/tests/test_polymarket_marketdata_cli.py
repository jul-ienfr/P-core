import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "prediction-core"


def _pythonpath_env():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    return env


def test_marketdata_plan_cli_prints_read_only_worker_split():
    result = subprocess.run(
        [sys.executable, "-m", "prediction_core.app", "marketdata-plan", "--discovery-interval-seconds", "45", "--max-hot-markets", "12"],
        capture_output=True,
        text=True,
        check=False,
        env=_pythonpath_env(),
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["mode"] == "paper/read-only marketdata scaffold"
    assert payload["discovery_interval_seconds"] == 45
    assert payload["max_hot_markets"] == 12
    assert payload["workers"]["marketdata_worker"]["api"] == "CLOB WebSocket"


def test_repo_wrapper_marketdata_plan_works_without_manual_pythonpath():
    result = subprocess.run(
        [str(SCRIPT), "marketdata-plan"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["workers"]["discovery_worker"]["api"] == "Gamma API"
    assert payload["workers"]["analytics_worker"]["api"] == "Data API"


def test_marketdata_replay_cli_replays_jsonl_events_into_snapshots(tmp_path):
    events_path = tmp_path / "clob-events.jsonl"
    events_path.write_text(
        "\n".join(
            [
                json.dumps({"event_type": "subscribed", "asset_id": "yes-token"}),
                json.dumps(
                    {
                        "event_type": "book",
                        "asset_id": "yes-token",
                        "bids": [{"price": "0.31", "size": "7"}],
                        "asks": [{"price": "0.36", "size": "2"}],
                        "sequence": 10,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [str(SCRIPT), "marketdata-replay", "--events-jsonl", str(events_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["mode"] == "paper/read-only clob websocket replay"
    assert payload["processed_events"] == 1
    assert payload["ignored_events"] == 1
    assert payload["snapshots"]["yes-token"]["best_bid"] == 0.31
    assert payload["snapshots"]["yes-token"]["best_ask"] == 0.36


def test_marketdata_stream_dry_run_cli_reuses_replay_fixture_without_network(tmp_path):
    events_path = tmp_path / "clob-events.jsonl"
    events_path.write_text(
        json.dumps(
            {
                "event_type": "book",
                "asset_id": "yes-token",
                "bids": [{"price": "0.41", "size": "5"}],
                "asks": [{"price": "0.44", "size": "2"}],
                "sequence": 20,
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            str(SCRIPT),
            "marketdata-stream",
            "--token-id",
            "yes-token",
            "--dry-run-events-jsonl",
            str(events_path),
            "--max-events",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["mode"] == "paper/read-only clob websocket stream"
    assert payload["dry_run"] is True
    assert payload["received_events"] == 1
    assert payload["snapshots"]["yes-token"]["best_bid"] == 0.41


def test_marketdata_stream_requires_either_dry_run_fixture_or_live_flag():
    result = subprocess.run(
        [str(SCRIPT), "marketdata-stream", "--token-id", "yes-token", "--max-events", "1"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "either --dry-run-events-jsonl or --live is required" in result.stderr


def test_marketdata_stream_rejects_live_without_event_limit():
    result = subprocess.run(
        [str(SCRIPT), "marketdata-stream", "--token-id", "yes-token", "--live"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "--live requires --max-events for bounded operator runs" in result.stderr


def test_marketdata_stream_rejects_live_combined_with_dry_run_fixture(tmp_path):
    events_path = tmp_path / "clob-events.jsonl"
    events_path.write_text("{}\n", encoding="utf-8")

    result = subprocess.run(
        [
            str(SCRIPT),
            "marketdata-stream",
            "--token-id",
            "yes-token",
            "--dry-run-events-jsonl",
            str(events_path),
            "--live",
            "--max-events",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "--live cannot be combined with --dry-run-events-jsonl" in result.stderr


def test_marketdata_stream_live_cli_uses_real_transport_when_explicitly_enabled():
    from prediction_core import app

    calls = []

    async def fake_run_clob_marketdata_stream(**kwargs):
        calls.append(kwargs)
        return {
            "mode": "paper/read-only clob websocket stream",
            "dry_run": kwargs["dry_run"],
            "token_ids": kwargs["token_ids"],
            "received_events": 0,
            "processed_events": 0,
            "ignored_events": 0,
            "invalid_events": 0,
            "errors": [],
            "snapshots": {},
        }

    with patch.object(sys, "argv", ["prediction-core", "marketdata-stream", "--token-id", "yes-token", "--live", "--max-events", "1"]), patch.object(
        app, "run_clob_marketdata_stream", fake_run_clob_marketdata_stream
    ):
        assert app.main() == 0

    assert len(calls) == 1
    assert calls[0]["token_ids"] == ["yes-token"]
    assert calls[0]["max_events"] == 1
    assert calls[0]["dry_run"] is False
    assert "stream_factory" not in calls[0]
