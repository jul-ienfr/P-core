from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

from prediction_core.storage.config import load_storage_stack_config, mask_url


ROOT = Path(__file__).resolve().parents[4]


def storage_health() -> dict[str, Any]:
    config = load_storage_stack_config()
    checks = {
        "postgres": _postgres_health(config.postgres.sync_database_url),
        "clickhouse": _clickhouse_health(config.clickhouse.url),
        "redis": _redis_health(config.redis.url),
        "nats": _nats_health(config.nats.url, monitor_url=config.nats.monitor_url, monitor_port=config.nats.monitor_port),
        "nats_events": _nats_event_schema_health(),
        "s3": _s3_health(config.s3.endpoint_url, config.s3.bucket),
        "grafana": _grafana_provisioning_health(),
    }
    return {
        "config": config.to_redacted_dict(),
        **checks,
        "summary": storage_health_summary(checks),
        "source_of_truth": _storage_source_of_truth_summary(),
    }


def storage_health_summary(checks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    configured = [name for name, check in checks.items() if check.get("configured")]
    healthy = [name for name, check in checks.items() if check.get("ok")]
    unhealthy = [name for name in configured if name not in healthy]
    required_primary = ["postgres"]
    degraded_services = [name for name in ("redis", "nats", "s3") if name in unhealthy]
    missing_required_primary = [name for name in required_primary if name not in healthy]
    degraded = bool(degraded_services)
    ready_for_paper = not missing_required_primary
    ready_for_live = ready_for_paper and not degraded
    return {
        "configured_count": len(configured),
        "healthy_count": len(healthy),
        "unhealthy": unhealthy,
        "degraded": degraded,
        "degraded_services": degraded_services,
        "ready": ready_for_paper,
        "ready_for_paper": ready_for_paper,
        "ready_for_live": ready_for_live,
        "missing_required_primary": missing_required_primary,
    }


def _storage_source_of_truth_summary() -> dict[str, Any]:
    return {
        "primary": "postgres",
        "ephemeral": ["redis", "nats"],
        "durable_event_transports": [],
        "live_trading_enabled": False,
    }


def _postgres_health(sync_database_url: str | None) -> dict[str, Any]:
    if not sync_database_url:
        return {"configured": False, "ok": False}
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        return {"configured": True, "ok": False, "error": "sqlalchemy_missing"}
    try:
        engine = create_engine(sync_database_url)
        with engine.connect() as connection:
            version = connection.execute(text("SELECT version()")).scalar()
            timescale = connection.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'")).scalar()
            migration = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
        return {"configured": True, "ok": True, "timescale": timescale, "migration": migration, "version": version}
    except Exception as exc:
        return {"configured": True, "ok": False, "error": type(exc).__name__}


def _clickhouse_health(url: str | None) -> dict[str, Any]:
    if not url:
        return {"configured": False, "ok": False}
    try:
        from urllib.request import urlopen
        with urlopen(f"{url.rstrip('/')}/ping", timeout=2) as response:
            body = response.read().decode("utf-8").strip()
        return {"configured": True, "ok": body == "Ok.", "response": body}
    except Exception as exc:
        return {"configured": True, "ok": False, "error": type(exc).__name__}


def _redis_health(url: str | None) -> dict[str, Any]:
    if not url:
        return {"configured": False, "ok": False}
    try:
        from redis import Redis
    except ImportError:
        return {"configured": True, "ok": False, "error": "redis_missing"}
    try:
        client = Redis.from_url(url, decode_responses=True)
        return {"configured": True, "ok": bool(client.ping())}
    except Exception as exc:
        return {"configured": True, "ok": False, "error": type(exc).__name__}


def _nats_health(url: str | None, *, monitor_url: str | None = None, monitor_port: int | None = None) -> dict[str, Any]:
    if not url and not monitor_url:
        return {"configured": False, "ok": False}
    try:
        if monitor_url:
            health_url = f"{monitor_url.rstrip('/')}/healthz"
        else:
            parts = urlsplit(url or "")
            host = parts.hostname or "localhost"
            resolved_monitor_port = monitor_port or (8222 if parts.port in (None, 4222) else parts.port + 4000)
            netloc = f"{host}:{resolved_monitor_port}"
            health_url = urlunsplit(("http", netloc, "/healthz", "", ""))
        with urlopen(health_url, timeout=2) as response:
            body = response.read().decode("utf-8").strip()
            status = response.status
        return {
            "configured": True,
            "ok": 200 <= status < 300,
            "response": body,
            "monitor_url": mask_url(health_url),
            "status": status,
        }
    except Exception as exc:
        return {"configured": True, "ok": False, "error": type(exc).__name__}


def _nats_event_schema_health() -> dict[str, Any]:
    from prediction_core.storage.events import EVENT_SCHEMA_VERSION, EVENT_SUBJECTS, REQUIRED_EVENT_FIELDS

    return {
        "configured": True,
        "ok": True,
        "schema_version": EVENT_SCHEMA_VERSION,
        "subjects": EVENT_SUBJECTS,
        "required_fields": list(REQUIRED_EVENT_FIELDS),
        "durable_source_of_truth": False,
    }


def _s3_health(endpoint_url: str | None, bucket: str | None) -> dict[str, Any]:
    if not bucket:
        return {"configured": False, "ok": False}
    try:
        import boto3
    except ImportError:
        return {"configured": True, "ok": False, "error": "boto3_missing"}
    try:
        config = load_storage_stack_config().s3
        client_kwargs: dict[str, Any] = {
            "aws_access_key_id": config.access_key_id,
            "aws_secret_access_key": config.secret_access_key,
            "region_name": config.region,
        }
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        if config.force_path_style:
            from botocore.config import Config

            client_kwargs["config"] = Config(s3={"addressing_style": "path"})
        client = boto3.client(
            "s3",
            **{key: value for key, value in client_kwargs.items() if value},
        )
        client.head_bucket(Bucket=bucket)
        return {"configured": True, "ok": True, "bucket": bucket}
    except Exception as exc:
        return {"configured": True, "ok": False, "bucket": bucket, "error": type(exc).__name__}


def _grafana_provisioning_health() -> dict[str, Any]:
    provisioning = ROOT / "infra" / "analytics" / "grafana" / "provisioning"
    dashboards = ROOT / "infra" / "analytics" / "grafana" / "dashboards"
    return {
        "configured": True,
        "ok": provisioning.exists() and dashboards.exists(),
        "provisioning_exists": provisioning.exists(),
        "dashboards_exists": dashboards.exists(),
    }
