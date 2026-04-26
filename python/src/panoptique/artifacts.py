from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Iterator
from uuid import uuid4

from .contracts import ArtifactMetadata


def _row_to_dict(row: Any) -> dict[str, Any]:
    if hasattr(row, "to_dict"):
        value = row.to_dict()
    elif isinstance(row, dict):
        value = row
    else:
        raise TypeError("JSONL audit rows must be JSON object mappings or contracts")
    if not isinstance(value, dict):
        raise TypeError("JSONL audit rows must encode to a JSON object")
    return value


class JsonlArtifactWriter:
    """Append-only raw JSONL writer for audit/replay archives."""

    def __init__(self, path: str | Path, *, source: str, artifact_type: str = "jsonl") -> None:
        self.path = Path(path)
        self.source = source
        self.artifact_type = artifact_type

    def write_many(self, rows: Iterable[Any]) -> ArtifactMetadata:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with self.path.open("a", encoding="utf-8") as handle:
            for row in rows:
                payload = _row_to_dict(row)
                handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
                handle.write("\n")
                count += 1
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        return ArtifactMetadata(
            artifact_id=str(uuid4()),
            artifact_type=self.artifact_type,
            path=str(self.path),
            created_at=datetime.now(UTC),
            source=self.source,
            row_count=count,
            sha256=digest,
        )


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise TypeError("JSONL audit row is not a JSON object")
                yield value
