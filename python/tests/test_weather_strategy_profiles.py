from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from weather_pm.strategy_profiles import classify_candidate_row, get_strategy_profile, list_strategy_profiles, operator_profile_matrix


EXPECTED_PROFILE_IDS = [
    "surface_grid_trader",
    "exact_bin_anomaly_hunter",
    "threshold_resolution_harvester",
    "profitable_consensus_radar",
    "conviction_signal_follower",
    "macro_weather_event_trader",
]


def test_lists_six_canonical_profiles_with_required_decision_fields() -> None:
    profiles = list_strategy_profiles()

    assert [profile["id"] for profile in profiles] == EXPECTED_PROFILE_IDS
    for profile in profiles:
        assert profile["label"]
        assert profile["inspiration"]
        assert profile["required_inputs"]
        assert profile["entry_gates"]
        assert profile["risk_caps"]["max_order_usdc"] > 0
        assert profile["risk_caps"]["max_position_usdc"] >= profile["risk_caps"]["max_order_usdc"]
        assert profile["risk_caps"]["live_order_allowed"] is False
        assert profile["execution_mode"] in {"paper_strict_limit", "watchlist_only", "paper_micro_strict_limit", "operator_review"}
        assert profile["do_not_trade_rules"]


def test_fetch_by_id_returns_deterministic_profile_and_rejects_unknown() -> None:
    profile = get_strategy_profile("threshold_resolution_harvester")

    assert profile["id"] == "threshold_resolution_harvester"
    assert "direct_resolution_source" in profile["required_inputs"]
    assert "source_missing" in profile["do_not_trade_rules"]

    try:
        get_strategy_profile("wallet_copy_trader")
    except KeyError as exc:
        assert "unknown strategy profile id" in str(exc)
    else:  # pragma: no cover - documents expected failure path
        raise AssertionError("unknown profile id should raise KeyError")


def test_classifies_shortlist_like_rows_to_canonical_profiles() -> None:
    rows = [
        {"market_id": "surface", "surface_inconsistency_count": 2, "surface_inconsistency_types": ["threshold_monotonicity_violation"], "source_direct": True},
        {"market_id": "exact", "surface_inconsistency_types": ["exact_bin_mass_exceeds_one"], "exact_bin_price_mass": 1.18, "source_direct": True},
        {"market_id": "threshold", "threshold_watch": {"eligible": True, "recommendation": "paper_micro_strict_limit"}, "hours_to_resolution": 2, "source_direct": True},
        {"market_id": "consensus", "consensus_signal": {"handle_count": 4, "net_side": "YES"}, "source_direct": True},
        {"market_id": "conviction", "matched_traders": ["alpha", "beta"], "decision_status": "trade", "probability_edge": 0.09, "source_direct": True},
        {"market_id": "macro", "event_category": "hurricane", "question": "Will a hurricane make landfall in Florida this month?", "source_direct": True},
    ]

    assert [classify_candidate_row(row)["profile_id"] for row in rows] == EXPECTED_PROFILE_IDS
    assert classify_candidate_row({"market_id": "blocked", "source_direct": False})["profile_id"] is None
    assert classify_candidate_row({"market_id": "blocked", "source_direct": False})["blockers"] == ["source_missing"]


def test_operator_matrix_is_compact_and_contains_risk_and_gate_summary() -> None:
    matrix = operator_profile_matrix()

    assert [row["id"] for row in matrix] == EXPECTED_PROFILE_IDS
    assert set(matrix[0]) == {"id", "label", "execution_mode", "max_order_usdc", "max_position_usdc", "entry_gates", "required_inputs", "do_not_trade"}
    assert matrix[0]["entry_gates"]
    assert matrix[0]["do_not_trade"]


def test_strategy_profiles_cli_outputs_compact_json_and_optional_markdown(tmp_path: Path) -> None:
    output_md = tmp_path / "profiles.md"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "strategy-profiles",
            "--output-md",
            str(output_md),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env={"PYTHONPATH": "src"},
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert payload["profile_count"] == 6
    assert [row["id"] for row in payload["profiles"]] == EXPECTED_PROFILE_IDS
    assert payload["artifacts"]["output_md"] == str(output_md)
    markdown = output_md.read_text(encoding="utf-8")
    assert "# Weather Strategy Profiles" in markdown
    assert "surface_grid_trader" in markdown
    assert "macro_weather_event_trader" in markdown
