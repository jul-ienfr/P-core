from __future__ import annotations

import fcntl
import importlib
import json
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from prediction_core.storage.config import redact_mapping


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
        if not math.isfinite(limit_price) or not 0.0 < limit_price < 1.0:
            raise ValueError("limit_price must be finite and between 0 and 1")
        if not math.isfinite(notional_usdc) or notional_usdc <= 0.0:
            raise ValueError("notional_usdc must be finite and positive")
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


class OrderManagementExecutor(Protocol):
    """Read-only/safe order management contract.

    Implementations may expose exchange state for reconciliation. Cancels must be
    explicit and safe; the live CLOB scaffold fails closed instead of issuing a
    network cancel.
    """

    def list_open_orders(self) -> list[dict[str, Any]]:
        ...

    def cancel_order(self, exchange_order_id: str) -> OrderResult:
        ...


class IdempotencyStore(Protocol):
    def seen(self, key: str) -> bool:
        ...

    def claim(self, key: str, metadata: dict[str, Any] | None = None, status: str = "pending") -> bool:
        ...

    def mark_submitted(self, key: str, metadata: dict[str, Any] | None = None) -> bool:
        ...

    def mark_rejected(self, key: str, metadata: dict[str, Any] | None = None) -> bool:
        ...


class ExecutionAuditLog(Protocol):
    def append(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...


class DryRunPolymarketExecutor:
    def __init__(self, *, open_orders: list[dict[str, Any]] | None = None) -> None:
        self.orders: list[OrderRequest] = []
        self._open_orders = list(open_orders or [])
        self.cancel_requests: list[str] = []

    def submit_order(self, order: OrderRequest) -> OrderResult:
        self.orders.append(order)
        exchange_order_id = f"dry-run:{order.idempotency_key}"
        self._open_orders.append({"id": exchange_order_id, "status": "open", "idempotency_key": order.idempotency_key, "token_id": order.token_id})
        return OrderResult(
            accepted=True,
            status="dry_run_accepted",
            exchange_order_id=exchange_order_id,
            idempotency_key=order.idempotency_key,
            raw_response={"dry_run": True, "order": order.to_dict()},
        )

    def list_open_orders(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._open_orders]

    def cancel_order(self, exchange_order_id: str) -> OrderResult:
        self.cancel_requests.append(str(exchange_order_id))
        return OrderResult(
            accepted=False,
            status="dry_run_cancel_not_submitted",
            exchange_order_id=str(exchange_order_id),
            idempotency_key=str(exchange_order_id),
            raw_response={"dry_run": True, "cancel_submitted": False},
        )


@dataclass(frozen=True, kw_only=True)
class ExecutionRiskLimits:
    max_order_notional_usdc: float
    max_total_exposure_usdc: float
    max_daily_loss_usdc: float
    max_spread: float

    def __post_init__(self) -> None:
        for field_name in ("max_order_notional_usdc", "max_total_exposure_usdc", "max_daily_loss_usdc", "max_spread"):
            value = float(getattr(self, field_name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{field_name} must be finite and positive")
            object.__setattr__(self, field_name, value)


@dataclass(frozen=True, kw_only=True)
class ExecutionRiskState:
    total_exposure_usdc: float = 0.0
    daily_realized_pnl_usdc: float = 0.0

    def __post_init__(self) -> None:
        total_exposure = float(self.total_exposure_usdc)
        daily_pnl = float(self.daily_realized_pnl_usdc)
        if not math.isfinite(total_exposure) or total_exposure < 0.0:
            raise ValueError("total_exposure_usdc must be finite and non-negative")
        if not math.isfinite(daily_pnl):
            raise ValueError("daily_realized_pnl_usdc must be finite")
        object.__setattr__(self, "total_exposure_usdc", total_exposure)
        object.__setattr__(self, "daily_realized_pnl_usdc", daily_pnl)


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
    if os.getenv("PREDICTION_CORE_RUST_ORDERBOOK") == "1":
        try:
            return _evaluate_execution_risk_with_rust(order=order, limits=limits, state=state, market_snapshot=market_snapshot)
        except (ImportError, AttributeError):
            pass
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
    else:
        try:
            spread_value = float(spread)
        except (TypeError, ValueError):
            blocked.append("invalid_spread")
        else:
            if not math.isfinite(spread_value):
                blocked.append("invalid_spread")
            elif spread_value > float(limits.max_spread):
                blocked.append("max_spread")
    return ExecutionRiskDecision(allowed=not blocked, blocked_by=blocked)


def _evaluate_execution_risk_with_rust(
    *,
    order: OrderRequest,
    limits: ExecutionRiskLimits,
    state: ExecutionRiskState,
    market_snapshot: dict[str, Any],
) -> ExecutionRiskDecision:
    backend = importlib.import_module("prediction_core._rust_orderbook")
    payload = backend.evaluate_execution_risk(
        order_notional_usdc=order.notional_usdc,
        total_exposure_usdc=state.total_exposure_usdc,
        daily_realized_pnl_usdc=state.daily_realized_pnl_usdc,
        max_order_notional_usdc=limits.max_order_notional_usdc,
        max_total_exposure_usdc=limits.max_total_exposure_usdc,
        max_daily_loss_usdc=limits.max_daily_loss_usdc,
        max_spread=limits.max_spread,
        spread=market_snapshot.get("spread"),
    )
    if not isinstance(payload, dict):
        raise ValueError("rust execution risk payload must be an object")
    return ExecutionRiskDecision(allowed=bool(payload["allowed"]), blocked_by=[str(reason) for reason in payload["blocked_by"]])


class JsonlIdempotencyStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._records: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                key = row.get("key")
                if key:
                    self._records[str(key)] = row

    def seen(self, key: str) -> bool:
        key = self._normalize_key(key)
        return key in self._records

    def claim(self, key: str, metadata: dict[str, Any] | None = None, status: str = "pending") -> bool:
        key = self._normalize_key(key)
        if key in self._records:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {"key": key, "claimed_at": _utc_now_iso(), "status": str(status or "pending"), "metadata": metadata or {}}
        flags = os.O_APPEND | os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(self.path, flags, 0o600)
        except FileExistsError:
            self._reload()
            if key in self._records:
                return False
            fd = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            self._reload()
            if key in self._records:
                return False
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._records[key] = row
        return True

    def mark_submitted(self, key: str, metadata: dict[str, Any] | None = None) -> bool:
        return self._mark_terminal(key, status="submitted", timestamp_field="submitted_at", metadata=metadata)

    def mark_rejected(self, key: str, metadata: dict[str, Any] | None = None) -> bool:
        return self._mark_terminal(key, status="rejected", timestamp_field="rejected_at", metadata=metadata)

    def _mark_terminal(self, key: str, *, status: str, timestamp_field: str, metadata: dict[str, Any] | None = None) -> bool:
        key = self._normalize_key(key)
        if key not in self._records:
            return False
        row = {"key": key, timestamp_field: _utc_now_iso(), "status": status, "metadata": metadata or {}}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._records[key] = row
        return True

    def _reload(self) -> None:
        self._records.clear()
        if not self.path.exists():
            return
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            key = row.get("key")
            if key:
                self._records[str(key)] = row

    @staticmethod
    def _normalize_key(key: str) -> str:
        if not str(key).strip():
            raise ValueError("key is required")
        return str(key)


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


class PostgresIdempotencyStore:
    def __init__(self, repository: Any, *, mode: str = ExecutionMode.PAPER.value, paper_only: bool = True) -> None:
        self.repository = repository
        self.mode = mode
        self.paper_only = paper_only

    def seen(self, key: str) -> bool:
        raise NotImplementedError("PostgresIdempotencyStore supports atomic claim; use claim()")

    def claim(self, key: str, metadata: dict[str, Any] | None = None, status: str = "pending") -> bool:
        metadata = {**(metadata or {}), "status": status}
        return self.repository.claim_idempotency_key(
            key=key,
            mode=str(metadata.get("mode") or self.mode),
            run_id=_optional_str(metadata.get("run_id")),
            market_id=_optional_str(metadata.get("market_id")),
            token_id=_optional_str(metadata.get("token_id")),
            metadata=metadata,
            paper_only=self.paper_only,
        )

    def mark_submitted(self, key: str, metadata: dict[str, Any] | None = None) -> bool:
        update = getattr(self.repository, "update_idempotency_key_status", None)
        if callable(update):
            return bool(update(key=key, status="submitted", metadata=metadata))
        return True

    def mark_rejected(self, key: str, metadata: dict[str, Any] | None = None) -> bool:
        update = getattr(self.repository, "update_idempotency_key_status", None)
        if callable(update):
            return bool(update(key=key, status="rejected", metadata=metadata))
        return True


class CompositeIdempotencyStore:
    def __init__(self, primary: IdempotencyStore, secondary: IdempotencyStore | None = None, *, strict_secondary_writes: bool = False) -> None:
        self.primary = primary
        self.secondary = secondary
        self.strict_secondary_writes = strict_secondary_writes

    def seen(self, key: str) -> bool:
        return self.primary.seen(key)

    def claim(self, key: str, metadata: dict[str, Any] | None = None, status: str = "pending") -> bool:
        claimed = self.primary.claim(key, metadata, status=status)
        if claimed and self.secondary is not None:
            try:
                self.secondary.claim(key, metadata, status=status)
            except Exception:
                if self.strict_secondary_writes:
                    raise
        return claimed

    def mark_submitted(self, key: str, metadata: dict[str, Any] | None = None) -> bool:
        marked = self.primary.mark_submitted(key, metadata)
        if marked and self.secondary is not None:
            try:
                self.secondary.mark_submitted(key, metadata)
            except Exception:
                if self.strict_secondary_writes:
                    raise
        return marked

    def mark_rejected(self, key: str, metadata: dict[str, Any] | None = None) -> bool:
        marked = self.primary.mark_rejected(key, metadata)
        if marked and self.secondary is not None:
            try:
                self.secondary.mark_rejected(key, metadata)
            except Exception:
                if self.strict_secondary_writes:
                    raise
        return marked


class PostgresExecutionAuditLog:
    def __init__(self, repository: Any, *, paper_only: bool = True, live_order_allowed: bool = False) -> None:
        self.repository = repository
        self.paper_only = paper_only
        self.live_order_allowed = live_order_allowed

    def append(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repository.append_execution_audit_event(
            event_type=event_type,
            payload=payload,
            run_id=_optional_str(payload.get("run_id")),
            market_id=_optional_str(payload.get("market_id")),
            token_id=_optional_str(payload.get("token_id")),
            paper_only=self.paper_only,
            live_order_allowed=self.live_order_allowed,
        )


class CompositeExecutionAuditLog:
    def __init__(self, primary: ExecutionAuditLog, secondary: ExecutionAuditLog | None = None, *, strict_secondary_writes: bool = False) -> None:
        self.primary = primary
        self.secondary = secondary
        self.strict_secondary_writes = strict_secondary_writes

    def append(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = self.primary.append(event_type, payload)
        if self.secondary is not None:
            try:
                self.secondary.append(event_type, payload)
            except Exception:
                if self.strict_secondary_writes:
                    raise
        return row


def _optional_str(value: Any) -> str | None:
    return None if value is None or not str(value).strip() else str(value)


def _exchange_order_id(row: Mapping[str, Any]) -> str | None:
    value = row.get("id") or row.get("order_id") or row.get("exchange_order_id")
    return str(value) if value else None


def _order_status(row: Mapping[str, Any], *, default: str = "unknown") -> str:
    status = str(row.get("status") or row.get("state") or default).strip().lower()
    return status or default


def _filled_size(row: Mapping[str, Any]) -> float:
    for key in ("filled_size", "filled", "filled_amount", "filled_shares"):
        if key not in row:
            continue
        try:
            value = float(row[key])
        except (TypeError, ValueError):
            return 0.0
        return value if math.isfinite(value) and value > 0 else 0.0
    return 0.0


def _order_size(row: Mapping[str, Any]) -> float | None:
    for key in ("size", "original_size", "order_size", "notional_usdc", "notional"):
        if key not in row:
            continue
        try:
            value = float(row[key])
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) and value > 0 else None
    return None


def _is_partial_fill(row: Mapping[str, Any]) -> bool:
    status = _order_status(row)
    if status in {"partially_filled", "partial"}:
        return True
    if status in {"filled", "complete", "completed"}:
        total_size = _order_size(row)
        return total_size is not None and 0.0 < _filled_size(row) < total_size
    return _filled_size(row) > 0.0


def _field_value(row: Mapping[str, Any], aliases: tuple[str, ...]) -> Any:
    for key in aliases:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _normalized_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(_enum_value(value)).strip().lower()
    return text or None


def _normalized_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _field_mismatches(order_id: str, local: Mapping[str, Any], exchange: Mapping[str, Any]) -> list[dict[str, Any]]:
    specs = (
        ("token_id", ("token_id", "asset_id", "clob_token_id"), ("token_id", "asset_id", "clob_token_id"), "text"),
        ("side", ("side",), ("side",), "text"),
        ("limit_price", ("limit_price", "price"), ("limit_price", "price"), "float"),
        ("notional", ("notional_usdc", "notional", "size", "order_size"), ("notional_usdc", "notional", "size", "order_size"), "float"),
    )
    mismatches: list[dict[str, Any]] = []
    for field_name, local_aliases, exchange_aliases, kind in specs:
        local_raw = _field_value(local, local_aliases)
        exchange_raw = _field_value(exchange, exchange_aliases)
        if local_raw is None or exchange_raw is None:
            continue
        if kind == "float":
            local_value = _normalized_float(local_raw)
            exchange_value = _normalized_float(exchange_raw)
            if local_value is None or exchange_value is None:
                continue
            different = not math.isclose(local_value, exchange_value, rel_tol=1e-9, abs_tol=1e-9)
        else:
            local_value = _normalized_text(local_raw)
            exchange_value = _normalized_text(exchange_raw)
            if local_value is None or exchange_value is None:
                continue
            different = local_value != exchange_value
        if different:
            mismatches.append({"exchange_order_id": order_id, "field": field_name, "local": local_value, "exchange": exchange_value})
    return mismatches


def _duplicate_ids(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for order_id in ids:
        if order_id in seen:
            duplicates.add(order_id)
        seen.add(order_id)
    return sorted(duplicates)


def reconcile_orders(
    *,
    local_orders: list[dict[str, Any]],
    exchange_orders: list[dict[str, Any]],
) -> dict[str, Any]:
    local_ids_list = [order_id for row in local_orders if (order_id := _exchange_order_id(row))]
    exchange_ids_list = [order_id for row in exchange_orders if (order_id := _exchange_order_id(row))]
    local_ids = set(local_ids_list)
    exchange_ids = set(exchange_ids_list)
    missing = sorted(local_ids - exchange_ids)
    unexpected = sorted(exchange_ids - local_ids)
    local_by_id = {order_id: row for row in local_orders if (order_id := _exchange_order_id(row))}
    exchange_by_id = {order_id: row for row in exchange_orders if (order_id := _exchange_order_id(row))}
    local_duplicate_ids = _duplicate_ids(local_ids_list)
    exchange_duplicate_ids = _duplicate_ids(exchange_ids_list)
    open_order_ids = sorted(
        order_id
        for order_id, row in exchange_by_id.items()
        if _order_status(row) in {"open", "live", "pending", "partially_filled"}
    )
    partial_fills = sorted(
        order_id
        for order_id, row in exchange_by_id.items()
        if _is_partial_fill(row)
    )
    status_mismatches = []
    field_mismatches = []
    for order_id in sorted(local_ids & exchange_ids):
        local_status = _order_status(local_by_id[order_id], default="submitted")
        exchange_status = _order_status(exchange_by_id[order_id], default="open")
        if local_status in {"filled", "cancelled", "canceled", "rejected"} and exchange_status in {"open", "live", "pending", "partially_filled"}:
            status_mismatches.append({"exchange_order_id": order_id, "local_status": local_status, "exchange_status": exchange_status})
        elif local_status in {"submitted", "pending", "open"} and exchange_status in {"rejected", "cancelled", "canceled", "expired"}:
            status_mismatches.append({"exchange_order_id": order_id, "local_status": local_status, "exchange_status": exchange_status})
        field_mismatches.extend(_field_mismatches(order_id, local_by_id[order_id], exchange_by_id[order_id]))
    critical = bool(missing or unexpected or local_duplicate_ids or exchange_duplicate_ids or field_mismatches)
    warning = bool(open_order_ids or partial_fills or status_mismatches)
    status = "critical" if critical else "warning" if warning else "ok"
    return {
        "ok": status == "ok",
        "status": status,
        "severity": status,
        "missing_on_exchange": missing,
        "unexpected_on_exchange": unexpected,
        "open_order_ids": open_order_ids,
        "partial_fill_order_ids": partial_fills,
        "status_mismatches": status_mismatches,
        "field_mismatches": field_mismatches,
        "duplicate_local_order_ids": local_duplicate_ids,
        "duplicate_exchange_order_ids": exchange_duplicate_ids,
        "local_order_count": len(local_orders),
        "exchange_order_count": len(exchange_orders),
    }


class ExecutionCredentialsError(RuntimeError):
    pass


class LiveExecutionUnavailableError(RuntimeError):
    pass


class LiveExecutionGuardrailError(RuntimeError):
    pass


LIVE_ACK_PHRASE = "I_UNDERSTAND_THIS_SUBMITS_REAL_POLYMARKET_ORDERS"
DEFAULT_CLOB_HOST = "https://clob.polymarket.com"


@dataclass(frozen=True, kw_only=True)
class ClobRestExecutorConfig:
    private_key: str
    funder_address: str
    chain_id: int
    host: str = DEFAULT_CLOB_HOST
    signature_type: int | None = None
    live_enabled: bool = False
    live_ack: str = ""
    allow_order_submission: bool = False
    max_order_notional_usdc: float = 0.0
    min_order_size: float = 0.01
    size_tick: float = 0.01
    allowed_chain_ids: tuple[int, ...] = (137,)

    def __post_init__(self) -> None:
        if not str(self.private_key).strip() or not str(self.funder_address).strip():
            raise ExecutionCredentialsError("Polymarket CLOB REST credentials are required")
        chain_id = int(self.chain_id)
        if chain_id not in self.allowed_chain_ids:
            raise LiveExecutionGuardrailError("Polymarket CLOB chain id is not allowed")
        host = str(self.host).strip().rstrip("/")
        if host != DEFAULT_CLOB_HOST:
            raise LiveExecutionGuardrailError("Polymarket CLOB host is not allowed")
        max_order_notional = float(self.max_order_notional_usdc)
        if not math.isfinite(max_order_notional) or max_order_notional <= 0.0:
            raise LiveExecutionGuardrailError("POLYMARKET_MAX_ORDER_NOTIONAL_USDC must be finite and positive")
        min_order_size = float(self.min_order_size)
        size_tick = float(self.size_tick)
        if not math.isfinite(min_order_size) or min_order_size <= 0.0:
            raise LiveExecutionGuardrailError("min_order_size must be finite and positive")
        if not math.isfinite(size_tick) or size_tick <= 0.0:
            raise LiveExecutionGuardrailError("size_tick must be finite and positive")
        if self.live_enabled is not True:
            raise LiveExecutionGuardrailError("POLYMARKET_LIVE_ENABLED=1 is required")
        if self.live_ack != LIVE_ACK_PHRASE:
            raise LiveExecutionGuardrailError("POLYMARKET_LIVE_ACK confirmation is required")
        object.__setattr__(self, "chain_id", chain_id)
        object.__setattr__(self, "host", host)
        object.__setattr__(self, "max_order_notional_usdc", max_order_notional)
        object.__setattr__(self, "min_order_size", min_order_size)
        object.__setattr__(self, "size_tick", size_tick)


class ClobRestPolymarketExecutor:
    REQUIRED_ENV = (
        "POLYMARKET_PRIVATE_KEY",
        "POLYMARKET_FUNDER_ADDRESS",
        "POLYMARKET_CHAIN_ID",
    )
    OPTIONAL_ENV = (
        "POLYMARKET_CLOB_HOST",
        "POLYMARKET_SIGNATURE_TYPE",
        "POLYMARKET_LIVE_ENABLED",
        "POLYMARKET_LIVE_ACK",
        "POLYMARKET_MAX_ORDER_NOTIONAL_USDC",
    )

    def __init__(
        self,
        *,
        private_key: str | None = None,
        funder_address: str | None = None,
        chain_id: str | int | None = None,
        config: ClobRestExecutorConfig | None = None,
        client: Any | None = None,
        client_factory: Callable[[ClobRestExecutorConfig], Any] | None = None,
    ) -> None:
        if config is None:
            if private_key is None or funder_address is None or chain_id is None:
                raise ExecutionCredentialsError("Polymarket CLOB REST credentials are required")
            config = ClobRestExecutorConfig(
                private_key=str(private_key),
                funder_address=str(funder_address),
                chain_id=int(chain_id),
                live_enabled=True,
                live_ack=LIVE_ACK_PHRASE,
                allow_order_submission=False,
                max_order_notional_usdc=1_000_000_000_000.0,
            )
        self.config = config
        self.funder_address = config.funder_address
        self.chain_id = str(config.chain_id)
        self._client = client
        self._client_factory = client_factory

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        client: Any | None = None,
        client_factory: Callable[[ClobRestExecutorConfig], Any] | None = None,
    ) -> "ClobRestPolymarketExecutor":
        source = os.environ if env is None else env
        if str(source.get("PREDICTION_CORE_DISABLE_LIVE_EXECUTION", "")).strip() == "1":
            raise LiveExecutionGuardrailError("live Polymarket execution is disabled by kill switch")
        missing = [name for name in cls.REQUIRED_ENV if not str(source.get(name, "")).strip()]
        if missing:
            raise ExecutionCredentialsError("Polymarket CLOB REST credentials are required")
        try:
            chain_id = int(str(source["POLYMARKET_CHAIN_ID"]))
            max_order_notional = float(str(source.get("POLYMARKET_MAX_ORDER_NOTIONAL_USDC", "")))
        except (TypeError, ValueError) as exc:
            raise LiveExecutionGuardrailError("Polymarket live numeric environment values are invalid") from exc
        config = ClobRestExecutorConfig(
            private_key=str(source["POLYMARKET_PRIVATE_KEY"]),
            funder_address=str(source["POLYMARKET_FUNDER_ADDRESS"]),
            chain_id=chain_id,
            host=str(source.get("POLYMARKET_CLOB_HOST") or DEFAULT_CLOB_HOST),
            signature_type=_optional_int(source.get("POLYMARKET_SIGNATURE_TYPE")),
            live_enabled=str(source.get("POLYMARKET_LIVE_ENABLED", "")).strip() == "1",
            live_ack=str(source.get("POLYMARKET_LIVE_ACK", "")),
            allow_order_submission=True,
            max_order_notional_usdc=max_order_notional,
        )
        executor = cls(config=config, client=client, client_factory=client_factory)
        if executor._client is None and executor._client_factory is None:
            executor._client = _build_default_clob_client(config)
        return executor

    @property
    def live_submission_available(self) -> bool:
        return self.config.allow_order_submission and (self._client is not None or self._client_factory is not None)

    def submit_order(self, order: OrderRequest) -> OrderResult:
        if not self.config.allow_order_submission:
            raise LiveExecutionGuardrailError("live Polymarket order submission requires explicit permission")
        if order.order_type is not OrderType.LIMIT:
            raise LiveExecutionGuardrailError("live Polymarket execution only supports limit orders")
        if order.side is not OrderSide.BUY:
            raise LiveExecutionGuardrailError("live Polymarket execution only supports buy orders in this release")
        if order.notional_usdc > self.config.max_order_notional_usdc:
            raise LiveExecutionGuardrailError("order exceeds POLYMARKET_MAX_ORDER_NOTIONAL_USDC")
        size = self._order_size(order)
        client = self._resolve_client()
        payload = {
            "token_id": order.token_id,
            "price": order.limit_price,
            "size": size,
            "side": order.side.value.upper(),
            "order_type": order.order_type.value.upper(),
        }
        response = _call_first_available(client, ("submit_order", "place_order", "post_order", "create_order"), payload)
        normalized = _normalize_live_order_response(response)
        return OrderResult(
            accepted=normalized["accepted"],
            status=normalized["status"],
            exchange_order_id=normalized.get("exchange_order_id"),
            idempotency_key=order.idempotency_key,
            raw_response={"live": True, "request": {k: payload[k] for k in ("token_id", "price", "size", "side", "order_type")}, "response": _sanitize_payload(response)},
        )

    def list_open_orders(self) -> list[dict[str, Any]]:
        client = self._resolve_client()
        response = _call_first_available(client, ("list_open_orders", "get_open_orders", "get_orders"))
        if response is None:
            return []
        rows = response.get("orders", response) if isinstance(response, Mapping) else response
        if not isinstance(rows, list):
            raise LiveExecutionUnavailableError("Polymarket CLOB open-order response is not a list")
        return [_sanitize_payload(row) for row in rows if isinstance(row, Mapping)]

    def cancel_order(self, exchange_order_id: str) -> OrderResult:
        raise LiveExecutionUnavailableError("real CLOB REST cancel requires a separate explicit guardrail and is not enabled")

    def _resolve_client(self) -> Any:
        if self._client is None:
            if self._client_factory is None:
                self._client = _build_default_clob_client(self.config)
            else:
                self._client = self._client_factory(self.config)
        return self._client

    def _order_size(self, order: OrderRequest) -> float:
        return _compute_order_size_with_optional_rust(
            notional_usdc=order.notional_usdc,
            limit_price=order.limit_price,
            min_order_size=self.config.min_order_size,
            size_tick=self.config.size_tick,
        )


def _compute_order_size_with_optional_rust(
    *,
    notional_usdc: float,
    limit_price: float,
    min_order_size: float,
    size_tick: float,
) -> float:
    if os.getenv("PREDICTION_CORE_RUST_ORDERBOOK") == "1":
        try:
            backend = importlib.import_module("prediction_core._rust_orderbook")
            return float(
                backend.compute_order_size(
                    notional_usdc=float(notional_usdc),
                    limit_price=float(limit_price),
                    min_order_size=float(min_order_size),
                    size_tick=float(size_tick),
                )
            )
        except (ImportError, AttributeError):
            pass
    return _compute_order_size_python(
        notional_usdc=notional_usdc,
        limit_price=limit_price,
        min_order_size=min_order_size,
        size_tick=size_tick,
    )


def _compute_order_size_python(
    *,
    notional_usdc: float,
    limit_price: float,
    min_order_size: float,
    size_tick: float,
) -> float:
    raw_size = notional_usdc / limit_price
    size = math.floor(raw_size / size_tick) * size_tick
    size = round(size, 8)
    if not math.isfinite(size) or size < min_order_size:
        raise LiveExecutionGuardrailError("computed Polymarket order size is below minimum")
    effective_notional = size * limit_price
    if effective_notional <= 0.0 or effective_notional > notional_usdc:
        raise LiveExecutionGuardrailError("computed Polymarket order notional is invalid")
    if (notional_usdc - effective_notional) / notional_usdc > 0.05:
        raise LiveExecutionGuardrailError("computed Polymarket order size is too far below requested notional")
    return size


def _optional_int(value: Any) -> int | None:
    if value is None or not str(value).strip():
        return None
    return int(str(value))


def _build_default_clob_client(config: ClobRestExecutorConfig) -> Any:
    try:
        from py_clob_client.client import ClobClient
    except ImportError as exc:
        raise LiveExecutionUnavailableError("py-clob-client is required for live Polymarket execution") from exc
    kwargs: dict[str, Any] = {
        "host": config.host,
        "key": config.private_key,
        "chain_id": config.chain_id,
        "funder": config.funder_address,
    }
    if config.signature_type is not None:
        kwargs["signature_type"] = config.signature_type
    client = ClobClient(**kwargs)
    derive = getattr(client, "derive_api_key", None) or getattr(client, "create_or_derive_api_creds", None)
    if callable(derive):
        derive()
    return client


def _call_first_available(client: Any, method_names: tuple[str, ...], payload: dict[str, Any] | None = None) -> Any:
    for method_name in method_names:
        method = getattr(client, method_name, None)
        if callable(method):
            if payload is None:
                return method()
            try:
                return method(payload)
            except TypeError:
                return method(**payload)
    raise LiveExecutionUnavailableError(f"Polymarket CLOB client does not expose any of: {', '.join(method_names)}")


def _normalize_live_order_response(response: Any) -> dict[str, Any]:
    if isinstance(response, Mapping):
        status = str(response.get("status") or response.get("state") or "submitted")
        accepted_raw = response.get("accepted")
        accepted = bool(accepted_raw) if accepted_raw is not None else status.lower() not in {"rejected", "failed", "error"}
        order_id = response.get("id") or response.get("order_id") or response.get("exchange_order_id")
        return {"accepted": accepted, "status": status, "exchange_order_id": str(order_id) if order_id else None}
    order_id = getattr(response, "id", None) or getattr(response, "order_id", None)
    status = str(getattr(response, "status", "submitted"))
    return {"accepted": status.lower() not in {"rejected", "failed", "error"}, "status": status, "exchange_order_id": str(order_id) if order_id else None}


def _sanitize_payload(value: Any) -> Any:
    return redact_mapping(value, replacement="[redacted]")
