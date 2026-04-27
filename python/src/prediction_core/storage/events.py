from __future__ import annotations

import json
import os
from typing import Any, Awaitable, Callable


DEFAULT_PAPER_FLAGS = {"paper_only": True, "live_order_allowed": False}


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


async def publish_event(client: Any, subject: str, payload: dict[str, Any]) -> None:
    event_payload = {**DEFAULT_PAPER_FLAGS, **payload}
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
