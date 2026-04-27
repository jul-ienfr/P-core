from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol


class ExecutionMode(str, Enum):
    PAPER = "paper"
    DRY_RUN = "dry_run"
    LIVE = "live"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    LIMIT = "limit"


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, kw_only=True)
class OrderRequest:
    market_id: str
    token_id: str
    outcome: str
    side: OrderSide | str
    order_type: OrderType | str
    limit_price: float
    notional_usdc: float
    idempotency_key: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.market_id).strip():
            raise ValueError("market_id is required")
        if not str(self.token_id).strip():
            raise ValueError("token_id is required")
        if not str(self.outcome).strip():
            raise ValueError("outcome is required")
        if not str(self.idempotency_key).strip():
            raise ValueError("idempotency_key is required")
        object.__setattr__(
            self,
            "side",
            self.side if isinstance(self.side, OrderSide) else OrderSide(str(self.side).lower()),
        )
        object.__setattr__(
            self,
            "order_type",
            self.order_type
            if isinstance(self.order_type, OrderType)
            else OrderType(str(self.order_type).lower()),
        )
        limit_price = float(self.limit_price)
        notional_usdc = float(self.notional_usdc)
        if not 0.0 < limit_price < 1.0:
            raise ValueError("limit_price must be between 0 and 1")
        if notional_usdc <= 0.0:
            raise ValueError("notional_usdc must be positive")
        object.__setattr__(self, "limit_price", limit_price)
        object.__setattr__(self, "notional_usdc", notional_usdc)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["side"] = _enum_value(self.side)
        payload["order_type"] = _enum_value(self.order_type)
        return payload


@dataclass(frozen=True, kw_only=True)
class OrderResult:
    accepted: bool
    status: str
    idempotency_key: str
    exchange_order_id: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OrderExecutor(Protocol):
    def submit_order(self, order: OrderRequest) -> OrderResult:
        ...


class DryRunPolymarketExecutor:
    def __init__(self) -> None:
        self.orders: list[OrderRequest] = []

    def submit_order(self, order: OrderRequest) -> OrderResult:
        self.orders.append(order)
        return OrderResult(
            accepted=True,
            status="dry_run_accepted",
            exchange_order_id=f"dry-run:{order.idempotency_key}",
            idempotency_key=order.idempotency_key,
            raw_response={"dry_run": True, "order": order.to_dict()},
        )


@dataclass(frozen=True, kw_only=True)
class ExecutionRiskLimits:
    max_order_notional_usdc: float
    max_total_exposure_usdc: float
    max_daily_loss_usdc: float
    max_spread: float


@dataclass(frozen=True, kw_only=True)
class ExecutionRiskState:
    total_exposure_usdc: float = 0.0
    daily_realized_pnl_usdc: float = 0.0


@dataclass(frozen=True, kw_only=True)
class ExecutionRiskDecision:
    allowed: bool
    blocked_by: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_execution_risk(
    order: OrderRequest,
    *,
    limits: ExecutionRiskLimits,
    state: ExecutionRiskState,
    market_snapshot: dict[str, Any],
) -> ExecutionRiskDecision:
    blocked: list[str] = []
    if order.notional_usdc > float(limits.max_order_notional_usdc):
        blocked.append("max_order_notional_usdc")
    if state.total_exposure_usdc + order.notional_usdc > float(limits.max_total_exposure_usdc):
        blocked.append("max_total_exposure_usdc")
    if state.daily_realized_pnl_usdc <= -abs(float(limits.max_daily_loss_usdc)):
        blocked.append("max_daily_loss_usdc")
    spread = market_snapshot.get("spread")
    if spread is None:
        blocked.append("missing_spread")
    elif float(spread) > float(limits.max_spread):
        blocked.append("max_spread")
    return ExecutionRiskDecision(allowed=not blocked, blocked_by=blocked)


class JsonlIdempotencyStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._seen: set[str] = set()
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                key = row.get("key")
                if key:
                    self._seen.add(str(key))

    def seen(self, key: str) -> bool:
        if not str(key).strip():
            raise ValueError("key is required")
        return str(key) in self._seen

    def claim(self, key: str, metadata: dict[str, Any] | None = None) -> bool:
        if not str(key).strip():
            raise ValueError("key is required")
        key = str(key)
        if key in self._seen:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {"key": key, "claimed_at": _utc_now_iso(), "metadata": metadata or {}}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        self._seen.add(key)
        return True


class JsonlExecutionAuditLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not str(event_type).strip():
            raise ValueError("event_type is required")
        row = {"recorded_at": _utc_now_iso(), "event_type": str(event_type), "payload": payload}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        return row


def _exchange_order_id(row: Mapping[str, Any]) -> str | None:
    value = row.get("id") or row.get("order_id")
    return str(value) if value else None


def reconcile_orders(
    *,
    local_orders: list[dict[str, Any]],
    exchange_orders: list[dict[str, Any]],
) -> dict[str, Any]:
    local_ids = {str(row["exchange_order_id"]) for row in local_orders if row.get("exchange_order_id")}
    exchange_ids = {order_id for row in exchange_orders if (order_id := _exchange_order_id(row))}
    missing = sorted(local_ids - exchange_ids)
    unexpected = sorted(exchange_ids - local_ids)
    return {
        "ok": not missing and not unexpected,
        "missing_on_exchange": missing,
        "unexpected_on_exchange": unexpected,
        "local_order_count": len(local_orders),
        "exchange_order_count": len(exchange_orders),
    }


class ExecutionCredentialsError(RuntimeError):
    pass


class ClobRestPolymarketExecutor:
    REQUIRED_ENV = (
        "POLYMARKET_PRIVATE_KEY",
        "POLYMARKET_FUNDER_ADDRESS",
        "POLYMARKET_CHAIN_ID",
    )

    def __init__(self, *, private_key: str, funder_address: str, chain_id: str) -> None:
        self._private_key = private_key
        self.funder_address = funder_address
        self.chain_id = chain_id

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ClobRestPolymarketExecutor":
        source = os.environ if env is None else env
        missing = [name for name in cls.REQUIRED_ENV if not str(source.get(name, "")).strip()]
        if missing:
            raise ExecutionCredentialsError("Polymarket CLOB REST credentials are required")
        return cls(
            private_key=str(source["POLYMARKET_PRIVATE_KEY"]),
            funder_address=str(source["POLYMARKET_FUNDER_ADDRESS"]),
            chain_id=str(source["POLYMARKET_CHAIN_ID"]),
        )

    def submit_order(self, order: OrderRequest) -> OrderResult:
        raise NotImplementedError("real CLOB REST submission not wired yet")
