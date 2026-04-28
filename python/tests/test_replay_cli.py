from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from prediction_core.storage.events import build_trading_event_envelope, trading_event_canonical_json

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.write_text("\n".join(trading_event_canonical_json(event) for event in events) + "\n", encoding="utf-8")


def _event(seq: int, payload: dict, previous_hash: str | None = None) -> dict:
    return build_trading_event_envelope(
        stream_id="cli-replay-stream",
        event_seq=seq,
        event_type="paper_order_recorded",
        payload=payload,
        source="prediction_core.tests",
        market_id="market-1",
        previous_hash=previous_hash,
        occurred_at="2026-04-28T00:00:00+00:00",
        recorded_at="2026-04-28T00:00:00+00:00",
    )


def test_replay_trading_events_cli_accepts_valid_chain(tmp_path: Path) -> None:
    first = _event(0, {"order_id": "o1"})
    second = _event(1, {"order_id": "o2"}, previous_hash=first["event_id"])
    events_path = tmp_path / "events.jsonl"
    _write_jsonl(events_path, [first, second])

    result = subprocess.run(
        [sys.executable, "-m", "prediction_core.app", "replay-trading-events", "--events-jsonl", str(events_path)],
        capture_output=True,
        text=True,
        env=_env(),
        check=False,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["valid"] is True
    assert payload["event_count"] == 2
    assert payload["digest"]
    assert payload["errors"] == []


def test_replay_trading_events_cli_rejects_invalid_chain(tmp_path: Path) -> None:
    first = _event(0, {"order_id": "o1"})
    second = _event(1, {"order_id": "o2"})
    events_path = tmp_path / "events.jsonl"
    _write_jsonl(events_path, [first, second])

    result = subprocess.run(
        [sys.executable, "-m", "prediction_core.app", "replay-trading-events", "--events-jsonl", str(events_path)],
        capture_output=True,
        text=True,
        env=_env(),
        check=False,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert payload["valid"] is False
    assert payload["event_count"] == 2
    assert payload["errors"] == ["event 1 previous_hash is required"]


def test_replay_trading_events_cli_reports_malformed_json_as_json(tmp_path: Path) -> None:
    events_path = tmp_path / "events.jsonl"
    events_path.write_text("{\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "prediction_core.app", "replay-trading-events", "--events-jsonl", str(events_path)],
        capture_output=True,
        text=True,
        env=_env(),
        check=False,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert payload["valid"] is False
    assert payload["event_count"] == 0
    assert payload["digest"] == ""
    assert payload["errors"][0].startswith("JSONDecodeError: ")


def test_replay_trading_events_cli_reports_non_object_jsonl_line_as_json(tmp_path: Path) -> None:
    events_path = tmp_path / "events.jsonl"
    events_path.write_text("[]\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "prediction_core.app", "replay-trading-events", "--events-jsonl", str(events_path)],
        capture_output=True,
        text=True,
        env=_env(),
        check=False,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert payload["valid"] is False
    assert payload["event_count"] == 0
    assert payload["digest"] == ""
    assert payload["errors"] == ["ValueError: line 1 must be a JSON object"]
