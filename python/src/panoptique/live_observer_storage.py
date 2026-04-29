"""Storage dispatchers for weather live-observer snapshot streams.

The v1 writer is intentionally conservative: local JSONL and local parquet are
implemented, while networked backends return paper-only skipped manifests unless
configured by a future phase.  No credentials are read and no network calls are
made here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from weather_pm.live_observer_config import LiveObserverConfig


_NETWORK_BACKENDS = frozenset({"clickhouse", "postgres", "postgres_timescale", "s3_archive"})
_LOCAL_BACKENDS = frozenset({"local_jsonl", "local_parquet"})


@dataclass(frozen=True)
class LiveObserverStorageResult:
    """Manifest returned by all live-observer storage writers."""

    backend: str
    status: str
    path_or_uri: str | None
    row_count: int
    paper_only: bool = True
    requested_backend: str | None = None
    dry_run: bool = False
    stream_name: str | None = None
    created_at: datetime | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "requested_backend": self.requested_backend or self.backend,
            "status": self.status,
            "path_or_uri": self.path_or_uri,
            "row_count": self.row_count,
            "paper_only": self.paper_only,
            "dry_run": self.dry_run,
            "stream_name": self.stream_name,
            "created_at": _json_value(self.created_at or datetime.now(UTC)),
            "message": self.message,
        }


class LiveObserverWriter(Protocol):
    def write_many(self, rows: Iterable[Any]) -> LiveObserverStorageResult:
        ...


class LocalJsonlLiveObserverWriter:
    """Append-only JSONL writer under the configured live-observer path."""

    def __init__(self, *, path: str | Path, stream_name: str, paper_only: bool = True) -> None:
        self.path = Path(path)
        self.stream_name = stream_name
        self.paper_only = paper_only

    def write_many(self, rows: Iterable[Any]) -> LiveObserverStorageResult:
        _enforce_paper_only(self.paper_only)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with self.path.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(_row_to_dict(row), sort_keys=True, separators=(",", ":")))
                handle.write("\n")
                count += 1
        return LiveObserverStorageResult(
            backend="local_jsonl",
            status="written",
            path_or_uri=str(self.path),
            row_count=count,
            paper_only=True,
            stream_name=self.stream_name,
            created_at=datetime.now(UTC),
        )


class LocalParquetLiveObserverWriter:
    """Local parquet writer with explicit JSONL fallback when pyarrow is absent."""

    def __init__(
        self,
        *,
        parquet_path: str | Path,
        fallback_jsonl_path: str | Path,
        stream_name: str,
        paper_only: bool = True,
    ) -> None:
        self.parquet_path = Path(parquet_path)
        self.fallback_jsonl_path = Path(fallback_jsonl_path)
        self.stream_name = stream_name
        self.paper_only = paper_only

    def write_many(self, rows: Iterable[Any]) -> LiveObserverStorageResult:
        _enforce_paper_only(self.paper_only)
        materialized = [_row_to_dict(row) for row in rows]
        if not _pyarrow_available():
            fallback = LocalJsonlLiveObserverWriter(
                path=self.fallback_jsonl_path,
                stream_name=self.stream_name,
                paper_only=True,
            ).write_many(materialized)
            return LiveObserverStorageResult(
                backend="local_jsonl",
                requested_backend="local_parquet",
                status="fallback_jsonl",
                path_or_uri=fallback.path_or_uri,
                row_count=fallback.row_count,
                paper_only=True,
                stream_name=self.stream_name,
                created_at=datetime.now(UTC),
                message="pyarrow is not installed; wrote explicit JSONL fallback",
            )

        self.parquet_path.parent.mkdir(parents=True, exist_ok=True)
        import pyarrow as pa  # type: ignore[import-not-found]
        import pyarrow.parquet as pq  # type: ignore[import-not-found]

        table = pa.Table.from_pylist(materialized)
        pq.write_table(table, self.parquet_path)
        return LiveObserverStorageResult(
            backend="local_parquet",
            status="written",
            path_or_uri=str(self.parquet_path),
            row_count=len(materialized),
            paper_only=True,
            stream_name=self.stream_name,
            created_at=datetime.now(UTC),
        )


class SkippedLiveObserverWriter:
    """Dry-run/skipped manifest for unsupported or unconfigured network backends."""

    def __init__(self, *, backend: str, stream_name: str) -> None:
        self.backend = backend
        self.stream_name = stream_name

    def write_many(self, rows: Iterable[Any]) -> LiveObserverStorageResult:
        # Exhaust the iterable only to avoid surprising caller-side lazy errors;
        # the row_count remains 0 because nothing was persisted.
        for _ in rows:
            pass
        return LiveObserverStorageResult(
            backend=self.backend,
            status="skipped_not_configured",
            path_or_uri=None,
            row_count=0,
            paper_only=True,
            dry_run=True,
            stream_name=self.stream_name,
            created_at=datetime.now(UTC),
            message="backend is not configured for v1 local storage; no network call made",
        )


def create_live_observer_writer(
    config: LiveObserverConfig,
    *,
    backend: str | None = None,
    stream_name: str,
) -> LiveObserverWriter:
    """Create a safe writer for a configured backend and stream."""

    _enforce_config_safety(config)
    selected = backend or config.storage.primary
    safe_stream = _safe_stream_name(stream_name)
    if selected == "local_jsonl":
        return LocalJsonlLiveObserverWriter(
            path=Path(config.paths.jsonl_dir) / f"{safe_stream}.jsonl",
            stream_name=safe_stream,
            paper_only=config.safety.paper_only,
        )
    if selected == "local_parquet":
        return LocalParquetLiveObserverWriter(
            parquet_path=Path(config.paths.parquet_dir) / f"{safe_stream}.parquet",
            fallback_jsonl_path=Path(config.paths.jsonl_dir) / f"{safe_stream}.jsonl",
            stream_name=safe_stream,
            paper_only=config.safety.paper_only,
        )
    if selected in _NETWORK_BACKENDS:
        return SkippedLiveObserverWriter(backend=selected, stream_name=safe_stream)
    raise ValueError(f"unknown live observer storage backend: {selected}")


def write_live_observer_rows(
    config: LiveObserverConfig,
    *,
    backend: str | None = None,
    stream_name: str,
    rows: Iterable[Any],
) -> LiveObserverStorageResult:
    """Dispatch rows to one configured writer and return its manifest."""

    return create_live_observer_writer(config, backend=backend, stream_name=stream_name).write_many(rows)


def _pyarrow_available() -> bool:
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        return False
    return True


def _enforce_config_safety(config: LiveObserverConfig) -> None:
    _enforce_paper_only(config.safety.paper_only)
    if config.safety.live_order_allowed:
        raise ValueError("live_order_allowed must be false for live-observer storage")


def _enforce_paper_only(paper_only: bool) -> None:
    if paper_only is not True:
        raise ValueError("paper_only must be true for live-observer storage")


def _row_to_dict(row: Any) -> dict[str, Any]:
    if hasattr(row, "to_dict"):
        value = row.to_dict()
    elif isinstance(row, Mapping):
        value = dict(row)
    else:
        raise TypeError("live-observer rows must be mappings or expose to_dict()")
    if not isinstance(value, dict):
        raise TypeError("live-observer rows must serialize to JSON object mappings")
    return {str(key): _json_value(item) for key, item in value.items()}


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _safe_stream_name(stream_name: str) -> str:
    cleaned = stream_name.strip().replace("/", "_").replace("..", "_")
    if not cleaned:
        raise ValueError("stream_name is required")
    return cleaned
