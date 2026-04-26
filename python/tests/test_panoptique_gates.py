from __future__ import annotations

from panoptique.gates import GateDecision, decide_live_microtest_gate, decide_measurement_gate


def test_small_samples_are_not_enough_data_even_with_good_hit_rate() -> None:
    decision = decide_measurement_gate(
        total_predictions=12,
        matched_observations=8,
        hit_rate=0.90,
        categories={"weather", "sports"},
        liquidity_caveat_rate=0.0,
        out_of_sample_positive=True,
    )

    assert isinstance(decision, GateDecision)
    assert decision.status == "not_enough_data"
    assert decision.enough_data is False
    assert "100+ shadow predictions" in " ".join(decision.reasons)
    assert "30+ matched" in " ".join(decision.reasons)


def test_enough_data_requires_category_diversity_or_weather_caveat() -> None:
    decision = decide_measurement_gate(
        total_predictions=150,
        matched_observations=45,
        hit_rate=0.55,
        categories={"weather"},
        liquidity_caveat_rate=0.10,
        out_of_sample_positive=None,
    )

    assert decision.status == "enough_data"
    assert decision.enough_data is True
    assert decision.weather_only_caveat is True
    assert any("weather-only" in reason for reason in decision.reasons)
    assert decision.paper_strategy_ready is False


def test_promising_requires_larger_sample_oos_signal_and_liquidity() -> None:
    decision = decide_measurement_gate(
        total_predictions=240,
        matched_observations=210,
        hit_rate=0.58,
        categories={"weather", "politics"},
        liquidity_caveat_rate=0.15,
        out_of_sample_positive=True,
    )

    assert decision.status == "promising"
    assert decision.enough_data is True
    assert decision.paper_strategy_ready is True


def test_rejected_after_enough_data_when_directional_signal_bad() -> None:
    decision = decide_measurement_gate(
        total_predictions=160,
        matched_observations=70,
        hit_rate=0.45,
        categories={"weather", "sports"},
        liquidity_caveat_rate=0.05,
        out_of_sample_positive=False,
    )

    assert decision.status == "rejected"
    assert decision.enough_data is True
    assert decision.paper_strategy_ready is False
    assert any("directional" in reason for reason in decision.reasons)


def test_live_microtest_gate_blocks_without_all_phase_8_evidence_and_approval() -> None:
    decision = decide_live_microtest_gate(
        matched_observations=199,
        out_of_sample_positive_archetypes=[],
        paper_strategy_positive_after_costs=False,
        unresolved_leakage_issues=["fixture timestamps reused future prices"],
        dashboard_state_exposed=False,
        explicit_user_approval=False,
    )

    assert decision.status == "blocked"
    assert decision.separate_plan_may_be_drafted is False
    assert decision.live_trading_allowed_by_this_plan is False
    reason_text = " ".join(decision.reasons)
    assert "200+ matched" in reason_text
    assert "out-of-sample positive" in reason_text
    assert "conservative spread/slippage" in reason_text
    assert "leakage" in reason_text
    assert "dashboard" in reason_text
    assert "explicit Julien approval" in reason_text


def test_live_microtest_gate_only_allows_separate_plan_after_all_gates() -> None:
    decision = decide_live_microtest_gate(
        matched_observations=240,
        out_of_sample_positive_archetypes=["crowd_flow"],
        paper_strategy_positive_after_costs=True,
        unresolved_leakage_issues=[],
        dashboard_state_exposed=True,
        explicit_user_approval=True,
    )

    assert decision.status == "eligible_for_separate_plan"
    assert decision.separate_plan_may_be_drafted is True
    assert decision.live_trading_allowed_by_this_plan is False
