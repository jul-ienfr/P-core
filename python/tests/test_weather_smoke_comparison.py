from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PYTHON_SRC = Path(__file__).resolve().parents[1] / "src"


def test_smoke_comparison_reports_pattern_blocker_and_context_deltas() -> None:
    from weather_pm.smoke_comparison import build_smoke_comparison

    before = {
        "paper_only": True,
        "live_order_allowed": False,
        "summary": {"robust_patterns": 0, "research_only_patterns": 1},
        "research_only_patterns": [
            {"pattern_id": "threshold|toronto|buy|unclear", "promotion_blockers": ["missing_weather_context", "insufficient_historical_orderbook_coverage"]}
        ],
        "resolution_coverage_summary": {"resolved_pct": 50.0},
        "orderbook_context_summary": {"with_orderbook_context": 0, "missing_orderbook_context": 10},
    }
    after = {
        "paper_only": True,
        "live_order_allowed": False,
        "summary": {"robust_patterns": 1, "research_only_patterns": 0},
        "robust_patterns": [{"pattern_id": "threshold|toronto|buy|unclear", "promotion_blockers": []}],
        "resolution_coverage_summary": {"resolved_pct": 100.0},
        "orderbook_context_summary": {"with_orderbook_context": 8, "missing_orderbook_context": 2},
    }

    payload = build_smoke_comparison(before, after)

    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    assert payload["summary"]["robust_patterns_delta"] == 1
    assert payload["summary"]["research_only_patterns_delta"] == -1
    assert payload["context_deltas"]["resolved_pct"] == {"before": 50.0, "after": 100.0, "delta": 50.0}
    assert payload["context_deltas"]["with_orderbook_context"] == {"before": 0, "after": 8, "delta": 8}
    assert payload["patterns"][0]["removed_blockers"] == ["insufficient_historical_orderbook_coverage", "missing_weather_context"]
    assert "robust_patterns: 0 -> 1 (+1)" in payload["markdown"]
    assert "removed blockers: insufficient_historical_orderbook_coverage, missing_weather_context" in payload["markdown"]


def test_cli_smoke_comparison_writes_json_and_markdown(tmp_path: Path) -> None:
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    output_json = tmp_path / "delta.json"
    output_md = tmp_path / "delta.md"
    before.write_text(json.dumps({"paper_only": True, "live_order_allowed": False, "summary": {"robust_patterns": 0}}), encoding="utf-8")
    after.write_text(json.dumps({"paper_only": True, "live_order_allowed": False, "summary": {"robust_patterns": 2}}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "smoke-comparison",
            "--before-json",
            str(before),
            "--after-json",
            str(after),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(PYTHON_SRC)},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"robust_patterns_delta": 2, "research_only_patterns_delta": 0}
    written = json.loads(output_json.read_text(encoding="utf-8"))
    assert written["summary"]["robust_patterns_delta"] == 2
    assert "robust_patterns: 0 -> 2 (+2)" in output_md.read_text(encoding="utf-8")
