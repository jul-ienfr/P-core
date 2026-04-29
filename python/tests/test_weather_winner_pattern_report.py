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
        "robust_patterns": [
            {
                "pattern_id": "p1",
                "archetype": "threshold_harvester",
                "resolved_trades": 20,
                "promotion_eligible": True,
                "promotion_blockers": [],
                "promotion_metrics": {"oos_resolved_trades": 8, "historical_capturable_ratio": 0.9},
            }
        ],
        "anti_patterns": [{"pattern_id": "bad", "reason": "negative_out_of_sample_pnl"}],
        "research_only_patterns": [
            {
                "pattern_id": "blocked",
                "reason": "insufficient_resolved_sample",
                "promotion_eligible": False,
                "promotion_blockers": ["insufficient_resolved_sample", "stale_forecast"],
                "promotion_metrics": {"resolved_trades": 12, "forecast_fresh_pct": 50.0},
            }
        ],
        "summary": {"capturability_gaps": 2, "promotion_gate_version": "weather_winner_pattern_v2_2026_04"},
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
        "Research-only patterns",
        "Capturability gaps",
        "Paper candidates / watch-only",
        "Promotion readiness",
        "Promotion blockers",
        "Next data gaps",
    ]:
        assert section in md
    assert "Promotion gate: weather_winner_pattern_v2_2026_04" in md
    assert "Eligible robust patterns: 1" in md
    assert "blocked: insufficient_resolved_sample, stale_forecast" in md
    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False


def test_report_markdown_surfaces_research_only_matches_as_watch_not_probe() -> None:
    from weather_pm.winner_pattern_report import build_winner_pattern_operator_report

    patterns = {
        "paper_only": True,
        "live_order_allowed": False,
        "robust_patterns": [],
        "anti_patterns": [],
        "research_only_patterns": [
            {
                "pattern_id": "threshold|seoul|buy|unclear",
                "reason": "concentrated_or_small_sample",
                "examples": 18,
                "out_of_sample_pnl": 12.5,
                "promotion_eligible": False,
                "promotion_blockers": ["insufficient_resolved_sample", "wallet_concentrated_pnl"],
                "promotion_metrics": {
                    "resolved_trades": 18,
                    "oos_pnl": 4.2,
                    "oos_win_rate": 0.61,
                    "historical_capturable_ratio": 0.83,
                    "forecast_fresh_pct": 100.0,
                },
            },
            {
                "pattern_id": "threshold|paris|buy|unclear",
                "reason": "stale_forecast",
                "examples": 9,
                "out_of_sample_pnl": 2.0,
                "promotion_eligible": False,
                "promotion_blockers": ["stale_forecast", "insufficient_resolved_sample"],
                "promotion_metrics": {"resolved_trades": 9, "forecast_fresh_pct": 22.0},
            },
        ],
        "operator_next_actions": ["Expand sample size and reduce wallet concentration before promotion."],
    }
    candidates = {
        "paper_only": True,
        "live_order_allowed": False,
        "paper_candidates": [],
        "watch_only": [
            {
                "market_id": "2112238",
                "decision": "watch_only",
                "reason": "research_only_pattern_match",
                "matched_pattern_id": "threshold|seoul|buy|unclear",
                "matched_pattern_status": "research_only",
                "paper_probe_authorized": False,
            }
        ],
        "summary": {"research_only_matches": 1},
    }

    payload = build_winner_pattern_operator_report(patterns, candidates)

    md = payload["markdown"]
    assert "Research-only patterns" in md
    assert "threshold|seoul|buy|unclear: concentrated_or_small_sample" in md
    assert "Research-only matches: 1" in md
    assert "2112238: research_only_pattern_match -> threshold|seoul|buy|unclear" in md
    assert "Paper candidates: 0" in md
    assert "Top promotion blockers" in md
    assert "insufficient_resolved_sample: 2" in md
    assert "wallet_concentrated_pnl: 1" in md
    assert "Closest research-only patterns" in md
    assert "threshold|seoul|buy|unclear: readiness=" in md
    assert "resolved=18" in md
    assert payload["summary"]["research_only_matches"] == 1
    assert payload["summary"]["top_promotion_blockers"] == [
        {"blocker": "insufficient_resolved_sample", "patterns": 2},
        {"blocker": "stale_forecast", "patterns": 1},
        {"blocker": "wallet_concentrated_pnl", "patterns": 1},
    ]
    assert payload["summary"]["closest_research_only_patterns"][0]["pattern_id"] == "threshold|seoul|buy|unclear"
    assert payload["summary"]["closest_research_only_patterns"][0]["paper_only"] is True
    assert payload["summary"]["closest_research_only_patterns"][0]["live_order_allowed"] is False
    assert payload["live_order_allowed"] is False


def test_report_surfaces_actionable_blocker_gaps_when_metrics_available() -> None:
    from weather_pm.winner_pattern_report import build_winner_pattern_operator_report

    patterns = {
        "paper_only": True,
        "live_order_allowed": False,
        "robust_patterns": [],
        "research_only_patterns": [
            {
                "pattern_id": "threshold|toronto|buy|unclear",
                "promotion_eligible": False,
                "promotion_blockers": ["incomplete_forecast_context", "stale_forecast"],
                "promotion_metrics": {
                    "resolved_trades": 29,
                    "forecast_complete_pct": 0.0,
                    "forecast_fresh_pct": 0.0,
                },
            }
        ],
        "anti_patterns": [
            {
                "pattern_id": "threshold|toronto|sell|unclear",
                "promotion_eligible": False,
                "promotion_blockers": [
                    "insufficient_resolved_sample",
                    "insufficient_independent_wallets",
                ],
                "promotion_metrics": {"resolved_trades": 15, "unique_wallets": 2},
            }
        ],
    }

    payload = build_winner_pattern_operator_report(patterns, _paper_candidates())

    gaps = payload["summary"]["promotion_blocker_gaps"]
    assert gaps[0] == {
        "pattern_id": "threshold|toronto|buy|unclear",
        "blocker": "incomplete_forecast_context",
        "current": "0/29",
        "required": "28/29",
        "missing": 28,
    }
    assert {
        "pattern_id": "threshold|toronto|buy|unclear",
        "blocker": "stale_forecast",
        "current": "0/29",
        "required": "27/29",
        "missing": 27,
    } in gaps
    assert {
        "pattern_id": "threshold|toronto|sell|unclear",
        "blocker": "insufficient_resolved_sample",
        "current": 15,
        "required": 20,
        "missing": 5,
    } in gaps
    assert {
        "pattern_id": "threshold|toronto|sell|unclear",
        "blocker": "insufficient_independent_wallets",
        "current": 2,
        "required": 4,
        "missing": 2,
    } in gaps
    assert "Promotion blocker gaps" in payload["markdown"]
    assert "threshold|toronto|buy|unclear / incomplete_forecast_context: 0/29, need 28/29 (+28)" in payload["markdown"]
    assert "threshold|toronto|sell|unclear / insufficient_resolved_sample: 15, need 20 (+5)" in payload["markdown"]


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
