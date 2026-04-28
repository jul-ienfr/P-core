from __future__ import annotations

import sys
import types

from weather_pm.edge_sizing import calculate_edge_sizing


def test_calculate_edge_sizing_returns_buy_when_prediction_clears_market_and_costs() -> None:
    sizing = calculate_edge_sizing(
        prediction_probability=0.62,
        market_price=0.55,
        edge_cost_bps=120.0,
    )

    assert sizing.recommendation == "buy"
    assert sizing.raw_edge == 0.07
    assert sizing.net_edge == 0.058
    assert sizing.edge_bps == 700
    assert sizing.net_edge_bps == 580
    assert sizing.kelly_fraction > 0.0
    assert sizing.suggested_fraction <= sizing.kelly_fraction


def test_calculate_edge_sizing_skips_when_execution_costs_consume_edge() -> None:
    sizing = calculate_edge_sizing(
        prediction_probability=0.54,
        market_price=0.52,
        edge_cost_bps=250.0,
    )

    assert sizing.recommendation == "skip"
    assert sizing.raw_edge == 0.02
    assert sizing.net_edge == -0.005
    assert sizing.kelly_fraction > 0.0
    assert sizing.suggested_fraction == 0.0


def test_calculate_edge_sizing_supports_sell_side_edges() -> None:
    sizing = calculate_edge_sizing(
        prediction_probability=0.40,
        market_price=0.48,
        side="sell",
        edge_cost_bps=100.0,
    )

    assert sizing.recommendation == "sell"
    assert sizing.raw_edge == -0.08
    assert sizing.net_edge == 0.07
    assert sizing.edge_bps == -800
    assert sizing.net_edge_bps == 700
    assert sizing.suggested_fraction > 0.0


def test_calculate_edge_sizing_uses_rust_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("PREDICTION_CORE_RUST_ORDERBOOK", "1")
    fake_module = types.ModuleType("prediction_core._rust_orderbook")

    def rust_calculate_edge_sizing(**kwargs):
        assert kwargs["prediction_probability"] == 0.62
        assert kwargs["market_price"] == 0.55
        return {
            "prediction_probability": 0.62,
            "market_price": 0.55,
            "side": "buy",
            "raw_edge": 0.07,
            "net_edge": 0.058,
            "edge_bps": 700,
            "net_edge_bps": 580,
            "kelly_fraction": 0.1556,
            "suggested_fraction": 0.02,
            "recommendation": "buy",
        }

    fake_module.calculate_edge_sizing = rust_calculate_edge_sizing
    monkeypatch.setitem(sys.modules, "prediction_core._rust_orderbook", fake_module)

    sizing = calculate_edge_sizing(prediction_probability=0.62, market_price=0.55, edge_cost_bps=120.0)

    assert sizing.to_dict() == {
        "prediction_probability": 0.62,
        "market_price": 0.55,
        "side": "buy",
        "raw_edge": 0.07,
        "net_edge": 0.058,
        "edge_bps": 700,
        "net_edge_bps": 580,
        "kelly_fraction": 0.1556,
        "suggested_fraction": 0.02,
        "recommendation": "buy",
    }


def test_calculate_edge_sizing_rejects_invalid_probabilities() -> None:
    try:
        calculate_edge_sizing(prediction_probability=1.2, market_price=0.5)
    except ValueError as exc:
        assert "prediction_probability" in str(exc)
    else:
        raise AssertionError("expected invalid probability to raise")


def test_calculate_edge_sizing_rejects_non_finite_inputs() -> None:
    for kwargs, field in (
        ({"prediction_probability": float("nan"), "market_price": 0.5}, "prediction_probability"),
        ({"prediction_probability": 0.5, "market_price": float("inf")}, "market_price"),
        ({"prediction_probability": 0.5, "market_price": 0.4, "edge_cost_bps": float("nan")}, "edge_cost_bps"),
        ({"prediction_probability": 0.5, "market_price": 0.4, "kelly_scale": float("inf")}, "kelly_scale"),
    ):
        try:
            calculate_edge_sizing(**kwargs)
        except ValueError as exc:
            assert field in str(exc)
            assert "finite" in str(exc)
        else:
            raise AssertionError(f"expected {field} to reject non-finite input")
