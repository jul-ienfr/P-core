from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from prediction_core.polymarket_execution import (
    CompositeExecutionAuditLog,
    CompositeIdempotencyStore,
    DryRunPolymarketExecutor,
    ExecutionRiskLimits,
    ExecutionRiskState,
    JsonlExecutionAuditLog,
    JsonlIdempotencyStore,
    OrderExecutor,
    OrderManagementExecutor,
    PostgresExecutionAuditLog,
    PostgresIdempotencyStore,
)
from prediction_core.polymarket_runtime import (
    ExecutionDisabledError,
    authorize_polymarket_live_execution,
    preflight_polymarket_live_readiness,
    run_polymarket_runtime_cycle,
)


@dataclass(frozen=True, kw_only=True)
class PolymarketDaemonConfig:
    markets: list[dict[str, Any]]
    probabilities: dict[str, float]
    mode: str = "paper"
    once: bool = False
    interval_seconds: float = 60.0
    heartbeat_seconds: float = 300.0
    dry_run_events_jsonl: str | None = None
    max_events: int | None = None
    min_liquidity: float = 0.0
    min_edge: float = 0.0
    max_snapshot_age_seconds: float | None = None
    paper_notional_usdc: float = 5.0
    idempotency_jsonl: str | None = None
    audit_jsonl: str | None = None
    max_order_notional_usdc: float | None = None
    max_total_exposure_usdc: float | None = None
    max_daily_loss_usdc: float | None = None
    max_spread: float | None = None
    total_exposure_usdc: float = 0.0
    daily_realized_pnl_usdc: float = 0.0
    positions_confirmed: bool = False
    postgres_primary_confirmed: bool = False
    operator_ack: str = ""
    max_orders_per_cycle: int = 1
    run_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class PolymarketDaemonResult:
    run_id: str
    mode: str
    status: str
    once: bool
    cycles_completed: int
    heartbeat_seconds: float
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def polymarket_daemon_ops_status() -> dict[str, Any]:
    return {
        "daemon": "configured",
        "risk": "configured",
        "provider": "polymarket_clob_read_path",
        "settlement": "not_configured",
        "notification": "not_configured",
        "analytics": "configured_off_hot_path",
    }


async def run_polymarket_daemon_once(
    config: PolymarketDaemonConfig,
    *,
    repository: Any | None = None,
    order_executor: OrderExecutor | None = None,
    order_management: OrderManagementExecutor | None = None,
) -> PolymarketDaemonResult:
    run_id = config.run_id or f"polymarket-daemon-{uuid4()}"
    if config.mode not in {"paper", "dry_run", "live"}:
        raise ValueError('mode must be "paper", "dry_run", or "live"')
    if repository is not None:
        repository.upsert_run(
            run_id=run_id,
            mode=f"polymarket_daemon_{config.mode}",
            status="running",
            config=asdict(config),
            paper_only=config.mode != "live",
            live_order_allowed=config.mode == "live",
        )
    try:
        result = await _run_cycle(config, repository=repository, order_executor=order_executor, order_management=order_management)
    except ExecutionDisabledError as exc:
        daemon_result = PolymarketDaemonResult(
            run_id=run_id,
            mode=config.mode,
            status="refused",
            once=True,
            cycles_completed=0,
            heartbeat_seconds=config.heartbeat_seconds,
            error=str(exc),
        )
    except Exception as exc:
        if repository is not None:
            repository.complete_run(run_id=run_id, status="failed", summary={"error": str(exc)})
        raise
    else:
        result["ops_status"] = polymarket_daemon_ops_status()
        daemon_result = PolymarketDaemonResult(
            run_id=run_id,
            mode=config.mode,
            status="completed",
            once=True,
            cycles_completed=1,
            heartbeat_seconds=config.heartbeat_seconds,
            result=result,
        )
    if repository is not None:
        repository.complete_run(run_id=run_id, status=daemon_result.status, summary=daemon_result.to_dict())
    return daemon_result


async def run_polymarket_daemon(
    config: PolymarketDaemonConfig,
    *,
    repository: Any | None = None,
    order_executor: OrderExecutor | None = None,
    order_management: OrderManagementExecutor | None = None,
) -> PolymarketDaemonResult:
    if config.once:
        return await run_polymarket_daemon_once(config, repository=repository, order_executor=order_executor, order_management=order_management)
    completed = 0
    last: PolymarketDaemonResult | None = None
    while True:
        last = await run_polymarket_daemon_once(config, repository=repository, order_executor=order_executor, order_management=order_management)
        completed += 1
        await asyncio.sleep(config.interval_seconds)
    return last  # pragma: no cover


def _load_live_submitted_orders(repository: Any | None) -> list[dict[str, Any]]:
    if repository is None:
        return []
    loader = getattr(repository, "list_live_submitted_orders", None)
    if loader is None:
        return []
    orders = loader()
    if not isinstance(orders, list):
        raise ExecutionDisabledError("live daemon requires local order state as a list")
    return orders


async def _run_cycle(
    config: PolymarketDaemonConfig,
    *,
    repository: Any | None = None,
    order_executor: OrderExecutor | None = None,
    order_management: OrderManagementExecutor | None = None,
) -> dict[str, Any]:
    risk_limits = None
    risk_state = None
    idempotency_store = None
    audit_log = None
    live_permit = None
    resolved_executor = order_executor
    if config.mode in {"dry_run", "live"}:
        required_risk_values = [config.max_order_notional_usdc, config.max_total_exposure_usdc, config.max_daily_loss_usdc, config.max_spread]
        if not config.idempotency_jsonl or not config.audit_jsonl or any(value is None for value in required_risk_values):
            raise ExecutionDisabledError("dry_run/live daemon requires JSONL idempotency, audit, and risk limits")
        risk_limits = ExecutionRiskLimits(
            max_order_notional_usdc=config.max_order_notional_usdc,
            max_total_exposure_usdc=config.max_total_exposure_usdc,
            max_daily_loss_usdc=config.max_daily_loss_usdc,
            max_spread=config.max_spread,
        )
        risk_state = ExecutionRiskState(
            total_exposure_usdc=config.total_exposure_usdc,
            daily_realized_pnl_usdc=config.daily_realized_pnl_usdc,
        )
        idempotency_store = JsonlIdempotencyStore(config.idempotency_jsonl)
        audit_log = JsonlExecutionAuditLog(config.audit_jsonl)
        if repository is not None:
            if config.mode == "live" and config.postgres_primary_confirmed:
                idempotency_store = PostgresIdempotencyStore(repository, mode=config.mode, paper_only=False)
                audit_log = PostgresExecutionAuditLog(repository, paper_only=False, live_order_allowed=True)
            elif config.mode == "dry_run":
                idempotency_store = CompositeIdempotencyStore(
                    idempotency_store,
                    PostgresIdempotencyStore(repository, mode=config.mode, paper_only=True),
                )
                audit_log = CompositeExecutionAuditLog(
                    audit_log,
                    PostgresExecutionAuditLog(repository, paper_only=True, live_order_allowed=False),
                )
    if config.mode == "dry_run":
        resolved_executor = resolved_executor or DryRunPolymarketExecutor()
    if config.mode == "live":
        if config.postgres_primary_confirmed is not True:
            raise ExecutionDisabledError("live daemon requires confirmed Postgres primary durability")
        if repository is None:
            raise ExecutionDisabledError("live daemon requires configured Postgres primary durability")
        if resolved_executor is None:
            raise ExecutionDisabledError("live daemon requires an injected live executor")
        local_orders = _load_live_submitted_orders(repository)
        preflight = preflight_polymarket_live_readiness(
            order_management=order_management or resolved_executor,  # type: ignore[arg-type]
            local_orders=local_orders,
            positions_confirmed=config.positions_confirmed,
            postgres_primary_confirmed=config.postgres_primary_confirmed,
            max_orders_per_cycle=config.max_orders_per_cycle,
        )
        live_permit = authorize_polymarket_live_execution(
            preflight=preflight,
            operator_ack=config.operator_ack,
            positions_confirmed=config.positions_confirmed,
            max_orders_per_cycle=config.max_orders_per_cycle,
        )
    return await run_polymarket_runtime_cycle(
        markets=config.markets,
        probabilities=config.probabilities,
        dry_run_events_jsonl=config.dry_run_events_jsonl,
        max_events=config.max_events,
        min_liquidity=config.min_liquidity,
        min_edge=config.min_edge,
        max_snapshot_age_seconds=config.max_snapshot_age_seconds,
        paper_notional_usdc=config.paper_notional_usdc,
        execution_mode=config.mode,
        order_executor=resolved_executor,
        risk_limits=risk_limits,
        risk_state=risk_state,
        idempotency_store=idempotency_store,
        audit_log=audit_log,
        live_permit=live_permit,
        max_orders_per_cycle=config.max_orders_per_cycle,
    )
