from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from panoptique.contracts import CrowdFlowObservation, ShadowPrediction
from panoptique.repositories import PanoptiqueRepository, connect_sqlite_memory
from panoptique.storage_exports import (
    EXPORTABLE_TABLES,
    build_db_health_report,
    build_export_query,
    export_table_to_parquet,
    redact_secrets,
)


def _repo_with_fixture_rows() -> PanoptiqueRepository:
    repo = PanoptiqueRepository(connect_sqlite_memory())
    repo.create_schema()
    observed_at = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)
    repo.insert_shadow_prediction(
        ShadowPrediction(
            prediction_id="pred-1",
            market_id="m1",
            agent_id="agent-a",
            observed_at=observed_at,
            horizon_seconds=900,
            predicted_crowd_direction="up",
            confidence=0.72,
            rationale="fixture",
            features={"signal": "ok", "api_key": "must-not-leak"},
        )
    )
    repo.insert_crowd_flow_observation(
        CrowdFlowObservation(
            observation_id="obs-1",
            prediction_id="pred-1",
            market_id="m1",
            observed_at=observed_at,
            window_seconds=900,
            price_delta=0.03,
            volume_delta=42.0,
            direction_hit=True,
            liquidity_caveat=None,
            metrics={"token": "must-not-leak", "spread": 0.02},
        )
    )
    return repo


def test_export_query_is_allowlisted_and_parameterized() -> None:
    query, params = build_export_query(
        "shadow_predictions",
        from_ts="2026-04-26T00:00:00+00:00",
        to_ts="2026-04-27T00:00:00+00:00",
    )

    assert "shadow_predictions" in EXPORTABLE_TABLES
    assert "FROM shadow_predictions" in query
    assert ":from_ts" in query
    assert ":to_ts" in query
    assert params == {"from_ts": "2026-04-26T00:00:00+00:00", "to_ts": "2026-04-27T00:00:00+00:00"}


def test_export_query_rejects_unapproved_tables() -> None:
    try:
        build_export_query("wallets")
    except ValueError as exc:
        assert "not exportable" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("wallets must not be exportable")


def test_redact_secrets_recurses_payloads() -> None:
    payload = {"api_key": "abc", "nested": {"token": "def", "safe": 1}, "rows": [{"secret": "ghi"}]}

    assert redact_secrets(payload) == {
        "api_key": "[REDACTED]",
        "nested": {"token": "[REDACTED]", "safe": 1},
        "rows": [{"secret": "[REDACTED]"}],
    }


def test_export_table_to_parquet_writes_manifest_and_redacts_json_fallback(tmp_path: Path) -> None:
    repo = _repo_with_fixture_rows()
    out_dir = tmp_path / "exports"

    manifest = export_table_to_parquet(
        repo.conn,
        table="shadow_predictions",
        output_dir=out_dir,
        from_ts="2026-04-26T00:00:00+00:00",
        to_ts="2026-04-27T00:00:00+00:00",
    )

    assert manifest.table == "shadow_predictions"
    assert manifest.row_count == 1
    assert manifest.path.endswith(".parquet")
    assert manifest.format in {"parquet", "jsonl-parquet-fallback"}
    assert Path(manifest.path).exists()
    manifest_payload = json.loads(Path(manifest.manifest_path).read_text())
    assert manifest_payload["source_of_truth"] == "postgresql_timescaledb_or_local_fixture"
    assert manifest_payload["paper_only"] is True
    exported_text = Path(manifest.path).read_bytes().decode("utf-8", errors="ignore")
    assert "must-not-leak" not in exported_text
    assert "[REDACTED]" in exported_text


def test_db_health_report_is_read_only_and_contains_required_checks() -> None:
    repo = _repo_with_fixture_rows()
    report = build_db_health_report(repo.conn, migration_version="0001_storage_foundation")
    payload = report.to_dict()

    assert payload["mode"] == "read_only"
    assert payload["checks"]["migration_version"] == "0001_storage_foundation"
    assert "latest_snapshot_age_seconds" in payload["checks"]
    assert "table_growth_rows" in payload["checks"]
    assert "failed_ingestion_count" in payload["checks"]
    assert "hypertable_compression_status" in payload["checks"]


def test_export_cli_exports_shadow_predictions(tmp_path: Path, capsys) -> None:
    from panoptique.cli import main

    db_path = tmp_path / "fixture.sqlite"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    repo = PanoptiqueRepository(conn)
    repo.create_schema()
    conn.close()
    repo = PanoptiqueRepository(sqlite3.connect(db_path))
    repo.insert_shadow_prediction(
        ShadowPrediction(
            prediction_id="pred-cli",
            market_id="m1",
            agent_id="agent-a",
            observed_at=datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
            horizon_seconds=900,
            predicted_crowd_direction="up",
            confidence=0.6,
            rationale="cli fixture",
            features={},
        )
    )
    repo.conn.close()

    status = main(
        [
            "export-parquet",
            "--table",
            "shadow_predictions",
            "--from",
            "2026-04-26T00:00:00+00:00",
            "--to",
            "2026-04-27T00:00:00+00:00",
            "--output-dir",
            str(tmp_path / "out"),
            "--sqlite-db",
            str(db_path),
        ]
    )

    assert status == 0
    captured = capsys.readouterr().out
    assert "export-parquet status=ok count=1" in captured
    assert "artifact=" in captured
