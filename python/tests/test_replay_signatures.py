from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from prediction_core.replay import execution_projection_canonical, execution_projection_signature


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
