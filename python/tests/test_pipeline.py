from __future__ import annotations

from weather_pm.market_parser import parse_market_question
from weather_pm.pipeline import _default_forecast, _default_model, score_market_from_fixture_market_id


def test_score_market_from_fixture_market_id_returns_full_payload() -> None:
    payload = score_market_from_fixture_market_id("denver-high-64")

    assert payload["market"]["city"] == "Denver"
    assert payload["score"]["grade"] in {"A", "B", "C", "D"}
    assert payload["decision"]["status"] in {"trade", "trade_small", "watchlist", "skip"}
    assert payload["neighbors"]["neighbor_market_count"] >= 2
    assert payload["execution"]["spread"] == 0.03


def test_default_model_distinguishes_below_threshold_direction_semantics() -> None:
    structure = parse_market_question("Will the lowest temperature in Miami be 63°F or below on April 23?")
    forecast = _default_forecast(structure)

    model = _default_model(structure, forecast)

    assert forecast.consensus_value == 62.8
    assert model.probability_yes > 0.54
