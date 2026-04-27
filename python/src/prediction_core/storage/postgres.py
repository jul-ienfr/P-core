from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from typing import Any
from uuid import uuid4

from panoptique.db import create_sync_engine, get_sync_database_url


def _utc_now() -> datetime:
    return datetime.now(UTC)


def create_prediction_core_sync_engine_from_env(**kwargs: Any) -> Any:
    return create_sync_engine(get_sync_database_url(required=True), **kwargs)


class OperationalStateRepository:
    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def upsert_run(
        self,
        *,
        run_id: str,
        mode: str,
        status: str,
        strategy_id: str | None = None,
        profile_id: str | None = None,
        started_at: datetime | None = None,
        config: dict[str, Any] | None = None,
        summary: dict[str, Any] | None = None,
        artifact_ids: list[str] | None = None,
        paper_only: bool = True,
        live_order_allowed: bool = False,
    ) -> None:
        self._execute(
            """
            INSERT INTO prediction_runs (
                run_id, strategy_id, profile_id, mode, status, started_at, config,
                summary, artifact_ids, paper_only, live_order_allowed
            ) VALUES (
                :run_id, :strategy_id, :profile_id, :mode, :status, :started_at, CAST(:config AS jsonb),
                CAST(:summary AS jsonb), CAST(:artifact_ids AS jsonb), :paper_only, :live_order_allowed
            )
            ON CONFLICT (run_id) DO UPDATE SET
                strategy_id = EXCLUDED.strategy_id,
                profile_id = EXCLUDED.profile_id,
                mode = EXCLUDED.mode,
                status = EXCLUDED.status,
                config = EXCLUDED.config,
                summary = EXCLUDED.summary,
                artifact_ids = EXCLUDED.artifact_ids,
                paper_only = EXCLUDED.paper_only,
                live_order_allowed = EXCLUDED.live_order_allowed
            """,
            {
                "run_id": run_id,
                "strategy_id": strategy_id,
                "profile_id": profile_id,
                "mode": mode,
                "status": status,
                "started_at": started_at or _utc_now(),
                "config": config or {},
                "summary": summary or {},
                "artifact_ids": artifact_ids or [],
                "paper_only": paper_only,
                "live_order_allowed": live_order_allowed,
            },
        )

    def complete_run(
        self,
        *,
        run_id: str,
        status: str,
        summary: dict[str, Any] | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        self._execute(
            """
            UPDATE prediction_runs
            SET status = :status, summary = CAST(:summary AS jsonb), completed_at = :completed_at
            WHERE run_id = :run_id
            """,
            {
                "run_id": run_id,
                "status": status,
                "summary": summary or {},
                "completed_at": completed_at or _utc_now(),
            },
        )

    def claim_idempotency_key(
        self,
        *,
        key: str,
        mode: str,
        run_id: str | None = None,
        market_id: str | None = None,
        token_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        paper_only: bool = True,
    ) -> bool:
        result = self._execute(
            """
            INSERT INTO execution_idempotency_keys (
                key, run_id, market_id, token_id, mode, metadata, paper_only
            ) VALUES (
                :key, :run_id, :market_id, :token_id, :mode, CAST(:metadata AS jsonb), :paper_only
            )
            ON CONFLICT (key) DO NOTHING
            """,
            {
                "key": key,
                "run_id": run_id,
                "market_id": market_id,
                "token_id": token_id,
                "mode": mode,
                "metadata": metadata or {},
                "paper_only": paper_only,
            },
        )
        return bool(getattr(result, "rowcount", 0))

    def append_execution_audit_event(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        execution_event_id: str | None = None,
        run_id: str | None = None,
        market_id: str | None = None,
        token_id: str | None = None,
        recorded_at: datetime | None = None,
        paper_only: bool = True,
        live_order_allowed: bool = False,
    ) -> dict[str, Any]:
        event_id = execution_event_id or str(uuid4())
        row = {
            "execution_event_id": event_id,
            "run_id": run_id,
            "market_id": market_id,
            "token_id": token_id,
            "event_type": event_type,
            "recorded_at": recorded_at or _utc_now(),
            "payload": payload,
            "paper_only": paper_only,
            "live_order_allowed": live_order_allowed,
        }
        self._execute(
            """
            INSERT INTO execution_audit_events (
                execution_event_id, run_id, market_id, token_id, event_type,
                recorded_at, payload, paper_only, live_order_allowed
            ) VALUES (
                :execution_event_id, :run_id, :market_id, :token_id, :event_type,
                :recorded_at, CAST(:payload AS jsonb), :paper_only, :live_order_allowed
            )
            """,
            row,
        )
        return row

    def record_artifact_metadata(
        self,
        *,
        artifact_id: str,
        artifact_type: str,
        source: str,
        uri: str,
        run_id: str | None = None,
        content_type: str | None = None,
        sha256: str | None = None,
        size_bytes: int | None = None,
        row_count: int | None = None,
        metadata: dict[str, Any] | None = None,
        paper_only: bool = True,
    ) -> None:
        self._execute(
            """
            INSERT INTO storage_artifacts (
                artifact_id, run_id, artifact_type, source, uri, content_type,
                sha256, size_bytes, row_count, metadata, paper_only
            ) VALUES (
                :artifact_id, :run_id, :artifact_type, :source, :uri, :content_type,
                :sha256, :size_bytes, :row_count, CAST(:metadata AS jsonb), :paper_only
            )
            ON CONFLICT (artifact_id) DO UPDATE SET
                run_id = EXCLUDED.run_id,
                artifact_type = EXCLUDED.artifact_type,
                source = EXCLUDED.source,
                uri = EXCLUDED.uri,
                content_type = EXCLUDED.content_type,
                sha256 = EXCLUDED.sha256,
                size_bytes = EXCLUDED.size_bytes,
                row_count = EXCLUDED.row_count,
                metadata = EXCLUDED.metadata,
                paper_only = EXCLUDED.paper_only
            """,
            {
                "artifact_id": artifact_id,
                "run_id": run_id,
                "artifact_type": artifact_type,
                "source": source,
                "uri": uri,
                "content_type": content_type,
                "sha256": sha256,
                "size_bytes": size_bytes,
                "row_count": row_count,
                "metadata": metadata or {},
                "paper_only": paper_only,
            },
        )

    def create_job_run(
        self,
        *,
        job_id: str,
        job_type: str,
        status: str = "pending",
        input: dict[str, Any] | None = None,
    ) -> None:
        self._execute(
            """
            INSERT INTO job_runs (job_id, job_type, status, input)
            VALUES (:job_id, :job_type, :status, CAST(:input AS jsonb))
            ON CONFLICT (job_id) DO UPDATE SET
                job_type = EXCLUDED.job_type,
                status = EXCLUDED.status,
                input = EXCLUDED.input
            """,
            {"job_id": job_id, "job_type": job_type, "status": status, "input": input or {}},
        )

    def lease_job(self, *, job_id: str, lease_owner: str, ttl_seconds: int = 60) -> bool:
        result = self._execute(
            """
            UPDATE job_runs
            SET status = 'running', started_at = COALESCE(started_at, now()),
                lease_owner = :lease_owner, lease_expires_at = :lease_expires_at
            WHERE job_id = :job_id
              AND status IN ('pending', 'running')
              AND (lease_expires_at IS NULL OR lease_expires_at < now() OR lease_owner = :lease_owner)
            """,
            {
                "job_id": job_id,
                "lease_owner": lease_owner,
                "lease_expires_at": _utc_now() + timedelta(seconds=ttl_seconds),
            },
        )
        return bool(getattr(result, "rowcount", 0))

    def finish_job(
        self,
        *,
        job_id: str,
        status: str,
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self._execute(
            """
            UPDATE job_runs
            SET status = :status, output = CAST(:output AS jsonb), error = :error, finished_at = now(),
                lease_owner = NULL, lease_expires_at = NULL
            WHERE job_id = :job_id
            """,
            {"job_id": job_id, "status": status, "output": output or {}, "error": error},
        )

    def _execute(self, sql: str, params: dict[str, Any]) -> Any:
        try:
            from sqlalchemy import text
        except ImportError as exc:
            raise RuntimeError("SQLAlchemy is required for Prediction Core PostgreSQL storage") from exc
        with self.engine.begin() as connection:
            return connection.execute(text(sql), _serialize_json_params(params))


def _serialize_json_params(params: dict[str, Any]) -> dict[str, Any]:
    json_param_names = {"config", "summary", "artifact_ids", "metadata", "payload", "input", "output"}
    serialized = dict(params)
    for name in json_param_names.intersection(serialized):
        value = serialized[name]
        if isinstance(value, (dict, list)):
            serialized[name] = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return serialized
