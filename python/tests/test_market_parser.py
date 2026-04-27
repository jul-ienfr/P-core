from __future__ import annotations

from weather_pm.market_parser import parse_market_question


def test_parse_threshold_high_question_tracks_higher_direction() -> None:
    result = parse_market_question("Will the highest temperature in Denver be 64F or higher?")

    assert result.city == "Denver"
    assert result.measurement_kind == "high"
    assert result.unit == "f"
    assert result.is_threshold is True
    assert result.is_exact_bin is False
    assert result.threshold_direction == "higher"
    assert result.target_value == 64.0
    assert result.range_low is None
    assert result.range_high is None


def test_parse_threshold_low_question_accepts_degree_symbol_and_or_below() -> None:
    result = parse_market_question("Will the lowest temperature in Miami be 63°F or below on April 23?")

    assert result.city == "Miami"
    assert result.measurement_kind == "low"
    assert result.unit == "f"
    assert result.is_threshold is True
    assert result.is_exact_bin is False
    assert result.threshold_direction == "below"
    assert result.target_value == 63.0
    assert result.range_low is None
    assert result.range_high is None
    assert result.date_local == "April 23"


def test_parse_exact_bin_low_question() -> None:
    result = parse_market_question("Will the lowest temperature in NYC be between 46F and 47F?")

    assert result.city == "NYC"
    assert result.measurement_kind == "low"
    assert result.unit == "f"
    assert result.is_threshold is False
    assert result.is_exact_bin is True
    assert result.threshold_direction is None
    assert result.target_value is None
    assert result.range_low == 46.0
    assert result.range_high == 47.0


def test_parse_exact_bin_question_supports_date_and_degree_symbols() -> None:
    result = parse_market_question("Will the highest temperature in Chicago be between 70°F and 71°F on April 30?")

    assert result.city == "Chicago"
    assert result.measurement_kind == "high"
    assert result.unit == "f"
    assert result.is_exact_bin is True
    assert result.range_low == 70.0
    assert result.range_high == 71.0
    assert result.date_local == "April 30"


def test_parse_exact_value_question_supports_exactly_format() -> None:
    result = parse_market_question("Will the highest temperature in Denver be exactly 64F on April 23?")

    assert result.city == "Denver"
    assert result.measurement_kind == "high"
    assert result.unit == "f"
    assert result.is_threshold is False
    assert result.is_exact_bin is True
    assert result.threshold_direction is None
    assert result.target_value == 64.0
    assert result.range_low == 64.0
    assert result.range_high == 64.0
    assert result.date_local == "April 23"


def test_parse_event_style_high_temperature_question_defaults_to_range_market() -> None:
    result = parse_market_question("Highest temperature in Dallas on December 5?")

    assert result.city == "Dallas"
    assert result.measurement_kind == "high"
    assert result.unit == "f"
    assert result.is_threshold is False
    assert result.is_exact_bin is True
    assert result.target_value is None
    assert result.range_low is None
    assert result.range_high is None
    assert result.date_local == "December 5"


def test_parse_event_style_low_temperature_question_supports_celsius_city_titles() -> None:
    result = parse_market_question("Lowest temperature in Tokyo on April 15?")

    assert result.city == "Tokyo"
    assert result.measurement_kind == "low"
    assert result.unit == "c"
    assert result.is_threshold is False
    assert result.is_exact_bin is True
    assert result.target_value is None
    assert result.range_low is None
    assert result.range_high is None
    assert result.date_local == "April 15"
