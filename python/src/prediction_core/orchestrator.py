from __future__ import annotations

import json
from typing import Any

from prediction_core.client import PredictionCoreClient


_VALID_SOURCES = {"fixture", "live"}
_VALID_DECISION_STATUSES = ("skip", "watchlist", "trade_small", "trade")


def run_weather_workflow(
    *,
    base_url: str,
    question: str,
    yes_price: float,
    run_id: str | None = None,
    market_id: str | None = None,
    source: str = "fixture",
    resolution_source: str | None = None,
    description: str | None = None,
    rules: str | None = None,
    requested_quantity: float | None = None,
    bankroll_usd: float | None = None,
    filled_quantity: float | None = None,
    fill_price: float | None = None,
    reference_price: float | None = None,
    fee_paid: float | None = None,
    position_side: str | None = None,
    execution_side: str | None = None,
    best_bid: float | None = None,
    best_ask: float | None = None,
    volume: float | None = None,
    volume_usd: float | None = None,
    hours_to_resolution: float | None = None,
    target_order_size_usd: float | None = None,
    taker_fee_bps: float | None = None,
    transaction_fee_bps: float | None = None,
    deposit_fee_usd: float | None = None,
    withdrawal_fee_usd: float | None = None,
    bids: list[dict[str, Any]] | None = None,
    asks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the existing server endpoints as one thin weather workflow.

    The workflow always checks health, parses the question, and scores the market.
    If both run_id and market_id are supplied, it also runs the paper trading cycle.
    """

    normalized_question = question.strip()
    if not normalized_question:
        raise ValueError("question is required")

    try:
        normalized_yes_price = float(yes_price)
    except (TypeError, ValueError) as exc:
        raise ValueError("yes_price must be numeric") from exc

    if source not in _VALID_SOURCES:
        raise ValueError("source must be 'fixture' or 'live'")

    if (run_id is None) != (market_id is None):
        raise ValueError("run_id and market_id must be provided together to enable paper_cycle")

    workflow_payload = _compact_dict(
        {
            "question": normalized_question,
            "yes_price": normalized_yes_price,
            "source": source,
            "resolution_source": resolution_source,
            "description": description,
            "rules": rules,
            "requested_quantity": requested_quantity,
            "bankroll_usd": bankroll_usd,
            "filled_quantity": filled_quantity,
            "fill_price": fill_price,
            "reference_price": reference_price,
            "fee_paid": fee_paid,
            "position_side": position_side,
            "execution_side": execution_side,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "volume": volume,
            "volume_usd": volume_usd,
            "hours_to_resolution": hours_to_resolution,
            "target_order_size_usd": target_order_size_usd,
            "taker_fee_bps": taker_fee_bps,
            "transaction_fee_bps": transaction_fee_bps,
            "deposit_fee_usd": deposit_fee_usd,
            "withdrawal_fee_usd": withdrawal_fee_usd,
            "bids": bids,
            "asks": asks,
        }
    )

    result = {
        "health": _request_json(base_url, "/health", method="GET"),
        "parse_market": _request_json(
            base_url,
            "/weather/parse-market",
            method="POST",
            payload={"question": normalized_question},
        ),
        "score_market": _request_json(
            base_url,
            "/weather/score-market",
            method="POST",
            payload=workflow_payload,
        ),
    }

    if run_id is not None and market_id is not None:
        result["paper_cycle"] = _request_json(
            base_url,
            "/weather/paper-cycle",
            method="POST",
            payload={
                "run_id": run_id,
                "market_id": market_id,
                **workflow_payload,
            },
        )

    return result


def consume_weather_markets(
    *,
    base_url: str,
    source: str = "fixture",
    limit: int = 20,
    min_status: str = "watchlist",
) -> dict[str, Any]:
    if source not in _VALID_SOURCES:
        raise ValueError("source must be 'fixture' or 'live'")
    if min_status not in _VALID_DECISION_STATUSES:
        supported = ", ".join(_VALID_DECISION_STATUSES)
        raise ValueError(f"min_status must be one of: {supported}")
    if limit < 1:
        raise ValueError("limit must be >= 1")

    client = PredictionCoreClient(base_url)
    health = client.health()
    markets = client.fetch_markets(source=source, limit=limit)

    selected_markets: list[dict[str, Any]] = []
    filtered_out = 0
    minimum_rank = _VALID_DECISION_STATUSES.index(min_status)
    for market in markets:
        market_id = market.get("id")
        if not isinstance(market_id, str) or not market_id.strip():
            filtered_out += 1
            continue
        score_bundle = client.score_market(market_id=market_id, source=source)
        decision = score_bundle.get("decision")
        decision_status = decision.get("status") if isinstance(decision, dict) else None
        if decision_status not in _VALID_DECISION_STATUSES:
            filtered_out += 1
            continue
        if _VALID_DECISION_STATUSES.index(decision_status) < minimum_rank:
            filtered_out += 1
            continue
        if source == "live" and _should_filter_live_candidate(market=market, score_bundle=score_bundle):
            filtered_out += 1
            continue
        selected_markets.append(
            {
                "market_id": market_id,
                "question": market.get("question"),
                "yes_price": market.get("yes_price"),
                "decision": decision,
                "model": _extract_model_payload(score_bundle),
                "edge": _extract_edge_payload(market=market, score_bundle=score_bundle),
                "score": score_bundle.get("score"),
                "market": score_bundle.get("market"),
                "resolution": score_bundle.get("resolution"),
                "execution": score_bundle.get("execution"),
                "execution_costs": score_bundle.get("execution_costs"),
            }
        )

    selected_markets.sort(
        key=lambda item: (
            float(item.get("score", {}).get("total_score", 0.0)) if isinstance(item.get("score"), dict) else 0.0,
            float(item.get("score", {}).get("raw_edge", 0.0)) if isinstance(item.get("score"), dict) else 0.0,
        ),
        reverse=True,
    )

    return {
        "health": health,
        "summary": {
            "source": source,
            "fetched": len(markets),
            "selected": len(selected_markets),
            "filtered_out": filtered_out,
            "min_status": min_status,
        },
        "markets": selected_markets,
    }


def _extract_model_payload(score_bundle: dict[str, Any]) -> dict[str, Any] | None:
    model = score_bundle.get("model")
    return model if isinstance(model, dict) else None



def _extract_edge_payload(*, market: dict[str, Any], score_bundle: dict[str, Any]) -> dict[str, Any] | None:
    edge = score_bundle.get("edge")
    if isinstance(edge, dict):
        return edge

    yes_price = market.get("yes_price")
    score = score_bundle.get("score")
    model = _extract_model_payload(score_bundle)
    raw_edge = score.get("raw_edge") if isinstance(score, dict) else None
    probability_yes = model.get("probability_yes") if isinstance(model, dict) else None

    payload: dict[str, Any] = {}
    if isinstance(yes_price, (int, float)):
        payload["market_implied_yes_probability"] = round(float(yes_price), 2)
    if isinstance(raw_edge, (int, float)):
        payload["probability_edge"] = round(float(raw_edge), 2)
    if isinstance(probability_yes, (int, float)):
        payload["theoretical_yes_price"] = round(float(probability_yes), 2)
    return payload or None



def _should_filter_live_candidate(*, market: dict[str, Any], score_bundle: dict[str, Any]) -> bool:
    yes_price = market.get("yes_price")
    if isinstance(yes_price, (int, float)) and (float(yes_price) <= 0.01 or float(yes_price) >= 0.99):
        return True

    execution = score_bundle.get("execution")
    if isinstance(execution, dict):
        fillable_size = execution.get("fillable_size_usd")
        if isinstance(fillable_size, (int, float)) and float(fillable_size) < 25.0:
            return True
        slippage_risk = execution.get("slippage_risk")
        if slippage_risk == "high":
            return True
        spread = execution.get("spread")
        if isinstance(spread, (int, float)) and float(spread) >= 0.07:
            return True

    return False


def _request_json(base_url: str, path: str, *, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    client = PredictionCoreClient(base_url)
    try:
        return client._request_json(method, path, payload)
    except Exception as exc:
        raise ValueError(str(exc)) from exc


def _compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
