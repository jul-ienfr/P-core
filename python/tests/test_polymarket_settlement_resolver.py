from weather_pm.models import MarketStructure
from weather_pm.official_settlement import OfficialSettlementResult, OfficialWeatherObservation
from weather_pm.polymarket_settlement import (
    enrich_exited_position_with_official_outcome,
    resolution_check_schedule_from_gamma_event,
    resolve_position_from_gamma_event,
    resolve_position_from_official_weather,
    validate_settlement,
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


def test_resolve_paper_position_from_official_weather_when_polymarket_not_final():
    structure = MarketStructure(
        city="Beijing",
        measurement_kind="high",
        unit="c",
        is_threshold=False,
        is_exact_bin=True,
        target_value=None,
        range_low=24.0,
        range_high=24.0,
        date_local="2026-04-26",
    )
    observation = OfficialWeatherObservation(
        provider="noaa",
        station_code="ZBAA",
        observed_date="2026-04-26",
        measurement_kind="high",
        value=24.2,
        unit="c",
        source="noaa_daily_summary",
    )
    official_result = OfficialSettlementResult(
        provider="noaa",
        resolved=True,
        outcome_yes=True,
        outcome_label="YES",
        observed_value=24.2,
        observed_unit="c",
        observation=observation,
        reason="official_observation_classified",
    )

    result = resolve_position_from_official_weather(
        {
            "question": "Will the highest temperature in Beijing be 24°C on April 26?",
            "side": "NO",
            "filled_usdc": 2.0,
            "shares": 2.439,
        },
        structure,
        official_result,
    )

    assert result["settlement_status"] == "SETTLED_LOST"
    assert result["winning_outcome"] == "Yes"
    assert result["paper_settlement_value_usdc"] == 0.0
    assert result["paper_realized_pnl_usdc"] == -2.0
    assert result["settlement_source"] == "official_weather:noaa"
    assert result["official_observed_value"] == 24.2
    assert result["official_observed_unit"] == "c"
    assert result["official_observation_source"] == "noaa_daily_summary"
    assert result["official_station_code"] == "ZBAA"
    assert result["official_reason"] == "official_observation_classified"


def test_gamma_closed_outcome_prices_remain_authoritative_over_official_weather():
    gamma_result = resolve_position_from_gamma_event(
        {
            "question": "Will the highest temperature in Beijing be 24°C on April 26?",
            "side": "NO",
            "filled_usdc": 2.0,
            "shares": 2.439,
        },
        BEIJING_EVENT,
    )
    official_result = OfficialSettlementResult(
        provider="noaa",
        resolved=True,
        outcome_yes=False,
        outcome_label="NO",
        observed_value=23.4,
        observed_unit="c",
        observation=None,
        reason="official_observation_classified",
    )

    assert gamma_result["settlement_status"] == "SETTLED_LOST"
    assert gamma_result["winning_outcome"] == "Yes"
    assert gamma_result["paper_settlement_value_usdc"] == 0.0
    assert gamma_result["paper_realized_pnl_usdc"] == -2.0
    assert gamma_result["settlement_source"] == "polymarket_closed_outcome_prices"

    official_fallback = resolve_position_from_official_weather(
        {
            "question": "Will the highest temperature in Beijing be 24°C on April 26?",
            "side": "NO",
            "filled_usdc": 2.0,
            "shares": 2.439,
        },
        MarketStructure(
            city="Beijing",
            measurement_kind="high",
            unit="c",
            is_threshold=False,
            is_exact_bin=True,
            target_value=None,
            range_low=24.0,
            range_high=24.0,
            date_local="2026-04-26",
        ),
        official_result,
    )
    validation = validate_settlement(official_result=official_result, polymarket_result=gamma_result)
    assert validation["settlement_validation_status"] == "settlement_mismatch"
    assert validation["manual_review_required"] is True
    assert validation["official_outcome"] == "No"
    assert validation["polymarket_outcome"] == "Yes"

    assert official_fallback["settlement_status"] == "SETTLED_WON"
    assert official_fallback["settlement_source"] == "official_weather:noaa"


def test_settlement_validation_reports_polymarket_resolved_and_matches():
    official_result = OfficialSettlementResult(
        provider="noaa",
        resolved=True,
        outcome_yes=True,
        outcome_label="YES",
        observed_value=24.2,
        observed_unit="c",
        observation=None,
        reason="official_observation_classified",
    )
    polymarket_result = resolve_position_from_gamma_event(
        {
            "question": "Will the highest temperature in Beijing be 24°C on April 26?",
            "side": "NO",
            "filled_usdc": 2.0,
            "shares": 2.439,
        },
        BEIJING_EVENT,
    )

    polymarket_only = validate_settlement(polymarket_result=polymarket_result)
    matches = validate_settlement(official_result=official_result, polymarket_result=polymarket_result)

    assert polymarket_only["settlement_validation_status"] == "polymarket_resolved"
    assert matches["settlement_validation_status"] == "settlement_matches"
    assert matches["manual_review_required"] is False


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
