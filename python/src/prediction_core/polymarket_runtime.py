from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from prediction_core.polymarket_execution import (
    DryRunPolymarketExecutor,
    ExecutionRiskLimits,
    ExecutionRiskState,
    JsonlExecutionAuditLog,
    JsonlIdempotencyStore,
    OrderExecutor,
    OrderRequest,
    OrderSide,
    OrderType,
    evaluate_execution_risk,
)
from prediction_core.polymarket_marketdata import (
    MarketDataCache,
    dry_run_jsonl_stream_factory,
    run_clob_marketdata_stream,
    select_hot_path_subscriptions,
)


class ExecutionDisabledError(RuntimeError):
    """Raised when a caller attempts to enable real order execution in this scaffold."""


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
) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    summary = {"paper_signal_count": 0, "hold_count": 0, "missing_snapshot_count": 0}

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
            if not snapshot or snapshot.get("best_ask") is None or probability is None:
                summary["missing_snapshot_count"] += 1
                decisions.append(
                    {
                        "market_id": market_id,
                        "question": question,
                        "token_id": token_id,
                        "outcome": outcome,
                        "action": "WAIT_MARKETDATA",
                        "execution_enabled": False,
                    }
                )
                continue

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
) -> dict[str, Any]:
    if execution_enabled and execution_mode == "paper":
        raise ExecutionDisabledError("real Polymarket execution is disabled in this scaffold")
    if execution_mode not in {"paper", "dry_run", "live"}:
        raise ValueError('execution_mode must be "paper", "dry_run", or "live"')
    if execution_mode == "dry_run" and order_executor is None:
        order_executor = DryRunPolymarketExecutor()
    if execution_mode == "live" and order_executor is None:
        raise ExecutionDisabledError("live execution requires an explicit order executor")
    if execution_mode in {"dry_run", "live"} and (risk_limits is None or risk_state is None):
        raise ExecutionDisabledError("live/dry-run execution requires risk limits and risk state")
    if execution_mode in {"dry_run", "live"} and (idempotency_store is None or audit_log is None):
        raise ExecutionDisabledError("live/dry-run execution requires idempotency store and audit log")

    paper_intents = []
    orders_submitted = []
    order_attempts = []
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
            risk = evaluate_execution_risk(order, limits=risk_limits, state=risk_state, market_snapshot=_snapshot_from_decision(decision))
            if not risk.allowed:
                attempt = {"status": "risk_blocked", "idempotency_key": order.idempotency_key, "order": order.to_dict(), "risk": risk.to_dict()}
                order_attempts.append(attempt)
                audit_log.append("execution_order_blocked", attempt)
                continue
            if idempotency_store.seen(order.idempotency_key):
                attempt = {"status": "duplicate_skipped", "idempotency_key": order.idempotency_key, "order": order.to_dict(), "risk": risk.to_dict()}
                order_attempts.append(attempt)
                audit_log.append("execution_order_blocked", attempt)
                continue
            idempotency_store.claim(order.idempotency_key, metadata={"market_id": order.market_id, "token_id": order.token_id})
            try:
                executor_result = order_executor.submit_order(order)  # type: ignore[union-attr]
            except Exception as exc:
                attempt = {"status": "executor_failed", "idempotency_key": order.idempotency_key, "order": order.to_dict(), "error": str(exc)}
                order_attempts.append(attempt)
                audit_log.append("execution_order_failed", attempt)
                raise
            submitted = {"order": order.to_dict(), "executor_result": executor_result.to_dict(), "risk": risk.to_dict()}
            orders_submitted.append(submitted)
            order_attempts.append({"status": executor_result.status, "idempotency_key": order.idempotency_key, **submitted})
            audit_log.append("execution_order_submitted", submitted)
        else:
            paper_intents.append({k: v for k, v in order_dict.items() if k != "idempotency_key"} | {"reason": "execution disabled; paper intent only"})

    return {
        "mode": f"{execution_mode} polymarket execution planner" if execution_mode != "paper" else "paper/read-only disabled execution planner",
        "execution_enabled": execution_mode in {"dry_run", "live"},
        "orders_submitted": orders_submitted,
        "order_attempts": order_attempts,
        "paper_intents": paper_intents,
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
    paper_notional_usdc: float = 5.0,
    execution_mode: str = "paper",
    order_executor: OrderExecutor | None = None,
    risk_limits: ExecutionRiskLimits | None = None,
    risk_state: ExecutionRiskState | None = None,
    idempotency_store: JsonlIdempotencyStore | None = None,
    audit_log: JsonlExecutionAuditLog | None = None,
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
            "invalid_events": 0,
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
    )
    scaffold = build_polymarket_runtime_scaffold()
    return {
        "mode": "paper/read-only polymarket runtime cycle",
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
    return {"spread": decision.get("spread"), "best_bid": decision.get("best_bid"), "best_ask": decision.get("best_ask")}


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
