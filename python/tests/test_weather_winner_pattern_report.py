from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PYTHON_SRC = Path(__file__).resolve().parents[1] / "src"


def _run_weather_pm(*args: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-m", "weather_pm.cli", *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(PYTHON_SRC)},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _winner_patterns() -> dict[str, object]:
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "robust_patterns": [{"pattern_id": "p1", "archetype": "threshold_harvester", "resolved_trades": 8}],
        "anti_patterns": [{"pattern_id": "bad", "reason": "negative_out_of_sample_pnl"}],
        "research_only_patterns": [],
        "summary": {"capturability_gaps": 2},
        "operator_next_actions": ["expand historical orderbook coverage"],
    }


def _paper_candidates() -> dict[str, object]:
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "paper_candidates": [{"market_id": "m1", "decision": "paper_candidate"}],
        "watch_only": [{"market_id": "m2", "decision": "watch_only", "reason": "missing_current_orderbook"}],
        "considered_markets": [
            {"market_id": "m1", "decision": "paper_candidate", "reason": "aligned"},
            {"market_id": "m2", "decision": "watch_only", "reason": "missing_current_orderbook"},
        ],
    }


def test_report_markdown_summarizes_required_operator_sections() -> None:
    from weather_pm.winner_pattern_report import build_winner_pattern_operator_report

    payload = build_winner_pattern_operator_report(_winner_patterns(), _paper_candidates(), resolution_coverage={"summary": {"resolved_pct": 87.5}}, orderbook_context={"summary": {"missing_orderbook_context": 2}})

    md = payload["markdown"]
    for section in [
        "# Weather Winner Pattern Engine",
        "Safety",
        "Coverage",
        "Robust patterns",
        "Anti-patterns",
        "Capturability gaps",
        "Paper candidates / watch-only",
        "Next data gaps",
    ]:
        assert section in md
    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False


def test_cli_winner_pattern_report_writes_json_md_and_compact_stdout(tmp_path: Path) -> None:
    patterns_path = tmp_path / "patterns.json"
    candidates_path = tmp_path / "candidates.json"
    coverage_path = tmp_path / "coverage.json"
    orderbook_path = tmp_path / "orderbook.json"
    output_json = tmp_path / "report.json"
    output_md = tmp_path / "report.md"
    patterns_path.write_text(json.dumps(_winner_patterns()), encoding="utf-8")
    candidates_path.write_text(json.dumps(_paper_candidates()), encoding="utf-8")
    coverage_path.write_text(json.dumps({"summary": {"resolved_pct": 87.5}}), encoding="utf-8")
    orderbook_path.write_text(json.dumps({"summary": {"missing_orderbook_context": 2}}), encoding="utf-8")

    result = _run_weather_pm(
        "winner-pattern-report",
        "--winner-patterns-json", str(patterns_path),
        "--paper-candidates-json", str(candidates_path),
        "--resolution-coverage-json", str(coverage_path),
        "--orderbook-context-json", str(orderbook_path),
        "--output-json", str(output_json),
        "--output-md", str(output_md),
    )

    assert result == {
        "paper_only": True,
        "live_order_allowed": False,
        "robust_patterns": 1,
        "paper_candidates": 1,
        "watch_only": 1,
        "output_md": str(output_md),
    }
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert artifact["summary"]["robust_patterns"] == 1
    assert "# Weather Winner Pattern Engine" in output_md.read_text(encoding="utf-8")
