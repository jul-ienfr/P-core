from __future__ import annotations

from dataclasses import asdict, dataclass
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
    "evaluate_portfolio_risk",
    "limits_from_mapping",
    "snapshot_from_mapping",
]
