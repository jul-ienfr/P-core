from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from typing import Any, Awaitable, Callable, Final


DEFAULT_PAPER_FLAGS: Final = {"paper_only": True, "live_order_allowed": False}
EVENT_SCHEMA_VERSION: Final = "prediction_core.storage.event.v1"
SUBJECT_PREFIX: Final = "prediction_core"
SUBJECT_JOB_REQUESTED: Final = f"{SUBJECT_PREFIX}.jobs.requested"
SUBJECT_JOB_LEASED: Final = f"{SUBJECT_PREFIX}.jobs.leased"
SUBJECT_JOB_FINISHED: Final = f"{SUBJECT_PREFIX}.jobs.finished"
SUBJECT_AUDIT_RECORDED: Final = f"{SUBJECT_PREFIX}.audit.recorded"
SUBJECT_STORAGE_HEALTH: Final = f"{SUBJECT_PREFIX}.storage.health"
EVENT_SUBJECTS: Final = {
    "job_requested": SUBJECT_JOB_REQUESTED,
    "job_leased": SUBJECT_JOB_LEASED,
    "job_finished": SUBJECT_JOB_FINISHED,
    "audit_recorded": SUBJECT_AUDIT_RECORDED,
    "storage_health": SUBJECT_STORAGE_HEALTH,
}
REQUIRED_EVENT_FIELDS: Final = ("schema_version", "event_type", "source", "occurred_at", "data")
REQUIRED_TRADING_EVENT_FIELDS: Final = (
    "schema_version",
    "event_id",
    "stream_id",
    "event_seq",
    "event_type",
    "occurred_at",
    "recorded_at",
    "source",
    "market_id",
    "correlation_id",
    "causation_id",
    "previous_hash",
    "payload_hash",
    "payload",
    "paper_only",
    "live_order_allowed",
)


def nats_url_from_env() -> str | None:
    return os.environ.get("PREDICTION_CORE_NATS_URL")


async def create_nats_client_from_env() -> Any | None:
    url = nats_url_from_env()
    if not url:
        return None
    try:
        import nats
    except ImportError as exc:
        raise RuntimeError("nats-py is required for NATS event publishing") from exc
    return await nats.connect(url)


def _iso_datetime(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return value or datetime.now(UTC).isoformat()


def trading_event_canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def stable_payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(trading_event_canonical_json(payload).encode("utf-8")).hexdigest()


def build_event_payload(
    *,
    event_type: str,
    data: dict[str, Any],
    source: str = "prediction_core.storage",
    occurred_at: datetime | str | None = None,
    schema_version: str = EVENT_SCHEMA_VERSION,
) -> dict[str, Any]:
    if not event_type.strip():
        raise ValueError("event_type is required")
    if not source.strip():
        raise ValueError("source is required")
    occurred_at_value = _iso_datetime(occurred_at)
    return {
        **DEFAULT_PAPER_FLAGS,
        "schema_version": schema_version,
        "event_type": event_type,
        "source": source,
        "occurred_at": occurred_at_value,
        "data": data,
    }


def build_trading_event_envelope(
    *,
    stream_id: str,
    event_seq: int,
    event_type: str,
    payload: dict[str, Any],
    source: str,
    market_id: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    previous_hash: str | None = None,
    occurred_at: datetime | str | None = None,
    recorded_at: datetime | str | None = None,
    event_id: str | None = None,
    schema_version: str = EVENT_SCHEMA_VERSION,
    paper_only: bool = True,
    live_order_allowed: bool = False,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("trading event payload must be an object")
    occurred_at_value = _iso_datetime(occurred_at)
    envelope = {
        "schema_version": schema_version,
        "event_id": event_id or "",
        "stream_id": stream_id,
        "event_seq": event_seq,
        "event_type": event_type,
        "occurred_at": occurred_at_value,
        "recorded_at": _iso_datetime(recorded_at) if recorded_at is not None else occurred_at_value,
        "source": source,
        "market_id": market_id,
        "correlation_id": correlation_id,
        "causation_id": causation_id,
        "previous_hash": previous_hash,
        "payload_hash": stable_payload_hash(payload),
        "payload": payload,
        "paper_only": paper_only,
        "live_order_allowed": live_order_allowed,
    }
    if not event_id:
        envelope["event_id"] = stable_payload_hash({**envelope, "event_id": None})
    return validate_trading_event_envelope(envelope)


def _expected_trading_event_id(payload: dict[str, Any]) -> str:
    return stable_payload_hash({**payload, "event_id": None})


def validate_trading_event_envelope_strict_event_id(payload: dict[str, Any]) -> dict[str, Any]:
    validated = validate_trading_event_envelope(payload)
    if validated["event_id"] != _expected_trading_event_id(validated):
        raise ValueError("event_id does not match envelope")
    return validated


def validate_trading_event_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_TRADING_EVENT_FIELDS if field not in payload]
    if missing:
        raise ValueError(f"trading event envelope missing required fields: {', '.join(missing)}")
    for field in ("event_type", "source", "stream_id"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} is required")
    if not isinstance(payload.get("event_id"), str) or not payload["event_id"].strip():
        raise ValueError("event_id is required")
    if (
        not isinstance(payload.get("event_seq"), int)
        or isinstance(payload.get("event_seq"), bool)
        or payload["event_seq"] < 0
    ):
        raise ValueError("event_seq must be a non-negative integer")
    if payload.get("live_order_allowed") is not False:
        raise ValueError("trading events must not enable live orders")
    if payload.get("paper_only") is not True:
        raise ValueError("trading events must remain paper_only")
    if not isinstance(payload.get("payload"), dict):
        raise ValueError("trading event payload must be an object")
    if payload.get("payload_hash") != stable_payload_hash(payload["payload"]):
        raise ValueError("payload_hash does not match payload")
    return payload


def validate_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_EVENT_FIELDS if field not in payload]
    if missing:
        raise ValueError(f"event payload missing required fields: {', '.join(missing)}")
    if payload.get("live_order_allowed") is not False:
        raise ValueError("storage events must not enable live orders")
    if payload.get("paper_only") is not True:
        raise ValueError("storage events must remain paper_only")
    if not isinstance(payload.get("data"), dict):
        raise ValueError("event data must be an object")
    return payload


async def publish_event(client: Any, subject: str, payload: dict[str, Any]) -> None:
    event_payload = {**DEFAULT_PAPER_FLAGS, **payload}
    if all(field in event_payload for field in REQUIRED_EVENT_FIELDS):
        validate_event_payload(event_payload)
    await client.publish(subject, trading_event_canonical_json(event_payload).encode("utf-8"))


class NatsEventPublisher:
    def __init__(self, client: Any) -> None:
        self.client = client

    async def publish(self, subject: str, payload: dict[str, Any]) -> None:
        await publish_event(self.client, subject, payload)


async def subscribe_events(client: Any, subject: str, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> Any:
    async def _wrapped(message: Any) -> None:
        await handler(json.loads(message.data.decode("utf-8")))

    return await client.subscribe(subject, cb=_wrapped)
