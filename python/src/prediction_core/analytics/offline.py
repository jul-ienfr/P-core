from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from prediction_core.analytics.events import serialize_event

_OFFLINE_METADATA: dict[str, bool | str] = {
    "backend": "jsonl_csv",
    "duckdb_required": False,
    "clickhouse_primary": True,
    "grafana_primary": True,
    "paper_only": True,
    "live_order_allowed": False,
}


@dataclass(frozen=True)
class OfflineAuditExportResult:
    """Paths and row counts produced by a lightweight offline audit export."""

    jsonl_path: Path
    csv_path: Path
    row_counts: dict[str, int]
    metadata: dict[str, bool | str]


def offline_audit_metadata() -> dict[str, bool | str]:
    """Return explicit guardrail metadata for local JSONL/CSV audit exports.

    ClickHouse/Grafana remain the canonical analytics cockpit. This helper is a
    reproducible local fallback and intentionally does not import or require
    DuckDB or any other analytical store.
    """

    return dict(_OFFLINE_METADATA)


def export_offline_audit(
    output_dir: str | Path,
    *,
    events: Iterable[Any] = (),
    reports: Iterable[Mapping[str, Any] | Any] = (),
    basename: str = "prediction_core_offline_audit",
) -> OfflineAuditExportResult:
    """Write normalized analytics rows to JSONL and CSV for local audit work.

    The export is intentionally stdlib-only and append-store neutral: it mirrors
    canonical analytics/evaluation rows for reproducible local inspection while
    preserving ClickHouse as primary storage and Grafana as the operator UI.
    """

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    rows = [*_event_rows(events), *_report_rows(reports)]
    row_counts: dict[str, int] = {}
    for row in rows:
        table = str(row.get("table", ""))
        row_counts[table] = row_counts.get(table, 0) + 1

    jsonl_path = destination / f"{basename}.jsonl"
    csv_path = destination / f"{basename}.csv"
    _write_jsonl(jsonl_path, rows)
    _write_csv(csv_path, rows)
    return OfflineAuditExportResult(
        jsonl_path=jsonl_path,
        csv_path=csv_path,
        row_counts=row_counts,
        metadata=offline_audit_metadata(),
    )


def _event_rows(events: Iterable[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in events:
        table = getattr(event, "table", event.__class__.__name__)
        row = serialize_event(event)
        row["table"] = table
        row = _decode_json_fields(row, fields=("raw", "settings"))
        rows.append(_normalize_value(row))
    return rows


def _report_rows(reports: Iterable[Mapping[str, Any] | Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for report in reports:
        payload = _mapping_from(report)
        rows.append(
            _normalize_value(
                {
                    "table": "canonical_evaluation_reports",
                    "canonical_evaluation_report": payload,
                    "paper_only": payload.get("paper_only", True),
                    "live_order_allowed": payload.get("live_order_allowed", False),
                }
            )
        )
    return rows


def _mapping_from(value: Mapping[str, Any] | Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    asdict_method = getattr(value, "asdict", None)
    if callable(asdict_method):
        return dict(asdict_method())
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Unsupported offline audit report type: {type(value)!r}")


def _decode_json_fields(row: dict[str, Any], *, fields: Iterable[str]) -> dict[str, Any]:
    decoded = dict(row)
    for field in fields:
        value = decoded.get(field)
        if isinstance(value, str):
            try:
                decoded[field] = json.loads(value)
            except json.JSONDecodeError:
                pass
    return decoded


def _normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:23]
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_value(item) for item in value]
    return value


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({field for row in rows for field in row}) or ["table"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_cell(row.get(field)) for field in fieldnames})


def _csv_cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    if value is None:
        return ""
    return value
