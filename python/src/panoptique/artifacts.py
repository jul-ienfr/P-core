from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
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


class S3ArtifactWriter:
    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "",
        source: str,
        artifact_type: str = "artifact",
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        region: str | None = None,
        force_path_style: bool = False,
        repository: Any | None = None,
        client: Any | None = None,
    ) -> None:
        if not bucket.strip():
            raise ValueError("bucket is required")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.source = source
        self.artifact_type = artifact_type
        self.repository = repository
        self._client = client
        self._client_kwargs = {
            "endpoint_url": endpoint_url,
            "aws_access_key_id": access_key_id,
            "aws_secret_access_key": secret_access_key,
            "region_name": region or "us-east-1",
        }
        self.force_path_style = force_path_style

    def upload_bytes(
        self,
        key: str,
        payload: bytes,
        *,
        content_type: str | None = None,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        paper_only: bool = True,
    ) -> ArtifactMetadata:
        object_key = self._object_key(key)
        client = self._client or self._create_client()
        extra_args = {"ContentType": content_type} if content_type else None
        if extra_args:
            client.put_object(Bucket=self.bucket, Key=object_key, Body=payload, **extra_args)
        else:
            client.put_object(Bucket=self.bucket, Key=object_key, Body=payload)
        digest = hashlib.sha256(payload).hexdigest()
        artifact_id = str(uuid4())
        uri = f"s3://{self.bucket}/{object_key}"
        if self.repository is not None:
            self.repository.record_artifact_metadata(
                artifact_id=artifact_id,
                artifact_type=self.artifact_type,
                source=self.source,
                uri=uri,
                run_id=run_id,
                content_type=content_type,
                sha256=digest,
                size_bytes=len(payload),
                metadata=metadata or {},
                paper_only=paper_only,
            )
        return ArtifactMetadata(
            artifact_id=artifact_id,
            artifact_type=self.artifact_type,
            path=uri,
            created_at=datetime.now(UTC),
            source=self.source,
            row_count=0,
            sha256=digest,
        )

    def upload_file(
        self,
        path: str | Path,
        *,
        key: str | None = None,
        content_type: str | None = None,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        paper_only: bool = True,
    ) -> ArtifactMetadata:
        file_path = Path(path)
        return self.upload_bytes(
            key or file_path.name,
            file_path.read_bytes(),
            content_type=content_type,
            run_id=run_id,
            metadata=metadata,
            paper_only=paper_only,
        )

    def _object_key(self, key: str) -> str:
        clean_key = str(key).lstrip("/")
        return f"{self.prefix}/{clean_key}" if self.prefix else clean_key

    def _create_client(self) -> Any:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is required for S3 artifact storage") from exc
        kwargs = {key: value for key, value in self._client_kwargs.items() if value}
        if self.force_path_style:
            from botocore.config import Config

            kwargs["config"] = Config(s3={"addressing_style": "path"})
        return boto3.client("s3", **kwargs)


def create_s3_artifact_writer_from_env(
    *,
    source: str,
    artifact_type: str = "artifact",
    prefix: str = "",
    repository: Any | None = None,
) -> S3ArtifactWriter | None:
    bucket = os.environ.get("PREDICTION_CORE_S3_BUCKET")
    endpoint_url = os.environ.get("PREDICTION_CORE_S3_ENDPOINT_URL")
    if not bucket:
        return None
    return S3ArtifactWriter(
        bucket=bucket,
        prefix=prefix,
        source=source,
        artifact_type=artifact_type,
        endpoint_url=endpoint_url,
        access_key_id=os.environ.get("PREDICTION_CORE_S3_ACCESS_KEY_ID"),
        secret_access_key=os.environ.get("PREDICTION_CORE_S3_SECRET_ACCESS_KEY"),
        region=os.environ.get("PREDICTION_CORE_S3_REGION") or "us-east-1",
        force_path_style=os.environ.get("PREDICTION_CORE_S3_FORCE_PATH_STYLE", "true").strip().lower() in {"1", "true", "yes", "on"},
        repository=repository,
    )


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise TypeError("JSONL audit row is not a JSON object")
                yield value
