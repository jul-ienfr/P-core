from __future__ import annotations

from datetime import UTC, datetime

import pytest

from panoptique.bookmaker import BookmakerInput, BookmakerOutput, bookmaker_v0


BASE = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)


def test_bookmaker_v0_weighted_average_contract_is_research_and_paper_only() -> None:
    output = bookmaker_v0(
        [
            BookmakerInput(agent_id="agent-a", probability_yes=0.60, weight=2.0, brier_score=0.16, calibration_bucket="0.6-0.7"),
            BookmakerInput(agent_id="agent-b", probability_yes=0.30, weight=1.0, brier_score=0.25, calibration_bucket="0.3-0.4"),
        ],
        market_id="m-1",
        generated_at=BASE,
    )

    assert isinstance(output, BookmakerOutput)
    assert output.market_id == "m-1"
    assert output.probability_yes == pytest.approx(0.5)
    assert output.method == "weighted_average_v0"
    assert output.research_only is True
    assert output.paper_only is True
    assert output.capital_allocated is False
    assert output.trading_action == "none"
    assert output.metadata["anti_correlation"] == {
        "status": "placeholder_not_applied",
        "note": "Future versions may discount correlated agents; v0 only reports a weighted average.",
    }
    assert output.metadata["metric_targets"] == [
        "event_outcome_forecasting",
        "crowd_movement_forecasting",
        "executable_edge_after_costs",
    ]
    assert "profit" not in output.to_json().lower()


def test_bookmaker_v0_ignores_non_positive_weights_and_clamps_probabilities() -> None:
    output = bookmaker_v0(
        [
            BookmakerInput(agent_id="ignored", probability_yes=0.99, weight=0.0),
            BookmakerInput(agent_id="agent-a", probability_yes=1.2, weight=1.0),
            BookmakerInput(agent_id="agent-b", probability_yes=-0.2, weight=1.0),
        ],
        market_id="m-1",
        generated_at=BASE,
    )

    assert output.probability_yes == 0.5
    assert output.contributing_agents == ["agent-a", "agent-b"]
    assert output.metadata["input_count"] == 3
    assert output.metadata["used_input_count"] == 2


def test_bookmaker_v0_requires_at_least_one_positive_weight() -> None:
    with pytest.raises(ValueError, match="at least one positive weight"):
        bookmaker_v0([BookmakerInput(agent_id="agent-a", probability_yes=0.6, weight=0.0)], market_id="m-1")
