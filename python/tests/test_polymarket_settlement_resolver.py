from weather_pm.polymarket_settlement import (
    enrich_exited_position_with_official_outcome,
    resolution_check_schedule_from_gamma_event,
    resolve_position_from_gamma_event,
)


BEIJING_EVENT = {
    "closed": True,
    "endDate": "2026-04-26T12:00:00Z",
    "closedTime": "2026-04-26T12:03:42Z",
    "markets": [
        {
            "question": "Will the highest temperature in Beijing be 24°C on April 26?",
            "closed": True,
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["1", "0"]',
        },
        {
            "question": "Will the highest temperature in Beijing be 25°C on April 26?",
            "closed": True,
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0", "1"]',
        },
    ],
}


def test_resolve_no_position_lost_when_closed_gamma_price_marks_yes_winner():
    result = resolve_position_from_gamma_event(
        {
            "question": "Will the highest temperature in Beijing be 24°C on April 26?",
            "side": "NO",
            "filled_usdc": 2.0,
            "shares": 2.439,
        },
        BEIJING_EVENT,
    )

    assert result["settlement_status"] == "SETTLED_LOST"
    assert result["winning_outcome"] == "Yes"
    assert result["paper_settlement_value_usdc"] == 0.0
    assert result["paper_realized_pnl_usdc"] == -2.0
    assert result["settlement_source"] == "polymarket_closed_outcome_prices"
    assert result["resolution_scheduled_at"] == "2026-04-26T12:00:00Z"
    assert result["resolution_checked_at"] == "2026-04-26T12:03:42Z"


def test_resolution_schedule_records_exact_resolution_time_and_next_check_seconds():
    schedule = resolution_check_schedule_from_gamma_event(
        {"endDate": "2026-04-26T12:00:00Z"},
        check_delay_seconds=75,
    )

    assert schedule["resolution_scheduled_at"] == "2026-04-26T12:00:00Z"
    assert schedule["auto_check_after_seconds"] == 75
    assert schedule["auto_check_at"] == "2026-04-26T12:01:15Z"


def test_resolve_no_position_won_when_closed_gamma_price_marks_no_winner():
    result = resolve_position_from_gamma_event(
        {
            "question": "Will the highest temperature in Beijing be 25°C on April 26?",
            "side": "NO",
            "filled_usdc": 15.0,
            "shares": 24.1935,
        },
        BEIJING_EVENT,
    )

    assert result["settlement_status"] == "SETTLED_WON"
    assert result["winning_outcome"] == "No"
    assert result["paper_settlement_value_usdc"] == 24.1935
    assert result["paper_realized_pnl_usdc"] == 9.1935


def test_open_or_ambiguous_market_remains_unsettled():
    result = resolve_position_from_gamma_event(
        {"question": "Will X happen?", "side": "NO", "filled_usdc": 1.0, "shares": 2.0},
        {"closed": False, "markets": [{"question": "Will X happen?", "outcomes": '["Yes", "No"]', "outcomePrices": '["0.45", "0.55"]'}]},
    )

    assert result["settlement_status"] == "UNSETTLED"
    assert result["settlement_source"] == "polymarket_not_final"


def test_exit_paper_position_gets_official_outcome_without_rewriting_exit_pnl():
    exited = {
        "question": "Will the highest temperature in Beijing be 24°C on April 26?",
        "side": "NO",
        "action": "EXIT_PAPER",
        "filled_usdc": 2.0,
        "shares": 2.439,
        "paper_realized_pnl_usdc": -0.0488,
        "reason": "p_side 0.7810 < hard_stop 0.7900",
    }

    enriched = enrich_exited_position_with_official_outcome(exited, BEIJING_EVENT)

    assert enriched["action"] == "EXIT_PAPER"
    assert enriched["paper_realized_pnl_usdc"] == -0.0488
    assert enriched["official_settlement_status"] == "SETTLED_LOST"
    assert enriched["official_winning_outcome"] == "Yes"
    assert enriched["official_paper_settlement_value_usdc"] == 0.0
    assert enriched["official_hold_to_settlement_pnl_usdc"] == -2.0
    assert enriched["official_settlement_source"] == "polymarket_closed_outcome_prices"
    assert enriched["resolution_scheduled_at"] == "2026-04-26T12:00:00Z"
    assert enriched["resolution_checked_at"] == "2026-04-26T12:03:42Z"
