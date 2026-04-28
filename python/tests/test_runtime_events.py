from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import pytest

from prediction_core.replay.signatures import verify_replay_event_chain
from prediction_core.runtime.events import (
    MARKET_DATA_SNAPSHOT_RECEIVED,
    MARKET_DATA_SNAPSHOT_REJECTED,
    OMS_INTENT_CREATED,
    OMS_ORDER_REJECTED,
    OMS_ORDER_RISK_BLOCKED,
    OMS_ORDER_SUBMITTED,
    PAPER_FILL_RECORDED,
    PAPER_POSITION_UPDATED,
    REPLAY_RUN_COMPLETED,
    REPLAY_RUN_STARTED,
    RISK_DECISION_RECORDED,
    RUNTIME_EVENT_TYPES,
    RUNTIME_RUN_COMPLETED,
    RUNTIME_RUN_STARTED,
    STRATEGY_SIGNAL_EMITTED,
    build_runtime_event,
    market_data_snapshot_received_event,
    market_data_snapshot_rejected_event,
    oms_intent_created_event,
    oms_order_rejected_event,
    oms_order_risk_blocked_event,
    oms_order_submitted_event,
    paper_fill_recorded_event,
    paper_position_updated_event,
    replay_run_completed_event,
    replay_run_started_event,
    risk_decision_recorded_event,
    runtime_run_completed_event,
    runtime_run_started_event,
    strategy_signal_emitted_event,
)
from prediction_core.storage.events import validate_trading_event_envelope


OCCURRED_AT = "2026-04-28T00:00:00+00:00"
RECORDED_AT = "2026-04-28T00:00:01+00:00"


def _runtime_event(
    *,
    event_type: str = "runtime.run_started",
    event_seq: int = 0,
    payload: dict[str, Any] | None = None,
    previous_hash: str | None = None,
) -> dict[str, Any]:
    return build_runtime_event(
        stream_id="runtime-stream-1",
        event_seq=event_seq,
        event_type=event_type,
        payload=payload or {"run_id": "run-1", "runtime_mode": "paper"},
        source="prediction_core.tests",
        market_id="market-1",
        correlation_id="correlation-1",
        causation_id="causation-1",
        previous_hash=previous_hash,
        occurred_at=OCCURRED_AT,
        recorded_at=RECORDED_AT,
    )


def test_build_runtime_event_returns_valid_trading_event_envelope() -> None:
    event = _runtime_event()

    assert validate_trading_event_envelope(event) == event


def test_build_runtime_event_is_stable_for_same_inputs() -> None:
    event = _runtime_event()
    same_event = _runtime_event()

    assert same_event["event_id"] == event["event_id"]
    assert same_event["payload_hash"] == event["payload_hash"]


def test_build_runtime_event_payload_changes_change_hashes() -> None:
    event = _runtime_event(payload={"run_id": "run-1", "runtime_mode": "paper"})
    changed_event = _runtime_event(payload={"run_id": "run-1", "runtime_mode": "shadow"})

    assert changed_event["payload_hash"] != event["payload_hash"]
    assert changed_event["event_id"] != event["event_id"]


def test_build_runtime_event_rejects_unknown_event_type() -> None:
    with pytest.raises(ValueError):
        _runtime_event(event_type="runtime.unknown")


@pytest.mark.parametrize(
    ("wrapper", "event_type"),
    [
        (runtime_run_started_event, RUNTIME_RUN_STARTED),
        (runtime_run_completed_event, RUNTIME_RUN_COMPLETED),
        (market_data_snapshot_received_event, MARKET_DATA_SNAPSHOT_RECEIVED),
        (market_data_snapshot_rejected_event, MARKET_DATA_SNAPSHOT_REJECTED),
        (strategy_signal_emitted_event, STRATEGY_SIGNAL_EMITTED),
        (risk_decision_recorded_event, RISK_DECISION_RECORDED),
        (oms_intent_created_event, OMS_INTENT_CREATED),
        (oms_order_risk_blocked_event, OMS_ORDER_RISK_BLOCKED),
        (oms_order_submitted_event, OMS_ORDER_SUBMITTED),
        (oms_order_rejected_event, OMS_ORDER_REJECTED),
        (paper_fill_recorded_event, PAPER_FILL_RECORDED),
        (paper_position_updated_event, PAPER_POSITION_UPDATED),
        (replay_run_started_event, REPLAY_RUN_STARTED),
        (replay_run_completed_event, REPLAY_RUN_COMPLETED),
    ],
)
def test_runtime_event_wrappers_set_fixed_event_type(wrapper: Any, event_type: str) -> None:
    event = wrapper(
        stream_id="runtime-stream-1",
        event_seq=0,
        payload={"run_id": "run-1", "runtime_mode": "paper"},
        source="prediction_core.tests",
        market_id="market-1",
        correlation_id="correlation-1",
        causation_id="causation-1",
        occurred_at=OCCURRED_AT,
        recorded_at=RECORDED_AT,
    )

    assert event["event_type"] == event_type


def test_runtime_events_verify_two_event_replay_chain() -> None:
    first = _runtime_event(event_seq=0, payload={"run_id": "run-1", "runtime_mode": "paper"})
    second = _runtime_event(
        event_type="runtime.run_completed",
        event_seq=1,
        payload={"run_id": "run-1", "status": "completed"},
        previous_hash=first["event_id"],
    )

    result = verify_replay_event_chain([first, second])

    assert result["valid"] is True
    assert result["event_count"] == 2
    assert result["errors"] == []


def test_all_runtime_events_are_paper_only_and_disallow_live_orders() -> None:
    event_types = tuple(RUNTIME_EVENT_TYPES.values()) if isinstance(RUNTIME_EVENT_TYPES, dict) else tuple(RUNTIME_EVENT_TYPES)

    for event_type in event_types:
        event = _runtime_event(event_type=event_type)

        assert event["paper_only"] is True
        assert event["live_order_allowed"] is False
