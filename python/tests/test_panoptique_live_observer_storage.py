import json
from pathlib import Path

import pytest

from panoptique.live_observer_storage import (
    LiveObserverStorageResult,
    create_live_observer_writer,
    write_live_observer_rows,
)
from weather_pm.live_observer_config import load_live_observer_config


def _config(tmp_path: Path, *, primary: str = "local_jsonl"):
    path = tmp_path / "config.yaml"
    path.write_text(
        f"""
version: 1
active_scenario: minimal
collection:
  enabled: true
  dry_run: false
scenarios:
  minimal:
    market_limit: 1
storage:
  enabled: true
  primary: {primary}
paths:
  base_dir: {tmp_path.as_posix()}
  jsonl_dir: {tmp_path.as_posix()}/jsonl
  parquet_dir: {tmp_path.as_posix()}/parquet
  manifests_dir: {tmp_path.as_posix()}/manifests
safety:
  paper_only: true
  live_order_allowed: false
""",
        encoding="utf-8",
    )
    return load_live_observer_config(path)


def test_local_jsonl_writer_uses_configured_base_dir_stream_and_returns_manifest(tmp_path):
    config = _config(tmp_path, primary="local_jsonl")
    writer = create_live_observer_writer(config, backend="local_jsonl", stream_name="compact_market_snapshot")

    result = writer.write_many([
        {"market_id": "m1", "observed_at": "2026-04-28T12:00:00+00:00"},
        {"market_id": "m2", "observed_at": "2026-04-28T12:01:00+00:00"},
    ])

    assert isinstance(result, LiveObserverStorageResult)
    assert result.backend == "local_jsonl"
    assert result.status == "written"
    assert result.row_count == 2
    assert result.paper_only is True
    assert result.path_or_uri.endswith("jsonl/compact_market_snapshot.jsonl")
    assert Path(result.path_or_uri).is_file()
    rows = [json.loads(line) for line in Path(result.path_or_uri).read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {"market_id": "m1", "observed_at": "2026-04-28T12:00:00+00:00"},
        {"market_id": "m2", "observed_at": "2026-04-28T12:01:00+00:00"},
    ]
    assert result.to_dict()["paper_only"] is True


def test_local_parquet_writer_falls_back_to_jsonl_explicitly_when_pyarrow_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("panoptique.live_observer_storage._pyarrow_available", lambda: False)
    config = _config(tmp_path, primary="local_parquet")
    writer = create_live_observer_writer(config, backend="local_parquet", stream_name="forecast_source_snapshot")

    result = writer.write_many([{"source": "noaa", "value": 12.5}])

    assert result.backend == "local_jsonl"
    assert result.requested_backend == "local_parquet"
    assert result.status == "fallback_jsonl"
    assert result.row_count == 1
    assert result.paper_only is True
    assert result.path_or_uri.endswith("jsonl/forecast_source_snapshot.jsonl")
    assert not result.path_or_uri.endswith(".parquet")


def test_not_configured_network_backends_return_skipped_dry_run_manifest(tmp_path):
    config = _config(tmp_path, primary="clickhouse")

    for backend in ["clickhouse", "postgres_timescale", "postgres", "s3_archive"]:
        result = write_live_observer_rows(
            config,
            backend=backend,
            stream_name="weather_bin_surface_snapshot",
            rows=[{"market_id": "m1"}],
        )

        assert result.backend == backend
        assert result.status == "skipped_not_configured"
        assert result.row_count == 0
        assert result.paper_only is True
        assert result.path_or_uri is None
        assert result.dry_run is True


def test_storage_refuses_non_paper_or_live_order_config(tmp_path):
    path = tmp_path / "unsafe.yaml"
    path.write_text(
        f"""
version: 1
active_scenario: minimal
collection:
  enabled: true
  dry_run: false
scenarios:
  minimal:
    market_limit: 1
storage:
  primary: local_jsonl
paths:
  base_dir: {tmp_path.as_posix()}
safety:
  paper_only: false
  live_order_allowed: false
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="paper_only"):
        load_live_observer_config(path)
