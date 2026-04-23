from __future__ import annotations

import pytest

from prediction_core.paper.sizing import derive_filled_execution, derive_requested_quantity


BASE_SCORE_BUNDLE = {
    "decision": {
        "status": "trade_small",
        "max_position_pct_bankroll": 0.01,
    }
}


def test_derive_requested_quantity_prefers_explicit_quantity() -> None:
    assert derive_requested_quantity(
        requested_quantity=4,
        bankroll_usd=1000,
        yes_price=0.53,
        score_bundle=BASE_SCORE_BUNDLE,
    ) == 4.0


def test_derive_requested_quantity_from_bankroll_and_decision() -> None:
    assert derive_requested_quantity(
        requested_quantity=None,
        bankroll_usd=1000,
        yes_price=0.53,
        score_bundle=BASE_SCORE_BUNDLE,
    ) == 18.867925


def test_derive_requested_quantity_returns_zero_for_non_tradeable_decision() -> None:
    assert derive_requested_quantity(
        requested_quantity=None,
        bankroll_usd=1000,
        yes_price=0.63,
        score_bundle={"decision": {"status": "skip", "max_position_pct_bankroll": 0.0}},
    ) == 0.0


def test_derive_requested_quantity_rejects_negative_bankroll() -> None:
    with pytest.raises(ValueError, match="bankroll_usd must be >= 0"):
        derive_requested_quantity(
            requested_quantity=None,
            bankroll_usd=-1,
            yes_price=0.53,
            score_bundle=BASE_SCORE_BUNDLE,
        )


def test_derive_requested_quantity_rejects_zero_yes_price_for_bankroll_sizing() -> None:
    with pytest.raises(ValueError, match="yes_price must be > 0"):
        derive_requested_quantity(
            requested_quantity=None,
            bankroll_usd=1000,
            yes_price=0.0,
            score_bundle=BASE_SCORE_BUNDLE,
        )


def test_derive_requested_quantity_rejects_bankroll_without_score_bundle() -> None:
    with pytest.raises(ValueError, match="bankroll_usd requires question and yes_price for scored sizing"):
        derive_requested_quantity(
            requested_quantity=None,
            bankroll_usd=1000,
            yes_price=0.53,
            score_bundle=None,
        )


def test_derive_requested_quantity_rejects_missing_sizing_inputs() -> None:
    with pytest.raises(ValueError, match="requested_quantity is required when bankroll_usd or scored question sizing is unavailable"):
        derive_requested_quantity(
            requested_quantity=None,
            bankroll_usd=None,
            yes_price=None,
            score_bundle=None,
        )


def test_derive_requested_quantity_rejects_missing_max_position_pct_bankroll() -> None:
    with pytest.raises(ValueError, match="max_position_pct_bankroll is required for bankroll sizing"):
        derive_requested_quantity(
            requested_quantity=None,
            bankroll_usd=1000,
            yes_price=0.53,
            score_bundle={"decision": {"status": "trade_small"}},
        )


def test_derive_filled_execution_prefers_explicit_fill_values() -> None:
    filled_quantity, fill_price = derive_filled_execution(
        filled_quantity=2,
        fill_price=0.51,
        requested_quantity=4,
        yes_price=0.53,
        score_bundle=BASE_SCORE_BUNDLE,
    )
    assert filled_quantity == 2.0
    assert fill_price == 0.51


def test_derive_filled_execution_from_tradeable_decision() -> None:
    filled_quantity, fill_price = derive_filled_execution(
        filled_quantity=None,
        fill_price=None,
        requested_quantity=4,
        yes_price=0.53,
        score_bundle=BASE_SCORE_BUNDLE,
    )
    assert filled_quantity == 4.0
    assert fill_price == 0.53


def test_derive_filled_execution_returns_zero_fill_for_non_tradeable_decision() -> None:
    filled_quantity, fill_price = derive_filled_execution(
        filled_quantity=None,
        fill_price=None,
        requested_quantity=4,
        yes_price=0.63,
        score_bundle={"decision": {"status": "skip", "max_position_pct_bankroll": 0.0}},
    )
    assert filled_quantity == 0.0
    assert fill_price == 0.63


def test_derive_filled_execution_rejects_partial_manual_fill_input() -> None:
    with pytest.raises(ValueError, match="filled_quantity and fill_price must be provided together"):
        derive_filled_execution(
            filled_quantity=2,
            fill_price=None,
            requested_quantity=4,
            yes_price=0.53,
            score_bundle=BASE_SCORE_BUNDLE,
        )


def test_derive_filled_execution_rejects_missing_scored_inputs_for_auto_fill() -> None:
    with pytest.raises(ValueError, match="filled_quantity and fill_price are required when no scored question is provided"):
        derive_filled_execution(
            filled_quantity=None,
            fill_price=None,
            requested_quantity=4,
            yes_price=None,
            score_bundle=None,
        )


def test_derive_filled_execution_rejects_negative_filled_quantity() -> None:
    with pytest.raises(ValueError, match="filled_quantity must be >= 0"):
        derive_filled_execution(
            filled_quantity=-1,
            fill_price=0.53,
            requested_quantity=4,
            yes_price=0.53,
            score_bundle=BASE_SCORE_BUNDLE,
        )


def test_derive_filled_execution_rejects_fill_above_requested_quantity() -> None:
    with pytest.raises(ValueError, match="filled_quantity must be <= requested_quantity"):
        derive_filled_execution(
            filled_quantity=5,
            fill_price=0.53,
            requested_quantity=4,
            yes_price=0.53,
            score_bundle=BASE_SCORE_BUNDLE,
        )


def test_derive_filled_execution_rejects_missing_decision_for_auto_fill() -> None:
    with pytest.raises(ValueError, match="decision status is required for auto fill"):
        derive_filled_execution(
            filled_quantity=None,
            fill_price=None,
            requested_quantity=4,
            yes_price=0.53,
            score_bundle={"decision": {}},
        )
