from __future__ import annotations

from datetime import UTC, datetime
import json

import pytest

from prediction_core.strategies import (
    StrategyDescriptor,
    StrategyMode,
    StrategyRunRequest,
    StrategyRunResult,
    StrategySide,
    StrategySignal,
    StrategyTarget,
)


def test_signal_serializes_json_friendly_payload() -> None:
    signal = StrategySignal(
        strategy_id="weather_baseline",
        market_id="m1",
        target=StrategyTarget.EVENT_OUTCOME_FORECASTING,
        mode=StrategyMode.PAPER_ONLY,
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        side=StrategySide.YES,
        probability=0.62,
        confidence=0.71,
        expected_move=0.08,
        features={"edge": 0.04},
        risks=["fixture"],
        source={"kind": "unit"},
        metadata={"gate_status": "pass"},
    )

    payload = signal.to_dict()
    assert payload["strategy_id"] == "weather_baseline"
    assert payload["market_id"] == "m1"
    assert payload["target"] == "event_outcome_forecasting"
    assert payload["mode"] == "paper_only"
    assert payload["generated_at"] == "2026-01-01T00:00:00+00:00"
    assert payload["features"]["edge"] == 0.04
    assert payload["risks"] == ["fixture"]
    assert payload["source"]["kind"] == "unit"
    assert payload["trading_action"] == "none"
    assert json.loads(signal.to_json())["market_id"] == "m1"


def test_probability_confidence_and_expected_move_bounds() -> None:
    kwargs = dict(
        strategy_id="s",
        market_id="m",
        target=StrategyTarget.EVENT_OUTCOME_FORECASTING,
        mode=StrategyMode.RESEARCH_ONLY,
        generated_at=datetime.now(UTC),
    )
    with pytest.raises(ValueError, match="probability"):
        StrategySignal(**kwargs, probability=1.1, confidence=0.5)
    with pytest.raises(ValueError, match="confidence"):
        StrategySignal(**kwargs, probability=0.5, confidence=-0.1)
    with pytest.raises(ValueError, match="expected_move"):
        StrategySignal(**kwargs, confidence=0.5, expected_move=1.5)


def test_live_allowed_representable_but_not_default() -> None:
    default = StrategyDescriptor(strategy_id="s", name="S", target="event_outcome_forecasting")
    live = StrategyDescriptor(strategy_id="l", name="L", target="event_outcome_forecasting", mode="live_allowed")
    assert default.mode == StrategyMode.RESEARCH_ONLY
    assert live.mode == StrategyMode.LIVE_ALLOWED
    assert live.to_dict()["mode"] == "live_allowed"


def test_trading_action_none_invariant() -> None:
    with pytest.raises(ValueError, match="trading_action"):
        StrategySignal(
            strategy_id="s",
            market_id="m",
            target="event_outcome_forecasting",
            mode="paper_only",
            generated_at=datetime.now(UTC),
            confidence=0.5,
            trading_action="buy",
        )


def test_request_and_result_serialization() -> None:
    request = StrategyRunRequest(market_id="m", payload={"x": 1})
    signal = StrategySignal(
        strategy_id="s",
        market_id="m",
        target="event_outcome_forecasting",
        mode="research_only",
        generated_at=datetime.now(UTC),
        confidence=0.0,
        features={},
        risks=[],
        source={},
    )
    result = StrategyRunResult(strategy_id="s", market_id="m", mode="research_only", signals=[signal])
    assert request.to_dict()["market_id"] == "m"
    assert result.to_dict()["signals"][0]["strategy_id"] == "s"
