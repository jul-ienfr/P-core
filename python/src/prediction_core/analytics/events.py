from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from typing import Any


def _format_clickhouse_datetime64(value: datetime) -> str:
    """Format a datetime as a UTC ClickHouse DateTime64(3) literal."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%d %H:%M:%S.%f")[:23]


@dataclass(frozen=True)
class ProfileDecisionEvent:
    run_id: str
    strategy_id: str
    profile_id: str
    market_id: str
    observed_at: datetime
    mode: str
    decision_status: str
    skip_reason: str = ""
    token_id: str = ""
    execution_mode: str = ""
    edge: float | None = None
    limit_price: float | None = None
    requested_spend_usdc: float | None = None
    capped_spend_usdc: float | None = None
    source_ok: bool = False
    orderbook_ok: bool = False
    risk_ok: bool = False
    paper_only: bool = True
    live_order_allowed: bool = False
    raw: dict[str, Any] | None = None

    @property
    def table(self) -> str:
        return "profile_decisions"


@dataclass(frozen=True)
class DebugDecisionEvent:
    run_id: str
    strategy_id: str
    profile_id: str
    market_id: str
    observed_at: datetime
    mode: str
    decision_status: str
    skip_reason: str = ""
    token_id: str = ""
    edge: float | None = None
    limit_price: float | None = None
    source_ok: bool = False
    orderbook_ok: bool = False
    risk_ok: bool = False
    blocker: str = ""
    raw: dict[str, Any] | None = None

    @property
    def table(self) -> str:
        return "debug_decisions"


@dataclass(frozen=True)
class PaperOrderEvent:
    run_id: str
    strategy_id: str
    profile_id: str
    market_id: str
    observed_at: datetime
    mode: str
    paper_order_id: str
    side: str
    status: str
    token_id: str = ""
    price: float | None = None
    size: float | None = None
    spend_usdc: float | None = None
    opening_fee_usdc: float | None = None
    opening_slippage_usdc: float | None = None
    estimated_exit_cost_usdc: float | None = None
    paper_only: bool = True
    live_order_allowed: bool = False
    raw: dict[str, Any] | None = None

    @property
    def table(self) -> str:
        return "paper_orders"


@dataclass(frozen=True)
class PaperPositionEvent:
    run_id: str
    strategy_id: str
    profile_id: str
    market_id: str
    observed_at: datetime
    mode: str
    paper_position_id: str
    quantity: float
    status: str
    token_id: str = ""
    avg_price: float | None = None
    exposure_usdc: float | None = None
    mtm_bid_usdc: float | None = None
    raw: dict[str, Any] | None = None

    @property
    def table(self) -> str:
        return "paper_positions"


@dataclass(frozen=True)
class StrategyMetricEvent:
    run_id: str
    strategy_id: str
    observed_at: datetime
    mode: str
    signal_count: int
    trade_count: int
    skip_count: int
    profile_id: str = ""
    market_id: str = ""
    avg_edge: float | None = None
    gross_pnl_usdc: float | None = None
    net_pnl_usdc: float | None = None
    exposure_usdc: float | None = None
    raw: dict[str, Any] | None = None

    @property
    def table(self) -> str:
        return "strategy_metrics"


@dataclass(frozen=True)
class ProfileMetricEvent:
    run_id: str
    profile_id: str
    observed_at: datetime
    mode: str
    decision_count: int
    trade_count: int
    skip_count: int
    strategy_id: str = ""
    market_id: str = ""
    exposure_usdc: float | None = None
    gross_pnl_usdc: float | None = None
    net_pnl_usdc: float | None = None
    roi: float | None = None
    raw: dict[str, Any] | None = None

    @property
    def table(self) -> str:
        return "profile_metrics"


def serialize_event(event: Any) -> dict[str, Any]:
    row = asdict(event)
    observed_at = row.get("observed_at")
    if isinstance(observed_at, datetime):
        row["observed_at"] = _format_clickhouse_datetime64(observed_at)
    raw = row.get("raw")
    row["raw"] = json.dumps(raw or {}, sort_keys=True, separators=(",", ":"))
    row.pop("table", None)
    return row
