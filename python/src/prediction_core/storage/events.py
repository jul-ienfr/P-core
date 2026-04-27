from __future__ import annotations

from datetime import UTC, datetime
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
    if isinstance(occurred_at, datetime):
        occurred_at_value = occurred_at.astimezone(UTC).isoformat()
    else:
        occurred_at_value = occurred_at or datetime.now(UTC).isoformat()
    return {
        **DEFAULT_PAPER_FLAGS,
        "schema_version": schema_version,
        "event_type": event_type,
        "source": source,
        "occurred_at": occurred_at_value,
        "data": data,
    }


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
    await client.publish(subject, json.dumps(event_payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


class NatsEventPublisher:
    def __init__(self, client: Any) -> None:
        self.client = client

    async def publish(self, subject: str, payload: dict[str, Any]) -> None:
        await publish_event(self.client, subject, payload)


async def subscribe_events(client: Any, subject: str, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> Any:
    async def _wrapped(message: Any) -> None:
        await handler(json.loads(message.data.decode("utf-8")))

    return await client.subscribe(subject, cb=_wrapped)
