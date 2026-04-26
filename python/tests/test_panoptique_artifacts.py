from __future__ import annotations

from datetime import UTC, datetime
import json

from panoptique.artifacts import JsonlArtifactWriter, read_jsonl
from panoptique.contracts import Market


def test_jsonl_artifact_writer_appends_contract_rows_and_metadata(tmp_path) -> None:
    path = tmp_path / "audit" / "markets.jsonl"
    writer = JsonlArtifactWriter(path, source="unit-test", artifact_type="markets")
    created = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)

    metadata = writer.write_many(
        [
            Market(
                market_id="pm-1",
                slug="weather-nyc",
                question="Will it rain in NYC?",
                source="polymarket",
                created_at=created,
                raw={"gamma_id": "1"},
            )
        ]
    )

    assert path.exists()
    rows = list(read_jsonl(path))
    assert rows[0]["market_id"] == "pm-1"
    assert rows[0]["created_at"] == "2026-04-26T12:00:00+00:00"
    assert metadata.row_count == 1
    assert metadata.sha256
    assert metadata.path == str(path)
    assert json.loads(metadata.to_json())["artifact_type"] == "markets"


def test_jsonl_writer_rejects_non_object_rows(tmp_path) -> None:
    writer = JsonlArtifactWriter(tmp_path / "bad.jsonl", source="unit-test")

    try:
        writer.write_many([["not", "an", "object"]])
    except TypeError as exc:
        assert "JSON object" in str(exc)
    else:
        raise AssertionError("expected non-object row rejection")
