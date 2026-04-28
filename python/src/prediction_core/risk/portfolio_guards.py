from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Mapping


@dataclass(frozen=True)
class CircuitBreakerState:
    tripped: bool = False
    reason: str | None = None
    tripped_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioRiskLimits:
    max_open_positions: int = 10
    max_daily_loss_usdc: float = 50.0
    max_deployed_capital_usdc: float = 250.0
    min_liquidity_usd: float = 100.0


@dataclass(frozen=True)
class PortfolioRiskSnapshot:
    open_position_count: int = 0
    deployed_capital_usdc: float = 0.0
    daily_realized_pnl_usdc: float = 0.0
    circuit_breaker: CircuitBreakerState = CircuitBreakerState()


@dataclass(frozen=True)
class ProposedPaperOrder:
    market_id: str
    token_id: str | None = None
    notional_usdc: float = 0.0
    liquidity_usd: float = 0.0


@dataclass(frozen=True)
class PortfolioRiskResult:
    ok: bool
    blockers: list[str]
    reasons: list[str]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "blockers": list(self.blockers), "reasons": list(self.reasons), "diagnostics": dict(self.diagnostics)}


@dataclass(frozen=True)
class RiskSizingInput:
    """Generic paper/dry-run sizing request, independent of predictive models."""

    instrument_id: str
    requested_notional_usdc: float
    current_exposure_usdc: float = 0.0
    portfolio_equity_usdc: float = 0.0
    net_edge: float = 0.0
    all_in_cost_bps: float = 0.0
    all_in_cost_usdc: float = 0.0
    market_exposure_usdc: float = 0.0
    side: str | None = None
    strategy_id: str | None = None


@dataclass(frozen=True)
class RiskSizingLimits:
    """Deterministic pre-trade risk/sizing constraints for paper/dry-run flows."""

    max_notional_usdc: float
    max_exposure_usdc: float
    max_drawdown_fraction: float | None = None
    max_drawdown_usdc: float | None = None
    max_turnover_fraction: float | None = None
    max_turnover_usdc: float | None = None
    max_market_concentration_fraction: float | None = None
    max_all_in_cost_bps: float | None = None
    max_all_in_cost_usdc: float | None = None
    min_net_edge: float = 0.0


@dataclass(frozen=True)
class RiskSizingSnapshot:
    """ClickHouse/Grafana-friendly risk state and projected sizing values."""

    gross_exposure_usdc: float = 0.0
    peak_equity_usdc: float = 0.0
    current_equity_usdc: float = 0.0
    turnover_usdc: float = 0.0
    instrument_id: str | None = None
    requested_notional_usdc: float = 0.0
    approved_notional_usdc: float = 0.0
    projected_exposure_usdc: float = 0.0
    projected_turnover_usdc: float = 0.0
    market_exposure_usdc: float = 0.0
    market_concentration_fraction: float = 0.0
    drawdown_usdc: float = 0.0
    drawdown_fraction: float = 0.0
    paper_only: bool = True
    live_order_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RiskSizingDecision:
    approved: bool
    approved_notional_usdc: float
    blockers: list[str]
    reasons: list[str]
    diagnostics: dict[str, Any]
    snapshot: RiskSizingSnapshot
    paper_only: bool = True
    live_order_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "approved_notional_usdc": self.approved_notional_usdc,
            "blockers": list(self.blockers),
            "reasons": list(self.reasons),
            "diagnostics": dict(self.diagnostics),
            "snapshot": self.snapshot.to_dict(),
            "paper_only": True,
            "live_order_allowed": False,
        }


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _finite(value: float, field: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite")
    return value


def _optional_finite(value: float | None, field: str) -> float | None:
    if value is None:
        return None
    return _finite(value, field)


def evaluate_risk_sizing(request: RiskSizingInput, snapshot: RiskSizingSnapshot | None = None, limits: RiskSizingLimits | None = None) -> RiskSizingDecision:
    """Evaluate generic paper/dry-run risk constraints and clamp requested size.

    This function is intentionally independent of predictive-model outputs: callers
    pass already-computed net edge/cost/exposure facts and receive a deterministic
    decision plus a snapshot payload suitable for analytics ingestion.
    """
    snapshot = snapshot or RiskSizingSnapshot()
    if limits is None:
        limits = RiskSizingLimits(max_notional_usdc=float("inf"), max_exposure_usdc=float("inf"))

    requested = max(0.0, _finite(request.requested_notional_usdc, "requested_notional_usdc"))
    current_exposure = max(0.0, _finite(request.current_exposure_usdc, "current_exposure_usdc"))
    gross_exposure = max(0.0, _finite(snapshot.gross_exposure_usdc, "gross_exposure_usdc"))
    portfolio_equity = max(0.0, _finite(request.portfolio_equity_usdc, "portfolio_equity_usdc"))
    peak_equity = max(0.0, _finite(snapshot.peak_equity_usdc, "peak_equity_usdc"))
    current_equity = max(0.0, _finite(snapshot.current_equity_usdc, "current_equity_usdc"))
    turnover = max(0.0, _finite(snapshot.turnover_usdc, "turnover_usdc"))
    market_exposure = max(0.0, _finite(request.market_exposure_usdc, "market_exposure_usdc"))
    net_edge = _finite(request.net_edge, "net_edge")
    all_in_cost_bps = max(0.0, _finite(request.all_in_cost_bps, "all_in_cost_bps"))
    all_in_cost_usdc = max(0.0, _finite(request.all_in_cost_usdc, "all_in_cost_usdc"))

    max_notional = max(0.0, _finite(limits.max_notional_usdc, "max_notional_usdc"))
    max_exposure = max(0.0, _finite(limits.max_exposure_usdc, "max_exposure_usdc"))
    max_drawdown_fraction = _optional_finite(limits.max_drawdown_fraction, "max_drawdown_fraction")
    max_drawdown_usdc = _optional_finite(limits.max_drawdown_usdc, "max_drawdown_usdc")
    max_turnover_fraction = _optional_finite(limits.max_turnover_fraction, "max_turnover_fraction")
    max_turnover_usdc = _optional_finite(limits.max_turnover_usdc, "max_turnover_usdc")
    max_market_concentration_fraction = _optional_finite(limits.max_market_concentration_fraction, "max_market_concentration_fraction")
    max_all_in_cost_bps = _optional_finite(limits.max_all_in_cost_bps, "max_all_in_cost_bps")
    max_all_in_cost_usdc = _optional_finite(limits.max_all_in_cost_usdc, "max_all_in_cost_usdc")
    min_net_edge = _finite(limits.min_net_edge, "min_net_edge")

    approved_notional = min(requested, max_notional)
    reasons: list[str] = []
    if approved_notional < requested:
        reasons.append("requested_notional_clamped_to_max_notional")

    remaining_exposure = max(0.0, max_exposure - current_exposure)
    if approved_notional > remaining_exposure:
        approved_notional = remaining_exposure
        reasons.append("requested_notional_clamped_to_remaining_exposure")

    projected_exposure = gross_exposure + approved_notional
    projected_turnover = turnover + approved_notional
    equity_base = portfolio_equity or current_equity or peak_equity
    drawdown_usdc = max(0.0, peak_equity - current_equity) if peak_equity else 0.0
    drawdown_fraction = drawdown_usdc / peak_equity if peak_equity > 0 else 0.0
    turnover_fraction = projected_turnover / equity_base if equity_base > 0 else 0.0
    concentration_denominator = max(projected_exposure, portfolio_equity, current_equity)
    market_concentration = (market_exposure + approved_notional) / concentration_denominator if concentration_denominator > 0 else 0.0

    blockers: list[str] = []
    if max_drawdown_fraction is not None and drawdown_fraction > max_drawdown_fraction:
        blockers.append("max_drawdown_fraction")
    if max_drawdown_usdc is not None and drawdown_usdc > max_drawdown_usdc:
        blockers.append("max_drawdown_usdc")
    if max_turnover_fraction is not None and turnover_fraction > max_turnover_fraction:
        blockers.append("max_turnover_fraction")
    if max_turnover_usdc is not None and projected_turnover > max_turnover_usdc:
        blockers.append("max_turnover_usdc")
    if max_market_concentration_fraction is not None and market_concentration > max_market_concentration_fraction:
        blockers.append("max_market_concentration_fraction")
    if max_all_in_cost_bps is not None and all_in_cost_bps > max_all_in_cost_bps:
        blockers.append("max_all_in_cost_bps")
    if max_all_in_cost_usdc is not None and all_in_cost_usdc > max_all_in_cost_usdc:
        blockers.append("max_all_in_cost_usdc")
    if net_edge < min_net_edge:
        blockers.append("min_net_edge")
    if requested > 0 and approved_notional <= 0 and max_exposure <= current_exposure:
        blockers.append("max_exposure_usdc")

    if blockers:
        approved_notional = 0.0

    output_snapshot = RiskSizingSnapshot(
        gross_exposure_usdc=round(gross_exposure, 6),
        peak_equity_usdc=round(peak_equity, 6),
        current_equity_usdc=round(current_equity, 6),
        turnover_usdc=round(turnover, 6),
        instrument_id=request.instrument_id,
        requested_notional_usdc=round(requested, 6),
        approved_notional_usdc=round(approved_notional, 6),
        projected_exposure_usdc=round(projected_exposure, 6),
        projected_turnover_usdc=round(projected_turnover, 6),
        market_exposure_usdc=round(market_exposure, 6),
        market_concentration_fraction=round(market_concentration, 6),
        drawdown_usdc=round(drawdown_usdc, 6),
        drawdown_fraction=round(drawdown_fraction, 6),
        paper_only=True,
        live_order_allowed=False,
    )
    diagnostics = {
        "paper_only": True,
        "live_order_allowed": False,
        "instrument_id": request.instrument_id,
        "side": request.side,
        "strategy_id": request.strategy_id,
        "requested_notional_usdc": round(requested, 6),
        "approved_notional_usdc": round(approved_notional, 6),
        "current_exposure_usdc": round(current_exposure, 6),
        "max_notional_usdc": round(max_notional, 6),
        "max_exposure_usdc": round(max_exposure, 6),
        "remaining_exposure_usdc": round(remaining_exposure, 6),
        "net_edge": round(net_edge, 6),
        "min_net_edge": round(min_net_edge, 6),
        "all_in_cost_bps": round(all_in_cost_bps, 6),
        "all_in_cost_usdc": round(all_in_cost_usdc, 6),
        "turnover_fraction": round(turnover_fraction, 6),
    }
    return RiskSizingDecision(
        approved=not blockers and approved_notional > 0.0,
        approved_notional_usdc=round(approved_notional, 6),
        blockers=blockers,
        reasons=reasons,
        diagnostics=diagnostics,
        snapshot=output_snapshot,
        paper_only=True,
        live_order_allowed=False,
    )


def evaluate_portfolio_risk(order: ProposedPaperOrder, snapshot: PortfolioRiskSnapshot | None = None, limits: PortfolioRiskLimits | None = None) -> PortfolioRiskResult:
    """Evaluate paper/dry-run portfolio limits without execution side effects."""
    snapshot = snapshot or PortfolioRiskSnapshot()
    limits = limits or PortfolioRiskLimits()
    projected_deployed = float(snapshot.deployed_capital_usdc) + max(0.0, float(order.notional_usdc))
    diagnostics: dict[str, Any] = {
        "paper_only": True,
        "live_order_allowed": False,
        "market_id": order.market_id,
        "token_id": order.token_id,
        "proposed_notional_usdc": float(order.notional_usdc),
        "liquidity_usd": float(order.liquidity_usd),
        "open_position_count": int(snapshot.open_position_count),
        "max_open_positions": int(limits.max_open_positions),
        "daily_realized_pnl_usdc": float(snapshot.daily_realized_pnl_usdc),
        "max_daily_loss_usdc": float(limits.max_daily_loss_usdc),
        "deployed_capital_usdc": float(snapshot.deployed_capital_usdc),
        "max_deployed_capital_usdc": float(limits.max_deployed_capital_usdc),
        "projected_deployed_capital_usdc": projected_deployed,
        "min_liquidity_usd": float(limits.min_liquidity_usd),
        "circuit_breaker": snapshot.circuit_breaker.to_dict(),
    }
    blockers: list[str] = []
    reasons: list[str] = []

    if snapshot.circuit_breaker.tripped:
        blockers.append("circuit_breaker_tripped")
        reason = snapshot.circuit_breaker.reason or "unspecified"
        reasons.append(f"circuit breaker tripped: {reason}")

    if int(snapshot.open_position_count) >= int(limits.max_open_positions):
        blockers.append("max_open_positions_reached")
        reasons.append(f"open positions {int(snapshot.open_position_count)} >= cap {int(limits.max_open_positions)}")

    if float(snapshot.daily_realized_pnl_usdc) <= -abs(float(limits.max_daily_loss_usdc)):
        blockers.append("daily_paper_loss_cap_reached")
        reasons.append(f"daily paper PnL {float(snapshot.daily_realized_pnl_usdc):g} <= loss cap {-abs(float(limits.max_daily_loss_usdc)):g}")

    if projected_deployed > float(limits.max_deployed_capital_usdc):
        blockers.append("deployed_capital_cap_reached")
        reasons.append(f"projected deployed capital {projected_deployed:g} > cap {float(limits.max_deployed_capital_usdc):g}")

    if float(order.liquidity_usd) < float(limits.min_liquidity_usd):
        blockers.append("min_liquidity_not_met")
        reasons.append(f"liquidity {float(order.liquidity_usd):g} < minimum {float(limits.min_liquidity_usd):g}")

    return PortfolioRiskResult(ok=not blockers, blockers=blockers, reasons=reasons, diagnostics=diagnostics)


def limits_from_mapping(raw: Mapping[str, Any] | None) -> PortfolioRiskLimits:
    raw = raw or {}
    return PortfolioRiskLimits(
        max_open_positions=_int(raw.get("max_open_positions"), PortfolioRiskLimits.max_open_positions),
        max_daily_loss_usdc=_float(raw.get("max_daily_loss_usdc"), PortfolioRiskLimits.max_daily_loss_usdc),
        max_deployed_capital_usdc=_float(raw.get("max_deployed_capital_usdc"), PortfolioRiskLimits.max_deployed_capital_usdc),
        min_liquidity_usd=_float(raw.get("min_liquidity_usd"), PortfolioRiskLimits.min_liquidity_usd),
    )


def snapshot_from_mapping(raw: Mapping[str, Any] | None) -> PortfolioRiskSnapshot:
    raw = raw or {}
    circuit_raw = raw.get("circuit_breaker") if isinstance(raw.get("circuit_breaker"), Mapping) else {}
    return PortfolioRiskSnapshot(
        open_position_count=_int(raw.get("open_position_count")),
        deployed_capital_usdc=_float(raw.get("deployed_capital_usdc")),
        daily_realized_pnl_usdc=_float(raw.get("daily_realized_pnl_usdc")),
        circuit_breaker=CircuitBreakerState(
            tripped=bool(circuit_raw.get("tripped", raw.get("circuit_breaker_tripped", False))),
            reason=circuit_raw.get("reason") or raw.get("circuit_breaker_reason"),
            tripped_at=circuit_raw.get("tripped_at") or raw.get("circuit_breaker_tripped_at"),
        ),
    )


__all__ = [
    "CircuitBreakerState",
    "PortfolioRiskLimits",
    "PortfolioRiskResult",
    "PortfolioRiskSnapshot",
    "ProposedPaperOrder",
    "RiskSizingDecision",
    "RiskSizingInput",
    "RiskSizingLimits",
    "RiskSizingSnapshot",
    "evaluate_portfolio_risk",
    "evaluate_risk_sizing",
    "limits_from_mapping",
    "snapshot_from_mapping",
]
