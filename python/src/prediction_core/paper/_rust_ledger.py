from __future__ import annotations

import importlib
import os
from typing import Any

RUST_LEDGER_ENV = "PREDICTION_CORE_RUST_ORDERBOOK"


def rust_ledger_enabled() -> bool:
    return os.getenv(RUST_LEDGER_ENV) == "1"


def fee_amount_with_optional_rust(*, notional: float, bps: float, fixed: float, python_fallback: Any) -> float:
    if not rust_ledger_enabled():
        return python_fallback(notional, bps=bps, fixed=fixed)
    try:
        backend = importlib.import_module("prediction_core._rust_orderbook")
        return float(backend.paper_fee_amount(notional=float(notional), bps=float(bps), fixed=float(fixed)))
    except Exception:
        return python_fallback(notional, bps=bps, fixed=fixed)


def opening_cost_state_with_optional_rust(
    *,
    filled_usdc: float,
    top_ask: float | None,
    avg_fill_price: float | None,
    shares: float,
    mtm_usdc: float,
    opening_fee_bps: float,
    opening_fixed_fee_usdc: float,
    estimated_exit_fee_bps: float,
    estimated_exit_fixed_fee_usdc: float,
) -> dict[str, Any] | None:
    if not rust_ledger_enabled():
        return None
    try:
        backend = importlib.import_module("prediction_core._rust_orderbook")
        payload = backend.paper_opening_cost_state(
            filled_usdc=float(filled_usdc),
            top_ask=top_ask,
            avg_fill_price=avg_fill_price,
            shares=float(shares),
            mtm_usdc=float(mtm_usdc),
            opening_fee_bps=float(opening_fee_bps),
            opening_fixed_fee_usdc=float(opening_fixed_fee_usdc),
            estimated_exit_fee_bps=float(estimated_exit_fee_bps),
            estimated_exit_fixed_fee_usdc=float(estimated_exit_fixed_fee_usdc),
        )
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return dict(payload)


def refresh_pnl_with_optional_rust(
    *,
    mtm_usdc: float,
    all_in_entry_cost_usdc: float,
    estimated_exit_fee_usdc: float,
    realized_exit_fee_usdc: float | None,
    python_fallback: Any,
) -> float:
    if not rust_ledger_enabled():
        return python_fallback(
            mtm_usdc=mtm_usdc,
            all_in_entry_cost_usdc=all_in_entry_cost_usdc,
            estimated_exit_fee_usdc=estimated_exit_fee_usdc,
            realized_exit_fee_usdc=realized_exit_fee_usdc,
        )
    try:
        backend = importlib.import_module("prediction_core._rust_orderbook")
        return float(
            backend.paper_refresh_pnl(
                mtm_usdc=float(mtm_usdc),
                all_in_entry_cost_usdc=float(all_in_entry_cost_usdc),
                estimated_exit_fee_usdc=float(estimated_exit_fee_usdc),
                realized_exit_fee_usdc=realized_exit_fee_usdc,
            )
        )
    except Exception:
        return python_fallback(
            mtm_usdc=mtm_usdc,
            all_in_entry_cost_usdc=all_in_entry_cost_usdc,
            estimated_exit_fee_usdc=estimated_exit_fee_usdc,
            realized_exit_fee_usdc=realized_exit_fee_usdc,
        )


def exit_policy_with_optional_rust(
    *,
    entry_price: float | None,
    current_price: float | None,
    highest_price: float | None,
    filled_usdc: float,
    shares: float,
    status: str,
    stop_loss_pct: float,
    trailing_stop_pct: float,
    breakeven_after_profit_pct: float,
) -> dict[str, Any] | None:
    if not rust_ledger_enabled():
        return None
    try:
        backend = importlib.import_module("prediction_core._rust_orderbook")
        payload = backend.paper_evaluate_exit_policy(
            entry_price=entry_price,
            current_price=current_price,
            highest_price=highest_price,
            filled_usdc=float(filled_usdc),
            shares=float(shares),
            status=str(status),
            stop_loss_pct=float(stop_loss_pct),
            trailing_stop_pct=float(trailing_stop_pct),
            breakeven_after_profit_pct=float(breakeven_after_profit_pct),
        )
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return dict(payload)


def settlement_pnl_with_optional_rust(
    *,
    shares: float,
    all_in_entry_cost_usdc: float,
    filled_usdc: float,
    won: bool,
) -> dict[str, Any] | None:
    if not rust_ledger_enabled():
        return None
    try:
        backend = importlib.import_module("prediction_core._rust_orderbook")
        payload = backend.paper_settlement_pnl(
            shares=float(shares),
            all_in_entry_cost_usdc=float(all_in_entry_cost_usdc),
            filled_usdc=float(filled_usdc),
            won=bool(won),
        )
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return dict(payload)
