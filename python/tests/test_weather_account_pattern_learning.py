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


def test_account_pattern_learning_digest_turns_validation_and_radar_into_guardrails(tmp_path: Path) -> None:
    validation = tmp_path / "validation.json"
    radar = tmp_path / "radar.json"
    output_json = tmp_path / "digest.json"
    output_md = tmp_path / "digest.md"

    validation.write_text(
        json.dumps(
            {
                "paper_only": True,
                "live_order_allowed": False,
                "robust_patterns_confirmed_out_of_sample": [
                    {
                        "handle": "jey",
                        "city": "Toronto",
                        "weather_market_type": "threshold",
                        "effective_position": "no",
                        "test_pnl": 42.0,
                        "test_roi": 0.21,
                        "test_trades": 8,
                        "walk_forward_score": 3.4,
                    }
                ],
                "anti_patterns_to_ban": [
                    {
                        "handle": "marchyel",
                        "city": "New York City",
                        "market_type": "exact_range",
                        "side": "no",
                        "pnl": -265.6,
                        "roi": -0.065,
                        "trades": 10,
                    }
                ],
                "downgraded_suspect_concentrated_positives": [
                    {"handle": "whale", "top1_pnl_share": 0.91, "trades": 4}
                ],
            }
        ),
        encoding="utf-8",
    )
    radar.write_text(
        json.dumps(
            {
                "paper_only": True,
                "live_order_allowed": False,
                "summary": {"matched_market_sides": 2},
                "candidates": [
                    {
                        "radar_action": "WATCH_CONFLICTS_REQUIRE_MANUAL_REVIEW",
                        "city": "New York City",
                        "weather_market_type": "exact_range",
                        "effective_position": "No",
                        "question": "Will the highest temperature in New York City be between 60-61°F on April 29?",
                        "book": {"best_ask": 0.07, "spread": 0.01},
                        "anti_pattern_conflicts": [
                            {"handle": "marchyel", "kind": "anti_city", "pnl": -265.6, "roi": -0.065, "trades": 10}
                        ],
                        "suspect_concentration_hits": [],
                    },
                    {
                        "radar_action": "WATCH_STALE_OR_EXTREME_PRICE",
                        "city": "Toronto",
                        "weather_market_type": "threshold",
                        "effective_position": "No",
                        "question": "Will the high temperature in Toronto be 20°C or higher?",
                        "book": {"best_ask": 0.91, "spread": 0.01},
                        "anti_pattern_conflicts": [],
                        "suspect_concentration_hits": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = _run_weather_pm(
        "account-pattern-learning-digest",
        "--validation-json",
        str(validation),
        "--live-radar-json",
        str(radar),
        "--output-json",
        str(output_json),
        "--output-md",
        str(output_md),
    )

    assert result["summary"]["robust_patterns"] == 1
    assert result["summary"]["anti_patterns"] == 1
    assert result["summary"]["radar_candidates"] == 2
    assert result["summary"]["blocked_by_conflict"] == 1
    assert result["summary"]["watch_only"] == 2
    assert result["summary"]["paper_shadow_probe_authorized"] == 0
    assert result["summary"]["real_order_authorized"] == 0
    assert "paper_probe_authorized" not in result["summary"]
    assert result["summary"]["paper_only"] is True
    assert result["summary"]["live_order_allowed"] is False

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    assert payload["guardrails"][0]["rule"] == "block_conflicting_anti_patterns"
    assert payload["radar_lessons"][0]["operator_action"] == "watch_only_conflict_visible"
    markdown = output_md.read_text(encoding="utf-8")
    assert markdown.startswith("# Account Pattern Learning Digest")
    assert "paper_shadow_probe_authorized=0" in markdown
    assert "real_order_authorized=0" in markdown
    assert "paper_probe_authorized" not in markdown
