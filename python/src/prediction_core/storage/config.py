from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_SECRET_KEYS = ("PASSWORD", "SECRET", "ACCESS_KEY", "PRIVATE_KEY", "FUNDER", "API_KEY", "CREDENTIAL", "AUTH", "TOKEN")


@dataclass(frozen=True, kw_only=True)
class PostgresConfig:
    database_url: str | None
    sync_database_url: str | None


@dataclass(frozen=True, kw_only=True)
class ClickHouseConfig:
    url: str | None
    host: str | None
    port: int | None
    database: str | None
    user: str | None
    password: str | None


@dataclass(frozen=True, kw_only=True)
class RedisConfig:
    url: str | None


@dataclass(frozen=True, kw_only=True)
class NatsConfig:
    url: str | None
    monitor_url: str | None
    monitor_port: int | None


@dataclass(frozen=True, kw_only=True)
class S3Config:
    endpoint_url: str | None
    access_key_id: str | None
    secret_access_key: str | None
    bucket: str | None
    region: str | None
    force_path_style: bool


@dataclass(frozen=True, kw_only=True)
class StorageStackConfig:
    postgres: PostgresConfig
    clickhouse: ClickHouseConfig
    redis: RedisConfig
    nats: NatsConfig
    s3: S3Config

    def to_redacted_dict(self) -> dict[str, object]:
        return redact_mapping(asdict(self))


def _env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _env_bool(name: str, *, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str) -> int | None:
    value = os.environ.get(name)
    if not value:
        return None
    return int(value)


def mask_url(url: str | None) -> str | None:
    if not url:
        return url
    parts = urlsplit(url)
    query = urlencode([(key, "***" if any(secret in key.upper() for secret in _SECRET_KEYS) else value) for key, value in parse_qsl(parts.query, keep_blank_values=True)])
    if "@" not in parts.netloc or ":" not in parts.netloc.split("@", 1)[0]:
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
    username, hostinfo = parts.netloc.rsplit("@", 1)[0].split(":", 1)[0], parts.netloc.rsplit("@", 1)[1]
    return urlunsplit((parts.scheme, f"{username}:***@{hostinfo}", parts.path, query, parts.fragment))


def redact_mapping(value: object) -> object:
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for key, item in value.items():
            if any(secret in str(key).upper() for secret in _SECRET_KEYS):
                redacted[str(key)] = "***" if item else item
            elif str(key).lower().endswith("url") or str(key).lower().endswith("database_url") or str(key).lower().endswith("sync_database_url"):
                redacted[str(key)] = mask_url(item if isinstance(item, str) else None)
            else:
                redacted[str(key)] = redact_mapping(item)
        return redacted
    if isinstance(value, list):
        return [redact_mapping(item) for item in value]
    if isinstance(value, str) and "://" in value:
        return mask_url(value)
    return value


def load_storage_stack_config() -> StorageStackConfig:
    return StorageStackConfig(
        postgres=PostgresConfig(
            database_url=_env("PREDICTION_CORE_DATABASE_URL", "PANOPTIQUE_DATABASE_URL"),
            sync_database_url=_env("PREDICTION_CORE_SYNC_DATABASE_URL", "PANOPTIQUE_SYNC_DATABASE_URL"),
        ),
        clickhouse=ClickHouseConfig(
            url=_env("PREDICTION_CORE_CLICKHOUSE_URL"),
            host=_env("PREDICTION_CORE_CLICKHOUSE_HOST"),
            port=_env_int("PREDICTION_CORE_CLICKHOUSE_PORT"),
            database=_env("PREDICTION_CORE_CLICKHOUSE_DATABASE"),
            user=_env("PREDICTION_CORE_CLICKHOUSE_USER"),
            password=_env("PREDICTION_CORE_CLICKHOUSE_PASSWORD"),
        ),
        redis=RedisConfig(url=_env("PREDICTION_CORE_REDIS_URL", "PANOPTIQUE_REDIS_URL")),
        nats=NatsConfig(
            url=_env("PREDICTION_CORE_NATS_URL"),
            monitor_url=_env("PREDICTION_CORE_NATS_MONITOR_URL"),
            monitor_port=_env_int("PREDICTION_CORE_NATS_MONITOR_PORT"),
        ),
        s3=S3Config(
            endpoint_url=_env("PREDICTION_CORE_S3_ENDPOINT_URL"),
            access_key_id=_env("PREDICTION_CORE_S3_ACCESS_KEY_ID"),
            secret_access_key=_env("PREDICTION_CORE_S3_SECRET_ACCESS_KEY"),
            bucket=_env("PREDICTION_CORE_S3_BUCKET"),
            region=_env("PREDICTION_CORE_S3_REGION") or "us-east-1",
            force_path_style=_env_bool("PREDICTION_CORE_S3_FORCE_PATH_STYLE", default=True),
        ),
    )
