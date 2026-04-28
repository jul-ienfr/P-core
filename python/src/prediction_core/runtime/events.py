from __future__ import annotations

from datetime import datetime
from typing import Any, Final

from prediction_core.storage.events import build_trading_event_envelope

RUNTIME_RUN_STARTED: Final = "runtime.run_started"
RUNTIME_RUN_COMPLETED: Final = "runtime.run_completed"
MARKET_DATA_SNAPSHOT_RECEIVED: Final = "market_data.snapshot_received"
MARKET_DATA_SNAPSHOT_REJECTED: Final = "market_data.snapshot_rejected"
STRATEGY_SIGNAL_EMITTED: Final = "strategy.signal_emitted"
RISK_DECISION_RECORDED: Final = "risk.decision_recorded"
OMS_INTENT_CREATED: Final = "oms.intent_created"
OMS_ORDER_RISK_BLOCKED: Final = "oms.order_risk_blocked"
OMS_ORDER_SUBMITTED: Final = "oms.order_submitted"
OMS_ORDER_REJECTED: Final = "oms.order_rejected"
PAPER_FILL_RECORDED: Final = "paper.fill_recorded"
PAPER_POSITION_UPDATED: Final = "paper.position_updated"
REPLAY_RUN_STARTED: Final = "replay.run_started"
REPLAY_RUN_COMPLETED: Final = "replay.run_completed"

RUNTIME_EVENT_TYPES: Final = (
    RUNTIME_RUN_STARTED,
    RUNTIME_RUN_COMPLETED,
    MARKET_DATA_SNAPSHOT_RECEIVED,
    MARKET_DATA_SNAPSHOT_REJECTED,
    STRATEGY_SIGNAL_EMITTED,
    RISK_DECISION_RECORDED,
    OMS_INTENT_CREATED,
    OMS_ORDER_RISK_BLOCKED,
    OMS_ORDER_SUBMITTED,
    OMS_ORDER_REJECTED,
    PAPER_FILL_RECORDED,
    PAPER_POSITION_UPDATED,
    REPLAY_RUN_STARTED,
    REPLAY_RUN_COMPLETED,
)


def build_runtime_event(
    *,
    stream_id: str,
    event_seq: int,
    event_type: str,
    payload: dict[str, Any],
    source: str = "prediction_core.runtime",
    market_id: str = "runtime",
    correlation_id: str | None = None,
    causation_id: str | None = None,
    previous_hash: str | None = None,
    occurred_at: str | datetime | None = None,
    recorded_at: str | datetime | None = None,
) -> dict[str, Any]:
    if event_type not in RUNTIME_EVENT_TYPES:
        raise ValueError(f"unknown runtime event_type: {event_type}")
    return build_trading_event_envelope(
        stream_id=stream_id,
        event_seq=event_seq,
        event_type=event_type,
        payload=payload,
        source=source,
        market_id=market_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        previous_hash=previous_hash,
        occurred_at=occurred_at,
        recorded_at=recorded_at,
    )


def runtime_run_started_event(**kwargs: Any) -> dict[str, Any]:
    return build_runtime_event(event_type=RUNTIME_RUN_STARTED, **kwargs)


def runtime_run_completed_event(**kwargs: Any) -> dict[str, Any]:
    return build_runtime_event(event_type=RUNTIME_RUN_COMPLETED, **kwargs)


def market_data_snapshot_received_event(**kwargs: Any) -> dict[str, Any]:
    return build_runtime_event(event_type=MARKET_DATA_SNAPSHOT_RECEIVED, **kwargs)


def market_data_snapshot_rejected_event(**kwargs: Any) -> dict[str, Any]:
    return build_runtime_event(event_type=MARKET_DATA_SNAPSHOT_REJECTED, **kwargs)


def strategy_signal_emitted_event(**kwargs: Any) -> dict[str, Any]:
    return build_runtime_event(event_type=STRATEGY_SIGNAL_EMITTED, **kwargs)


def risk_decision_recorded_event(**kwargs: Any) -> dict[str, Any]:
    return build_runtime_event(event_type=RISK_DECISION_RECORDED, **kwargs)


def oms_intent_created_event(**kwargs: Any) -> dict[str, Any]:
    return build_runtime_event(event_type=OMS_INTENT_CREATED, **kwargs)


def oms_order_risk_blocked_event(**kwargs: Any) -> dict[str, Any]:
    return build_runtime_event(event_type=OMS_ORDER_RISK_BLOCKED, **kwargs)


def oms_order_submitted_event(**kwargs: Any) -> dict[str, Any]:
    return build_runtime_event(event_type=OMS_ORDER_SUBMITTED, **kwargs)


def oms_order_rejected_event(**kwargs: Any) -> dict[str, Any]:
    return build_runtime_event(event_type=OMS_ORDER_REJECTED, **kwargs)


def paper_fill_recorded_event(**kwargs: Any) -> dict[str, Any]:
    return build_runtime_event(event_type=PAPER_FILL_RECORDED, **kwargs)


def paper_position_updated_event(**kwargs: Any) -> dict[str, Any]:
    return build_runtime_event(event_type=PAPER_POSITION_UPDATED, **kwargs)


def replay_run_started_event(**kwargs: Any) -> dict[str, Any]:
    return build_runtime_event(event_type=REPLAY_RUN_STARTED, **kwargs)


def replay_run_completed_event(**kwargs: Any) -> dict[str, Any]:
    return build_runtime_event(event_type=REPLAY_RUN_COMPLETED, **kwargs)
