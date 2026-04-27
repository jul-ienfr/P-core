from __future__ import annotations

from typing import Any, Callable


def build_paper_portfolio_report(
    positions: list[dict[str, Any]],
    closed_positions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Aggregate paper portfolio without mixing spend, realized PnL and open MTM."""
    closed_positions = closed_positions or []
    rows = list(positions) + list(closed_positions)

    def is_settled(p: dict[str, Any]) -> bool:
        return p.get("settlement_status") in {"SETTLED_WON", "SETTLED_LOST"}

    def is_exit(p: dict[str, Any]) -> bool:
        return p.get("action") == "EXIT_PAPER"

    def is_open(p: dict[str, Any]) -> bool:
        return not is_settled(p) and not is_exit(p)

    def realized_pnl(p: dict[str, Any]) -> float | None:
        explicit = _float_or_none(p.get("paper_realized_pnl_usdc"))
        if explicit is not None:
            return explicit
        if is_settled(p):
            return (_float_or_zero(p.get("paper_settlement_value_usdc")) - _float_or_zero(p.get("filled_usdc")))
        return None

    def sum_where(pred: Callable[[dict[str, Any]], bool], getter: Callable[[dict[str, Any]], float | None]) -> float:
        return round(sum((getter(p) or 0.0) for p in rows if pred(p)), 6)

    open_spend = sum_where(is_open, lambda p: _float_or_none(p.get("filled_usdc")))
    open_shares = sum_where(is_open, lambda p: _float_or_none(p.get("shares")))
    realized_total = sum_where(lambda p: is_settled(p) or is_exit(p), realized_pnl)
    open_mtm = sum_where(is_open, lambda p: _float_or_none(p.get("paper_mtm_bid_usdc")))

    return {
        "counts": {
            "total": len(rows),
            "open": sum(1 for p in rows if is_open(p)),
            "settled": sum(1 for p in rows if is_settled(p)),
            "exit_paper": sum(1 for p in rows if is_exit(p)),
        },
        "spend_usdc": {
            "total_displayed": sum_where(lambda p: True, lambda p: _float_or_none(p.get("filled_usdc"))),
            "settled": sum_where(is_settled, lambda p: _float_or_none(p.get("filled_usdc"))),
            "exit_paper_displayed": sum_where(is_exit, lambda p: _float_or_none(p.get("filled_usdc"))),
            "open": open_spend,
        },
        "pnl_usdc": {
            "settled_realized": sum_where(is_settled, realized_pnl),
            "exit_realized": sum_where(is_exit, realized_pnl),
            "realized_total": realized_total,
            "open_mtm_bid": open_mtm,
            "realized_plus_open_mtm": round(realized_total + open_mtm, 6),
            "if_open_loses": round(realized_total - open_spend, 6),
            "if_open_wins_full_payout": round(realized_total + open_shares - open_spend, 6),
            "official_hold_to_settlement_for_exits": sum_where(
                is_exit, lambda p: _float_or_none(p.get("official_hold_to_settlement_pnl_usdc"))
            ),
        },
    }


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_or_zero(value: Any) -> float:
    return _float_or_none(value) or 0.0
