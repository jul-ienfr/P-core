from __future__ import annotations

import prediction_core.execution as execution


EXPECTED_PUBLIC_SYMBOLS = {
    "AdapterBoundaryPolicy",
    "AdapterPolicyEvaluation",
    "AmmTradeQuote",
    "AuditResult",
    "BookLevel",
    "ExecutionAssumptions",
    "ExecutionCostBreakdown",
    "ExecutionParityQuote",
    "FillEstimate",
    "OrderBookSnapshot",
    "PolymarketFeeCategory",
    "PolymarketFeeEstimate",
    "PolymarketMarketRules",
    "PolymarketOrderValidation",
    "PredictionMarketAdapterCapability",
    "ReplayScenario",
    "TradingFeeEstimate",
    "TradingFeeSchedule",
    "TransferCostEstimate",
    "TransferFeeSchedule",
    "amm_prices",
    "audit_known_prediction_market_candidates",
    "build_execution_cost_breakdown",
    "compute_trading_fee",
    "compute_transfer_costs",
    "candidate_prediction_market_adapter_capability",
    "deterministic_replay_scenarios",
    "estimate_execution_costs",
    "estimate_fill",
    "estimate_fill_from_book",
    "estimate_order_cost",
    "estimate_polymarket_fee",
    "estimate_trading_fee",
    "estimate_transfer_costs",
    "evaluate_prediction_market_adapter_policy",
    "normalize_polymarket_fee_category",
    "normalize_polymarket_market_rules",
    "polymarket_order_size_for_notional",
    "quote_amm_buy",
    "quote_amm_sell",
    "quote_execution_cost",
    "quote_execution_parity",
    "validate_polymarket_limit_order",
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
    assert callable(execution.deterministic_replay_scenarios)
    assert callable(execution.build_execution_cost_breakdown)
    assert callable(execution.estimate_execution_costs)
    assert callable(execution.quote_execution_cost)
    assert callable(execution.quote_execution_parity)
    assert callable(execution.estimate_order_cost)
    assert callable(execution.amm_prices)
    assert callable(execution.quote_amm_buy)
    assert callable(execution.quote_amm_sell)


def test_execution_package_exposes_model_types() -> None:
    for symbol in [
        "AdapterBoundaryPolicy",
        "AdapterPolicyEvaluation",
        "AmmTradeQuote",
        "AuditResult",
        "BookLevel",
        "ExecutionAssumptions",
        "ExecutionCostBreakdown",
        "ExecutionParityQuote",
        "FillEstimate",
        "OrderBookSnapshot",
        "PolymarketFeeCategory",
        "PolymarketFeeEstimate",
        "PolymarketMarketRules",
        "PolymarketOrderValidation",
        "PredictionMarketAdapterCapability",
        "ReplayScenario",
        "TradingFeeEstimate",
        "TradingFeeSchedule",
        "TransferCostEstimate",
        "TransferFeeSchedule",
    ]:
        assert isinstance(getattr(execution, symbol), type)
