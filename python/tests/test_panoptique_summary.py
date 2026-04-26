from __future__ import annotations

import json
from pathlib import Path

from panoptique.cli import main
from panoptique.repositories import PanoptiqueRepository, connect_sqlite_memory
from panoptique.summary import build_panoptique_summary
from tests.test_panoptique_measurement import obs, pred, snap


def test_summary_degrades_without_repository() -> None:
    summary = build_panoptique_summary(None, report_path="reports/latest.md")

    assert summary.source == "none"
    assert summary.readiness_state == "empty"
    assert summary.shadow_prediction_count == 0
    assert summary.matched_observation_count == 0
    assert summary.current_gate_status == "not_enough_data"
    assert summary.latest_operator_report_path == "reports/latest.md"
    assert summary.recommendation is None


def test_summary_counts_repository_state_without_recommendations() -> None:
    conn = connect_sqlite_memory()
    repo = PanoptiqueRepository(conn)
    repo.create_schema()
    repo.insert_market_snapshot(snap("m1", 0, 0.50, 100.0))
    repo.insert_shadow_prediction(pred("p1", "bot_a", "up", 0.8))
    repo.insert_crowd_flow_observation(obs("p1", "m1", "bot_a", True, 0.03, 20.0, 0.8))

    summary = build_panoptique_summary(repo, report_path=Path("report.md"))

    assert summary.source == "db"
    assert summary.readiness_state == "ready"
    assert summary.snapshot_freshness_seconds is not None
    assert summary.shadow_prediction_count == 1
    assert summary.matched_observation_count == 1
    assert summary.current_gate_status == "measurement_pending"
    assert summary.latest_operator_report_path == "report.md"
    assert summary.recommendation is None


def test_cli_summary_json_degrades_without_db(capsys) -> None:
    exit_code = main(["summary", "--report-path", "report.md", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "none"
    assert payload["readiness_state"] == "empty"
    assert payload["current_gate_status"] == "not_enough_data"
    assert payload["latest_operator_report_path"] == "report.md"
    assert payload["recommendation"] is None
