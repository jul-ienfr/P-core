from __future__ import annotations

import json
import os
from typing import Any


def create_redis_from_env() -> Any | None:
    url = os.environ.get("PREDICTION_CORE_REDIS_URL") or os.environ.get("PANOPTIQUE_REDIS_URL")
    if not url:
        return None
    try:
        from redis import Redis
    except ImportError as exc:
        raise RuntimeError("redis package is required for Redis storage") from exc
    return Redis.from_url(url, decode_responses=True)


class RedisMarketDataCacheSink:
    def __init__(self, redis_client: Any, *, prefix: str = "pcore:marketdata:snapshot", ttl_seconds: int | None = None) -> None:
        self.redis_client = redis_client
        self.prefix = prefix.rstrip(":")
        self.ttl_seconds = ttl_seconds

    def __call__(self, snapshot: Any) -> None:
        payload = snapshot.to_dict() if hasattr(snapshot, "to_dict") else dict(snapshot)
        key = f"{self.prefix}:{payload['token_id']}"
        value = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if self.ttl_seconds is None:
            self.redis_client.set(key, value)
        else:
            self.redis_client.setex(key, self.ttl_seconds, value)


def set_short_ttl_idempotency(redis_client: Any, key: str, *, ttl_seconds: int = 300) -> bool:
    return bool(redis_client.set(f"pcore:idempotency:{key}", "1", nx=True, ex=ttl_seconds))


def set_run_status(redis_client: Any, run_id: str, status: str, *, ttl_seconds: int = 3600) -> None:
    redis_client.setex(f"pcore:run:{run_id}:status", ttl_seconds, status)
