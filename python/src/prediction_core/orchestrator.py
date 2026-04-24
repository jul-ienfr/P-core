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


def run_weather_paper_batch(
    *,
    base_url: str,
    source: str = "fixture",
    limit: int = 20,
    min_status: str = "trade_small",
    run_id_prefix: str = "weather-paper",
    bankroll_usd: float | None = None,
    requested_quantity: float | None = None,
) -> dict[str, Any]:
    """Fetch markets, score/filter candidates, then run paper-cycle for each selected candidate."""

    candidate_payload = consume_weather_markets(
        base_url=base_url,
        source=source,
        limit=limit,
        min_status=min_status,
    )
    client = PredictionCoreClient(base_url)
    paper_cycles: list[dict[str, Any]] = []
    for candidate in candidate_payload["markets"]:
        market_id = str(candidate["market_id"])
        question = str(candidate.get("question") or "")
        yes_price = candidate.get("yes_price")
        if not question or not isinstance(yes_price, (int, float)):
            continue

        score_bundle = {
            key: value
            for key, value in candidate.items()
            if key in {"decision", "model", "edge", "score", "market", "resolution", "execution", "execution_costs"}
        }
        paper_payload = _compact_dict(
            {
                "question": question,
                "yes_price": float(yes_price),
                "source": source,
                "bankroll_usd": bankroll_usd,
                "requested_quantity": requested_quantity,
            }
        )
        for market_key, payload_key in (
            ("best_bid", "best_bid"),
            ("best_ask", "best_ask"),
            ("hours_to_resolution", "hours_to_resolution"),
            ("volume_usd", "volume"),
        ):
            value = candidate.get(market_key)
            if isinstance(value, (int, float)):
                paper_payload[payload_key] = float(value)

        execution_info = score_bundle.get("execution")
        if isinstance(execution_info, dict):
            for source_key, target_key in (
                ("best_bid", "best_bid"),
                ("best_ask", "best_ask"),
                ("hours_to_resolution", "hours_to_resolution"),
                ("volume_usd", "volume"),
                ("transaction_fee_bps", "transaction_fee_bps"),
                ("deposit_fee_usd", "deposit_fee_usd"),
                ("withdrawal_fee_usd", "withdrawal_fee_usd"),
            ):
                value = execution_info.get(source_key)
                if isinstance(value, (int, float)):
                    paper_payload[target_key] = float(value)

        simulation_bundle = client.paper_cycle(
            run_id=f"{run_id_prefix}-{market_id}",
            market_id=market_id,
            **paper_payload,
        )
        paper_cycles.append(
            {
                "run_id": f"{run_id_prefix}-{market_id}",
                "market_id": market_id,
                "question": question,
                "decision": candidate.get("decision"),
                "simulation": simulation_bundle.get("simulation"),
                "postmortem": simulation_bundle.get("postmortem"),
                "score_bundle": simulation_bundle.get("score_bundle"),
            }
        )

    result = dict(candidate_payload)
    result["paper_cycles"] = paper_cycles
    result["summary"] = dict(candidate_payload["summary"])
    result["summary"]["paper_cycles"] = len(paper_cycles)
    return result



def consume_weather_markets(
    *,
    base_url: str,
    source: str = "fixture",
    limit: int = 20,
    min_status: str = "watchlist",
    explain_filtered: bool = False,
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
    filtered_markets: list[dict[str, Any]] = []
    filtered_out = 0
    minimum_rank = _VALID_DECISION_STATUSES.index(min_status)
    for market in markets:
        market_id = market.get("id")
        if not isinstance(market_id, str) or not market_id.strip():
            filtered_out += 1
            if explain_filtered:
                filtered_markets.append(_candidate_payload(market=market, score_bundle={}, filter_reason="missing_market_id"))
            continue
        score_bundle = client.score_market(market_id=market_id, source=source)
        decision = score_bundle.get("decision")
        decision_status = decision.get("status") if isinstance(decision, dict) else None
        filter_reason: str | None = None
        if decision_status not in _VALID_DECISION_STATUSES:
            filter_reason = "invalid_decision_status"
        elif _VALID_DECISION_STATUSES.index(decision_status) < minimum_rank:
            filter_reason = "decision_below_min_status"
        elif source == "live":
            filter_reason = _live_candidate_filter_reason(market=market, score_bundle=score_bundle)

        if filter_reason is not None:
            filtered_out += 1
            if explain_filtered:
                filtered_markets.append(_candidate_payload(market=market, score_bundle=score_bundle, filter_reason=filter_reason))
            continue
        selected_markets.append(_candidate_payload(market=market, score_bundle=score_bundle))

    selected_markets.sort(
        key=lambda item: (
            float(item.get("score", {}).get("total_score", 0.0)) if isinstance(item.get("score"), dict) else 0.0,
            float(item.get("score", {}).get("raw_edge", 0.0)) if isinstance(item.get("score"), dict) else 0.0,
        ),
        reverse=True,
    )

    result = {
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
    if explain_filtered:
        result["filtered_markets"] = filtered_markets
    return result


def _candidate_payload(
    *,
    market: dict[str, Any],
    score_bundle: dict[str, Any],
    filter_reason: str | None = None,
) -> dict[str, Any]:
    payload = {
        "market_id": market.get("id"),
        "question": market.get("question"),
        "yes_price": market.get("yes_price"),
        "decision": score_bundle.get("decision"),
        "model": _extract_model_payload(score_bundle),
        "edge": _extract_edge_payload(market=market, score_bundle=score_bundle),
        "score": score_bundle.get("score"),
        "market": score_bundle.get("market"),
        "resolution": score_bundle.get("resolution"),
        "execution": score_bundle.get("execution"),
        "execution_costs": score_bundle.get("execution_costs"),
    }
    if filter_reason is not None:
        payload["filter_reason"] = filter_reason
    return payload


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



def _live_candidate_filter_reason(*, market: dict[str, Any], score_bundle: dict[str, Any]) -> str | None:
    yes_price = market.get("yes_price")
    if isinstance(yes_price, (int, float)) and (float(yes_price) <= 0.01 or float(yes_price) >= 0.99):
        return "extreme_yes_price"

    execution = score_bundle.get("execution")
    if isinstance(execution, dict):
        fillable_size = execution.get("fillable_size_usd")
        if isinstance(fillable_size, (int, float)) and float(fillable_size) < 25.0:
            return "insufficient_fillable_size"
        slippage_risk = execution.get("slippage_risk")
        if slippage_risk == "high":
            return "high_slippage_risk"
        spread = execution.get("spread")
        if isinstance(spread, (int, float)) and float(spread) >= 0.07:
            return "wide_spread"

    return None


def _request_json(base_url: str, path: str, *, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    client = PredictionCoreClient(base_url)
    try:
        return client._request_json(method, path, payload)
    except Exception as exc:
        raise ValueError(str(exc)) from exc


def _compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
