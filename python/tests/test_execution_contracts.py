from __future__ import annotations

import prediction_core.execution as execution


EXPECTED_PUBLIC_SYMBOLS = {
    "AmmTradeQuote",
    "BookLevel",
    "ExecutionCostBreakdown",
    "FillEstimate",
    "OrderBookSnapshot",
    "TradingFeeEstimate",
    "TradingFeeSchedule",
    "TransferCostEstimate",
    "TransferFeeSchedule",
    "amm_prices",
    "build_execution_cost_breakdown",
    "compute_trading_fee",
    "compute_transfer_costs",
    "estimate_execution_costs",
    "estimate_fill",
    "estimate_fill_from_book",
    "estimate_order_cost",
    "estimate_trading_fee",
    "estimate_transfer_costs",
    "quote_amm_buy",
    "quote_amm_sell",
    "quote_execution_cost",
}


def test_execution_package_exports_expected_public_symbols() -> None:
    assert set(execution.__all__) == EXPECTED_PUBLIC_SYMBOLS


def test_execution_package_exposes_callable_entrypoints() -> None:
    assert callable(execution.estimate_fill)
    assert callable(execution.estimate_fill_from_book)
    assert callable(execution.compute_trading_fee)
    assert callable(execution.estimate_trading_fee)
    assert callable(execution.compute_transfer_costs)
    assert callable(execution.estimate_transfer_costs)
    assert callable(execution.build_execution_cost_breakdown)
    assert callable(execution.estimate_execution_costs)
    assert callable(execution.quote_execution_cost)
    assert callable(execution.estimate_order_cost)
    assert callable(execution.amm_prices)
    assert callable(execution.quote_amm_buy)
    assert callable(execution.quote_amm_sell)


def test_execution_package_exposes_model_types() -> None:
    for symbol in [
        "AmmTradeQuote",
        "BookLevel",
        "ExecutionCostBreakdown",
        "FillEstimate",
        "OrderBookSnapshot",
        "TradingFeeEstimate",
        "TradingFeeSchedule",
        "TransferCostEstimate",
        "TransferFeeSchedule",
    ]:
        assert isinstance(getattr(execution, symbol), type)
