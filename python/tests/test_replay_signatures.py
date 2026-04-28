from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import pytest

from prediction_core.replay.signatures import (
    execution_projection_canonical,
    execution_projection_signature,
    replay_event_stream_canonical,
    replay_event_stream_digest,
    verify_replay_event_chain,
)
from prediction_core.storage.events import build_trading_event_envelope


def test_execution_projection_signature_strips_bookkeeping_fields_recursively() -> None:
    projection = SimpleNamespace(
        model_dump=lambda mode="json": {
            "projection_id": "proj-123",
            "content_hash": "hash-1",
            "created_at": "2026-04-22T12:00:00Z",
            "venue": "polymarket",
            "legs": [
                {
                    "trade_intent_id": "intent-1",
                    "side": "buy",
                    "price": 0.42,
                }
            ],
            "metadata": {
                "anchor_at": "2026-04-22T12:00:01Z",
                "summary": "keep-me",
            },
        }
    )

    assert execution_projection_signature(projection) == {
        "venue": "polymarket",
        "legs": [{"side": "buy", "price": 0.42}],
        "metadata": {"summary": "keep-me"},
    }


def test_execution_projection_signature_returns_none_for_none() -> None:
    assert execution_projection_signature(None) is None


def test_execution_projection_canonical_keeps_only_replay_relevant_surface() -> None:
    projection = SimpleNamespace(
        model_dump=lambda mode="json": {
            "projection_id": "proj-123",
            "packet_kind": "execution_projection",
            "run_id": "run-123",
            "venue": "polymarket",
            "market_id": "market-123",
            "requested_mode": "live",
            "projected_mode": "shadow",
            "projection_verdict": "degraded",
            "highest_safe_mode": "shadow",
            "highest_safe_requested_mode": "shadow",
            "highest_authorized_mode": "live",
            "recommended_effective_mode": "shadow",
            "blocking_reasons": ["kill_switch_enabled"],
            "downgrade_reasons": ["venue_health_degraded"],
            "manual_review_required": True,
            "summary": "requested live -> projected shadow",
            "basis": {
                "readiness": {
                    "status": "ready",
                    "notes": ["keep-basis"],
                }
            },
            "modes": {
                "live": {"allowed": False},
                "shadow": {"allowed": True},
            },
            "metadata": {
                "highest_safe_mode": "shadow",
                "highest_authorized_mode": "live",
                "requested_mode": "live",
                "ephemeral": "drop-me",
            },
            "content_hash": "hash-1",
            "expires_at": "2026-04-22T12:00:00Z",
        }
    )

    assert execution_projection_canonical(projection) == {
        "venue": "polymarket",
        "market_id": "market-123",
        "requested_mode": "live",
        "projected_mode": "shadow",
        "projection_verdict": "degraded",
        "highest_safe_mode": "shadow",
        "highest_authorized_mode": "live",
        "recommended_effective_mode": "shadow",
        "blocking_reasons": ["kill_switch_enabled"],
        "downgrade_reasons": ["venue_health_degraded"],
        "manual_review_required": True,
        "summary": "requested live -> projected shadow",
        "basis": {
            "readiness": {
                "status": "ready",
                "notes": ["keep-basis"],
            }
        },
        "modes": {
            "live": {"allowed": False},
            "shadow": {"allowed": True},
        },
        "metadata": {
            "highest_safe_mode": "shadow",
            "highest_authorized_mode": "live",
            "requested_mode": "live",
        },
    }


def test_execution_projection_canonical_returns_none_for_non_mapping_payloads() -> None:
    assert execution_projection_canonical(object()) is None


def _trading_event(event_seq: int, payload: dict[str, Any], previous_hash: str | None = None) -> dict[str, Any]:
    return build_trading_event_envelope(
        stream_id="stream-1",
        event_seq=event_seq,
        event_type="paper.order.recorded",
        payload=payload,
        source="prediction_core.tests",
        market_id="market-1",
        previous_hash=previous_hash,
        occurred_at="2026-04-28T00:00:00+00:00",
        recorded_at="2026-04-28T00:00:00+00:00",
    )


def test_replay_event_stream_digest_is_stable_for_identical_events() -> None:
    events = [_trading_event(0, {"order_id": "order-1", "quantity": 1})]
    same_events = [_trading_event(0, {"order_id": "order-1", "quantity": 1})]

    assert replay_event_stream_digest(events) == replay_event_stream_digest(same_events)


def test_replay_event_stream_digest_changes_when_payload_changes() -> None:
    events = [_trading_event(0, {"order_id": "order-1", "quantity": 1})]
    changed_events = [_trading_event(0, {"order_id": "order-1", "quantity": 2})]

    assert replay_event_stream_digest(events) != replay_event_stream_digest(changed_events)


def test_replay_event_stream_digest_changes_when_events_are_reordered_and_chain_is_invalid() -> None:
    first = _trading_event(0, {"order_id": "order-1"})
    second = _trading_event(0, {"order_id": "order-2"}, previous_hash=first["event_id"])
    events = [first, second]
    reordered = [second, first]

    assert replay_event_stream_digest(events) != replay_event_stream_digest(reordered)
    assert verify_replay_event_chain(reordered)["valid"] is False


def test_replay_event_stream_canonical_rejects_decreasing_event_seq() -> None:
    events = [
        _trading_event(1, {"order_id": "order-1"}),
        _trading_event(0, {"order_id": "order-2"}),
    ]

    with pytest.raises(ValueError, match="event_seq must be monotonic non-decreasing"):
        replay_event_stream_canonical(events)


def test_verify_replay_event_chain_returns_valid_for_linked_events() -> None:
    first = _trading_event(0, {"order_id": "order-1"})
    second = _trading_event(1, {"order_id": "order-2"}, previous_hash=first["event_id"])

    result = verify_replay_event_chain([first, second])

    assert result["valid"] is True
    assert result["event_count"] == 2
    assert result["errors"] == []


def test_verify_replay_event_chain_rejects_missing_previous_hash_after_first() -> None:
    first = _trading_event(0, {"order_id": "order-1"})
    second = _trading_event(1, {"order_id": "order-2"})

    result = verify_replay_event_chain([first, second])

    assert result["valid"] is False
    assert "event 1 previous_hash is required" in result["errors"]


def test_replay_event_stream_canonical_rejects_tampered_envelope_metadata() -> None:
    event = _trading_event(0, {"order_id": "order-1"})
    tampered = {**event, "event_type": "tampered", "event_seq": 1, "source": "tampered.source"}

    with pytest.raises(ValueError, match="event_id does not match envelope"):
        replay_event_stream_canonical([tampered])
