from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from prediction_core.storage.config import redact_mapping

from prediction_core.polymarket_execution import (
    ClobRestPolymarketExecutor,
    DryRunPolymarketExecutor,
    ExecutionRiskLimits,
    ExecutionRiskState,
    JsonlExecutionAuditLog,
    JsonlIdempotencyStore,
    OrderExecutor,
    OrderManagementExecutor,
    OrderRequest,
    reconcile_orders,
    OrderSide,
    OrderType,
    evaluate_execution_risk,
)


def preflight_polymarket_live_readiness(
    env: dict[str, str] | None = None,
    *,
    order_management: OrderManagementExecutor | None = None,
    local_orders: list[dict[str, Any]] | None = None,
    positions_confirmed: bool = False,
    live_submission_wired: bool | None = None,
) -> dict[str, Any]:
    """Check live CLOB environment without constructing a live executor or submitting/canceling orders."""
    source = env if env is not None else __import__("os").environ
    required = list(ClobRestPolymarketExecutor.REQUIRED_ENV)
    missing = [name for name in required if not str(source.get(name, "")).strip()]
    configured = [name for name in required if name not in missing]
    credentials_ready = not missing
    live_ack_ready = str(source.get("POLYMARKET_LIVE_ACK", "")) == "I_UNDERSTAND_THIS_SUBMITS_REAL_POLYMARKET_ORDERS"
    live_enabled = str(source.get("POLYMARKET_LIVE_ENABLED", "")).strip() == "1"
    kill_switch_active = str(source.get("PREDICTION_CORE_DISABLE_LIVE_EXECUTION", "")).strip() == "1"
    if live_submission_wired is None:
        live_submission_wired = bool(getattr(order_management, "live_submission_available", False))
    execution_available = bool(live_submission_wired and live_enabled and live_ack_ready and not kill_switch_active)
    exchange_orders: list[dict[str, Any]] | None = None
    reconciliation: dict[str, Any] | None = None
    open_orders_confirmed = False
    open_orders_error: dict[str, str] | None = None
    if order_management is not None:
        try:
            exchange_orders = order_management.list_open_orders()
        except Exception as exc:
            exchange_orders = None
            open_orders_error = _sanitize_preflight_error(exc, source)
        else:
            reconciliation = reconcile_orders(local_orders=local_orders or [], exchange_orders=exchange_orders)
            open_orders_confirmed = reconciliation["status"] == "ok" and not reconciliation["open_order_ids"]
    readiness_blockers = []
    if not credentials_ready:
        readiness_blockers.append("missing_clob_credentials")
    if not live_enabled:
        readiness_blockers.append("live_not_enabled")
    if not live_ack_ready:
        readiness_blockers.append("live_ack_not_confirmed")
    if kill_switch_active:
        readiness_blockers.append("live_kill_switch_active")
    if not live_submission_wired:
        readiness_blockers.append("live_submission_unavailable")
    if order_management is None:
        readiness_blockers.append("open_orders_not_confirmed")
    elif open_orders_error is not None:
        readiness_blockers.append("open_orders_check_failed")
    elif not open_orders_confirmed:
        readiness_blockers.append("open_orders_or_reconciliation_not_clear")
    if not positions_confirmed:
        readiness_blockers.append("positions_not_confirmed")
    ready = credentials_ready and live_submission_wired and execution_available and open_orders_confirmed and positions_confirmed
    return {
        "mode": "polymarket live read-only preflight",
        "ready": ready,
        "not_ready": not ready,
        "credentials_ready": credentials_ready,
        "live_submission_wired": live_submission_wired,
        "execution_available": execution_available,
        "open_orders_confirmed": open_orders_confirmed,
        "positions_confirmed": positions_confirmed,
        "readiness_blockers": readiness_blockers,
        "checks": {
            "clob_env": {
                "ready": credentials_ready,
                "required": required,
                "configured": configured,
                "missing": missing,
            },
            "live_submission_wired": live_submission_wired,
            "execution_available": execution_available,
            "live_enabled": live_enabled,
            "live_ack_ready": live_ack_ready,
            "kill_switch_active": kill_switch_active,
            "executor_constructed": order_management is not None,
            "orders_submitted": 0,
            "cancel_submitted": False,
            "open_orders": {
                "source_injected": order_management is not None,
                "confirmed": open_orders_confirmed,
                "count": len(exchange_orders or []),
                "error": open_orders_error,
            },
            "positions_confirmed": positions_confirmed,
            "reconciliation": reconciliation,
        },
    }

from prediction_core.polymarket_marketdata import (
    MarketDataCache,
    dry_run_jsonl_stream_factory,
    run_clob_marketdata_stream,
    select_hot_path_subscriptions,
)


class ExecutionDisabledError(RuntimeError):
    """Raised when a caller attempts to enable real order execution in this scaffold."""


@dataclass(frozen=True, kw_only=True)
class LiveExecutionPermit:
    preflight_ready: bool
    operator_ack: str
    positions_confirmed: bool
    max_orders_per_cycle: int = 1

    def __post_init__(self) -> None:
        if self.preflight_ready is not True:
            raise ExecutionDisabledError("live execution requires a ready preflight")
        if self.operator_ack != "I_UNDERSTAND_THIS_SUBMITS_REAL_POLYMARKET_ORDERS":
            raise ExecutionDisabledError("live execution requires operator acknowledgement")
        if self.positions_confirmed is not True:
            raise ExecutionDisabledError("live execution requires confirmed positions")
        if int(self.max_orders_per_cycle) != 1:
            raise ExecutionDisabledError("live execution is limited to one order per cycle")


def build_polymarket_runtime_scaffold() -> dict[str, Any]:
    return {
        "mode": "paper/read-only polymarket runtime scaffold",
        "execution_enabled": False,
        "guardrails": {
            "no_real_orders": True,
            "paper_intents_only": True,
            "live_marketdata_allowed": True,
            "execution_requires_future_explicit_auth": True,
        },
        "workers": {
            "discovery_worker": {
                "api": "Gamma API",
                "status": "configured",
                "hot_path": False,
                "role": "discover active markets, rules, outcomes, and clobTokenIds outside the trading hot path",
            },
            "marketdata_worker": {
                "api": "CLOB WebSocket",
                "status": "configured",
                "hot_path": True,
                "role": "stream orderbook events into an in-memory cache keyed by CLOB token id",
            },
            "decision_worker": {
                "api": "local cache",
                "status": "configured",
                "hot_path": True,
                "role": "compare model probabilities with cached best ask/bid and emit paper signals",
            },
            "execution_worker": {
                "api": "CLOB REST",
                "status": "disabled",
                "hot_path": True,
                "role": "future authenticated order placement/cancel path; currently records paper intents only",
            },
            "analytics_worker": {
                "api": "Data API",
                "status": "configured",
                "hot_path": False,
                "role": "post-cycle audit, trades/wallet analytics, and reporting outside the hot path",
            },
        },
    }


def evaluate_cached_market_decisions(
    *,
    markets: list[dict[str, Any]],
    snapshots: dict[str, dict[str, Any]],
    probabilities: dict[str, float],
    min_edge: float = 0.0,
    max_snapshot_age_seconds: float | None = None,
) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    summary = {"paper_signal_count": 0, "hold_count": 0, "missing_snapshot_count": 0, "invalid_snapshot_count": 0, "stale_snapshot_count": 0}

    for market in markets:
        if market.get("closed") is True:
            continue
        market_id = str(market.get("id") or market.get("market_id") or "").strip()
        if not market_id:
            continue
        token_ids = _coerce_list(market.get("clobTokenIds") or market.get("clob_token_ids"))
        outcomes = _coerce_list(market.get("outcomes")) or [f"outcome_{index}" for index in range(len(token_ids))]
        question = market.get("question") or market.get("title") or ""

        for index, token_id in enumerate(token_ids):
            outcome = str(outcomes[index]) if index < len(outcomes) else f"outcome_{index}"
            snapshot = snapshots.get(token_id)
            probability = _coerce_probability(probabilities.get(token_id))
            wait_reason = _marketdata_wait_reason(snapshot, probability=probability, max_snapshot_age_seconds=max_snapshot_age_seconds)
            if wait_reason is not None:
                if wait_reason == "missing_snapshot":
                    summary["missing_snapshot_count"] += 1
                elif wait_reason == "stale_snapshot":
                    summary["stale_snapshot_count"] += 1
                else:
                    summary["invalid_snapshot_count"] += 1
                decisions.append(
                    {
                        "market_id": market_id,
                        "question": question,
                        "token_id": token_id,
                        "outcome": outcome,
                        "action": "WAIT_MARKETDATA",
                        "execution_enabled": False,
                        "wait_reason": wait_reason,
                    }
                )
                continue

            assert snapshot is not None
            best_ask = float(snapshot["best_ask"])
            best_bid = snapshot.get("best_bid")
            edge = round(probability - best_ask, 10)
            action = "PAPER_SIGNAL_ONLY" if edge >= min_edge else "HOLD"
            if action == "PAPER_SIGNAL_ONLY":
                summary["paper_signal_count"] += 1
            else:
                summary["hold_count"] += 1
            decisions.append(
                {
                    "market_id": market_id,
                    "question": question,
                    "token_id": token_id,
                    "outcome": outcome,
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "spread": snapshot.get("spread"),
                    "bid_depth": snapshot.get("bid_depth"),
                    "ask_depth": snapshot.get("ask_depth"),
                    "sequence": snapshot.get("sequence"),
                    "received_at": snapshot.get("received_at"),
                    "source": snapshot.get("source"),
                    "model_probability": probability,
                    "edge_vs_ask": edge,
                    "action": action,
                    "execution_enabled": False,
                }
            )

    return {
        "mode": "paper/read-only local decision scaffold",
        "execution_enabled": False,
        "min_edge": min_edge,
        "summary": summary,
        "decisions": decisions,
    }


def plan_disabled_execution_actions(
    decisions: list[dict[str, Any]],
    *,
    notional_usdc: float = 5.0,
    execution_enabled: bool = False,
    execution_mode: str = "paper",
    order_executor: OrderExecutor | None = None,
    risk_limits: ExecutionRiskLimits | None = None,
    risk_state: ExecutionRiskState | None = None,
    idempotency_store: JsonlIdempotencyStore | None = None,
    audit_log: JsonlExecutionAuditLog | None = None,
    live_permit: LiveExecutionPermit | None = None,
    max_orders_per_cycle: int | None = None,
) -> dict[str, Any]:
    if execution_enabled and execution_mode == "paper":
        raise ExecutionDisabledError("real Polymarket execution is disabled in this scaffold")
    if execution_mode not in {"paper", "dry_run", "live"}:
        raise ValueError('execution_mode must be "paper", "dry_run", or "live"')
    if execution_mode == "dry_run":
        if order_executor is None:
            order_executor = DryRunPolymarketExecutor()
        elif type(order_executor) is not DryRunPolymarketExecutor:
            raise ExecutionDisabledError("dry-run Polymarket execution only accepts the built-in DryRunPolymarketExecutor")
    if execution_mode == "live":
        if order_executor is None:
            raise ExecutionDisabledError("live Polymarket execution requires an explicit executor")
        if live_permit is None:
            raise ExecutionDisabledError("live Polymarket execution requires a ready preflight permit")
        if max_orders_per_cycle is None:
            max_orders_per_cycle = live_permit.max_orders_per_cycle
        if int(max_orders_per_cycle) != 1:
            raise ExecutionDisabledError("live execution is limited to one order per cycle")
    if execution_mode in {"dry_run", "live"} and (risk_limits is None or risk_state is None):
        raise ExecutionDisabledError("live/dry-run execution requires risk limits and risk state")
    if execution_mode in {"dry_run", "live"} and (idempotency_store is None or audit_log is None):
        raise ExecutionDisabledError("live/dry-run execution requires idempotency store and audit log")

    paper_intents = []
    orders_submitted = []
    order_attempts = []
    summary = {
        "risk_blocked_count": 0,
        "duplicate_skipped_count": 0,
        "executor_failed_count": 0,
        "not_accepted_count": 0,
        "rejected_count": 0,
        "submitted_count": 0,
        "pending_count": 0,
        "reserved_exposure_usdc": 0.0,
    }
    reserved_exposure_usdc = 0.0
    for decision in decisions:
        if decision.get("action") != "PAPER_SIGNAL_ONLY":
            continue
        order_dict = _build_order_dict(decision, notional_usdc=notional_usdc)
        if execution_mode in {"dry_run", "live"}:
            order = OrderRequest(
                market_id=str(order_dict["market_id"]),
                token_id=str(order_dict["token_id"]),
                outcome=str(order_dict["outcome"]),
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                limit_price=float(order_dict["limit_price"]),
                notional_usdc=float(order_dict["notional_usdc"]),
                idempotency_key=str(order_dict["idempotency_key"]),
                metadata={"source": "polymarket_runtime", "decision": decision},
            )
            assert risk_limits is not None
            assert risk_state is not None
            assert idempotency_store is not None
            assert audit_log is not None
            audit_log.append("execution_decision_seen", {"decision": decision, "order": order.to_dict()})
            effective_risk_state = ExecutionRiskState(
                total_exposure_usdc=risk_state.total_exposure_usdc + reserved_exposure_usdc,
                daily_realized_pnl_usdc=risk_state.daily_realized_pnl_usdc,
            )
            risk = evaluate_execution_risk(order, limits=risk_limits, state=effective_risk_state, market_snapshot=_snapshot_from_decision(decision))
            if not risk.allowed:
                attempt = {"status": "risk_blocked", "idempotency_key": order.idempotency_key, "order": order.to_dict(), "risk": risk.to_dict()}
                order_attempts.append(attempt)
                summary["risk_blocked_count"] += 1
                audit_log.append("execution_order_blocked", attempt)
                continue
            claimed = idempotency_store.claim(
                order.idempotency_key,
                metadata={"market_id": order.market_id, "token_id": order.token_id, "mode": execution_mode},
                status="pending",
            )
            if not claimed:
                attempt = {"status": "duplicate_skipped", "idempotency_key": order.idempotency_key, "order": order.to_dict(), "risk": risk.to_dict()}
                order_attempts.append(attempt)
                summary["duplicate_skipped_count"] += 1
                audit_log.append("execution_order_blocked", attempt)
                continue
            if execution_mode == "live" and summary["submitted_count"] >= int(max_orders_per_cycle or 1):
                attempt = {"status": "max_orders_per_cycle_blocked", "idempotency_key": order.idempotency_key, "order": order.to_dict(), "risk": risk.to_dict()}
                order_attempts.append(attempt)
                summary["rejected_count"] += 1
                idempotency_store.mark_rejected(order.idempotency_key, metadata={"market_id": order.market_id, "token_id": order.token_id, "status": "max_orders_per_cycle_blocked", "mode": execution_mode})
                audit_log.append("execution_order_blocked", attempt)
                continue
            summary["pending_count"] += 1
            try:
                executor_result = order_executor.submit_order(order)  # type: ignore[union-attr]
            except Exception as exc:
                attempt_status = "execution_order_unknown" if execution_mode == "live" else "executor_failed"
                attempt = {"status": attempt_status, "idempotency_key": order.idempotency_key, "order": order.to_dict(), "error": redact_mapping({"error": str(exc)})["error"]}
                order_attempts.append(attempt)
                summary["executor_failed_count"] += 1
                audit_log.append("execution_order_failed", attempt)
                raise
            submitted = {"order": order.to_dict(), "executor_result": executor_result.to_dict(), "risk": risk.to_dict()}
            if executor_result.accepted:
                idempotency_store.mark_submitted(
                    order.idempotency_key,
                    metadata={"market_id": order.market_id, "token_id": order.token_id, "status": executor_result.status, "mode": execution_mode},
                )
                reserved_exposure_usdc += order.notional_usdc
                summary["submitted_count"] += 1
                summary["pending_count"] -= 1
                summary["reserved_exposure_usdc"] = reserved_exposure_usdc
                orders_submitted.append(submitted)
                order_attempts.append({"status": executor_result.status, "idempotency_key": order.idempotency_key, **submitted})
                audit_log.append("execution_order_submitted", submitted)
            else:
                idempotency_store.mark_rejected(
                    order.idempotency_key,
                    metadata={"market_id": order.market_id, "token_id": order.token_id, "status": executor_result.status, "mode": execution_mode, "accepted": False},
                )
                summary["pending_count"] -= 1
                summary["not_accepted_count"] += 1
                summary["rejected_count"] += 1
                order_attempts.append({"status": "not_accepted", "idempotency_key": order.idempotency_key, **submitted})
                audit_log.append("execution_order_rejected", submitted)
        else:
            paper_intents.append({k: v for k, v in order_dict.items() if k != "idempotency_key"} | {"reason": "execution disabled; paper intent only"})

    return {
        "mode": f"{execution_mode} polymarket execution planner",
        "execution_enabled": execution_mode in {"dry_run", "live"},
        "paper_only": execution_mode != "live",
        "live_order_allowed": execution_mode == "live" and live_permit is not None,
        "orders_submitted": orders_submitted,
        "order_attempts": order_attempts,
        "paper_intents": paper_intents,
        "summary": summary,
    }


async def run_polymarket_runtime_cycle(
    *,
    markets: list[dict[str, Any]],
    probabilities: dict[str, float],
    stream_factory: Callable[[str, dict[str, Any]], AsyncIterator[dict[str, Any]]] | None = None,
    dry_run_events_jsonl: str | None = None,
    max_events: int | None = None,
    min_liquidity: float = 0.0,
    min_edge: float = 0.0,
    max_snapshot_age_seconds: float | None = None,
    paper_notional_usdc: float = 5.0,
    execution_mode: str = "paper",
    order_executor: OrderExecutor | None = None,
    risk_limits: ExecutionRiskLimits | None = None,
    risk_state: ExecutionRiskState | None = None,
    idempotency_store: JsonlIdempotencyStore | None = None,
    audit_log: JsonlExecutionAuditLog | None = None,
    live_permit: LiveExecutionPermit | None = None,
    max_orders_per_cycle: int | None = None,
) -> dict[str, Any]:
    subscriptions = select_hot_path_subscriptions(markets, min_liquidity=min_liquidity)
    token_ids = [subscription["token_id"] for subscription in subscriptions]
    if not token_ids:
        marketdata = {
            "mode": "paper/read-only clob websocket stream",
            "dry_run": dry_run_events_jsonl is not None,
            "received_events": 0,
            "processed_events": 0,
            "ignored_events": 0,
            "unsubscribed_events": 0,
            "invalid_events": 0,
            "invalid_json_events": 0,
            "sequence_rejected_events": 0,
            "stale_events": 0,
            "idle_timeouts": 0,
            "stream_errors": 0,
            "reconnects": 0,
            "errors": [],
            "snapshots": {},
        }
    else:
        cache = MarketDataCache()
        resolved_stream_factory = stream_factory
        dry_run = dry_run_events_jsonl is not None
        if resolved_stream_factory is None:
            if dry_run_events_jsonl is None:
                raise ValueError("stream_factory or dry_run_events_jsonl is required")
            resolved_stream_factory = _dry_run_factory(dry_run_events_jsonl)
        marketdata = await run_clob_marketdata_stream(
            token_ids=token_ids,
            stream_factory=resolved_stream_factory,
            cache=cache,
            max_events=max_events,
            dry_run=dry_run,
        )

    decisions = evaluate_cached_market_decisions(
        markets=markets,
        snapshots=marketdata["snapshots"],
        probabilities=probabilities,
        min_edge=min_edge,
        max_snapshot_age_seconds=max_snapshot_age_seconds,
    )
    execution = plan_disabled_execution_actions(
        decisions["decisions"],
        notional_usdc=paper_notional_usdc,
        execution_mode=execution_mode,
        order_executor=order_executor,
        risk_limits=risk_limits,
        risk_state=risk_state,
        idempotency_store=idempotency_store,
        audit_log=audit_log,
        live_permit=live_permit,
        max_orders_per_cycle=max_orders_per_cycle,
    )
    scaffold = build_polymarket_runtime_scaffold()
    return {
        "mode": f"{execution_mode} polymarket runtime cycle",
        "paper_only": execution_mode != "live",
        "live_order_allowed": execution_mode == "live" and live_permit is not None,
        "guardrails": scaffold["guardrails"],
        "subscriptions": subscriptions,
        "marketdata": marketdata,
        "decisions": decisions,
        "execution": execution,
        "analytics": {
            "mode": "paper/read-only analytics placeholder",
            "status": "configured",
            "note": "Data API analytics stays off hot path and is not called by this local cycle",
        },
    }


def _sanitize_preflight_error(exc: Exception, source: dict[str, str] | Any) -> dict[str, str]:
    message = str(redact_mapping({"error": str(exc)})["error"])
    for key, value in getattr(source, "items", lambda: [])():
        if not any(secret in str(key).upper() for secret in ("PASSWORD", "SECRET", "ACCESS_KEY", "PRIVATE_KEY", "FUNDER", "API_KEY", "CREDENTIAL", "AUTH", "TOKEN")):
            continue
        secret = str(value or "")
        if secret and len(secret) >= 4:
            message = message.replace(secret, "[redacted]")
    return {"type": exc.__class__.__name__, "message": message[:500]}


def _marketdata_wait_reason(snapshot: dict[str, Any] | None, *, probability: float | None, max_snapshot_age_seconds: float | None) -> str | None:
    if not snapshot:
        return "missing_snapshot"
    if probability is None:
        return "missing_probability"
    if snapshot.get("best_ask") is None:
        return "missing_best_ask"
    if snapshot.get("best_bid") is None:
        return "missing_best_bid"
    if snapshot.get("valid") is False:
        return str(snapshot.get("invalid_reason") or "invalid_snapshot")
    if max_snapshot_age_seconds is not None:
        age = _snapshot_age_seconds(snapshot.get("received_at"))
        if age is None or age > max_snapshot_age_seconds:
            return "stale_snapshot"
    return None


def _snapshot_age_seconds(received_at: Any) -> float | None:
    if not isinstance(received_at, str) or not received_at.strip():
        return None
    normalized = received_at.strip().replace("Z", "+00:00")
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()


def _dry_run_factory(path: str) -> Callable[[str, dict[str, Any]], AsyncIterator[dict[str, Any]]]:
    async def factory(url: str, subscribe_message: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        async for event in dry_run_jsonl_stream_factory(url, subscribe_message, path=path):
            yield event

    return factory


def _build_order_dict(decision: dict[str, Any], *, notional_usdc: float) -> dict[str, Any]:
    market_id = decision.get("market_id")
    token_id = decision.get("token_id")
    limit_price = float(decision.get("best_ask"))
    notional = float(notional_usdc)
    if notional <= 0.0 or notional != notional or notional in (float("inf"), float("-inf")):
        raise ValueError("notional_usdc must be finite and positive")
    return {
        "market_id": market_id,
        "token_id": token_id,
        "outcome": decision.get("outcome"),
        "side": "BUY",
        "limit_price": limit_price,
        "notional_usdc": notional,
        "idempotency_key": f"{market_id}:{token_id}:BUY:{limit_price}:{notional}",
    }


def _snapshot_from_decision(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "spread": decision.get("spread"),
        "best_bid": decision.get("best_bid"),
        "best_ask": decision.get("best_ask"),
        "bid_depth": decision.get("bid_depth"),
        "ask_depth": decision.get("ask_depth"),
        "sequence": decision.get("sequence"),
        "received_at": decision.get("received_at"),
        "source": decision.get("source"),
    }


def _coerce_list(value: Any) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            import json

            try:
                value = json.loads(stripped)
            except json.JSONDecodeError:
                return []
        elif stripped:
            value = [stripped]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _coerce_probability(value: Any) -> float | None:
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None
    if probability < 0 or probability > 1:
        return None
    return probability
