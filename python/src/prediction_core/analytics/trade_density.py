from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class TradeDensity:
    bot: str
    trades: int
    days: int
    trades_per_minute: float
    mean_minutes_between_trades: float | None
    trades_per_day: float
    pnl_usd: float | None = None
    pnl_per_trade: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TradeDensitySummary:
    days: int
    rows: list[TradeDensity]

    def to_dict(self) -> dict[str, Any]:
        return {"days": self.days, "rows": [row.to_dict() for row in self.rows]}


def summarize_trade_density(rows: Iterable[dict[str, Any]], *, days: int) -> TradeDensitySummary:
    resolved_days = int(days)
    if resolved_days <= 0:
        raise ValueError("days must be positive")
    minutes = resolved_days * 1440
    density_rows: list[TradeDensity] = []
    for row in rows:
        trades = int(row.get("trades") or row.get("N") or row.get("count") or 0)
        per_minute = trades / minutes if minutes else 0.0
        pnl = _optional_float(row.get("pnl_usd"))
        density_rows.append(
            TradeDensity(
                bot=str(row.get("bot") or row.get("name") or ""),
                trades=trades,
                days=resolved_days,
                trades_per_minute=round(per_minute, 3),
                mean_minutes_between_trades=round(1.0 / per_minute, 2) if per_minute > 0 else None,
                trades_per_day=round(trades / resolved_days, 2),
                pnl_usd=pnl,
                pnl_per_trade=round(pnl / trades, 4) if pnl is not None and trades > 0 else None,
            )
        )
    return TradeDensitySummary(days=resolved_days, rows=density_rows)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
