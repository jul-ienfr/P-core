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


def _patterns() -> dict[str, object]:
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "robust_patterns": [
            {"pattern_id": "p1", "market_type": "high_temperature", "city": "Paris", "side": "YES", "archetype": "threshold_harvester", "pattern_status": "robust_candidate"}
        ],
        "anti_patterns": [
            {"pattern_id": "bad", "market_type": "rain", "city": "Paris", "side": "YES", "pattern_status": "anti_pattern", "block_live_radar": True}
        ],
    }


def _market(market_id: str = "m1", market_type: str = "high_temperature") -> dict[str, object]:
    return {"market_id": market_id, "id": market_id, "city": "Paris", "market_type": market_type, "side": "YES", "question": "Will Paris high exceed 21C?"}


def test_robust_match_missing_current_book_stays_watch_only() -> None:
    from weather_pm.paper_candidate_gate import build_winner_pattern_paper_candidates

    payload = build_winner_pattern_paper_candidates(_patterns(), {"markets": [_market()]}, {"orderbooks": []}, {"contexts": [{"market_id": "m1", "weather_context_available": True}]})

    row = payload["considered_markets"][0]
    assert row["decision"] == "watch_only"
    assert row["reason"] == "missing_current_orderbook"
    assert row["paper_probe_authorized"] is False


def test_research_only_pattern_match_is_labeled_for_operator_without_authorizing_probe() -> None:
    from weather_pm.paper_candidate_gate import build_winner_pattern_paper_candidates

    patterns = {
        "paper_only": True,
        "live_order_allowed": False,
        "robust_patterns": [],
        "anti_patterns": [],
        "research_only_patterns": [
            {
                "pattern_id": "research-threshold-paris-yes",
                "market_type": "high_temperature",
                "city": "Paris",
                "side": "YES",
                "pattern_status": "research_only",
                "reason": "concentrated_or_small_sample",
            }
        ],
    }

    payload = build_winner_pattern_paper_candidates(
        patterns,
        {"markets": [_market()]},
        {"orderbooks": [{"market_id": "m1", "best_bid": 0.4, "best_ask": 0.42, "spread": 0.02}]},
        {"contexts": [{"market_id": "m1", "weather_context_available": True}]},
    )

    row = payload["considered_markets"][0]
    assert row["decision"] == "watch_only"
    assert row["reason"] == "research_only_pattern_match"
    assert row["matched_pattern_id"] == "research-threshold-paris-yes"
    assert row["matched_pattern_status"] == "research_only"
    assert row["paper_probe_authorized"] is False
    assert payload["summary"]["research_only_matches"] == 1
    assert payload["live_order_allowed"] is False


def test_anti_pattern_conflict_blocks_candidate() -> None:
    from weather_pm.paper_candidate_gate import build_winner_pattern_paper_candidates

    payload = build_winner_pattern_paper_candidates(_patterns(), {"markets": [_market("m2", "rain")]}, {"orderbooks": [{"market_id": "m2", "best_bid": 0.4, "best_ask": 0.42, "spread": 0.02}]}, {"contexts": [{"market_id": "m2", "weather_context_available": True}]})

    row = payload["considered_markets"][0]
    assert row["decision"] == "blocked"
    assert row["reason"] == "anti_pattern_conflict"
    assert row["paper_probe_authorized"] is False


def test_fully_aligned_tiny_paper_candidate_never_allows_live_orders() -> None:
    from weather_pm.paper_candidate_gate import build_winner_pattern_paper_candidates

    payload = build_winner_pattern_paper_candidates(_patterns(), {"markets": [_market()]}, {"orderbooks": [{"market_id": "m1", "best_bid": 0.4, "best_ask": 0.42, "spread": 0.02, "depth_near_touch": 100}]}, {"contexts": [{"market_id": "m1", "weather_context_available": True}]})

    row = payload["paper_candidates"][0]
    assert row["decision"] == "paper_candidate"
    assert row["paper_notional_cap_usdc"] <= 5
    assert row["paper_probe_authorized"] is True
    assert row["live_order_allowed"] is False
    assert payload["live_order_allowed"] is False


def test_cli_winner_pattern_paper_candidates_preserves_skip_reasons(tmp_path: Path) -> None:
    patterns_path = tmp_path / "patterns.json"
    markets_path = tmp_path / "markets.json"
    orderbooks_path = tmp_path / "orderbooks.json"
    weather_path = tmp_path / "weather.json"
    output_json = tmp_path / "candidates.json"
    output_md = tmp_path / "candidates.md"
    patterns_path.write_text(json.dumps(_patterns()), encoding="utf-8")
    markets_path.write_text(json.dumps({"markets": [_market("m1"), _market("m2", "rain")]}), encoding="utf-8")
    orderbooks_path.write_text(json.dumps({"orderbooks": [{"market_id": "m2", "best_bid": 0.4, "best_ask": 0.42, "spread": 0.02}]}), encoding="utf-8")
    weather_path.write_text(json.dumps({"contexts": [{"market_id": "m1", "weather_context_available": True}, {"market_id": "m2", "weather_context_available": True}]}), encoding="utf-8")

    result = _run_weather_pm(
        "winner-pattern-paper-candidates",
        "--winner-patterns-json", str(patterns_path),
        "--current-markets-json", str(markets_path),
        "--current-orderbooks-json", str(orderbooks_path),
        "--current-weather-context-json", str(weather_path),
        "--output-json", str(output_json),
        "--output-md", str(output_md),
    )

    assert result["paper_only"] is True
    assert result["live_order_allowed"] is False
    assert result["considered_markets"] == 2
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    reasons = {row["market_id"]: row["reason"] for row in artifact["considered_markets"]}
    assert reasons["m1"] == "missing_current_orderbook"
    assert reasons["m2"] == "anti_pattern_conflict"
    assert "missing_current_orderbook" in output_md.read_text(encoding="utf-8")
