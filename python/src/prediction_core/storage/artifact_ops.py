from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_ALLOWED_ARTIFACT_ROOTS = (
    Path("/home/jul/P-core/data/polymarket"),
    Path("/home/jul/P-core/data/panoptique"),
)
DEFAULT_MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 1024 * 1024 * 1024


def plan_artifact_mirror(
    *,
    input_dir: str | Path,
    bucket: str,
    prefix: str = "raw",
    source: str = "local",
    max_files: int | None = None,
    allow_outside_artifacts_root: bool = False,
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> dict[str, Any]:
    root = Path(input_dir)
    if max_files is not None and max_files < 0:
        raise ValueError("max_files must be non-negative")
    if max_file_size_bytes < 0:
        raise ValueError("max_file_size_bytes must be non-negative")
    if max_total_bytes < 0:
        raise ValueError("max_total_bytes must be non-negative")
    if not root.exists() or not root.is_dir():
        raise ValueError("input_dir must be an existing directory")
    if root.is_symlink():
        raise ValueError("input_dir symlinks are not allowed")
    root = root.resolve(strict=True)
    if not allow_outside_artifacts_root and not any(root == allowed or root.is_relative_to(allowed) for allowed in DEFAULT_ALLOWED_ARTIFACT_ROOTS):
        raise ValueError("input_dir must be under an allowed artifact root or use --allow-outside-artifacts-root")

    files = []
    total_bytes = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("artifact symlinks are not allowed")
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size > max_file_size_bytes:
            raise ValueError("artifact file exceeds max_file_size_bytes")
        if total_bytes + size > max_total_bytes:
            raise ValueError("artifact plan exceeds max_total_bytes")
        files.append(path)
        total_bytes += size
        if max_files is not None and len(files) >= max_files:
            break

    planned = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        key = _artifact_key(prefix=prefix, source=source, relative_path=relative)
        planned.append(
            {
                "path": str(path),
                "uri": f"s3://{bucket}/{key}",
                "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return {
        "dry_run": True,
        "input_dir": str(root),
        "bucket": bucket,
        "planned_count": len(planned),
        "total_bytes": total_bytes,
        "artifacts": planned,
    }


def replay_jsonl_audit_plan(*, jsonl_path: str | Path, max_rows: int | None = None) -> dict[str, Any]:
    if max_rows is not None and max_rows < 0:
        raise ValueError("max_rows must be non-negative")
    path = Path(jsonl_path)
    if not path.exists() or not path.is_file():
        raise ValueError("jsonl_path must be an existing file")
    rows = []
    event_type_counts: dict[str, int] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if max_rows is not None and len(rows) >= max_rows:
                break
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, dict):
                raise ValueError(f"line {line_number} must be a JSON object")
            event_type = str(payload.get("event_type") or "unknown")
            event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1
            rows.append({"line": line_number, "event_type": event_type, "has_payload": isinstance(payload.get("payload"), dict)})
    return {
        "dry_run": True,
        "jsonl_path": str(path),
        "row_count": len(rows),
        "event_type_counts": event_type_counts,
        "rows": rows,
        "planned_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def _artifact_key(*, prefix: str, source: str, relative_path: str) -> str:
    today = datetime.now(UTC).date().isoformat()
    clean_prefix = prefix.strip("/")
    clean_source = source.strip("/") or "local"
    return f"{clean_prefix}/source={clean_source}/date={today}/{relative_path.lstrip('/')}"
