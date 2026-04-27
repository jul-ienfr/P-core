from __future__ import annotations

from prediction_core.risk.portfolio_guards import (
    CircuitBreakerState,
    PortfolioRiskLimits,
    PortfolioRiskSnapshot,
    ProposedPaperOrder,
    evaluate_portfolio_risk,
)


def test_portfolio_risk_blocks_max_open_positions() -> None:
    result = evaluate_portfolio_risk(
        ProposedPaperOrder(market_id="m-new", token_id="t-new", notional_usdc=5.0, liquidity_usd=500.0),
        PortfolioRiskSnapshot(open_position_count=3),
        PortfolioRiskLimits(max_open_positions=3),
    )

    assert result.ok is False
    assert result.blockers == ["max_open_positions_reached"]
    assert result.reasons[0] == "open positions 3 >= cap 3"
    assert result.diagnostics["open_position_count"] == 3
    assert result.diagnostics["max_open_positions"] == 3


def test_portfolio_risk_blocks_daily_paper_loss_cap() -> None:
    result = evaluate_portfolio_risk(
        ProposedPaperOrder(market_id="m-new", token_id="t-new", notional_usdc=5.0, liquidity_usd=500.0),
        PortfolioRiskSnapshot(daily_realized_pnl_usdc=-25.01),
        PortfolioRiskLimits(max_daily_loss_usdc=25.0),
    )

    assert result.ok is False
    assert "daily_paper_loss_cap_reached" in result.blockers
    assert result.diagnostics["daily_realized_pnl_usdc"] == -25.01
    assert result.diagnostics["max_daily_loss_usdc"] == 25.0


def test_portfolio_risk_blocks_deployed_capital_cap_with_proposed_order() -> None:
    result = evaluate_portfolio_risk(
        ProposedPaperOrder(market_id="m-new", token_id="t-new", notional_usdc=15.0, liquidity_usd=500.0),
        PortfolioRiskSnapshot(deployed_capital_usdc=90.0),
        PortfolioRiskLimits(max_deployed_capital_usdc=100.0),
    )

    assert result.ok is False
    assert "deployed_capital_cap_reached" in result.blockers
    assert result.diagnostics["projected_deployed_capital_usdc"] == 105.0


def test_portfolio_risk_blocks_min_liquidity() -> None:
    result = evaluate_portfolio_risk(
        ProposedPaperOrder(market_id="thin", token_id="thin-token", notional_usdc=5.0, liquidity_usd=99.99),
        PortfolioRiskSnapshot(),
        PortfolioRiskLimits(min_liquidity_usd=100.0),
    )

    assert result.ok is False
    assert result.blockers == ["min_liquidity_not_met"]
    assert result.diagnostics["liquidity_usd"] == 99.99
    assert result.diagnostics["min_liquidity_usd"] == 100.0


def test_portfolio_risk_blocks_circuit_breaker_state() -> None:
    result = evaluate_portfolio_risk(
        ProposedPaperOrder(market_id="m-new", token_id="t-new", notional_usdc=5.0, liquidity_usd=500.0),
        PortfolioRiskSnapshot(circuit_breaker=CircuitBreakerState(tripped=True, reason="operator_pause", tripped_at="2026-04-27T00:00:00Z")),
        PortfolioRiskLimits(),
    )

    assert result.ok is False
    assert result.blockers == ["circuit_breaker_tripped"]
    assert result.reasons == ["circuit breaker tripped: operator_pause"]
    assert result.diagnostics["circuit_breaker"] == {"tripped": True, "reason": "operator_pause", "tripped_at": "2026-04-27T00:00:00Z"}


def test_portfolio_risk_allows_safe_paper_order_with_diagnostics() -> None:
    result = evaluate_portfolio_risk(
        ProposedPaperOrder(market_id="m-ok", token_id="t-ok", notional_usdc=10.0, liquidity_usd=250.0),
        PortfolioRiskSnapshot(open_position_count=1, deployed_capital_usdc=20.0, daily_realized_pnl_usdc=-2.0),
        PortfolioRiskLimits(max_open_positions=3, max_daily_loss_usdc=25.0, max_deployed_capital_usdc=100.0, min_liquidity_usd=100.0),
    )

    assert result.ok is True
    assert result.blockers == []
    assert result.reasons == []
    assert result.diagnostics["paper_only"] is True
    assert result.diagnostics["live_order_allowed"] is False
    assert result.diagnostics["projected_deployed_capital_usdc"] == 30.0
