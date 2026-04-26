from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class AmmTradeQuote:
    shares_received: float
    effective_price: float
    total_cost: float
    new_reserve_yes: float
    new_reserve_no: float

    @property
    def cash_received(self) -> float:
        return max(0.0, -self.total_cost)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["cash_received"] = self.cash_received
        return payload


def amm_prices(*, reserve_yes: float, reserve_no: float) -> tuple[float, float]:
    yes = max(0.0, float(reserve_yes))
    no = max(0.0, float(reserve_no))
    total = yes + no
    if total <= 0:
        return 0.5, 0.5
    return no / total, yes / total


def _is_yes_outcome(outcome: str, *, yes_name: str) -> bool:
    return str(outcome).strip().upper() == yes_name.strip().upper()


def quote_amm_buy(
    *,
    reserve_yes: float,
    reserve_no: float,
    outcome: str,
    amount_usd: float,
    yes_name: str = "YES",
) -> AmmTradeQuote:
    if amount_usd <= 0:
        raise ValueError("amount_usd must be positive")

    yes = float(reserve_yes)
    no = float(reserve_no)
    amount = float(amount_usd)
    k = yes * no

    if _is_yes_outcome(outcome, yes_name=yes_name):
        new_no = no + amount
        new_yes = k / new_no if new_no else 0.0
        shares_out = amount + (yes - new_yes)
    else:
        new_yes = yes + amount
        new_no = k / new_yes if new_yes else 0.0
        shares_out = amount + (no - new_no)

    effective_price = amount / shares_out if shares_out > 0 else 0.0
    return AmmTradeQuote(
        shares_received=shares_out,
        effective_price=effective_price,
        total_cost=amount,
        new_reserve_yes=new_yes,
        new_reserve_no=new_no,
    )


def quote_amm_sell(
    *,
    reserve_yes: float,
    reserve_no: float,
    outcome: str,
    shares: float,
    yes_name: str = "YES",
) -> AmmTradeQuote:
    if shares <= 0:
        raise ValueError("shares must be positive")

    yes = float(reserve_yes)
    no = float(reserve_no)
    share_count = float(shares)
    reserve_sold = yes if _is_yes_outcome(outcome, yes_name=yes_name) else no

    b_coeff = yes + no - share_count
    c_coeff = -share_count * reserve_sold
    discriminant = b_coeff**2 - 4.0 * c_coeff
    swap_size = (-b_coeff + math.sqrt(discriminant)) / 2.0
    cash_out = share_count - swap_size

    k = yes * no
    if _is_yes_outcome(outcome, yes_name=yes_name):
        new_yes = yes + swap_size
        new_no = k / new_yes if new_yes else 0.0
    else:
        new_no = no + swap_size
        new_yes = k / new_no if new_no else 0.0

    effective_price = cash_out / share_count if share_count > 0 else 0.0
    return AmmTradeQuote(
        shares_received=cash_out,
        effective_price=effective_price,
        total_cost=-cash_out,
        new_reserve_yes=new_yes,
        new_reserve_no=new_no,
    )
