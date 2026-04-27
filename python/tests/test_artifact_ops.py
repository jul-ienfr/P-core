import json

import pytest

from prediction_core.storage.artifact_ops import plan_artifact_mirror, replay_jsonl_audit_plan


def test_plan_artifact_mirror_builds_s3_uris(tmp_path):
    artifact = tmp_path / "nested" / "artifact.json"
    artifact.parent.mkdir()
    artifact.write_text("{}", encoding="utf-8")

    result = plan_artifact_mirror(input_dir=tmp_path, bucket="bucket", prefix="raw", source="weather_pm", allow_outside_artifacts_root=True)

    assert result["dry_run"] is True
    assert result["planned_count"] == 1
    assert result["artifacts"][0]["uri"].startswith("s3://bucket/raw/source=weather_pm/date=")
    assert result["artifacts"][0]["uri"].endswith("/nested/artifact.json")
    assert result["artifacts"][0]["sha256"]


def test_plan_artifact_mirror_rejects_missing_dir(tmp_path):
    with pytest.raises(ValueError, match="input_dir"):
        plan_artifact_mirror(input_dir=tmp_path / "missing", bucket="bucket", allow_outside_artifacts_root=True)


def test_plan_artifact_mirror_rejects_outside_allowed_roots_by_default(tmp_path):
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="allowed artifact root"):
        plan_artifact_mirror(input_dir=tmp_path, bucket="bucket")


def test_plan_artifact_mirror_rejects_symlinks_and_size_limits(tmp_path):
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}", encoding="utf-8")
    link = tmp_path / "artifact-link.json"
    link.symlink_to(artifact)

    with pytest.raises(ValueError, match="symlinks"):
        plan_artifact_mirror(input_dir=tmp_path, bucket="bucket", allow_outside_artifacts_root=True)

    link.unlink()
    with pytest.raises(ValueError, match="max_file_size_bytes"):
        plan_artifact_mirror(input_dir=tmp_path, bucket="bucket", allow_outside_artifacts_root=True, max_file_size_bytes=1)
    with pytest.raises(ValueError, match="max_total_bytes"):
        plan_artifact_mirror(input_dir=tmp_path, bucket="bucket", allow_outside_artifacts_root=True, max_total_bytes=1)


def test_plan_artifact_mirror_rejects_negative_max_files(tmp_path):
    with pytest.raises(ValueError, match="max_files"):
        plan_artifact_mirror(input_dir=tmp_path, bucket="bucket", allow_outside_artifacts_root=True, max_files=-1)


def test_replay_jsonl_audit_plan_counts_event_types(tmp_path):
    path = tmp_path / "audit.jsonl"
    path.write_text(
        json.dumps({"event_type": "seen", "payload": {}}) + "\n" + json.dumps({"event_type": "seen", "payload": {}}) + "\n",
        encoding="utf-8",
    )

    result = replay_jsonl_audit_plan(jsonl_path=path)

    assert result["dry_run"] is True
    assert result["row_count"] == 2
    assert result["event_type_counts"] == {"seen": 2}
    assert result["rows"][0]["has_payload"] is True


def test_replay_jsonl_audit_plan_rejects_negative_max_rows(tmp_path):
    path = tmp_path / "audit.jsonl"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="max_rows"):
        replay_jsonl_audit_plan(jsonl_path=path, max_rows=-1)
