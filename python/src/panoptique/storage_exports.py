from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

EXPORTABLE_TABLES: dict[str, str] = {
    "shadow_predictions": "observed_at",
    "crowd_flow_observations": "observed_at",
}

SECRET_KEY_FRAGMENTS = ("secret", "token", "key", "password", "credential", "wallet")


@dataclass(frozen=True)
class ExportManifest:
    table: str
    path: str
    manifest_path: str
    format: str
    row_count: int
    sha256: str
    created_at: str
    from_ts: str | None
    to_ts: str | None
    source_of_truth: str = "postgresql_timescaledb_or_local_fixture"
    raw_artifacts_remain_canonical: bool = True
    paper_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DBHealthReport:
    checked_at: str
    mode: str
    checks: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StorageCommandResult:
    command: str
    status: str
    count: int
    artifact_path: str
    report_path: str
    db_status: str = "read_only"
    errors: tuple[str, ...] = ()


def redact_secrets(value: Any) -> Any:
    """Return a JSON-safe copy with obvious credential-bearing keys redacted."""
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(fragment in key_text for fragment in SECRET_KEY_FRAGMENTS):
                redacted[str(key)] = "[REDACTED]"
            else:
                redacted[str(key)] = redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def _decode_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _json_safe_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): redact_secrets(_decode_jsonish(value)) for key, value in row.items()}


def build_export_query(table: str, *, from_ts: str | None = None, to_ts: str | None = None) -> tuple[str, dict[str, Any]]:
    if table not in EXPORTABLE_TABLES:
        raise ValueError(f"Table {table!r} is not exportable; allowed tables: {', '.join(sorted(EXPORTABLE_TABLES))}")
    time_column = EXPORTABLE_TABLES[table]
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if from_ts is not None:
        clauses.append(f"{time_column} >= :from_ts")
        params["from_ts"] = from_ts
    if to_ts is not None:
        clauses.append(f"{time_column} < :to_ts")
        params["to_ts"] = to_ts
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return f"SELECT * FROM {table}{where} ORDER BY {time_column}", params


def _sqlite_query(conn: sqlite3.Connection, query: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(query, dict(params)).fetchall()
    return [_json_safe_row(dict(row)) for row in rows]


def _write_jsonl_parquet_fallback(path: Path, rows: list[dict[str, Any]]) -> str:
    """Write newline-delimited JSON with a .parquet extension when parquet engines are absent.

    The command name and file extension stay stable for DuckDB/parquet deployments, while
    minimal local/test environments remain dependency-light and auditable.
    """
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    return "jsonl-parquet-fallback"


def _write_real_parquet_if_available(path: Path, rows: list[dict[str, Any]]) -> str | None:
    try:
        import pyarrow as pa  # type: ignore
        import pyarrow.parquet as pq  # type: ignore
    except Exception:
        return None
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)
    return "parquet"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_table_to_parquet(
    conn: sqlite3.Connection,
    *,
    table: str,
    output_dir: str | Path,
    from_ts: str | None = None,
    to_ts: str | None = None,
) -> ExportManifest:
    query, params = build_export_query(table, from_ts=from_ts, to_ts=to_ts)
    rows = _sqlite_query(conn, query, params)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    parquet_path = output_path / f"{table}_{stamp}.parquet"
    fmt = _write_real_parquet_if_available(parquet_path, rows) or _write_jsonl_parquet_fallback(parquet_path, rows)
    manifest_path = parquet_path.with_suffix(".manifest.json")
    manifest = ExportManifest(
        table=table,
        path=str(parquet_path),
        manifest_path=str(manifest_path),
        format=fmt,
        row_count=len(rows),
        sha256=_sha256(parquet_path),
        created_at=datetime.now(UTC).isoformat(),
        from_ts=from_ts,
        to_ts=to_ts,
    )
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _scalar(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> Any:
    try:
        row = conn.execute(query, params).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return row[0]


def _latest_age_seconds(conn: sqlite3.Connection) -> float | None:
    latest = _scalar(conn, "SELECT MAX(observed_at) FROM market_price_snapshots")
    if latest is None:
        latest = _scalar(conn, "SELECT MAX(observed_at) FROM shadow_predictions")
    if not latest:
        return None
    try:
        observed = datetime.fromisoformat(str(latest).replace("Z", "+00:00"))
    except ValueError:
        return None
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - observed).total_seconds())


def build_db_health_report(conn: sqlite3.Connection, *, migration_version: str | None = None) -> DBHealthReport:
    table_counts = {
        table: int(_scalar(conn, f"SELECT COUNT(*) FROM {table}") or 0)
        for table in ["market_price_snapshots", "orderbook_snapshots", "shadow_predictions", "crowd_flow_observations", "ingestion_health"]
    }
    failed_ingestion_count = int(_scalar(conn, "SELECT COUNT(*) FROM ingestion_health WHERE status NOT IN ('ok', 'healthy')") or 0)
    checks = {
        "latest_snapshot_age_seconds": _latest_age_seconds(conn),
        "table_growth_rows": table_counts,
        "failed_ingestion_count": failed_ingestion_count,
        "hypertable_compression_status": "requires_timescaledb_catalog; safe_read_only_check_in_prod",
        "migration_version": migration_version or "unknown_without_alembic_connection",
    }
    return DBHealthReport(checked_at=datetime.now(UTC).isoformat(), mode="read_only", checks=checks)


def write_db_health_report(conn: sqlite3.Connection, *, output_dir: str | Path, migration_version: str | None = None) -> DBHealthReport:
    report = build_db_health_report(conn, migration_version=migration_version)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    path = output_path / f"db_health_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


TIMESCALE_HEALTH_SQL = """
-- Read-only PostgreSQL/TimescaleDB health checks for Phase 9.
SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables ORDER BY hypertable_name;
SELECT hypertable_name, compression_enabled FROM timescaledb_information.hypertables ORDER BY hypertable_name;
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;
"""


RETENTION_AUDIT_POLICY = """
Retention policy: do not drop raw audit/replay archives. Database retention may only be
applied after an operator records the replay requirement, backup location, restore smoke
test, and raw archive coverage for the affected interval. Phase 9 ships documentation and
safe policy SQL; it does not execute destructive retention.
"""
