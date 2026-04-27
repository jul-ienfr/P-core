import sys
import types

from panoptique.artifacts import S3ArtifactWriter


class FakeS3Client:
    def __init__(self):
        self.objects = []

    def put_object(self, **kwargs):
        self.objects.append(kwargs)


class FakeRepository:
    def __init__(self):
        self.rows = []

    def record_artifact_metadata(self, **kwargs):
        self.rows.append(kwargs)


def test_s3_artifact_writer_uploads_and_records_metadata():
    client = FakeS3Client()
    repo = FakeRepository()
    writer = S3ArtifactWriter(bucket="bucket", prefix="raw/date=2026-04-27", source="test", repository=repo, client=client)

    metadata = writer.upload_bytes("artifact.json", b"{}", content_type="application/json", run_id="run-1")

    assert client.objects[0]["Bucket"] == "bucket"
    assert client.objects[0]["Key"] == "raw/date=2026-04-27/artifact.json"
    assert metadata.path == "s3://bucket/raw/date=2026-04-27/artifact.json"
    assert repo.rows[0]["run_id"] == "run-1"
    assert repo.rows[0]["paper_only"] is True


def test_s3_artifact_writer_uses_path_style_config(monkeypatch):
    captured = {}

    class FakeConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_botocore_config = types.SimpleNamespace(Config=FakeConfig)
    fake_botocore = types.SimpleNamespace(config=fake_botocore_config)
    def fake_client(service, **kwargs):
        captured["call"] = (service, kwargs)
        return FakeS3Client()

    fake_boto3 = types.SimpleNamespace(client=fake_client)
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore", fake_botocore)
    monkeypatch.setitem(sys.modules, "botocore.config", fake_botocore_config)

    writer = S3ArtifactWriter(bucket="bucket", source="test", force_path_style=True)
    writer._create_client()

    service, kwargs = captured["call"]
    assert service == "s3"
    assert kwargs["config"].kwargs == {"s3": {"addressing_style": "path"}}
