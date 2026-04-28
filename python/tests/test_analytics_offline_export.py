from __future__ import annotations

import csv
import json
import sys
from datetime import UTC, datetime

from prediction_core.analytics.events import StrategyMetricEvent
from prediction_core.analytics.offline import export_offline_audit, offline_audit_metadata


def test_offline_audit_export_writes_metric_and_report_rows_without_duckdb(tmp_path) -> None:
    sys.modules.pop("duckdb", None)
    observed_at = datetime(2026, 4, 28, 12, 30, 15, 123000, tzinfo=UTC)
    report = {
        "strategy_id": "weather-v1",
        "profile_id": "profile-a",
        "market_id": "market-1",
        "net_pnl_usdc": 7.25,
        "paper_only": True,
        "live_order_allowed": False,
    }
    metric = StrategyMetricEvent(
        run_id="run-phase-4",
        strategy_id="weather-v1",
        profile_id="profile-a",
        market_id="market-1",
        observed_at=observed_at,
        mode="paper",
        signal_count=3,
        trade_count=1,
        skip_count=2,
        avg_edge=0.09,
        net_pnl_usdc=7.25,
        raw={"canonical_evaluation_report": report},
    )

    result = export_offline_audit(tmp_path, events=[metric], reports=[report])

    assert result.metadata == offline_audit_metadata()
    assert result.metadata["backend"] == "jsonl_csv"
    assert result.metadata["duckdb_required"] is False
    assert result.metadata["clickhouse_primary"] is True
    assert result.metadata["grafana_primary"] is True
    assert result.metadata["paper_only"] is True
    assert result.metadata["live_order_allowed"] is False
    assert "duckdb" not in sys.modules

    jsonl_rows = [json.loads(line) for line in result.jsonl_path.read_text().splitlines()]
    assert [row["table"] for row in jsonl_rows] == ["strategy_metrics", "canonical_evaluation_reports"]
    assert jsonl_rows[0]["observed_at"] == "2026-04-28 12:30:15.123"
    assert jsonl_rows[0]["raw"]["canonical_evaluation_report"] == report
    assert jsonl_rows[1]["canonical_evaluation_report"] == report
    assert result.row_counts == {"strategy_metrics": 1, "canonical_evaluation_reports": 1}

    with result.csv_path.open(newline="") as csv_file:
        csv_rows = list(csv.DictReader(csv_file))
    assert [row["table"] for row in csv_rows] == ["strategy_metrics", "canonical_evaluation_reports"]
    assert json.loads(csv_rows[0]["raw"])["canonical_evaluation_report"] == report
    assert json.loads(csv_rows[1]["canonical_evaluation_report"]) == report


def test_offline_audit_metadata_documents_canonical_cockpit_and_safety() -> None:
    metadata = offline_audit_metadata()

    assert metadata == {
        "backend": "jsonl_csv",
        "duckdb_required": False,
        "clickhouse_primary": True,
        "grafana_primary": True,
        "paper_only": True,
        "live_order_allowed": False,
    }
