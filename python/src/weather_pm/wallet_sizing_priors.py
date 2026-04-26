from __future__ import annotations

from statistics import median
from typing import Any

OPERATOR_DEFAULT_STYLE = "breadth/grid small-ticket surface trader"
COPY_WARNING = "wallet priors adjust size/confidence but do not authorize blind copy-trading"

_COPY_MODES = {
    "breadth/grid small-ticket surface trader": "imitate_small_grid_notional",
    "sparse/large-ticket conviction trader": "confidence_only_cap_size",
    "selective weather trader": "confidence_only_no_size_bump",
}
_UNKNOWN_COPY_MODE = "model_execution_only"


def build_wallet_sizing_priors(payload: dict[str, Any]) -> dict[str, Any]:
    """Summarize recent trade-size priors by profitable wallet style.

    Wallet priors are intended to guide confidence and conservative notional bands;
    they do not authorize blind copy-trading or large-ticket size imitation.
    """

    accounts = payload.get("accounts", [])
    if not isinstance(accounts, list):
        accounts = []

    grouped: dict[str, list[dict[str, Any]]] = {}
    for account in accounts:
        if not isinstance(account, dict):
            continue
        style = str(account.get("style") or "unknown")
        grouped.setdefault(style, []).append(account)

    styles: dict[str, dict[str, Any]] = {}
    for style in sorted(grouped):
        style_accounts = grouped[style]
        avg_values = [_as_float(account.get("recent_trade_avg_usdc")) for account in style_accounts]
        max_values = [_as_float(account.get("recent_trade_max_usdc")) for account in style_accounts]
        avg_values = [value for value in avg_values if value is not None]
        max_values = [value for value in max_values if value is not None]

        styles[style] = {
            "accounts": len(style_accounts),
            "median_recent_trade_avg_usdc": _rounded_median(avg_values),
            "median_recent_trade_max_usdc": _rounded_median(max_values),
            "recommended_copy_mode": _COPY_MODES.get(style, _UNKNOWN_COPY_MODE),
        }

    return {
        "styles": styles,
        "operator_default_style": OPERATOR_DEFAULT_STYLE,
        "copy_warning": COPY_WARNING,
    }


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rounded_median(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(median(values)), 2)
