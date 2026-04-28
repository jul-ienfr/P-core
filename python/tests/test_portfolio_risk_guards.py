from __future__ import annotations

from prediction_core.risk import (
    CircuitBreakerState,
    PortfolioRiskLimits,
    PortfolioRiskSnapshot,
    ProposedPaperOrder,
    RiskSizingInput,
    RiskSizingLimits,
    RiskSizingSnapshot,
    evaluate_portfolio_risk,
    evaluate_risk_sizing,
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


def test_generic_risk_sizing_allows_and_emits_clickhouse_ready_snapshot() -> None:
    decision = evaluate_risk_sizing(
        RiskSizingInput(
            instrument_id="generic-market",
            requested_notional_usdc=20.0,
            current_exposure_usdc=30.0,
            portfolio_equity_usdc=200.0,
            net_edge=0.04,
            all_in_cost_bps=25.0,
            market_exposure_usdc=10.0,
        ),
        RiskSizingSnapshot(
            gross_exposure_usdc=40.0,
            peak_equity_usdc=250.0,
            current_equity_usdc=225.0,
            turnover_usdc=60.0,
        ),
        RiskSizingLimits(
            max_notional_usdc=25.0,
            max_exposure_usdc=100.0,
            max_drawdown_fraction=0.20,
            max_turnover_fraction=0.50,
            max_market_concentration_fraction=0.20,
            max_all_in_cost_bps=50.0,
            min_net_edge=0.02,
        ),
    )

    assert decision.approved is True
    assert decision.approved_notional_usdc == 20.0
    assert decision.blockers == []
    assert decision.snapshot.paper_only is True
    assert decision.snapshot.live_order_allowed is False
    payload = decision.to_dict()
    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    assert payload["snapshot"]["instrument_id"] == "generic-market"
    assert payload["snapshot"]["projected_exposure_usdc"] == 60.0
    assert payload["snapshot"]["drawdown_fraction"] == 0.10


def test_generic_risk_sizing_clamps_notional_to_max_notional_and_exposure() -> None:
    decision = evaluate_risk_sizing(
        RiskSizingInput(
            instrument_id="generic-market",
            requested_notional_usdc=80.0,
            current_exposure_usdc=70.0,
            portfolio_equity_usdc=500.0,
            net_edge=0.05,
            all_in_cost_bps=10.0,
        ),
        RiskSizingSnapshot(gross_exposure_usdc=70.0, peak_equity_usdc=500.0, current_equity_usdc=500.0),
        RiskSizingLimits(max_notional_usdc=50.0, max_exposure_usdc=100.0, min_net_edge=0.01),
    )

    assert decision.approved is True
    assert decision.approved_notional_usdc == 30.0
    assert decision.blockers == []
    assert set(decision.reasons) >= {"requested_notional_clamped_to_max_notional", "requested_notional_clamped_to_remaining_exposure"}
    assert decision.diagnostics["requested_notional_usdc"] == 80.0
    assert decision.diagnostics["approved_notional_usdc"] == 30.0


def test_generic_risk_sizing_blocks_drawdown_turnover_concentration_cost_and_edge() -> None:
    decision = evaluate_risk_sizing(
        RiskSizingInput(
            instrument_id="crowded-market",
            requested_notional_usdc=10.0,
            current_exposure_usdc=80.0,
            portfolio_equity_usdc=100.0,
            net_edge=0.005,
            all_in_cost_bps=80.0,
            all_in_cost_usdc=3.0,
            market_exposure_usdc=60.0,
        ),
        RiskSizingSnapshot(
            gross_exposure_usdc=80.0,
            peak_equity_usdc=150.0,
            current_equity_usdc=120.0,
            turnover_usdc=55.0,
        ),
        RiskSizingLimits(
            max_notional_usdc=20.0,
            max_exposure_usdc=100.0,
            max_drawdown_fraction=0.10,
            max_turnover_fraction=0.50,
            max_market_concentration_fraction=0.50,
            max_all_in_cost_bps=50.0,
            max_all_in_cost_usdc=2.0,
            min_net_edge=0.02,
        ),
    )

    assert decision.approved is False
    assert decision.approved_notional_usdc == 0.0
    assert set(decision.blockers) == {
        "max_drawdown_fraction",
        "max_turnover_fraction",
        "max_market_concentration_fraction",
        "max_all_in_cost_bps",
        "max_all_in_cost_usdc",
        "min_net_edge",
    }
    assert decision.snapshot.drawdown_fraction == 0.20
    assert decision.snapshot.projected_turnover_usdc == 65.0
    assert decision.snapshot.market_concentration_fraction == 0.583333


def test_generic_risk_sizing_blocks_when_max_drawdown_usdc_reached() -> None:
    decision = evaluate_risk_sizing(
        RiskSizingInput(instrument_id="any", requested_notional_usdc=5.0, current_exposure_usdc=0.0, portfolio_equity_usdc=100.0, net_edge=0.05),
        RiskSizingSnapshot(gross_exposure_usdc=0.0, peak_equity_usdc=100.0, current_equity_usdc=84.0),
        RiskSizingLimits(max_notional_usdc=10.0, max_exposure_usdc=50.0, max_drawdown_usdc=15.0, min_net_edge=0.01),
    )

    assert decision.approved is False
    assert decision.blockers == ["max_drawdown_usdc"]
    assert decision.snapshot.drawdown_usdc == 16.0
