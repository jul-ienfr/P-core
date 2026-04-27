from __future__ import annotations

from prediction_core.paper.exit_policy import (
    ExitDecision,
    ExitPolicy,
    PaperPositionSnapshot,
    annotate_order_with_exit_policy,
    evaluate_exit_policy,
)


def _snapshot(**overrides) -> PaperPositionSnapshot:
    payload = {
        "entry_price": 0.40,
        "current_price": 0.50,
        "highest_price": 0.55,
        "filled_usdc": 10.0,
        "shares": 25.0,
        "status": "filled",
    }
    payload.update(overrides)
    return PaperPositionSnapshot(**payload)


def test_exit_policy_recommends_stop_loss_when_price_breaches_loss_floor() -> None:
    decision = evaluate_exit_policy(
        _snapshot(current_price=0.33, highest_price=0.45),
        ExitPolicy(stop_loss_pct=0.15, trailing_stop_pct=0.20, breakeven_after_profit_pct=0.25),
    )

    assert decision == ExitDecision(
        action="EXIT_REVIEW_PAPER",
        reason="stop_loss",
        trigger_price=0.34,
        current_price=0.33,
        unrealized_return_pct=-0.175,
    )


def test_exit_policy_recommends_trailing_stop_after_reversal_from_high_water_mark() -> None:
    decision = evaluate_exit_policy(
        _snapshot(entry_price=0.40, current_price=0.50, highest_price=0.72),
        ExitPolicy(stop_loss_pct=0.20, trailing_stop_pct=0.25, breakeven_after_profit_pct=0.50),
    )

    assert decision.action == "EXIT_REVIEW_PAPER"
    assert decision.reason == "trailing_stop"
    assert decision.trigger_price == 0.54
    assert decision.unrealized_return_pct == 0.25


def test_exit_policy_recommends_breakeven_after_profit_retrace() -> None:
    decision = evaluate_exit_policy(
        _snapshot(entry_price=0.40, current_price=0.405, highest_price=0.55),
        ExitPolicy(stop_loss_pct=0.20, trailing_stop_pct=0.40, breakeven_after_profit_pct=0.25),
    )

    assert decision.action == "EXIT_REVIEW_PAPER"
    assert decision.reason == "breakeven_after_profit"
    assert decision.trigger_price == 0.40
    assert decision.unrealized_return_pct == 0.0125


def test_exit_policy_holds_when_no_exit_trigger_is_met() -> None:
    decision = evaluate_exit_policy(
        _snapshot(entry_price=0.40, current_price=0.48, highest_price=0.52),
        ExitPolicy(stop_loss_pct=0.20, trailing_stop_pct=0.25, breakeven_after_profit_pct=0.30),
    )

    assert decision.action == "HOLD"
    assert decision.reason == "no_exit_trigger"
    assert decision.trigger_price is None
    assert decision.current_price == 0.48


def test_exit_policy_holds_with_missing_price_or_unfilled_position() -> None:
    missing_price = evaluate_exit_policy(_snapshot(current_price=None), ExitPolicy())
    unfilled = evaluate_exit_policy(_snapshot(status="planned", shares=0.0, filled_usdc=0.0), ExitPolicy())

    assert missing_price.action == "HOLD"
    assert missing_price.reason == "missing_price"
    assert missing_price.current_price is None
    assert unfilled.action == "HOLD"
    assert unfilled.reason == "not_open_position"


def test_annotate_order_with_exit_policy_adds_pure_recommendation_without_mutating_order() -> None:
    order = {
        "status": "filled",
        "avg_fill_price": 0.40,
        "filled_usdc": 10.0,
        "shares": 25.0,
        "actual_refresh_price": 0.50,
        "refresh_history": [{"best_bid": 0.72}, {"best_bid": 0.50}],
    }

    annotated = annotate_order_with_exit_policy(
        order,
        ExitPolicy(stop_loss_pct=0.20, trailing_stop_pct=0.25, breakeven_after_profit_pct=0.50),
    )

    assert "exit_policy" not in order
    assert annotated is not order
    assert annotated["exit_policy"] == {
        "action": "EXIT_REVIEW_PAPER",
        "reason": "trailing_stop",
        "trigger_price": 0.54,
        "current_price": 0.5,
        "unrealized_return_pct": 0.25,
    }
    assert annotated["operator_action"] != "SELL"
