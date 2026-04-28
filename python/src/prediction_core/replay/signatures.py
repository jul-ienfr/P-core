from __future__ import annotations

import hashlib
import json
from typing import Any

from prediction_core.storage.events import trading_event_canonical_json, validate_trading_event_envelope_strict_event_id

_BOOKKEEPING_KEYS = {
    "projection_id",
    "content_hash",
    "expires_at",
    "anchor_at",
    "readiness_ref",
    "compliance_ref",
    "capital_ref",
    "reconciliation_ref",
    "health_ref",
    "created_at",
    "updated_at",
    "observed_at",
    "checked_at",
    "timestamp",
    "snapshot_id",
    "readiness_id",
    "compliance_id",
    "reconciliation_id",
    "report_id",
    "decision_id",
    "forecast_id",
    "recommendation_id",
    "trade_intent_id",
}

_CANONICAL_METADATA_KEYS = {
    "highest_safe_mode",
    "highest_authorized_mode",
    "requested_mode",
    "projected_mode",
    "projection_verdict",
    "recommended_effective_mode",
    "manual_review_required",
    "blocking_reasons",
    "downgrade_reasons",
    "summary",
}

_CANONICAL_PROJECTION_KEYS = (
    "venue",
    "market_id",
    "requested_mode",
    "projected_mode",
    "projection_verdict",
    "highest_safe_mode",
    "highest_authorized_mode",
    "recommended_effective_mode",
    "blocking_reasons",
    "downgrade_reasons",
    "manual_review_required",
    "summary",
    "basis",
    "modes",
    "metadata",
)


def replay_event_stream_canonical(events: list[dict]) -> list[dict]:
    canonical_events: list[dict] = []
    previous_seq: int | None = None
    for event in events:
        validated = validate_trading_event_envelope_strict_event_id(event)
        event_seq = validated["event_seq"]
        if previous_seq is not None and event_seq < previous_seq:
            raise ValueError("event_seq must be monotonic non-decreasing")
        previous_seq = event_seq
        canonical_events.append(json.loads(trading_event_canonical_json(validated)))
    return canonical_events


def replay_event_stream_digest(events: list[dict]) -> str:
    canonical_events = replay_event_stream_canonical(events)
    canonical_stream = "".join(trading_event_canonical_json(event) for event in canonical_events)
    return hashlib.sha256(canonical_stream.encode("utf-8")).hexdigest()


def verify_replay_event_chain(events: list[dict]) -> dict[str, object]:
    canonical_events = replay_event_stream_canonical(events)
    errors: list[str] = []
    for index, event in enumerate(canonical_events):
        previous_hash = event.get("previous_hash")
        if index == 0:
            if previous_hash is not None:
                errors.append("event 0 previous_hash must be None")
            continue
        if previous_hash is None:
            errors.append(f"event {index} previous_hash is required")
        elif previous_hash != canonical_events[index - 1]["event_id"]:
            errors.append(f"event {index} previous_hash does not match previous event_id")
    return {
        "valid": not errors,
        "event_count": len(canonical_events),
        "digest": replay_event_stream_digest(canonical_events),
        "errors": errors,
    }


def execution_projection_signature(projection: Any | None) -> dict[str, Any] | None:
    payload = _projection_payload(projection)
    if payload is None:
        return None
    return _strip_bookkeeping(payload)


def execution_projection_canonical(projection: Any | None) -> dict[str, Any] | None:
    payload = _projection_payload(projection)
    if payload is None:
        return None

    signature = _strip_bookkeeping(payload)
    canonical = {
        key: signature[key]
        for key in _CANONICAL_PROJECTION_KEYS
        if key != "metadata" and key in signature
    }

    metadata = signature.get("metadata")
    if isinstance(metadata, dict):
        canonical_metadata = {
            key: metadata[key]
            for key in _CANONICAL_METADATA_KEYS
            if key in metadata
        }
        if canonical_metadata:
            canonical["metadata"] = canonical_metadata

    return canonical


def _projection_payload(projection: Any | None) -> dict[str, Any] | None:
    if projection is None:
        return None

    model_dump = getattr(projection, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(mode="json")
    elif isinstance(projection, dict):
        payload = dict(projection)
    else:
        return None

    if not isinstance(payload, dict):
        return None
    return payload


def _strip_bookkeeping(payload: Any) -> Any:
    if isinstance(payload, dict):
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            if key in _BOOKKEEPING_KEYS:
                continue
            cleaned[key] = _strip_bookkeeping(value)
        return cleaned
    if isinstance(payload, list):
        return [_strip_bookkeeping(item) for item in payload]
    return payload
