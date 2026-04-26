from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

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
) -> dict[str, Any]:
    if execution_enabled:
        raise ExecutionDisabledError("real Polymarket execution is disabled in this scaffold")

    paper_intents = []
    for decision in decisions:
        if decision.get("action") != "PAPER_SIGNAL_ONLY":
            continue
        paper_intents.append(
            {
                "market_id": decision.get("market_id"),
                "token_id": decision.get("token_id"),
                "outcome": decision.get("outcome"),
                "side": "BUY",
                "limit_price": decision.get("best_ask"),
                "notional_usdc": float(notional_usdc),
                "reason": "execution disabled; paper intent only",
            }
        )

    return {
        "mode": "paper/read-only disabled execution planner",
        "execution_enabled": False,
        "orders_submitted": [],
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
    execution = plan_disabled_execution_actions(decisions["decisions"], notional_usdc=paper_notional_usdc)
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
